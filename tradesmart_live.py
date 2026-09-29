import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from market_feed import MarketBar, MarketDataFeed
from tradesmart_websocket import TradesmartWebSocket


def _tick_time(value):
    if value is None or value == "":
        return pd.Timestamp.now(tz="UTC")
    try:
        n = float(value)
        if n > 10_000_000_000:
            n /= 1000.0
        if n > 1_000_000_000:
            return pd.Timestamp(datetime.fromtimestamp(n, tz=timezone.utc))
    except Exception:
        pass
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if not pd.isna(ts):
            return ts
    except Exception:
        pass
    return pd.Timestamp.now(tz="UTC")


@dataclass
class CandleState:
    bucket: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class Tradesmart5mFeed:
    """TradeSmart touchline -> completed 5-minute OHLCV bars.

    Volume is treated as cumulative when the broker supplies cumulative
    touchline volume; deltas are accumulated into the candle.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        exchange: str,
        token: str,
        symbol: str,
        stale_after_seconds: float = 180.0,
        on_bar: Optional[Callable[[MarketBar], None]] = None,
    ):
        self.exchange = exchange
        self.token = str(token)
        self.symbol = symbol
        self.feed = MarketDataFeed(symbol, stale_after_seconds=stale_after_seconds)
        self.feed.connect()
        if on_bar:
            self.feed.subscribe(on_bar)

        self.ws = TradesmartWebSocket(
            client_id=client_id,
            access_token=access_token,
            on_message=self._on_message,
        )
        self.ws.subscribe_touchline([f"{exchange}|{self.token}"])
        self.ws.subscribe_orders()
        self.ws.subscribe_positions()

        self._lock = threading.Lock()
        self._candle = None
        self._last_cumulative_volume = None
        self._last_price = None
        self._last_tick_at = None
        self.order_updates = []
        self.position_updates = []

    @property
    def connected(self):
        return self.ws.connected

    def start(self):
        self.ws.start(background=True)

    def stop(self):
        self.ws.stop()
        self.feed.close()

    def health(self):
        h = self.feed.health()
        if not self.ws.connected:
            return h.__class__(
                connected=False,
                stale=True,
                last_bar_timestamp=h.last_bar_timestamp,
                age_seconds=h.age_seconds,
                message="TradeSmart WebSocket is disconnected.",
            )
        return h

    def can_trade(self):
        return self.connected and self.feed.can_trade()

    def _volume_delta(self, cumulative):
        if cumulative is None:
            return 0.0
        try:
            value = float(cumulative)
        except Exception:
            return 0.0
        if self._last_cumulative_volume is None:
            self._last_cumulative_volume = value
            return 0.0
        delta = value - self._last_cumulative_volume
        self._last_cumulative_volume = value
        if delta < 0:
            return 0.0
        return delta

    def _flush(self):
        candle = self._candle
        if candle is None:
            return None
        self._candle = None
        bar = MarketBar(
            symbol=self.symbol,
            timestamp=candle.bucket,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            complete=True,
        )
        self.feed.publish(bar)
        return bar

    def _on_touchline(self, data):
        try:
            price = float(data.get("lp"))
        except Exception:
            return
        if price <= 0:
            return

        ts = _tick_time(data.get("ft") or data.get("ltt") or data.get("tm"))
        bucket = ts.floor("5min")
        delta_volume = self._volume_delta(data.get("v"))

        with self._lock:
            self._last_tick_at = time.time()
            self._last_price = price

            if self._candle is None:
                self._candle = CandleState(bucket, price, price, price, price, delta_volume)
                return

            if bucket < self._candle.bucket:
                return

            if bucket > self._candle.bucket:
                self._flush()
                self._candle = CandleState(bucket, price, price, price, price, delta_volume)
                return

            self._candle.high = max(self._candle.high, price)
            self._candle.low = min(self._candle.low, price)
            self._candle.close = price
            self._candle.volume += delta_volume

    def _on_message(self, data):
        task = str(data.get("t", "")).lower()
        if task in {"tf", "df"}:
            self._on_touchline(data)
        elif task == "om":
            with self._lock:
                self.order_updates.append(dict(data))
                self.order_updates = self.order_updates[-100:]
        elif task == "pm":
            with self._lock:
                self.position_updates.append(dict(data))
                self.position_updates = self.position_updates[-100:]

    def snapshot(self):
        with self._lock:
            candle = self._candle
            return {
                "connected": self.connected,
                "last_price": self._last_price,
                "last_tick_at": self._last_tick_at,
                "forming_candle": None if candle is None else {
                    "timestamp": str(candle.bucket),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                },
                "order_updates": list(self.order_updates[-20:]),
                "position_updates": list(self.position_updates[-20:]),
            }
