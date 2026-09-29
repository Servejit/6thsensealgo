import unittest
import pandas as pd

from event_engine import EventType
from signal_pipeline import SignalEventPipeline


class SignalPipelineTests(unittest.TestCase):
    def test_emits_bar_then_signal(self):
        df = pd.DataFrame([{
            "timestamp": "2026-01-01 09:15",
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10,
            "lips": 3, "teeth": 2, "jaw": 1,
            "cloud_top": 1, "cloud_bottom": 0,
            "tenkan": 2, "kijun": 1,
        }])
        p = SignalEventPipeline("TEST")
        events = p.process_dataframe(df)
        self.assertEqual([e.event_type for e in events], [EventType.SIGNAL])
        self.assertEqual(len(p.event_engine.history), 2)
        self.assertEqual(p.event_engine.history[0].event_type, EventType.BAR_CLOSED)
        self.assertEqual(p.event_engine.history[1].event_type, EventType.SIGNAL)
        self.assertEqual(p.event_engine.history[1].payload["signal"], "BUY")

    def test_duplicate_bar_is_not_processed(self):
        df = pd.DataFrame([{
            "timestamp": "2026-01-01 09:15",
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10,
            "lips": 3, "teeth": 2, "jaw": 1,
            "cloud_top": 1, "cloud_bottom": 0,
            "tenkan": 2, "kijun": 1,
        }])
        p = SignalEventPipeline("TEST")
        self.assertEqual(len(p.process_dataframe(df)), 1)
        self.assertEqual(len(p.process_dataframe(df)), 0)

    def test_signal_payload_contains_strategy_values(self):
        df = pd.DataFrame([{
            "timestamp": "2026-01-01 09:15",
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10,
            "lips": 3, "teeth": 2, "jaw": 1,
            "cloud_top": 1, "cloud_bottom": 0,
            "tenkan": 2, "kijun": 1,
        }])
        p = SignalEventPipeline("TEST")
        p.process_dataframe(df)
        event = p.event_engine.last(EventType.SIGNAL)
        self.assertEqual(event.payload["signal"], "BUY")
        self.assertEqual(event.payload["score"], 100.0)


if __name__ == "__main__":
    unittest.main()
