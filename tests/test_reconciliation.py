import unittest

from reconciliation import (
    BROKER_ONLY, LOCAL_ONLY, MATCHED, QUANTITY_MISMATCH, SIDE_MISMATCH,
    ORDER_STATUS_MISMATCH, BrokerOrder, BrokerPosition, reconcile,
    reconciliation_action, BLOCK_NEW_ORDERS,
)


class ReconciliationTests(unittest.TestCase):
    def test_flat_matches_flat(self):
        result = reconcile(None, None)
        self.assertEqual(result.status, MATCHED)

    def test_local_only_blocks(self):
        local = {"side": "BUY", "qty": 10, "entry": 100}
        result = reconcile(local, None)
        self.assertEqual(result.status, LOCAL_ONLY)
        self.assertEqual(reconciliation_action(result), BLOCK_NEW_ORDERS)

    def test_broker_only_blocks(self):
        broker = BrokerPosition("NSE", "BUY", 10, 100)
        result = reconcile(None, broker)
        self.assertEqual(result.status, BROKER_ONLY)

    def test_quantity_mismatch(self):
        local = {"side": "BUY", "qty": 10, "entry": 100}
        broker = BrokerPosition("NSE", "BUY", 11, 100)
        result = reconcile(local, broker)
        self.assertEqual(result.status, QUANTITY_MISMATCH)

    def test_side_mismatch(self):
        local = {"side": "BUY", "qty": 10, "entry": 100}
        broker = BrokerPosition("NSE", "SELL", 10, 100)
        result = reconcile(local, broker)
        self.assertEqual(result.status, SIDE_MISMATCH)

    def test_order_status_mismatch(self):
        local_orders = [{"order_id": "1", "status": "OPEN"}]
        broker_orders = [BrokerOrder("1", "NSE", "BUY", 10, "FILLED", 100)]
        result = reconcile(None, None, local_orders, broker_orders)
        self.assertEqual(result.status, ORDER_STATUS_MISMATCH)

    def test_matching_order_and_position(self):
        local = {"side": "BUY", "qty": 10, "entry": 100}
        broker = BrokerPosition("NSE", "BUY", 10, 100)
        result = reconcile(local, broker)
        self.assertEqual(result.status, MATCHED)


if __name__ == "__main__":
    unittest.main()
