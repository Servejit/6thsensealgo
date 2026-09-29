import pandas as pd
import numpy as np

def add_indicators(df):
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]

    def smma(series, period):
        return series.ewm(alpha=1 / period, adjust=False).mean()

    median = (high + low) / 2.0
    df["jaw"] = smma(median, 13).shift(8)
    df["teeth"] = smma(median, 8).shift(5)
    df["lips"] = smma(median, 5).shift(3)

    df["tenkan"] = (high.rolling(9).max() + low.rolling(9).min()) / 2
    df["kijun"] = (high.rolling(26).max() + low.rolling(26).min()) / 2
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(26)
    df["senkou_b"] = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)
    df["cloud_bottom"] = df[["senkou_a", "senkou_b"]].min(axis=1)
    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["volume_ma20"] = df["volume"].rolling(20).mean()
    return df

def direction_signal(row):
    needed = ["lips","teeth","jaw","close","cloud_top","cloud_bottom","tenkan","kijun"]
    if any(pd.isna(row.get(c)) for c in needed):
        return "NONE"
    if row["lips"] > row["teeth"] > row["jaw"] and row["close"] > row["cloud_top"] and row["tenkan"] > row["kijun"]:
        return "BUY"
    if row["lips"] < row["teeth"] < row["jaw"] and row["close"] < row["cloud_bottom"] and row["tenkan"] < row["kijun"]:
        return "SELL"
    return "NONE"

def score_signal(row):
    direction = direction_signal(row)
    if direction == "NONE":
        return 0.0, direction
    score = 0.0
    if direction == "BUY":
        if row["lips"] > row["teeth"] > row["jaw"]:
            score += 30
        if row["close"] > row["cloud_top"] and row["tenkan"] > row["kijun"]:
            score += 30
        if row["close"] > row["cloud_top"]:
            score += 20
        if row["lips"] > row["teeth"] > row["jaw"]:
            score += 20
    else:
        if row["lips"] < row["teeth"] < row["jaw"]:
            score += 30
        if row["close"] < row["cloud_bottom"] and row["tenkan"] < row["kijun"]:
            score += 30
        if row["close"] < row["cloud_bottom"]:
            score += 20
        if row["lips"] < row["teeth"] < row["jaw"]:
            score += 20
    return min(score, 100.0), direction
