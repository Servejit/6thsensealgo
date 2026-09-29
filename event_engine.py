from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List
import itertools


class EventType(str, Enum):
    BAR_CLOSED = "BAR_CLOSED"
    SIGNAL = "SIGNAL"
    RISK_BLOCK = "RISK_BLOCK"
    ORDER_EVENT = "ORDER_EVENT"
    RECONCILIATION = "RECONCILIATION"


@dataclass(frozen=True)
class TradingEvent:
    sequence: int
    event_type: EventType
    timestamp: Any
    symbol: str
    payload: Dict[str, Any] = field(default_factory=dict)


class EventEngine:
    """Deterministic, synchronous trading-event dispatcher.

    Events are assigned a monotonically increasing sequence number and are
    dispatched in insertion order. The engine is intentionally broker-neutral
    and contains no order-routing logic.
    """

    def __init__(self):
        self._sequence = itertools.count(1)
        self._handlers: Dict[EventType, List[Callable[[TradingEvent], None]]] = {}
        self.history: List[TradingEvent] = []

    def subscribe(self, event_type: EventType, handler: Callable[[TradingEvent], None]):
        self._handlers.setdefault(event_type, []).append(handler)
        return handler

    def emit(self, event_type: EventType, timestamp, symbol: str, payload=None):
        event = TradingEvent(
            sequence=next(self._sequence),
            event_type=EventType(event_type),
            timestamp=timestamp,
            symbol=symbol,
            payload=dict(payload or {}),
        )
        self.history.append(event)
        for handler in list(self._handlers.get(event.event_type, [])):
            handler(event)
        return event

    def clear_history(self):
        self.history.clear()

    def last(self, event_type=None):
        if event_type is None:
            return self.history[-1] if self.history else None
        event_type = EventType(event_type)
        for event in reversed(self.history):
            if event.event_type == event_type:
                return event
        return None
