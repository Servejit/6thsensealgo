from dataclasses import dataclass
from typing import Optional
import os
import os


@dataclass
class ExecutionConfig:
    live_enabled: bool = False
    broker_connected: bool = False
    static_ip_configured: bool = False
    api_2fa_configured: bool = False
    reconciliation_enabled: bool = False
    kill_switch_enabled: bool = True


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def live_config_from_env():
    return ExecutionConfig(
        live_enabled=_env_bool("TRADESMART_LIVE_ENABLED", False),
        broker_connected=_env_bool("TRADESMART_BROKER_CONNECTED", False),
        static_ip_configured=_env_bool("TRADESMART_STATIC_IP_CONFIGURED", False),
        api_2fa_configured=_env_bool("TRADESMART_API_2FA_CONFIGURED", False),
        reconciliation_enabled=_env_bool("TRADESMART_RECONCILIATION_ENABLED", False),
        kill_switch_enabled=_env_bool("TRADESMART_KILL_SWITCH_ENABLED", True),
    )


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def live_config_from_env():
    return ExecutionConfig(
        live_enabled=_env_bool("TRADESMART_LIVE_ENABLED", False),
        broker_connected=_env_bool("TRADESMART_BROKER_CONNECTED", False),
        static_ip_configured=_env_bool("TRADESMART_STATIC_IP_CONFIGURED", False),
        api_2fa_configured=_env_bool("TRADESMART_API_2FA_CONFIGURED", False),
        reconciliation_enabled=_env_bool("TRADESMART_RECONCILIATION_ENABLED", False),
        kill_switch_enabled=_env_bool("TRADESMART_KILL_SWITCH_ENABLED", True),
    )


class ExecutionGuard:
    """Fail-closed safety gate for any future live execution."""

    def __init__(self, config=None):
        self.config = config or live_config_from_env()

    def live_ready(self):
        c = self.config
        return all([
            c.live_enabled,
            c.broker_connected,
            c.static_ip_configured,
            c.api_2fa_configured,
            c.reconciliation_enabled,
            c.kill_switch_enabled,
        ])

    def reasons(self):
        c = self.config
        checks = {
            "LIVE_ENABLED": c.live_enabled,
            "BROKER_CONNECTED": c.broker_connected,
            "STATIC_IP_CONFIGURED": c.static_ip_configured,
            "API_2FA_CONFIGURED": c.api_2fa_configured,
            "RECONCILIATION_ENABLED": c.reconciliation_enabled,
            "KILL_SWITCH_ENABLED": c.kill_switch_enabled,
        }
        return [name for name, ok in checks.items() if not ok]

    def assert_live_allowed(self, reconciliation_ok=False, risk_ok=False):
        reasons = self.reasons()
        if not reconciliation_ok:
            reasons.append("RECONCILIATION_NOT_MATCHED")
        if not risk_ok:
            reasons.append("RISK_GATE_NOT_APPROVED")
        if reasons:
            raise RuntimeError(
                "LIVE EXECUTION BLOCKED. Missing safety gates: " + ", ".join(reasons)
            )

    def status(self, reconciliation_ok=False, risk_ok=False):
        return {
            "live_ready": self.live_ready() and reconciliation_ok and risk_ok,
            "base_gates": not self.reasons(),
            "reconciliation_ok": bool(reconciliation_ok),
            "risk_ok": bool(risk_ok),
            "blocked_reasons": self.reasons()
            + ([] if reconciliation_ok else ["RECONCILIATION_NOT_MATCHED"])
            + ([] if risk_ok else ["RISK_GATE_NOT_APPROVED"]),
        }


def paper_only_status():
    return {
        "live_execution": "DISABLED",
        "broker_orders": "DISABLED",
        "paper_execution": "ENABLED",
        "safety_gate": "ACTIVE",
    }
