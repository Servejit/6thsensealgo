from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
import time

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


@dataclass(frozen=True)
class FeedHealth:
    connected: bool
    stale: bool
    last_bar_timestamp: pd.Timestamp | None
    age_seconds: float | None
    message: str


class MarketDataFeed:
    """Broker-neutral market-data event interface with duplicate/order/stale protection."""

    def __init__(self, symbol: str, stale_after_seconds: float = 120.0):
        self.symbol = symbol
        self.stale_after_seconds = float(stale_after_seconds)
        self._callbacks = []
        self._last_bar_timestamp = None
        self._connected = False

    def connect(self):
        self._connected = True

    def close(self):
        self._connected = False

    def subscribe(self, callback: Callable[[MarketBar], None]):
        self._callbacks.append(callback)
        return callback

    def publish(self, bar: MarketBar):
        if bar.symbol != self.symbol:
            raise ValueError("MarketBar symbol does not match feed symbol.")
        if not bar.complete:
            return False

        ts = pd.to_datetime(bar.timestamp, errors="coerce")
        if pd.isna(ts):
            raise ValueError("MarketBar timestamp is invalid.")

        # Never process the same or an older completed bar twice.
        if self._last_bar_timestamp is not None and ts <= self._last_bar_timestamp:
            return False

        self._last_bar_timestamp = ts
        self._connected = True
        for callback in list(self._callbacks):
            callback(bar)
        return True

    def health(self, now=None) -> FeedHealth:
        if self._last_bar_timestamp is None:
            return FeedHealth(
                connected=self._connected,
                stale=True,
                last_bar_timestamp=None,
                age_seconds=None,
                message="No completed market bar received yet.",
            )

        current = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now)
        last = pd.to_datetime(self._last_bar_timestamp)
        if current.tzinfo is not None and last.tzinfo is None:
            current = current.tz_localize(None)
        elif current.tzinfo is None and last.tzinfo is not None:
            last = last.tz_localize(None)

        age = max(0.0, (current - last).total_seconds())
        stale = age > self.stale_after_seconds
        return FeedHealth(
            connected=self._connected,
            stale=stale,
            last_bar_timestamp=self._last_bar_timestamp,
            age_seconds=age,
            message="STALE: no recent completed bar." if stale else "Feed healthy.",
        )

    def can_trade(self, now=None):
        h = self.health(now)
        return h.connected and not h.stale

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
