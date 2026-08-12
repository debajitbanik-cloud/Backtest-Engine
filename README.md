# Trading Agent System

Multi-agent trading system with TypeScript backtest engine, Python live trading, free OHLCV data feeds, a TypeScript-Python integration bridge, and a React admin UI.

## Architecture
```
                    ┌──────────────────┐
                    │  Manager Agent   │
                    │  (Orchestrator)  │
                    └──────────────────┘
                              │
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
   ┌──────────┐      ┌──────────────┐       ┌──────────────┐
   │ TS Engine│──────│Python Agents │──────▶│   UI Admin   │
   │ backtest │◀────▶│(live trading)│◀─────▶│(SSE/REST API)│
   └──────────┘      └──────────────┘       └──────────────┘
        │                      │
        ▼                      ▼
   ┌──────────┐         ┌────────────┐
   │ Data     │◀────────│ Free Data │
   │ (shared) │         │ Feed       │
   │ (JSON)   │         │ (CCXT)     │
   └──────────┘         └────────────┘
```

## Quick Start

### Prerequisites
```bash
node --version  # v18+
python3 --version  # v3.10+
```

### 1. Install Dependencies
```bash
# TypeScript
cd /Users/zone/Desktop/Backtest\ Engine
npm install

# Python
cd agent_system
pip install -r requirements.txt
# Make sure NODE_ENV is NOT set to production when installing npm packages:
# unset NODE_ENV && npm install
```

### 2. Run TypeScript Backtest Engine (simulated data)
```bash
npx ts-node src/index.ts
```

### 3. Run TypeScript Engine with Real Binance Data (free, no API key)
```bash
npx ts-node src/index.ts --real-data --symbol BTCUSDT --timeframe 15m
```

### 4. Run Python Live Trading System
```bash
cd agent_system
python3 main.py
```

### 5. Start Admin UI
```bash
cd agent_system
python3 main.py   # UI auto-starts on http://127.0.0.1:3000
```

### 6. Run TypeScript Engine with Python Bridge (hybrid mode)
1. Start Python system: `cd agent_system && python3 main.py`
2. In another terminal: `npx ts-node src/index.ts --bridge`

## Free Data Sources

| Source | API Key | Granularity | Notes |
|--------|---------|-------------|-------|
| Binance Public API | No | 1m to 1d | Used in TS engine via `BinanceDataLoader` |
| CCXT (Binance/KuCoin/etc) | No | 1m to 1d | Used in Python engine via `FreeCryptoFeed` |
| CryptoDataDownload.com | No | 1m to 1d | CSV downloads |
| CoinGecko/CoinPaprika | Free tier | Various | For portfolio/market overview |

## Data Flow
1. **TS Engine** fetches OHLCV from Binance public API → saves to `data/shared/*.json`
2. **Python system** reads `data/shared/*.json` via bridge REST endpoints
3. **Both engines** publish events to their respective buses
4. **Bridge** forwards Python events to TypeScript via SSE
5. **UI** consumes both engines via REST/SSE