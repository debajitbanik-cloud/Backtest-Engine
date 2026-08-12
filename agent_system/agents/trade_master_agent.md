# Trade Master Agent

## Purpose
Logs every trade with full context, analyzes performance, runs strategy optimization, and generates daily reports for the Manager Agent.

## Responsibilities
- Record every trade entry/exit with complete metadata
- Calculate comprehensive performance metrics
- Analyze performance by mode, symbol, timeframe, exit reason
- Run parameter optimization using historical trades
- Generate daily reports with optimization suggestions
- Persist trade history to disk for audit/backtesting

## Configuration
```yaml
trade_master:
  data_dir: "data/trades"           # Trade log storage
  report_dir: "reports"             # Daily report output
  optimization_enabled: true        # Enable auto-optimization
  optimization_interval_hours: 24   # Optimization frequency
  min_trades_for_optimization: 50   # Minimum trades before optimizing
```

## Trade Record Schema
```json
{
  "trade_id": "trade_1705312800.123",
  "symbol": "BTCUSDT",
  "side": "long",
  "entry_price": 45000.0,
  "exit_price": 45450.0,
  "size": 0.15,
  "notional": 6750.0,
  "leverage": 10.0,
  "entry_time": "2024-01-15T10:00:00Z",
  "exit_time": "2024-01-15T10:45:00Z",
  "hold_duration_minutes": 45.0,
  "pnl": 67.5,
  "pnl_pct": 0.01,
  "fees": 13.5,
  "mode": "swing",
  "confluence_result": "bullish",
  "bias_direction": "bullish",
  "bias_confidence": 0.78,
  "stop_loss": 44100.0,
  "take_profit": 45450.0,
  "exit_reason": "tp",
  "metadata": {}
}
```

## Performance Metrics Calculated
- **Win Rate**: Winning trades / Total trades
- **Profit Factor**: Gross profit / |Gross loss|
- **Sharpe Ratio**: Mean return / Std return * √252
- **Max Drawdown**: Peak-to-trough equity decline
- **Avg Win / Avg Loss**: Mean PnL for winners/losers
- **Expectancy**: (Win Rate * Avg Win) - (Loss Rate * |Avg Loss|)

## Daily Report
Generated at midnight UTC, includes:
```json
{
  "date": "2024-01-15",
  "total_trades": 24,
  "winning_trades": 16,
  "losing_trades": 8,
  "win_rate": 0.667,
  "total_pnl": 1247.50,
  "total_pnl_pct": 0.125,
  "avg_win": 98.5,
  "avg_loss": -52.3,
  "profit_factor": 2.8,
  "max_drawdown": 320.0,
  "sharpe_ratio": 1.85,
  "scalping_trades": 10,
  "swing_trades": 14,
  "scalping_pnl": 450.0,
  "swing_pnl": 797.5,
  "best_trade": {...},
  "worst_trade": {...},
  "mode_performance": {
    "scalping": {"trades": 10, "pnl": 450, "win_rate": 0.7},
    "swing": {"trades": 14, "pnl": 797.5, "win_rate": 0.64}
  },
  "symbol_performance": {
    "BTCUSDT": {"trades": 8, "pnl": 500, "wins": 6},
    "ETHUSDT": {"trades": 10, "pnl": 400, "wins": 7}
  },
  "optimization_suggestions": [
    "Consider increasing swing allocation - higher win rate",
    "Consider avoiding DOGEUSDT - win rate 30%",
    "Stop losses hitting frequently - consider wider stops"
  ]
}
```

## Optimization Engine
Runs every 24 hours (configurable) when >= 50 trades available.

### Parameter Bounds
```python
parameter_bounds = {
    "bias.min_confidence": (0.5, 0.8),
    "confluence.required_alignment": (2, 4),
    "sizing.max_risk_per_trade": (0.01, 0.03),
    "style.scalping_target_pct": (0.002, 0.005),
    "style.swing_target_pct": (0.008, 0.02),
    "risk.max_portfolio_drawdown": (0.05, 0.15),
}
```

### Optimization Method
- Grid search over parameter combinations (simplified)
- Simulates Sharpe ratio with each combination
- Selects best parameters
- Publishes `AGENT_TUNING` events for target agents
- In production: Replace with Optuna/Bayesian optimization

### Optimization Result
```json
{
  "parameter": "bias.min_confidence",
  "old_value": 0.6,
  "new_value": 0.65,
  "expected_improvement": 0.1,
  "confidence": 0.7,
  "reasoning": "Optimization based on 100 recent trades"
}
```

## Event Subscriptions
- `POSITION_OPEN` - Record trade entry
- `POSITION_CLOSE` - Complete trade record
- `TRADE_EXECUTED` - Alternative execution logging
- `TRADE_REJECTED` - Log rejected trades
- `MODE_SWITCH` - Track mode for analysis
- `AGENT_TUNING` - Receive optimization control

## Event Publications
- `TRADE_LOG` - Published for every completed trade
- `DAILY_REPORT` - Published at midnight UTC
- `OPTIMIZATION_UPDATE` - Published after optimization run
- `AGENT_HEARTBEAT` - Total trades logged, status

## Data Persistence
- Trades saved to `data/trades/trades_YYYY-MM-DD.json`
- Daily reports saved to `reports/daily_report_YYYY-MM-DD.json`
- Automatic loading on startup
- JSON format for easy analysis

## Integration Points
- **All agents**: Source of trade data (position open/close)
- **ManagerAgent**: Receives daily reports, applies optimizations
- **PositionSizingAgent**: Trade history feeds Kelly calculation
- **StyleManagingAgent**: Mode performance feeds switching logic
- **RiskCheckingAgent**: Consecutive losses tracked from trades

## Tuning Parameters (from ManagerAgent)
- `optimization_enabled` - Enable/disable auto-optimization
- `optimization_interval_hours`
- `min_trades_for_optimization`
- Parameter bounds for optimization