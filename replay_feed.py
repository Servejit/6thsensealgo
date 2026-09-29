import pandas as pd

from market_feed import MarketDataFeed, dataframe_to_bars


class ReplayFeed(MarketDataFeed):
    """Deterministic historical CSV/DataFrame feed using the same MarketBar contract."""

    def __init__(self, symbol: str, stale_after_seconds: float = 120.0):
        super().__init__(symbol, stale_after_seconds=stale_after_seconds)
        self.connect()

    def replay(self, df: pd.DataFrame, reset=False):
        if reset:
            self._last_bar_timestamp = None
        count = 0
        for bar in dataframe_to_bars(df, self.symbol):
            if self.publish(bar):
                count += 1
        return count

    def replay_csv(self, path, reset=False):
        return self.replay(pd.read_csv(path), reset=reset)
