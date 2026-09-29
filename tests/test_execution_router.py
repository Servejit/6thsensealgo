import unittest

from execution_guard import ExecutionConfig, ExecutionGuard
from execution_router import ExecutionRequest, ExecutionRouter
from reconciliation import reconcile


class ExecutionRouterTests(unittest.TestCase):
    def test_paper_order_is_allowed(self):
        router = ExecutionRouter("PAPER")
        order = router.submit(ExecutionRequest("TEST", "BUY", 2, 100.0, "TEST"))
        self.assertEqual(order.status, "FILLED")

    def test_live_is_blocked_by_default(self):
        router = ExecutionRouter("LIVE")
        with self.assertRaises(RuntimeError):
            router.submit(
                ExecutionRequest("TEST", "BUY", 2, 100.0),
                reconcile(None, None),
                risk_ok=True,
            )

    def test_live_requires_reconciliation(self):
        config = ExecutionConfig(
            live_enabled=True,
            broker_connected=True,
            static_ip_configured=True,
            api_2fa_configured=True,
            reconciliation_enabled=True,
            kill_switch_enabled=True,
        )
        router = ExecutionRouter("LIVE", guard=ExecutionGuard(config))
        with self.assertRaises(RuntimeError):
            router.submit(ExecutionRequest("TEST", "BUY", 2, 100.0), None, risk_ok=True)

    def test_live_requires_risk(self):
        config = ExecutionConfig(
            live_enabled=True,
            broker_connected=True,
            static_ip_configured=True,
            api_2fa_configured=True,
            reconciliation_enabled=True,
            kill_switch_enabled=True,
        )
        router = ExecutionRouter("LIVE", guard=ExecutionGuard(config))
        matched = reconcile(None, None)
        with self.assertRaises(RuntimeError):
            router.submit(ExecutionRequest("TEST", "BUY", 2, 100.0), matched, risk_ok=False)


if __name__ == "__main__":
    unittest.main()
