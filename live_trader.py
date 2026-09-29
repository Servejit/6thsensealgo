import threading
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from execution_guard import ExecutionGuard
from execution_router import ExecutionRequest, ExecutionRouter
from reconciliation import (
    BrokerOrder,
    BrokerPosition,
    reconcile,
    reconciliation_action,
)
from state_store import (
    load_orders,
    load_position,
    save_broker_snapshot,
    save_reconciliation,
    save_position,
)
from strategy_engine import add_indicators, direction_signal, score_signal
from tradesmart_broker import TradesmartBroker
from tradesmart_live import Tradesmart5mFeed


class LiveTrader:
    """Live 5-minute strategy runner.

    New entries are fail-closed behind the execution guard, broker
    reconciliation, feed health and risk limits. Order acknowledgement is
    never treated as a fill.
    """

    def __init__(
        self,
        symbol,
        exchange,
        token,
        capital,
        risk_engine,
        sl_pct,
        target_pct,
        broker,
        guard,
        order_type="LMT",
        product="MIS",
        retention="DAY",
        use_15m=True,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.token = str(token)
        self.capital = float(capital)
        self.risk = risk_engine
        self.sl_pct = float(sl_pct)
        self.target_pct = float(target_pct)
        self.broker = broker
        self.guard = guard
        self.order_type = str(order_type).upper()
        self.product = product
        self.retention = retention
        self.use_15m = bool(use_15m)

        self.router = ExecutionRouter(
            mode="LIVE",
            live_broker=broker,
            guard=guard,
        )
        self.feed = Tradesmart5mFeed(
            client_id=broker.client_id,
            access_token=broker.access_token,
            exchange=exchange,
            token=token,
            symbol=symbol,
            on_bar=self._on_bar,
        )

        self.lock = threading.RLock()
        self.running = False
        self.previous_signal = "NONE"
        self.position = load_position(symbol)
        self.reconciliation = None
        self.last_signal = "NONE"
        self.last_score = 0.0
        self.last_bar = None
        self.last_confirmation = "NOT AVAILABLE"
        self.last_action = "IDLE"
        self.last_error = None
        self.history = []
        self._bars = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        self._warmup_complete = False

    def warmup(self, lookback_days=5):
        df5 = self.broker.historical_candles(
            exchange=self.exchange,
            token=self.token,
            interval=5,
            lookback_days=lookback_days,
        )
        if df5.empty:
            raise RuntimeError("TradeSmart returned no 5m historical candles for warm-up.")
        self._bars = add_indicators(df5.copy())
        self._warmup_complete = True
        if self.position is None:
            last = self._bars.iloc[-1]
            self.previous_signal = direction_signal(last)
        return self._bars

    def _confirmation(self, row):
        if not self.use_15m:
            return "NOT USED"
        raw = self._bars[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
        raw = raw.dropna(subset=["timestamp"]).set_index("timestamp")
        df15 = raw.resample("15min", label="left", closed="left").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna().reset_index()
        if len(df15) < 60:
            return "NOT AVAILABLE"
        df15 = add_indicators(df15)
        candidates = df15[df15["timestamp"] <= row["timestamp"]]
        if candidates.empty:
            return "NOT AVAILABLE"
        return direction_signal(candidates.iloc[-1])

    def _append_bar(self, bar):
        row = pd.DataFrame([bar.as_dict()])
        self._bars = pd.concat(
            [self._bars, row], ignore_index=True
        ).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        self._bars = self._bars.tail(1500).reset_index(drop=True)
        self._bars = add_indicators(self._bars)

    def _broker_position(self):
        raw = self.broker.get_positions()
        if not isinstance(raw, list):
            raw = raw.get("values", []) if isinstance(raw, dict) else []
        candidates = []
        for p in raw:
            tsym = str(p.get("tsym", p.get("symbol", "")))
            if tsym != self.symbol:
                continue
            net = float(p.get("netqty", p.get("net_quantity", p.get("quantity", 0))) or 0)
            if net == 0:
                continue
            side = "BUY" if net > 0 else "SELL"
            qty = abs(int(net))
            entry = p.get("netavgprc", p.get("avgprc", p.get("entry")))
            candidates.append(BrokerPosition(
                symbol=self.symbol,
                side=side,
                quantity=qty,
                entry=float(entry) if entry not in (None, "") else None,
            ))
        return candidates[0] if candidates else None

    def _broker_orders(self):
        rows = self.broker.broker_orders(self.symbol)
        result = []
        for o in rows:
            status = str(o.get("status", "")).upper()
            result.append(BrokerOrder(
                order_id=str(o.get("norenordno", o.get("order_id", ""))),
                symbol=str(o.get("tsym", o.get("symbol", self.symbol))),
                side="BUY" if str(o.get("trantype", o.get("side", "B"))).upper() in {"B", "BUY"} else "SELL",
                quantity=int(float(o.get("qty", o.get("quantity", 0)) or 0)),
                status=self._normalize_broker_status(status),
                price=float(o.get("avgprc", o.get("prc", o.get("price", 0))) or 0),
            ))
        return result

    @staticmethod
    def _normalize_broker_status(status):
        mapping = {
            "NEW": "SUBMITTED",
            "PENDING": "SUBMITTED",
            "OPEN": "OPEN",
            "TRIGGER_PENDING": "OPEN",
            "COMPLETE": "FILLED",
            "CANCELED": "CANCELLED",
            "CANCELLED": "CANCELLED",
            "REJECTED": "REJECTED",
        }
        return mapping.get(status, status)

    def reconcile_now(self):
        local_position = load_position(self.symbol)
        local_orders = load_orders(self.symbol, 200)
        broker_position = self._broker_position()
        broker_orders = self._broker_orders()
        result = reconcile(
            local_position,
            broker_position,
            local_orders,
            broker_orders,
        )
        action = reconciliation_action(result)
        now = datetime.now(timezone.utc).isoformat()
        save_broker_snapshot(
            self.symbol,
            [broker_position.__dict__] if broker_position else [],
            [o.__dict__ for o in broker_orders],
            now,
        )
        save_reconciliation(self.symbol, result, action, now)
        self.reconciliation = result
        return result

    def start(self):
        with self.lock:
            if self.running:
                return
            self.guard.assert_live_allowed(
                reconciliation_ok=False,
                risk_ok=False,
            )
            self.warmup()
            result = self.reconcile_now()
            if not result.safe_for_new_orders:
                raise RuntimeError(
                    f"Live start blocked by reconciliation: {result.status} • {result.reason}"
                )
            self.feed.start()
            self.running = True
            self.last_action = "LIVE ENGINE RUNNING"

    def stop(self):
        with self.lock:
            self.running = False
            self.feed.stop()
            self.last_action = "LIVE ENGINE STOPPED"

    def emergency_stop(self):
        self.risk.stop()
        self.last_action = "EMERGENCY STOP: NEW ENTRIES BLOCKED"

    def _submit(self, side, qty, price, reason):
        risk_ok, risk_reason = self.risk.can_open()
        if not risk_ok:
            self.last_action = f"BLOCKED: {risk_reason}"
            return None
        result = self.reconcile_now()
        if not result.safe_for_new_orders:
            self.last_action = f"BLOCKED: RECONCILIATION {result.status}"
            return None
        request = ExecutionRequest(
            symbol=self.symbol,
            side=side,
            quantity=qty,
            price=max(float(price), 0.0001),
            reason=reason,
        )
        order = self.router.submit(
            request,
            reconciliation=result,
            risk_ok=True,
        )
        self.history.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action": "ORDER SUBMITTED",
            "side": side,
            "quantity": qty,
            "price": price,
            "order_id": order.order_id,
            "reason": reason,
        })
        self.last_action = f"{side} ORDER SUBMITTED: {order.order_id}"
        return order

    def _exit(self, side, qty, price, reason):
        result = self.reconcile_now()
        if not result.safe_for_new_orders:
            self.last_action = f"EXIT BLOCKED: RECONCILIATION {result.status}"
            return None
        request = ExecutionRequest(
            symbol=self.symbol,
            side=side,
            quantity=qty,
            price=max(float(price), 0.0001),
            reason=reason,
        )
        order = self.router.submit(
            request,
            reconciliation=result,
            risk_ok=True,
        )
        self.history.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action": "EXIT SUBMITTED",
            "side": side,
            "quantity": qty,
            "price": price,
            "order_id": order.order_id,
            "reason": reason,
        })
        self.last_action = f"EXIT ORDER SUBMITTED: {order.order_id}"
        return order

    def _on_bar(self, bar):
        with self.lock:
            if not self.running:
                return
            try:
                self._append_bar(bar)
                if len(self._bars) < 100:
                    self.last_action = "WARMING UP INDICATORS"
                    return
                row = self._bars.iloc[-1]
                signal = direction_signal(row)
                score = score_signal(row)[0]
                confirmation = self._confirmation(row)

                self.last_bar = row.to_dict()
                self.last_signal = signal
                self.last_score = float(score)
                self.last_confirmation = confirmation

                if self.position:
                    exit_price = None
                    reason = None
                    if self.position["side"] == "BUY":
                        if row["low"] <= self.position["sl"]:
                            exit_price, reason = self.position["sl"], "STOP LOSS"
                        elif row["high"] >= self.position["target"]:
                            exit_price, reason = self.position["target"], "TARGET"
                        elif signal == "SELL":
                            exit_price, reason = row["close"], "OPPOSITE SIGNAL"
                        if exit_price is not None:
                            self._exit("SELL", self.position["qty"], exit_price, reason)
                    else:
                        if row["high"] >= self.position["sl"]:
                            exit_price, reason = self.position["sl"], "STOP LOSS"
                        elif row["low"] <= self.position["target"]:
                            exit_price, reason = self.position["target"], "TARGET"
                        elif signal == "BUY":
                            exit_price, reason = row["close"], "OPPOSITE SIGNAL"
                        if exit_price is not None:
                            self._exit("BUY", self.position["qty"], exit_price, reason)

                starts = signal in {"BUY", "SELL"} and signal != self.previous_signal
                if self.position is None and starts:
                    if not self.feed.can_trade():
                        self.last_action = "BLOCKED: MARKET FEED STALE"
                    else:
                        ok, reason = self.risk.can_open()
                        if ok:
                            entry = float(row["close"])
                            qty = self.risk.position_size(entry, self.sl_pct)
                            if qty > 0:
                                self._submit(
                                    signal,
                                    qty,
                                    entry,
                                    f"6thSense {signal} start; score={score:.0f}; 15m={confirmation}",
                                )
                            else:
                                self.last_action = "BLOCKED: POSITION SIZE IS ZERO"
                        else:
                            self.last_action = f"BLOCKED: {reason}"

                self.previous_signal = signal
            except Exception as exc:
                self.last_error = str(exc)
                self.last_action = f"ERROR: {exc}"

    def snapshot(self):
        with self.lock:
            h = self.feed.health()
            return {
                "running": self.running,
                "symbol": self.symbol,
                "exchange": self.exchange,
                "token": self.token,
                "signal": self.last_signal,
                "score": self.last_score,
                "confirmation_15m": self.last_confirmation,
                "action": self.last_action,
                "position": self.position,
                "feed_connected": h.connected,
                "feed_stale": h.stale,
                "feed_message": h.message,
                "last_bar": self.last_bar,
                "last_error": self.last_error,
                "reconciliation": None if self.reconciliation is None else {
                    "status": self.reconciliation.status,
                    "reason": self.reconciliation.reason,
                    "safe_for_new_orders": self.reconciliation.safe_for_new_orders,
                },
                "history": list(self.history[-50:]),
            }
