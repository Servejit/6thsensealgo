from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool = True

    def as_dict(self):
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class MarketDataFeed:
    """Broker-neutral event interface.

    The current yfinance adapter can publish completed bars into this interface.
    A future broker websocket can implement the same contract without changing
    the strategy or execution layers.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._callbacks = []

    def subscribe(self, callback: Callable[[MarketBar], None]):
        self._callbacks.append(callback)
        return callback

    def publish(self, bar: MarketBar):
        if bar.symbol != self.symbol:
            raise ValueError("MarketBar symbol does not match feed symbol.")
        if not bar.complete:
            return
        for callback in list(self._callbacks):
            callback(bar)

    def clear_subscribers(self):
        self._callbacks.clear()


def dataframe_to_bars(df: pd.DataFrame, symbol: str):
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Missing market columns: " + ", ".join(sorted(missing)))

    for _, row in df.sort_values("timestamp").iterrows():
        ts = pd.to_datetime(row["timestamp"], errors="coerce")
        if pd.isna(ts):
            continue
        yield MarketBar(
            symbol=symbol,
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            complete=True,
        )


def utc_now():
    return datetime.now(timezone.utc).isoformat()
