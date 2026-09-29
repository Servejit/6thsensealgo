from datetime import datetime, timezone
from pathlib import Path

from execution_guard import ExecutionConfig, ExecutionGuard
from reconciliation import reconcile, reconciliation_action
from state_store import (
    init_db,
    load_last_reconciliation,
    load_orders,
    load_position,
    load_session,
)


def run_preflight(symbol, db_path="6thsense_state.db"):
    """Read-only production-readiness report. It never sends an order."""
    init_db()
    guard = ExecutionGuard(ExecutionConfig())

    local_position = load_position(symbol)
    local_orders = load_orders(symbol, 200)
    last = load_last_reconciliation(symbol)

    # With no authenticated live broker, the only safe broker snapshot is the
    # persisted paper state. This is intentionally not treated as a live broker.
    result = reconcile(local_position, None, local_orders, [])
    if last:
        reconciliation_status = last["status"]
        reconciliation_reason = last["reason"]
        reconciliation_action_name = last["action"]
    else:
        reconciliation_status = result.status
        reconciliation_reason = result.reason
        reconciliation_action_name = reconciliation_action(result)

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "database_present": Path(db_path).exists(),
        "open_position": bool(local_position),
        "session_present": bool(load_session(symbol)),
        "recent_orders": len(local_orders),
        "reconciliation_status": reconciliation_status,
        "reconciliation_reason": reconciliation_reason,
        "reconciliation_action": reconciliation_action_name,
        "live_ready": guard.live_ready(),
        "blocked_reasons": guard.reasons(),
        "paper_only": True,
    }
