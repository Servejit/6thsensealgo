from dataclasses import dataclass
from typing import Any, Dict, List, Optional


MATCHED = "MATCHED"
LOCAL_ONLY = "LOCAL_ONLY"
BROKER_ONLY = "BROKER_ONLY"
QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
SIDE_MISMATCH = "SIDE_MISMATCH"
PRICE_MISMATCH = "PRICE_MISMATCH"
ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
BLOCK_NEW_ORDERS = "BLOCK_NEW_ORDERS"


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    side: str
    quantity: int
    entry: Optional[float] = None


@dataclass(frozen=True)
class BrokerOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    price: Optional[float] = None


@dataclass
class ReconciliationResult:
    status: str
    reason: str
    local_position: Optional[Dict[str, Any]]
    broker_position: Optional[Dict[str, Any]]
    order_mismatches: List[Dict[str, Any]]

    @property
    def safe_for_new_orders(self) -> bool:
        return self.status == MATCHED


def normalize_position(value) -> Optional[BrokerPosition]:
    if value is None:
        return None
    if isinstance(value, BrokerPosition):
        return value
    return BrokerPosition(
        symbol=str(value["symbol"]),
        side=str(value["side"]).upper(),
        quantity=int(value.get("quantity", value.get("qty", 0))),
        entry=float(value["entry"]) if value.get("entry") is not None else None,
    )


def _compare_position(local, broker, price_tolerance=1e-6):
    if local is None and broker is None:
        return MATCHED, "Both local and broker are FLAT."
    if local is not None and broker is None:
        return LOCAL_ONLY, "Local state has an open position but broker is FLAT."
    if local is None and broker is not None:
        return BROKER_ONLY, "Broker has an open position but local state is FLAT."

    if int(local["qty"]) != int(broker.quantity):
        return QUANTITY_MISMATCH, "Position quantities differ."
    if str(local["side"]).upper() != broker.side.upper():
        return SIDE_MISMATCH, "Position sides differ."

    if local.get("entry") is not None and broker.entry is not None:
        if abs(float(local["entry"]) - float(broker.entry)) > price_tolerance:
            return PRICE_MISMATCH, "Position entry prices differ."

    return MATCHED, "Local and broker positions match."


def reconcile(local_position, broker_position=None, local_orders=None,
               broker_orders=None, price_tolerance=1e-6):
    local = local_position
    broker = normalize_position(broker_position)
    status, reason = _compare_position(local, broker, price_tolerance)

    local_orders = local_orders or []
    broker_orders = broker_orders or []
    broker_by_id = {str(o.order_id): o for o in broker_orders}
    order_mismatches = []

    for order in local_orders:
        oid = str(order["order_id"])
        bo = broker_by_id.get(oid)
        if bo is None:
            if str(order.get("status", "")).upper() in {"OPEN", "SUBMITTED", "PARTIALLY_FILLED"}:
                order_mismatches.append({
                    "order_id": oid,
                    "status": LOCAL_ONLY,
                    "reason": "Local active order is absent at broker.",
                })
            continue
        if str(order.get("status", "")).upper() != str(bo.status).upper():
            order_mismatches.append({
                "order_id": oid,
                "status": ORDER_STATUS_MISMATCH,
                "reason": f"Local={order.get('status')} Broker={bo.status}",
            })

    local_ids = {str(o["order_id"]) for o in local_orders}
    for bo in broker_orders:
        if str(bo.order_id) not in local_ids and str(bo.status).upper() in {
            "OPEN", "SUBMITTED", "PARTIALLY_FILLED", "FILLED"
        }:
            order_mismatches.append({
                "order_id": str(bo.order_id),
                "status": BROKER_ONLY,
                "reason": "Broker order is absent from local journal.",
            })

    if status == MATCHED and order_mismatches:
        status = order_mismatches[0]["status"]
        reason = order_mismatches[0]["reason"]

    return ReconciliationResult(
        status=status,
        reason=reason,
        local_position=local,
        broker_position=broker.__dict__ if broker else None,
        order_mismatches=order_mismatches,
    )


def reconciliation_action(result: ReconciliationResult) -> str:
    return "ALLOW_NEW_ORDERS" if result.safe_for_new_orders else BLOCK_NEW_ORDERS
