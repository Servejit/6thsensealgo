import streamlit as st
import pandas as pd
import numpy as np
from strategy_engine import add_indicators, direction_signal, score_signal

st.set_page_config(page_title="6thSense Algo Trading", page_icon="📈", layout="wide")
st.title("📈 6thSense Algo Trading")
st.caption("5m trigger + 15m confirmation • Backtest/Paper Trading • Live execution disabled")

def prepare_data(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    aliases = {"datetime":"timestamp","date":"timestamp","time":"timestamp","adj_close":"close"}
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    required = ["open","high","low","close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    if "volume" not in df.columns:
        df["volume"] = 0
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.date_range("2026-01-01", periods=len(df), freq="5min")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    for c in required + ["volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=required).reset_index(drop=True)
    return add_indicators(df)

def make_15m(data):
    x = data.set_index("timestamp")[["open","high","low","close","volume"]].resample("15min").agg({
        "open":"first","high":"max","low":"min","close":"last","volume":"sum"
    }).dropna().reset_index()
    return add_indicators(x)

def confirmation_for(row, confirm_df):
    candidates = confirm_df[confirm_df["timestamp"] <= row["timestamp"]]
    if candidates.empty:
        return "NOT AVAILABLE"
    return direction_signal(candidates.iloc[-1])

def backtest(df, capital, risk_pct, sl_pct, target_pct, max_trades, use_15m):
    cash = float(capital)
    position = None
    trades, curve = [], []
    count = 0
    confirm_df = make_15m(df) if use_15m else None

    for i in range(1, len(df)):
        row = df.iloc[i]

        if position:
            exit_price, reason = None, None
            if position["side"] == "BUY":
                if row["low"] <= position["sl"]:
                    exit_price, reason = position["sl"], "STOP LOSS"
                elif row["high"] >= position["target"]:
                    exit_price, reason = position["target"], "TARGET"
                elif direction_signal(row) == "SELL":
                    exit_price, reason = float(row["close"]), "OPPOSITE SIGNAL"
            else:
                if row["high"] >= position["sl"]:
                    exit_price, reason = position["sl"], "STOP LOSS"
                elif row["low"] <= position["target"]:
                    exit_price, reason = position["target"], "TARGET"
                elif direction_signal(row) == "BUY":
                    exit_price, reason = float(row["close"]), "OPPOSITE SIGNAL"

            if exit_price is not None:
                pnl = ((exit_price - position["entry"]) if position["side"] == "BUY" else (position["entry"] - exit_price)) * position["qty"]
                cash += pnl
                trades.append({
                    "Entry Time":position["time"],"Exit Time":row["timestamp"],
                    "Side":position["side"],"Entry":position["entry"],"Exit":exit_price,
                    "Quantity":position["qty"],"P&L":pnl,"Exit Reason":reason
                })
                position = None

        trigger = direction_signal(row)
        confirmation = confirmation_for(row, confirm_df) if confirm_df is not None else "NOT USED"

        if position is None and trigger != "NONE" and count < max_trades:
            entry = float(row["close"])
            risk_amount = cash * risk_pct / 100.0
            risk_per_share = entry * sl_pct / 100.0
            qty = max(1, int(risk_amount / risk_per_share)) if risk_per_share > 0 else 1
            if trigger == "BUY":
                sl, target = entry * (1-sl_pct/100), entry * (1+target_pct/100)
            else:
                sl, target = entry * (1+sl_pct/100), entry * (1-target_pct/100)
            score, _ = score_signal(row)
            position = {"time":row["timestamp"],"entry":entry,"qty":qty,"sl":sl,"target":target,"side":trigger,"score":score,"confirmation":confirmation}
            count += 1

        unrealized = 0.0
        if position:
            unrealized = ((row["close"]-position["entry"]) if position["side"]=="BUY" else (position["entry"]-row["close"])) * position["qty"]
        curve.append({"Time":row["timestamp"],"Equity":cash+unrealized})

    if position and len(df):
        final_price = float(df.iloc[-1]["close"])
        pnl = ((final_price-position["entry"]) if position["side"]=="BUY" else (position["entry"]-final_price))*position["qty"]
        cash += pnl
        trades.append({"Entry Time":position["time"],"Exit Time":df.iloc[-1]["timestamp"],"Side":position["side"],"Entry":position["entry"],"Exit":final_price,"Quantity":position["qty"],"P&L":pnl,"Exit Reason":"END OF DATA"})

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(curve)
    total_pnl = float(trades_df["P&L"].sum()) if not trades_df.empty else 0.0
    win_rate = float((trades_df["P&L"] > 0).mean()*100) if not trades_df.empty else 0.0
    max_dd = 0.0
    if not equity_df.empty:
        equity_df["Peak"] = equity_df["Equity"].cummax()
        max_dd = float((equity_df["Equity"]-equity_df["Peak"]).min())
    return trades_df, equity_df, cash, total_pnl, win_rate, max_dd

st.sidebar.header("Trading Configuration")
mode = st.sidebar.selectbox("Mode", ["BACKTEST","PAPER TRADING"])
symbol = st.sidebar.text_input("Symbol","NIFTY 200")
capital = st.sidebar.number_input("Initial Capital (₹)",1000.0,100000000.0,100000.0,5000.0)
risk_pct = st.sidebar.number_input("Risk per Trade (%)",0.1,10.0,1.0,0.1)
sl_pct = st.sidebar.number_input("Stop Loss (%)",0.05,20.0,0.75,0.05)
target_pct = st.sidebar.number_input("Target (%)",0.05,50.0,1.50,0.05)
max_trades = st.sidebar.number_input("Maximum Trades",1,1000,10,1)
use_15m = st.sidebar.checkbox("15m confirmation",True)
st.sidebar.error("LIVE trading is disabled. No real broker order can be sent.")

tab1,tab2,tab3,tab4 = st.tabs(["📊 Backtest","🧠 6thSense Strategy","📝 Paper Trading","🛡️ Risk Controls"])

with tab1:
    st.subheader("5m Trigger Backtest")
    upload = st.file_uploader("Upload OHLCV CSV",type=["csv"])
    if upload:
        try:
            data = prepare_data(pd.read_csv(upload))
            a,b,c,d = st.columns(4)
            a.metric("Candles",f"{len(data):,}")
            b.metric("Last Close",f"₹{data.iloc[-1]['close']:,.2f}")
            c.metric("5m Signal",direction_signal(data.iloc[-1]))
            score,_ = score_signal(data.iloc[-1])
            d.metric("Score",f"{score:.0f}/100")
            if st.button("▶ Run 6thSense Backtest",type="primary"):
                st.session_state["result"] = backtest(data,capital,risk_pct,sl_pct,target_pct,max_trades,use_15m)
            if "result" in st.session_state:
                trades,equity,final_capital,pnl,win_rate,max_dd = st.session_state["result"]
                a,b,c,d = st.columns(4)
                a.metric("Final Capital",f"₹{final_capital:,.2f}")
                b.metric("Total P&L",f"₹{pnl:,.2f}")
                c.metric("Win Rate",f"{win_rate:.2f}%")
                d.metric("Max Drawdown",f"₹{max_dd:,.2f}")
                if not equity.empty:
                    st.subheader("Equity Curve")
                    st.line_chart(equity.set_index("Time")["Equity"])
                st.subheader("Trade Journal")
                st.dataframe(trades,use_container_width=True) if not trades.empty else st.info("No qualifying 6thSense signals.")
                if not trades.empty:
                    st.download_button("Download Trade Journal",trades.to_csv(index=False).encode(),"6thsense_trade_journal.csv","text/csv")
        except Exception as e:
            st.error(f"CSV error: {e}")
    else:
        st.info("Upload 5-minute OHLCV data to begin.")

with tab2:
    st.subheader("🧠 6thSense Strategy")
    st.markdown("""
### BUY STARTS — 5m trigger
- Alligator: Lips > Teeth > Jaw
- Price: Close above Ichimoku cloud top
- Ichimoku: Tenkan > Kijun

### SELL STARTS — 5m trigger
- Alligator: Lips < Teeth < Jaw
- Price: Close below Ichimoku cloud bottom
- Ichimoku: Tenkan < Kijun

### 15m confirmation
15m direction is calculated separately as confirmation/conflict. It does not suppress the 5m trigger.
""")
    st.success("Signal labels: BUY STARTS / SELL STARTS, with 15m confirmation state attached.")

with tab3:
    st.subheader("📝 Paper Trading")
    if "paper_orders" not in st.session_state:
        st.session_state["paper_orders"] = []
    x,y = st.columns(2)
    with x:
        if st.button("Simulate BUY"):
            st.session_state["paper_orders"].append({"Time":pd.Timestamp.now(),"Symbol":symbol,"Side":"BUY","Quantity":1,"Status":"PAPER"})
            st.success("Paper BUY recorded. No broker order was sent.")
    with y:
        if st.button("Simulate SELL"):
            st.session_state["paper_orders"].append({"Time":pd.Timestamp.now(),"Symbol":symbol,"Side":"SELL","Quantity":1,"Status":"PAPER"})
            st.success("Paper SELL recorded. No broker order was sent.")
    if st.session_state["paper_orders"]:
        st.dataframe(pd.DataFrame(st.session_state["paper_orders"]),use_container_width=True)

with tab4:
    st.subheader("🛡️ Risk Controls")
    for label in ["Maximum daily loss protection","Maximum trades protection","Duplicate-order protection","Position reconciliation","Order-status verification","Emergency stop"]:
        st.checkbox(label,True)
    st.error("Real-money execution remains disabled until the broker/API and required compliance layers are completed.")

st.divider()
st.caption("6thSense Algo Trading • 5m trigger + 15m confirmation • Backtest/Paper only")
