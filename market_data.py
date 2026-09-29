import pandas as pd
import yfinance as yf
from strategy_engine import add_indicators, direction_signal

def fetch_5m(symbol, period="5d"):
    df = yf.Ticker(symbol).history(period=period, interval="5m", auto_adjust=False)
    if df.empty:
        raise ValueError(f"No market data returned for {symbol}")
    df = df.reset_index()
    time_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={time_col:"timestamp", "Open":"open", "High":"high", "Low":"low", "Close":"close", "Volume":"volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return add_indicators(df[["timestamp","open","high","low","close","volume"]].dropna().reset_index(drop=True))

def make_15m(df):
    x = df.set_index("timestamp")[["open","high","low","close","volume"]].resample("15min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna().reset_index()
    return add_indicators(x)

def latest_confirmation(df5, df15):
    if df5.empty or df15.empty:
        return "NOT AVAILABLE"
    ts = df5.iloc[-1]["timestamp"]
    c = df15[df15["timestamp"] <= ts]
    return "NOT AVAILABLE" if c.empty else direction_signal(c.iloc[-1])
