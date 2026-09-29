from datetime import datetime, timezone
from pathlib import Path
from execution_guard import ExecutionConfig, ExecutionGuard
from state_store import init_db, load_orders, load_position, load_session

def run_preflight(symbol, db_path="6thsense_state.db"):
    """Read-only readiness report. It never sends an order."""
    init_db()
    guard = ExecutionGuard(ExecutionConfig())
    return {"timestamp_utc":datetime.now(timezone.utc).isoformat(),"symbol":symbol,
            "database_present":Path(db_path).exists(),"open_position":bool(load_position(symbol)),
            "session_present":bool(load_session(symbol)),"recent_orders":len(load_orders(symbol,20)),
            "live_ready":guard.live_ready(),"blocked_reasons":guard.reasons(),"paper_only":True}
