from dataclasses import dataclass
from datetime import date


@dataclass
class RiskState:
    starting_equity: float
    realized_pnl: float = 0.0
    trade_count: int = 0
    emergency_stop: bool = False

    def daily_loss_pct(self):
        if self.starting_equity <= 0:
            return 0.0
        return max(0.0, -self.realized_pnl / self.starting_equity * 100.0)


class RiskEngine:
    def __init__(
        self,
        starting_equity,
        risk_pct,
        max_daily_loss_pct,
        max_trades,
        state=None,
    ):
        self.risk_pct = float(risk_pct)
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_trades = int(max_trades)

        if state:
            self.state = RiskState(
                starting_equity=float(state["starting_equity"]),
                realized_pnl=float(state.get("realized_pnl", 0.0)),
                trade_count=int(state.get("trade_count", 0)),
                emergency_stop=bool(state.get("emergency_stop", False)),
            )
        else:
            self.state = RiskState(float(starting_equity))

    def can_open(self):
        if self.state.emergency_stop:
            return False, "EMERGENCY STOP"
        if self.state.trade_count >= self.max_trades:
            return False, "MAX TRADES REACHED"
        if self.state.daily_loss_pct() >= self.max_daily_loss_pct:
            return False, "DAILY LOSS LIMIT REACHED"
        return True, "OK"

    def position_size(self, entry, sl_pct):
        if entry <= 0 or sl_pct <= 0:
            return 0
        risk_amount = self.state.starting_equity * self.risk_pct / 100.0
        risk_per_unit = entry * sl_pct / 100.0
        return max(0, int(risk_amount / risk_per_unit))

    def record_trade(self, pnl):
        self.state.realized_pnl += float(pnl)
        self.state.trade_count += 1

    def stop(self):
        self.state.emergency_stop = True

    def reset(self):
        self.state.emergency_stop = False

    def reset_daily(self, starting_equity):
        self.state = RiskState(float(starting_equity))
