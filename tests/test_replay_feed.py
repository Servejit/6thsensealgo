import unittest
import pandas as pd

from replay_feed import ReplayFeed


class ReplayFeedTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame([
            {"timestamp": "2026-01-01 09:15", "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 10},
            {"timestamp": "2026-01-01 09:20", "open": 1.5, "high": 2.2, "low": 1.2, "close": 2, "volume": 20},
            {"timestamp": "2026-01-01 09:25", "open": 2, "high": 2.5, "low": 1.8, "close": 2.2, "volume": 30},
        ])

    def test_replay_is_deterministic(self):
        feed = ReplayFeed("TEST")
        received = []
        feed.subscribe(received.append)
        self.assertEqual(feed.replay(self.data()), 3)
        self.assertEqual([b.close for b in received], [1.5, 2, 2.2])

    def test_second_replay_does_not_duplicate(self):
        feed = ReplayFeed("TEST")
        self.assertEqual(feed.replay(self.data()), 3)
        self.assertEqual(feed.replay(self.data()), 0)

    def test_reset_allows_replay_again(self):
        feed = ReplayFeed("TEST")
        self.assertEqual(feed.replay(self.data()), 3)
        self.assertEqual(feed.replay(self.data(), reset=True), 3)

    def test_out_of_order_rows_are_normalized(self):
        feed = ReplayFeed("TEST")
        received = []
        feed.subscribe(received.append)
        df = self.data().iloc[[2, 0, 1]]
        self.assertEqual(feed.replay(df), 3)
        self.assertEqual([str(x.timestamp) for x in received],
                         ["2026-01-01 09:15:00", "2026-01-01 09:20:00", "2026-01-01 09:25:00"])


if __name__ == "__main__":
    unittest.main()
