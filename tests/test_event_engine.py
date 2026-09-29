import unittest
from event_engine import EventEngine, EventType


class EventEngineTests(unittest.TestCase):
    def test_sequence_and_dispatch_order(self):
        engine = EventEngine()
        received = []
        engine.subscribe(EventType.BAR_CLOSED, lambda e: received.append(("bar", e.sequence)))
        engine.subscribe(EventType.SIGNAL, lambda e: received.append(("signal", e.sequence)))

        first = engine.emit(EventType.BAR_CLOSED, "09:15", "TEST", {"close": 100})
        second = engine.emit(EventType.SIGNAL, "09:15", "TEST", {"signal": "BUY"})

        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(received, [("bar", 1), ("signal", 2)])
        self.assertEqual(engine.history[-1].event_type, EventType.SIGNAL)

    def test_handlers_are_isolated_by_type(self):
        engine = EventEngine()
        received = []
        engine.subscribe(EventType.ORDER_EVENT, lambda e: received.append(e))
        engine.emit(EventType.BAR_CLOSED, "09:15", "TEST")
        self.assertEqual(received, [])

    def test_payload_is_copied(self):
        engine = EventEngine()
        payload = {"signal": "BUY"}
        event = engine.emit(EventType.SIGNAL, "09:15", "TEST", payload)
        payload["signal"] = "SELL"
        self.assertEqual(event.payload["signal"], "BUY")

    def test_last_event(self):
        engine = EventEngine()
        engine.emit(EventType.BAR_CLOSED, "09:15", "TEST")
        signal = engine.emit(EventType.SIGNAL, "09:15", "TEST", {"signal": "BUY"})
        self.assertEqual(engine.last(EventType.SIGNAL), signal)


if __name__ == "__main__":
    unittest.main()
