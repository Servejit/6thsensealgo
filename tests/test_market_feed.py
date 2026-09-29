import unittest
import pandas as pd

from market_feed import MarketBar, MarketDataFeed, dataframe_to_bars


class MarketFeedTests(unittest.TestCase):
    def test_publish_completed_bar(self):
        feed = MarketDataFeed("TEST")
        received = []
        feed.subscribe(received.append)
        feed.publish(MarketBar("TEST", pd.Timestamp("2026-01-01 09:15"), 1, 2, 0.5, 1.5, 100))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].close, 1.5)

    def test_incomplete_bar_is_not_published(self):
        feed = MarketDataFeed("TEST")
        received = []
        feed.subscribe(received.append)
        feed.publish(MarketBar("TEST", pd.Timestamp("2026-01-01 09:15"), 1, 2, 0.5, 1.5, 100, complete=False))
        self.assertEqual(received, [])

    def test_symbol_is_enforced(self):
        feed = MarketDataFeed("TEST")
        with self.assertRaises(ValueError):
            feed.publish(MarketBar("OTHER", pd.Timestamp("2026-01-01 09:15"), 1, 2, 0.5, 1.5, 100))

    def test_dataframe_conversion(self):
        df = pd.DataFrame([{
            "timestamp": "2026-01-01 09:15",
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100
        }])
        bars = list(dataframe_to_bars(df, "TEST"))
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].symbol, "TEST")


if __name__ == "__main__":
    unittest.main()
