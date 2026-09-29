from execution_guard import ExecutionConfig, ExecutionGuard

def test_default_live_execution_is_blocked():
    guard=ExecutionGuard()
    assert guard.live_ready() is False
    assert "LIVE_ENABLED" in guard.reasons()

def test_partial_configuration_stays_blocked():
    config=ExecutionConfig(live_enabled=True,broker_connected=True,static_ip_configured=True,
                           api_2fa_configured=True,reconciliation_enabled=False,kill_switch_enabled=True)
    guard=ExecutionGuard(config)
    assert guard.live_ready() is False
    assert "RECONCILIATION_ENABLED" in guard.reasons()

def test_all_gates_are_required():
    config=ExecutionConfig(live_enabled=True,broker_connected=True,static_ip_configured=True,
                           api_2fa_configured=True,reconciliation_enabled=True,kill_switch_enabled=True)
    assert ExecutionGuard(config).live_ready() is True
