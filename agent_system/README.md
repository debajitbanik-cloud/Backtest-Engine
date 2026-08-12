# Trading Agent System

A multi-agent trading system with specialized agents for different aspects of trading, coordinated by a central Manager Agent.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Manager Agent                             │
│  (Orchestration, Parameter Tuning, Daily Reports)           │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Bias         │    │  Style        │    │  Risk         │
│  Determining  │    │  Managing     │    │  Checking     │
│  Agent        │    │  Agent        │    │  Agent        │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│           Multi-Timeframe Confluence Agent                  │
│         (Filters signals across timeframes)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Position Sizing Agent                          │
│         (Calculates optimal position sizes)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│            Leverage Adjustment Agent                        │
│         (Dynamic leverage based on margin)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Trade Master Agent                             │
│    (Logs trades, analyzes performance, optimizes, reports)  │
└─────────────────────────────────────────────────────────────┘
```

## Agents

### 1. LeverageAdjustmentAgent
- Monitors margin requirements in real-time
- Dynamically adjusts leverage based on margin usage
- Reduces leverage proactively before margin calls
- Coordinates with RiskCheckingAgent for emergency reductions

### 2. BiasDeterminingAgent
- Analyzes market bias (bullish/bearish/neutral) across multiple timeframes
- Uses EMA alignment, RSI, MACD, volume, volatility
- Outputs bias signals with confidence scores
- Feeds into Confluence Agent

### 3. MultiTimeframeConfluenceAgent
- Checks for signal alignment across 5m, 15m, 1h, 4h, 1d timeframes
- Identifies key support/resistance levels
- Requires minimum 3 timeframes aligned for signal
- Filters trades through PositionSizingAgent

### 4. PositionSizingAgent
- Calculates optimal position size using multiple methods:
  - Fixed risk (% of account)
  - Kelly Criterion (based on win rate)
  - Volatility-adjusted (ATR-based)
  - Confluence-weighted (boosted by signal strength)
- Respects portfolio risk limits, correlation limits, margin constraints

### 5. StyleManagingAgent
- Switches between **Scalping** (15m max hold, 0.3% target) and **Swing** (1%+ target, hours-days)
- Decision factors: volatility, trend strength, volume, historical mode performance
- Provides mode-specific parameters to other agents

### 6. RiskCheckingAgent
- Monitors: portfolio drawdown, daily loss, position concentration, losing streaks, held losers, margin health, correlation, volatility
- Auto-mitigation: reduce/close positions, reduce leverage, hedge
- Cooldown between mitigation actions

### 7. TradeMasterAgent
- Logs every trade with full context (mode, confluence, bias, entry/exit reasons)
- Calculates performance metrics: win rate, profit factor, Sharpe, max drawdown
- Generates daily reports with optimization suggestions
- Runs parameter optimization (grid search / Bayesian)

### 8. ManagerAgent
- Orchestrates all sub-agents
- Receives daily reports, analyzes performance
- Tunes agent parameters based on results
- Manages system modes: normal/cautious/aggressive/defensive
- Generates manager summaries for human oversight

## Data Feed

**Delta Exchange Integration:**
- WebSocket for real-time ticker, candles, orderbook, trades
- REST API for historical data
- Automatic reconnection with exponential backoff
- Authentication support for private endpoints

## Event Bus

All agents communicate via async Event Bus (pub/sub):
- Decoupled, scalable communication
- Event types for market data, signals, positions, risk, trades, system events
- Event history for debugging/replay

## Configuration

All settings in `config/settings.yaml`:
- Agent-specific parameters
- Risk limits
- Data feed settings
- Trading symbols

## Installation

```bash
cd agent_system
pip install -r requirements.txt
```

## Running

```bash
# Set Delta Exchange credentials
export DELTA_API_KEY="your_key"
export DELTA_API_SECRET="your_secret"

# Run the system
python main.py
```

## Agent Communication Flow

1. **DeltaDataFeed** → publishes `MARKET_TICK` / `MARKET_CANDLE`
2. **BiasDeterminingAgent** → consumes ticks/candles → publishes `BIAS_SIGNAL`
3. **MultiTimeframeConfluenceAgent** → consumes bias signals → publishes `CONFLUENCE_SIGNAL`
4. **StyleManagingAgent** → consumes market data/bias/confluence → publishes `MODE_SWITCH`
5. **PositionSizingAgent** → consumes confluence/bias/leverage → publishes `POSITION_SIZING`
6. **LeverageAdjustmentAgent** → consumes position updates → publishes `LEVERAGE_ADJUSTMENT`
7. **RiskCheckingAgent** → consumes positions/margin → publishes `RISK_ALERT` / `RISK_MITIGATION`
8. **TradeMasterAgent** → consumes position open/close → publishes `TRADE_LOG` / `DAILY_REPORT`
9. **ManagerAgent** → consumes all heartbeats/reports → publishes `AGENT_TUNING` / manages system mode

## Extending

To add a new agent:
1. Create agent class inheriting from `BaseAgent`
2. Define subscriptions in `config.subscriptions`
3. Implement `_handle_event` for incoming events
4. Publish events using `_publish(EventType.X, payload)`
5. Register in `main.py` with dependencies
6. Add configuration to `settings.yaml`

## Directory Structure

```
agent_system/
├── main.py                    # Entry point
├── requirements.txt
├── config/
│   ├── settings.yaml          # All configuration
│   └── __init__.py            # Config loader
├── core/
│   ├── event_bus.py           # Pub/sub event system
│   ├── base_agent.py          # Base agent class
│   └── agent_registry.py      # Agent lifecycle management
├── agents/
│   ├── leverage_adjustment_agent.py
│   ├── bias_determining_agent.py
│   ├── multitimeframe_confluence_agent.py
│   ├── position_sizing_agent.py
│   ├── style_managing_agent.py
│   ├── risk_checking_agent.py
│   ├── trade_master_agent.py
│   └── manager_agent.py
├── data/
│   └── delta_exchange_feed.py # Delta Exchange WebSocket/REST
├── reports/                   # Generated reports
└── data/trades/              # Trade logs
```