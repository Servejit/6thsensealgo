from dataclasses import dataclass
from datetime import datetime
from typing import Optional

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

class PaperBroker:
    """Broker-neutral paper adapter. It never sends real orders."""
    def __init__(self):
        self.orders = {}

    def submit(self, symbol, side, quantity, price, reason=""):
        order_id = f"PAPER-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        order = Order(order_id, symbol, side, int(quantity), "MARKET", float(price),
                      "FILLED", datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), reason)
        self.orders[order_id] = order
        return order

    def cancel(self, order_id):
        if order_id in self.orders and self.orders[order_id].status == "OPEN":
            self.orders[order_id].status = "CANCELLED"
            return self.orders[order_id]
        return None

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def positions(self):
        return []
