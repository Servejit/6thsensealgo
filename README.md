# 6thSense Algo Trading

Automated algorithmic-trading application under development.

## Current architecture

- Streamlit dashboard
- 5m 6thSense trigger
- Independent 15m confirmation
- CSV backtesting
- Live market-data polling for paper trading
- BUY/SELL signal-start protection
- Automatic paper stop-loss and target
- Risk-based position sizing
- Maximum daily-loss and maximum-trade controls
- Emergency stop
- Broker-neutral paper order adapter
- Persistent SQLite paper positions and order journal
- Disabled live-broker adapter (no real orders)

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

## Important

The current execution layer is **paper-only**. The broker interface is deliberately separated from the strategy so a future authenticated broker integration can be added without changing the 6thSense signal engine.

Do not treat yfinance polling as production-grade execution data. A production system should use the broker/exchange-supported real-time feed and verify order status, fills, positions, and risk limits independently.

## Roadmap

1. Validate indicator conventions against the user's chart platform.
2. Improve event-driven scheduler/websocket market feed.
3. Add persistent daily risk/session state and restart reconciliation.
4. Add broker-specific authenticated adapter.
5. Add live execution only after extensive paper/forward testing and required broker/exchange safeguards.
