# 6thSense Algo Trading

Automated algorithmic-trading application under development.

## Current architecture

- Streamlit dashboard
- 5m 6thSense trigger
- Independent 15m confirmation
- CSV backtesting
- Live market-data polling for paper trading
- Broker-neutral market-data event/feed interface
- BUY/SELL signal-start protection
- Automatic paper stop-loss and target
- Risk-based position sizing
- Maximum daily-loss and maximum-trade controls
- Emergency stop
- Broker-neutral paper order adapter
- Persistent SQLite paper positions and order journal
- Explicit order state machine: CREATED → SUBMITTED → OPEN/PARTIALLY_FILLED → FILLED/CANCELLED/REJECTED
- Broker-neutral reconciliation engine with discrepancy blocking
- Reconciliation audit history and manual dashboard check
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
2. Connect a broker/exchange websocket to the broker-neutral market-data feed.
3. Add event-driven scheduler, stale-feed detection, and reconnect handling.
4. Add broker-specific authenticated adapter implementing exchange/broker-supported order types.
5. Connect authenticated broker snapshots to the reconciliation engine.
6. Add production operational monitoring.
6. Add live execution only after extensive paper/forward testing and required broker/exchange safeguards.
