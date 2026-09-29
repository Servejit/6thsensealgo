from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from state_store import save_order, update_order_status, load_position, load_orders


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    price: float
    status: str
    created_at: str
    filled_at: Optional[str] = None
    reason: str = ""

    def transition(self, new_status):
        current = OrderState(self.status)
        target = OrderState(new_status)
        allowed = {
            OrderState.CREATED: {OrderState.SUBMITTED, OrderState.REJECTED},
            OrderState.SUBMITTED: {OrderState.OPEN, OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
            OrderState.OPEN: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
            OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED},
            OrderState.FILLED: set(),
            OrderState.CANCELLED: set(),
            OrderState.REJECTED: set(),
        }
        if target not in allowed[current]:
            raise ValueError(f"Invalid order transition: {current.value} -> {target.value}")
        self.status = target.value
        if target == OrderState.FILLED:
            self.filled_at = datetime.utcnow().isoformat()
        update_order_status(self.order_id, self.status, self.reason, self.filled_at)
        return self


@dataclass(frozen=True)
class BrokerOrderRecord:
    order_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    price: Optional[float] = None


class PaperBroker:
    """Persistent-journal paper adapter. It never sends real orders."""
    def __init__(self):
        self.orders = {}

    def submit(self, symbol, side, quantity, price, reason=""):
        now = datetime.utcnow().isoformat()
        order_id = f"PAPER-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        order = Order(order_id, symbol, side, int(quantity), "MARKET", float(price),
                      OrderState.CREATED.value, now, reason=reason)
        save_order(order)
        self.orders[order_id] = order
        order.transition(OrderState.SUBMITTED.value)
        order.transition(OrderState.FILLED.value)
        return order

    def cancel(self, order_id):
        order = self.orders.get(order_id)
        if order is None:
            return None
        if order.status in {OrderState.OPEN.value, OrderState.SUBMITTED.value}:
            return order.transition(OrderState.CANCELLED.value)
        return None

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def positions(self):
        position = load_position(self.orders[next(iter(self.orders))].symbol) if self.orders else None
        if not position:
            return []
        return [{
            "symbol": self.orders[next(iter(self.orders))].symbol,
            "side": position["side"],
            "quantity": position["qty"],
            "entry": position["entry"],
        }]

    def broker_orders(self, symbol=None):
        rows = load_orders(symbol, 200)
        return [
            BrokerOrderRecord(
                order_id=str(row["order_id"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                quantity=int(row["quantity"]),
                status=str(row["status"]),
                price=float(row["price"]) if row.get("price") is not None else None,
            )
            for row in rows
        ]


def order_state_is_terminal(status):
    return status in {OrderState.FILLED.value, OrderState.CANCELLED.value, OrderState.REJECTED.value}
