import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="6thSense Algo Trading", page_icon="📈", layout="wide")

st.title("📈 6thSense Algo Trading")
st.caption("Phase 1: backtest and paper-trading foundation. Real-money execution is disabled.")

def prepare_data(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    aliases = {"datetime": "timestamp", "date": "timestamp", "time": "timestamp", "adj_close": "close"}
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    if "volume" not in df.columns:
        df["volume"] = 0
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    for c in required + ["volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=required).reset_index(drop=True)
    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["volume_ma"] = df["volume"].rolling(20).mean()
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    return df

def signal_for(row, previous_close, require_volume):
    if pd.isna(row["ema_fast"]) or pd.isna(row["ema_slow"]) or pd.isna(row["rsi"]):
        return "NONE"
    trend = row["ema_fast"] > row["ema_slow"]
    momentum = row["rsi"] > 55
    volume_ok = True
    if require_volume:
        volume_ok = not pd.isna(row["volume_ma"]) and row["volume"] > row["volume_ma"]
    return "BUY" if trend and momentum and volume_ok and row["close"] > previous_close else "NONE"

def backtest(df, capital, risk_pct, sl_pct, target_pct, require_volume, max_trades):
    cash = float(capital)
    position = None
    trades = []
    curve = []
    count = 0

    for i in range(1, len(df)):
        row = df.iloc[i]
        previous_close = df.iloc[i - 1]["close"]

        if position:
            exit_price = None
            reason = None
            if row["low"] <= position["sl"]:
                exit_price, reason = position["sl"], "STOP LOSS"
            elif row["high"] >= position["target"]:
                exit_price, reason = position["target"], "TARGET"
            if exit_price is not None:
                pnl = (exit_price - position["entry"]) * position["qty"]
                cash += pnl
                trades.append({
                    "Entry Time": position["time"],
                    "Exit Time": row.get("timestamp", i),
                    "Side": "BUY",
                    "Entry": position["entry"],
                    "Exit": exit_price,
                    "Quantity": position["qty"],
                    "P&L": pnl,
                    "Exit Reason": reason
                })
                position = None

        if position is None and count < max_trades:
            if signal_for(row, previous_close, require_volume) == "BUY":
                entry = float(row["close"])
                risk_amount = cash * risk_pct / 100
                risk_per_share = entry * sl_pct / 100
                if risk_per_share > 0:
                    qty = max(1, int(risk_amount / risk_per_share))
                    position = {
                        "time": row.get("timestamp", i),
                        "entry": entry,
                        "qty": qty,
                        "sl": entry * (1 - sl_pct / 100),
                        "target": entry * (1 + target_pct / 100)
                    }
                    count += 1

        unrealized = 0
        if position:
            unrealized = (row["close"] - position["entry"]) * position["qty"]
        curve.append({"Time": row.get("timestamp", i), "Equity": cash + unrealized})

    if position and len(df):
        final_price = float(df.iloc[-1]["close"])
        pnl = (final_price - position["entry"]) * position["qty"]
        cash += pnl
        trades.append({
            "Entry Time": position["time"],
            "Exit Time": df.iloc[-1].get("timestamp", len(df) - 1),
            "Side": "BUY",
            "Entry": position["entry"],
            "Exit": final_price,
            "Quantity": position["qty"],
            "P&L": pnl,
            "Exit Reason": "END OF DATA"
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(curve)
    pnl = float(trades_df["P&L"].sum()) if not trades_df.empty else 0.0
    win_rate = float((trades_df["P&L"] > 0).mean() * 100) if not trades_df.empty else 0.0
    max_dd = 0.0
    if not equity_df.empty:
        equity_df["Peak"] = equity_df["Equity"].cummax()
        equity_df["Drawdown"] = equity_df["Equity"] - equity_df["Peak"]
        max_dd = float(equity_df["Drawdown"].min())
    return trades_df, equity_df, cash, pnl, win_rate, max_dd

st.sidebar.header("Trading Configuration")
mode = st.sidebar.selectbox("Mode", ["BACKTEST", "PAPER TRADING"])
symbol = st.sidebar.text_input("Symbol", "NIFTY 200")
timeframe = st.sidebar.selectbox("Timeframe", ["5m", "15m", "30m", "1h", "1d"])
capital = st.sidebar.number_input("Initial Capital (₹)", 1000.0, 100000000.0, 100000.0, 5000.0)
risk_pct = st.sidebar.number_input("Risk per Trade (%)", 0.1, 10.0, 1.0, 0.1)
sl_pct = st.sidebar.number_input("Stop Loss (%)", 0.05, 20.0, 0.75, 0.05)
target_pct = st.sidebar.number_input("Target (%)", 0.05, 50.0, 1.50, 0.05)
max_trades = st.sidebar.number_input("Maximum Trades", 1, 1000, 10, 1)
require_volume = st.sidebar.checkbox("Require volume confirmation", True)
st.sidebar.divider()
st.sidebar.error("LIVE trading is disabled in Phase 1.")

tabs = st.tabs(["📊 Backtest", "🧠 Strategy", "📝 Paper Trading", "🛡️ Risk Controls"])

with tabs[0]:
    st.subheader("Historical OHLCV Backtest")
    upload = st.file_uploader("Upload OHLCV CSV", type=["csv"])
    if upload:
        try:
            data = prepare_data(pd.read_csv(upload))
            a, b, c, d = st.columns(4)
            a.metric("Candles", f"{len(data):,}")
            b.metric("Last Close", f"₹{data.iloc[-1]['close']:,.2f}")
            c.metric("EMA 9", f"₹{data.iloc[-1]['ema_fast']:,.2f}")
            d.metric("RSI", f"{data.iloc[-1]['rsi']:.2f}" if not pd.isna(data.iloc[-1]['rsi']) else "-")
            if st.button("▶ Run Backtest", type="primary"):
                result = backtest(data, capital, risk_pct, sl_pct, target_pct, require_volume, max_trades)
                st.session_state["result"] = result
            if "result" in st.session_state:
                trades, equity, final_capital, pnl, win_rate, max_dd = st.session_state["result"]
                a, b, c, d = st.columns(4)
                a.metric("Final Capital", f"₹{final_capital:,.2f}")
                b.metric("Total P&L", f"₹{pnl:,.2f}")
                c.metric("Win Rate", f"{win_rate:.2f}%")
                d.metric("Max Drawdown", f"₹{max_dd:,.2f}")
                if not equity.empty:
                    st.subheader("Equity Curve")
                    st.line_chart(equity.set_index("Time")["Equity"])
                st.subheader("Trade Journal")
                if trades.empty:
                    st.info("No trades matched the current conditions.")
                else:
                    st.dataframe(trades, use_container_width=True)
                    st.download_button("Download Trade Journal", trades.to_csv(index=False).encode(), "6thsense_trade_journal.csv", "text/csv")
        except Exception as e:
            st.error(f"CSV error: {e}")
    else:
        st.info("Upload historical OHLCV data to begin.")

with tabs[1]:
    st.subheader("🧠 Strategy Engine")
    st.write("The strategy engine is separated from execution so conditions can be tested without real orders.")
    st.markdown("""
Current Phase-1 placeholder:
- EMA 9 above EMA 21
- RSI above 55
- Optional volume confirmation
- Close above previous close

Next:
Price → Candle → Volume → Alligator → Ichimoku → Momentum → Multi-timeframe → Signal
""")
    st.info("Your exact 6thSense conditions will replace the placeholder conditions in the next phase.")

with tabs[2]:
    st.subheader("📝 Paper Trading")
    if "paper_orders" not in st.session_state:
        st.session_state["paper_orders"] = []
    x, y = st.columns(2)
    with x:
        if st.button("Simulate BUY"):
            st.session_state["paper_orders"].append({
                "Time": pd.Timestamp.now(),
                "Symbol": symbol,
                "Side": "BUY",
                "Quantity": 1,
                "Status": "PAPER"
            })
            st.success("Paper BUY recorded. No broker order was sent.")
    with y:
        if st.button("Clear Paper Session"):
            st.session_state["paper_orders"] = []
            st.rerun()
    if st.session_state["paper_orders"]:
        st.dataframe(pd.DataFrame(st.session_state["paper_orders"]), use_container_width=True)
    else:
        st.info("No paper orders yet.")

with tabs[3]:
    st.subheader("🛡️ Risk Controls")
    st.checkbox("Maximum daily loss protection", True)
    st.checkbox("Maximum trades protection", True)
    st.checkbox("Duplicate-order protection", True)
    st.checkbox("Position reconciliation", True)
    st.checkbox("Order-status verification", True)
    st.checkbox("Emergency stop", True)
    st.error("Real-money execution remains disabled until broker/API and compliance layers are completed.")

st.divider()
st.caption("6thSense Algo Trading • Phase 1 • Backtest/Paper only")
