from dataclasses import dataclass
from typing import Optional

from execution_guard import ExecutionGuard
from order_engine import PaperBroker, Order
from reconciliation import ReconciliationResult


@dataclass
class ExecutionRequest:
    symbol: str
    side: str
    quantity: int
    price: float
    reason: str = ""


class ExecutionRouter:
    """Single entry point for execution.

    PAPER mode uses only PaperBroker. LIVE mode is fail-closed and requires
    every execution guard plus a MATCHED reconciliation and approved risk gate.
    No live broker is implemented here.
    """

    def __init__(self, mode="PAPER", paper_broker=None, live_broker=None, guard=None):
        self.mode = str(mode).upper()
        self.paper_broker = paper_broker or PaperBroker()
        self.live_broker = live_broker
        self.guard = guard or ExecutionGuard()

    def submit(
        self,
        request: ExecutionRequest,
        reconciliation: Optional[ReconciliationResult] = None,
        risk_ok=False,
    ) -> Order:
        if request.quantity <= 0:
            raise ValueError("Order quantity must be positive.")
        if request.price <= 0:
            raise ValueError("Order price must be positive.")
        if request.side.upper() not in {"BUY", "SELL"}:
            raise ValueError("Order side must be BUY or SELL.")

        if self.mode == "PAPER":
            return self.paper_broker.submit(
                request.symbol,
                request.side.upper(),
                request.quantity,
                request.price,
                request.reason,
            )

        if self.mode != "LIVE":
            raise RuntimeError("Unknown execution mode: " + self.mode)

        reconciliation_ok = bool(
            reconciliation is not None and reconciliation.safe_for_new_orders
        )
        self.guard.assert_live_allowed(
            reconciliation_ok=reconciliation_ok,
            risk_ok=bool(risk_ok),
        )

        if self.live_broker is None:
            raise RuntimeError("LIVE execution is blocked: no live broker adapter is installed.")

        # A future broker adapter must be deliberately implemented here.
        raise RuntimeError(
            "LIVE execution is not implemented. The safety architecture is ready, "
            "but no real-money order can be submitted."
        )
