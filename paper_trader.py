from datetime import datetime
from strategy_engine import direction_signal, score_signal

class PaperTrader:
    def __init__(self, symbol, capital, risk_engine, sl_pct, target_pct):
        self.symbol = symbol
        self.cash = float(capital)
        self.risk = risk_engine
        self.sl_pct = float(sl_pct)
        self.target_pct = float(target_pct)
        self.position = None
        self.orders = []
        self.previous_signal = "NONE"

    def snapshot(self, price):
        unrealized = 0.0
        if self.position:
            if self.position["side"] == "BUY":
                unrealized = (price-self.position["entry"])*self.position["qty"]
            else:
                unrealized = (self.position["entry"]-price)*self.position["qty"]
        return {"Symbol":self.symbol,"Position":self.position["side"] if self.position else "FLAT","Qty":self.position["qty"] if self.position else 0,"Entry":self.position["entry"] if self.position else None,"SL":self.position["sl"] if self.position else None,"Target":self.position["target"] if self.position else None,"Cash":self.cash,"Unrealized P&L":unrealized,"Equity":self.cash+unrealized,"Realized P&L":self.risk.state.realized_pnl,"Trades":self.risk.state.trade_count,"Risk":self.risk.can_open()[1]}

    def process_bar(self, row, confirmation="NOT USED"):
        price=float(row["close"])
        signal=direction_signal(row)
        score,_=score_signal(row)
        event=None

        if self.position:
            exit_price=None
            reason=None
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
                self.cash+=pnl; self.risk.record_trade(pnl); self.position=None
                event={"Time":datetime.now(),"Action":"EXIT","Side":side,"Price":exit_price,"Quantity":qty,"P&L":pnl,"Reason":reason,"Signal":signal,"15m":confirmation,"Score":score,"Status":"PAPER"}
                self.orders.append(event); return event

        starts=signal in ("BUY","SELL") and signal!=self.previous_signal
        if self.position is None and starts:
            allowed,reason=self.risk.can_open()
            if not allowed:
                self.previous_signal=signal
                return {"Time":datetime.now(),"Action":"BLOCKED","Side":signal,"Price":price,"Quantity":0,"P&L":0.0,"Reason":reason,"Signal":signal,"15m":confirmation,"Score":score,"Status":"PAPER"}
            qty=self.risk.position_size(price,self.sl_pct)
            if qty<=0:
                self.previous_signal=signal; return None
            if signal=="BUY": sl,target=price*(1-self.sl_pct/100),price*(1+self.target_pct/100)
            else: sl,target=price*(1+self.sl_pct/100),price*(1-self.target_pct/100)
            self.position={"side":signal,"entry":price,"qty":qty,"sl":sl,"target":target,"time":row.get("timestamp"),"score":score,"confirmation":confirmation}
            event={"Time":datetime.now(),"Action":"ENTRY","Side":signal,"Price":price,"Quantity":qty,"P&L":0.0,"Reason":"6thSense SIGNAL START","Signal":signal,"15m":confirmation,"Score":score,"Status":"PAPER"}
            self.orders.append(event); self.previous_signal=signal; return event
        self.previous_signal=signal
        return None
