from datetime import datetime, date

from strategy_engine import direction_signal, score_signal
from order_engine import PaperBroker
from state_store import (
    init_db,
    save_order,
    save_position,
    load_position,
    load_orders,
    save_session,
    load_session,
)
from risk_engine import RiskEngine


class PaperTrader:
    """Persistent paper trader. It never sends real broker orders."""

    def __init__(self, symbol, capital, risk_engine, sl_pct, target_pct, feed=None):
        init_db()
        self.symbol = symbol
        self.sl_pct = float(sl_pct)
        self.target_pct = float(target_pct)
        self.broker = PaperBroker()
        self.feed = feed
        self.feed_enabled = feed is not None

        session = load_session(symbol)
        today = date.today().isoformat()

        if session and session["session_date"] == today:
            risk_state = {
                "starting_equity": session["starting_equity"],
                "realized_pnl": session["realized_pnl"],
                "trade_count": session["trade_count"],
                "emergency_stop": session["emergency_stop"],
            }
            self.risk = RiskEngine(
                session["starting_equity"],
                risk_engine.risk_pct,
                risk_engine.max_daily_loss_pct,
                risk_engine.max_trades,
                state=risk_state,
            )
            self.cash = float(session["cash"])
            self.previous_signal = session.get("previous_signal") or "NONE"
            self.last_bar_timestamp = session.get("last_bar_timestamp")
        else:
            self.risk = RiskEngine(
                capital,
                risk_engine.risk_pct,
                risk_engine.max_daily_loss_pct,
                risk_engine.max_trades,
            )
            self.cash = float(capital)
            self.previous_signal = "NONE"
            self.last_bar_timestamp = None

        saved = load_position(symbol)
        self.position = dict(saved) if saved else None
        self.orders = load_orders(symbol)

        # A new daily risk session starts with the persisted cash balance.
        if session and session["session_date"] != today:
            self.risk.reset_daily(self.cash)

        self._persist_session()

    def _persist_session(self):
        save_session(
            self.symbol,
            {
                "session_date": date.today().isoformat(),
                "starting_equity": self.risk.state.starting_equity,
                "cash": self.cash,
                "realized_pnl": self.risk.state.realized_pnl,
                "trade_count": self.risk.state.trade_count,
                "emergency_stop": self.risk.state.emergency_stop,
                "previous_signal": self.previous_signal,
                "last_bar_timestamp": self.last_bar_timestamp,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    def snapshot(self, price):
        unrealized = 0.0
        if self.position:
            unrealized = (
                (price - self.position["entry"])
                if self.position["side"] == "BUY"
                else (self.position["entry"] - price)
            ) * self.position["qty"]

        return {
            "Symbol": self.symbol,
            "Position": self.position["side"] if self.position else "FLAT",
            "Qty": self.position["qty"] if self.position else 0,
            "Entry": self.position["entry"] if self.position else None,
            "SL": self.position["sl"] if self.position else None,
            "Target": self.position["target"] if self.position else None,
            "Cash": self.cash,
            "Unrealized P&L": unrealized,
            "Equity": self.cash + unrealized,
            "Realized P&L": self.risk.state.realized_pnl,
            "Trades": self.risk.state.trade_count,
            "Daily Loss %": self.risk.state.daily_loss_pct(),
            "Risk": self.risk.can_open()[1],
            "Emergency Stop": "ON" if self.risk.state.emergency_stop else "OFF",
            "Last Bar": self.last_bar_timestamp or "NONE",
        }

    def _submit(
        self,
        side,
        qty,
        price,
        reason,
        action,
        signal,
        confirmation,
        score,
        pnl=0.0,
    ):
        order = self.broker.submit(
            self.symbol, side, qty, price, reason
        )
        event = {
            "Time": datetime.now().isoformat(timespec="seconds"),
            "Order ID": order.order_id,
            "Action": action,
            "Side": side,
            "Price": price,
            "Quantity": qty,
            "P&L": pnl,
            "Reason": reason,
            "Signal": signal,
            "15m": confirmation,
            "Score": score,
            "Status": "PAPER",
        }
        self.orders.append(event)
        save_order(order)
        return event

    def process_event(self, event, confirmation="NOT USED"):
        """Consume a shared SIGNAL event while retaining full bar data."""
        row = event.payload.get("row", {})
        if not row:
            return None
        signal = event.payload.get("signal", direction_signal(row))
        score = float(event.payload.get("score", score_signal(row)[0]))
        return self._process_bar_values(row, confirmation, signal, score)

    def process_bar(self, row, confirmation="NOT USED"):
        """Backward-compatible direct bar entry point."""
        signal = direction_signal(row)
        score = score_signal(row)[0]
        return self._process_bar_values(row, confirmation, signal, score)

    def _process_bar_values(self, row, confirmation="NOT USED", signal=None, score=None):
        bar_timestamp = row.get("timestamp")
        bar_timestamp = (
            bar_timestamp.isoformat()
            if hasattr(bar_timestamp, "isoformat")
            else str(bar_timestamp)
        )

        # Idempotency: the same completed bar can never be processed twice,
        # even when Streamlit reruns or the user presses the scan button again.
        if self.last_bar_timestamp and bar_timestamp <= self.last_bar_timestamp:
            return None

        price = float(row["close"])
        if signal is None:
            signal = direction_signal(row)
        if score is None:
            score = score_signal(row)[0]

        if self.position:
            exit_price = reason = None
            if self.position["side"] == "BUY":
                if float(row["low"]) <= self.position["sl"]:
                    exit_price, reason = self.position["sl"], "STOP LOSS"
                elif float(row["high"]) >= self.position["target"]:
                    exit_price, reason = self.position["target"], "TARGET"
                elif signal == "SELL":
                    exit_price, reason = price, "OPPOSITE SIGNAL"
            else:
                if float(row["high"]) >= self.position["sl"]:
                    exit_price, reason = self.position["sl"], "STOP LOSS"
                elif float(row["low"]) <= self.position["target"]:
                    exit_price, reason = self.position["target"], "TARGET"
                elif signal == "BUY":
                    exit_price, reason = price, "OPPOSITE SIGNAL"

            if exit_price is not None:
                side = self.position["side"]
                qty = self.position["qty"]
                pnl = (
                    (exit_price - self.position["entry"])
                    if side == "BUY"
                    else (self.position["entry"] - exit_price)
                ) * qty
                self.cash += pnl
                self.risk.record_trade(pnl)

                event = self._submit(
                    "SELL" if side == "BUY" else "BUY",
                    qty,
                    exit_price,
                    reason,
                    "EXIT",
                    signal,
                    confirmation,
                    score,
                    pnl,
                )
                self.position = None
                save_position(self.symbol, None)

                # The same bar has already been consumed. Do not immediately
                # reverse into a second trade on that bar.
                self.previous_signal = signal
                self.last_bar_timestamp = bar_timestamp
                self._persist_session()
                return event

        starts = signal in ("BUY", "SELL") and signal != self.previous_signal
        self.previous_signal = signal

        feed_ok = self.feed.can_trade() if self.feed_enabled else True
        if self.position is None and starts:
            if not feed_ok:
                self.last_bar_timestamp = bar_timestamp
                self._persist_session()
                return {
                    "Time": datetime.now().isoformat(timespec="seconds"),
                    "Action": "BLOCKED",
                    "Side": signal,
                    "Price": price,
                    "Quantity": 0,
                    "P&L": 0.0,
                    "Reason": "Market feed is stale or disconnected.",
                    "Signal": signal,
                    "15m": confirmation,
                    "Score": score,
                    "Status": "PAPER",
                }

            allowed, reason = self.risk.can_open()
            if not allowed:
                self.last_bar_timestamp = bar_timestamp
                self._persist_session()
                return {
                    "Time": datetime.now().isoformat(timespec="seconds"),
                    "Action": "BLOCKED",
                    "Side": signal,
                    "Price": price,
                    "Quantity": 0,
                    "P&L": 0.0,
                    "Reason": reason,
                    "Signal": signal,
                    "15m": confirmation,
                    "Score": score,
                    "Status": "PAPER",
                }

            qty = self.risk.position_size(price, self.sl_pct)
            if qty <= 0:
                self.last_bar_timestamp = bar_timestamp
                self._persist_session()
                return None

            if signal == "BUY":
                sl = price * (1 - self.sl_pct / 100)
                target = price * (1 + self.target_pct / 100)
            else:
                sl = price * (1 + self.sl_pct / 100)
                target = price * (1 - self.target_pct / 100)

            self.position = {
                "side": signal,
                "entry": price,
                "qty": qty,
                "sl": sl,
                "target": target,
                "time": bar_timestamp,
                "score": score,
                "confirmation": confirmation,
            }
            event = self._submit(
                signal,
                qty,
                price,
                "6thSense SIGNAL START",
                "ENTRY",
                signal,
                confirmation,
                score,
            )
            save_position(self.symbol, self.position)
            self.last_bar_timestamp = bar_timestamp
            self._persist_session()
            return event

        self.last_bar_timestamp = bar_timestamp
        self._persist_session()
        return None
