from dataclasses import dataclass

@dataclass
class ExecutionConfig:
    live_enabled: bool = False
    broker_connected: bool = False
    static_ip_configured: bool = False
    api_2fa_configured: bool = False
    reconciliation_enabled: bool = False
    kill_switch_enabled: bool = True

class ExecutionGuard:
    """Hard safety gate. Live orders remain impossible until every gate is true."""
    def __init__(self, config=None):
        self.config = config or ExecutionConfig()

    def live_ready(self):
        c = self.config
        return all([c.live_enabled, c.broker_connected, c.static_ip_configured,
                    c.api_2fa_configured, c.reconciliation_enabled,
                    c.kill_switch_enabled])

    def reasons(self):
        c = self.config
        checks = {"LIVE_ENABLED": c.live_enabled, "BROKER_CONNECTED": c.broker_connected,
                  "STATIC_IP_CONFIGURED": c.static_ip_configured, "API_2FA_CONFIGURED": c.api_2fa_configured,
                  "RECONCILIATION_ENABLED": c.reconciliation_enabled,
                  "KILL_SWITCH_ENABLED": c.kill_switch_enabled}
        return [name for name, ok in checks.items() if not ok]

    def assert_live_allowed(self):
        if not self.live_ready():
            raise RuntimeError("LIVE EXECUTION BLOCKED. Missing safety gates: " + ", ".join(self.reasons()))

def paper_only_status():
    return {"live_execution":"DISABLED","broker_orders":"DISABLED","paper_execution":"ENABLED","safety_gate":"ACTIVE"}
