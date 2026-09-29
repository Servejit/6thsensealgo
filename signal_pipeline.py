import pandas as pd

from event_engine import EventEngine, EventType
from market_feed import MarketDataFeed, dataframe_to_bars
from strategy_engine import direction_signal, score_signal


class SignalEventPipeline:
    """Shared deterministic BAR_CLOSED -> SIGNAL event pipeline."""

    def __init__(self, symbol, event_engine=None, feed=None):
        self.symbol = symbol
        self.event_engine = event_engine or EventEngine()
        self.feed = feed or MarketDataFeed(symbol)

    def process_bar(self, row):
        timestamp = row["timestamp"]
        self.event_engine.emit(
            EventType.BAR_CLOSED,
            timestamp,
            self.symbol,
            {"row": row.to_dict()},
        )
        signal = direction_signal(row)
        score = score_signal(row)[0]
        return self.event_engine.emit(
            EventType.SIGNAL,
            timestamp,
            self.symbol,
            {"signal": signal, "score": score, "row": row.to_dict()},
        )

    def process_dataframe(self, df):
        events = []
        self.feed.connect()
        for bar in dataframe_to_bars(df, self.symbol):
            if not self.feed.publish(bar):
                continue
            row = df[pd.to_datetime(df["timestamp"]) == bar.timestamp].iloc[-1]
            events.append(self.process_bar(row))
        return events
