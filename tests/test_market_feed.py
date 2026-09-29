import unittest
import pandas as pd

from market_feed import MarketBar, MarketDataFeed, dataframe_to_bars


class MarketFeedTests(unittest.TestCase):
    def bar(self, ts):
        return MarketBar("TEST", pd.Timestamp(ts), 1, 2, 0.5, 1.5, 100)

    def test_publish_completed_bar(self):
        feed = MarketDataFeed("TEST")
        received = []
        feed.subscribe(received.append)
        feed.connect()
        self.assertTrue(feed.publish(self.bar("2026-01-01 09:15")))
        self.assertEqual(len(received), 1)

    def test_duplicate_and_out_of_order_bars_are_ignored(self):
        feed = MarketDataFeed("TEST")
        received = []
        feed.subscribe(received.append)
        self.assertTrue(feed.publish(self.bar("2026-01-01 09:15")))
        self.assertFalse(feed.publish(self.bar("2026-01-01 09:15")))
        self.assertFalse(feed.publish(self.bar("2026-01-01 09:10")))
        self.assertEqual(len(received), 1)

    def test_incomplete_bar_is_not_published(self):
        feed = MarketDataFeed("TEST")
        received = []
        feed.subscribe(received.append)
        self.assertFalse(feed.publish(MarketBar("TEST", pd.Timestamp("2026-01-01 09:15"), 1, 2, .5, 1.5, 100, False)))
        self.assertEqual(received, [])

    def test_symbol_is_enforced(self):
        feed = MarketDataFeed("TEST")
        with self.assertRaises(ValueError):
            feed.publish(self.bar("2026-01-01 09:15"))

    def test_stale_feed(self):
        feed = MarketDataFeed("TEST", stale_after_seconds=60)
        feed.connect()
        feed.publish(self.bar("2026-01-01 09:15"))
        health = feed.health(pd.Timestamp("2026-01-01 09:17"))
        self.assertTrue(health.stale)
        self.assertFalse(feed.can_trade(pd.Timestamp("2026-01-01 09:17")))

    def test_healthy_feed(self):
        feed = MarketDataFeed("TEST", stale_after_seconds=120)
        feed.connect()
        feed.publish(self.bar("2026-01-01 09:15"))
        self.assertTrue(feed.can_trade(pd.Timestamp("2026-01-01 09:16")))

    def test_dataframe_conversion(self):
        df = pd.DataFrame([{"timestamp": "2026-01-01 09:15", "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 100}])
        bars = list(dataframe_to_bars(df, "TEST"))
        self.assertEqual(len(bars), 1)


if __name__ == "__main__":
    unittest.main()
