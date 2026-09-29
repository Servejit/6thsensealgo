from datetime import datetime
from strategy_engine import direction_signal, score_signal
from order_engine import PaperBroker
from state_store import init_db, save_order, save_position, load_position, load_orders

class PaperTrader:
    def __init__(self, symbol, capital, risk_engine, sl_pct, target_pct):
        init_db()
        self.symbol=symbol; self.cash=float(capital); self.risk=risk_engine
        self.sl_pct=float(sl_pct); self.target_pct=float(target_pct)
        self.broker=PaperBroker()
        saved=load_position(symbol)
        self.position=(dict(saved) if saved else None)
        self.orders=load_orders(symbol)
        self.previous_signal="NONE"

    def snapshot(self, price):
        unrealized=0.0
        if self.position:
            unrealized=((price-self.position["entry"]) if self.position["side"]=="BUY" else (self.position["entry"]-price))*self.position["qty"]
        return {"Symbol":self.symbol,"Position":self.position["side"] if self.position else "FLAT",
                "Qty":self.position["qty"] if self.position else 0,"Entry":self.position["entry"] if self.position else None,
                "SL":self.position["sl"] if self.position else None,"Target":self.position["target"] if self.position else None,
                "Cash":self.cash,"Unrealized P&L":unrealized,"Equity":self.cash+unrealized,
                "Realized P&L":self.risk.state.realized_pnl,"Trades":self.risk.state.trade_count,
                "Risk":self.risk.can_open()[1]}

    def _submit(self, side, qty, price, reason, action, signal, confirmation, score, pnl=0.0):
        order=self.broker.submit(self.symbol,side,qty,price,reason)
        event={"Time":datetime.now(),"Order ID":order.order_id,"Action":action,"Side":side,"Price":price,
               "Quantity":qty,"P&L":pnl,"Reason":reason,"Signal":signal,"15m":confirmation,"Score":score,"Status":"PAPER"}
        self.orders.append(event)
        save_order(order)
        return event

    def process_bar(self,row,confirmation="NOT USED"):
        price=float(row["close"]); signal=direction_signal(row); score,_=score_signal(row)

        if self.position:
            exit_price=reason=None
            if self.position["side"]=="BUY":
                if float(row["low"])<=self.position["sl"]: exit_price,reason=self.position["sl"],"STOP LOSS"
                elif float(row["high"])>=self.position["target"]: exit_price,reason=self.position["target"],"TARGET"
                elif signal=="SELL": exit_price,reason=price,"OPPOSITE SIGNAL"
            else:
                if float(row["high"])>=self.position["sl"]: exit_price,reason=self.position["sl"],"STOP LOSS"
                elif float(row["low"])<=self.position["target"]: exit_price,reason=self.position["target"],"TARGET"
                elif signal=="BUY": exit_price,reason=price,"OPPOSITE SIGNAL"
            if exit_price is not None:
                side=self.position["side"]; qty=self.position["qty"]
                pnl=((exit_price-self.position["entry"]) if side=="BUY" else (self.position["entry"]-exit_price))*qty
                self.cash+=pnl; self.risk.record_trade(pnl)
                event=self._submit("SELL" if side=="BUY" else "BUY",qty,exit_price,reason,"EXIT",signal,confirmation,score,pnl)
                self.position=None; save_position(self.symbol,None)
                return event

        starts=signal in ("BUY","SELL") and signal!=self.previous_signal
        self.previous_signal=signal
        if self.position is None and starts:
            allowed,reason=self.risk.can_open()
            if not allowed:
                return {"Time":datetime.now(),"Action":"BLOCKED","Side":signal,"Price":price,"Quantity":0,"P&L":0.0,
                        "Reason":reason,"Signal":signal,"15m":confirmation,"Score":score,"Status":"PAPER"}
            qty=self.risk.position_size(price,self.sl_pct)
            if qty<=0: return None
            sl,target=(price*(1-self.sl_pct/100),price*(1+self.target_pct/100)) if signal=="BUY" else (price*(1+self.sl_pct/100),price*(1-self.target_pct/100))
            self.position={"side":signal,"entry":price,"qty":qty,"sl":sl,"target":target,"time":str(row.get("timestamp")),"score":score,"confirmation":confirmation}
            event=self._submit(signal,qty,price,"6thSense SIGNAL START","ENTRY",signal,confirmation,score)
            save_position(self.symbol,self.position)
            return event
        return None
