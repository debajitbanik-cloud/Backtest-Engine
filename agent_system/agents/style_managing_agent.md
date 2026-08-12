# Style Managing Agent

## Purpose
Dynamically switches between scalping and swing trading modes based on market conditions, providing mode-specific parameters to all other agents.

## Responsibilities
- Monitor market volatility, trend strength, volume
- Switch between Scalping (15m max hold) and Swing (1%+ target, hours-days)
- Track performance of each mode for adaptive decisions
- Provide mode-specific parameters to PositionSizingAgent, RiskCheckingAgent, etc.
- Publish mode switch events for system-wide coordination

## Configuration
```yaml
style:
  # Scalping config
  scalping_max_hold_minutes: 15
  scalping_target_pct: 0.003      # 0.3%
  scalping_stop_pct: 0.002        # 0.2%
  scalping_min_volatility: 0.005  # 0.5% ATR
  scalping_max_spread_pct: 0.001  # 0.1%
  
  # Swing config
  swing_target_pct: 0.01          # 1%+
  swing_stop_pct: 0.005           # 0.5%
  swing_min_hold_hours: 2
  swing_max_hold_days: 7
  swing_min_trend_strength: 0.6
  
  # Switching criteria
  volatility_threshold_high: 0.03   # High vol -> scalping
  volatility_threshold_low: 0.01    # Low vol -> swing
  trend_threshold: 0.65             # Strong trend -> swing
  volume_threshold: 1.5             # High volume -> scalping
  cooldown_hours: 1                 # Min time between switches
```

## Trading Modes

### Scalping Mode
- **Max hold**: 15 minutes
- **Target**: 0.3% per trade
- **Stop**: 0.2%
- **Timeframes**: 1m, 5m
- **Min confluence**: bullish/bearish
- **Leverage multiplier**: 1.5x
- **Best for**: High volatility, high volume, ranging markets

### Swing Mode
- **Min hold**: 2 hours
- **Max hold**: 7 days
- **Target**: 1%+ per trade
- **Stop**: 0.5%
- **Timeframes**: 15m, 1h, 4h
- **Min confluence**: strong_bullish/strong_bearish
- **Leverage multiplier**: 1.0x
- **Best for**: Low volatility, strong trends, clear direction

### Hybrid Mode
- 40% allocation to scalping, 60% to swing
- Used when conditions are mixed

## Switching Logic
```
Every 60 seconds:
  Calculate metrics:
    - Volatility (ATR % annualized from 5m returns)
    - Trend strength (bias confidence + confluence)
    - Volume ratio (current vs 20-period avg)
  
  If volatility > 3% AND volume > 1.5x:
    -> SCALPING (confidence 0.8)
  
  Elif volatility < 1% AND trend_strength > 0.65:
    -> SWING (confidence 0.8)
  
  Else:
    -> Compare mode performance (win rates)
    -> Better mode wins, or HYBRID if close
  
  If mode != current_mode AND confidence > 0.7 AND cooldown passed:
    -> SWITCH MODE
```

## Event Subscriptions
- `MARKET_TICK` - Real-time volatility/volume calculation
- `MARKET_CANDLE` - 15m candles for trend analysis
- `BIAS_SIGNAL` - Trend strength from BiasDeterminingAgent
- `CONFLUENCE_SIGNAL` - Confluence result for trend confirmation
- `TRADE_EXECUTED` - Track performance by mode
- `AGENT_TUNING` - Parameter updates from ManagerAgent

## Event Publications
- `MODE_SWITCH` - Published on mode change
  ```json
  {
    "old_mode": "swing",
    "new_mode": "scalping",
    "reasoning": "High vol (0.042) + high volume (2.1x)",
    "parameters": {
      "max_hold_minutes": 15,
      "target_pct": 0.003,
      "stop_pct": 0.002,
      "timeframes": ["1m", "5m"],
      "min_confluence": "bullish",
      "leverage_multiplier": 1.5
    },
    "timestamp": "2024-01-15T10:30:00Z"
  }
  ```
- `SCALPING_MODE` / `SWING_MODE` - Specific mode events
- `AGENT_HEARTBEAT` - Current mode and performance stats

## Mode Parameters Provided to Other Agents
```python
# Scalping
{
  "max_hold_minutes": 15,
  "target_pct": 0.003,
  "stop_pct": 0.002,
  "timeframes": ["1m", "5m"],
  "min_confluence": "bullish",
  "leverage_multiplier": 1.5
}

# Swing
{
  "min_hold_hours": 2,
  "max_hold_days": 7,
  "target_pct": 0.01,
  "stop_pct": 0.005,
  "timeframes": ["15m", "1h", "4h"],
  "min_confluence": "strong_bullish",
  "leverage_multiplier": 1.0
}
```

## Integration Points
- **PositionSizingAgent**: Receives mode-specific target/stop for sizing
- **RiskCheckingAgent**: Adjusts hold-time limits based on mode
- **BiasDeterminingAgent**: Primary timeframe shifts with mode
- **MultiTimeframeConfluenceAgent**: Required confluence level changes
- **ManagerAgent**: Can override mode, tunes switching thresholds

## Performance Tracking
- Tracks trades, wins, PnL per mode
- Uses historical performance for tie-breaking decisions
- Reports to ManagerAgent for optimization

## Tuning Parameters (from ManagerAgent)
- `volatility_threshold_high` / `volatility_threshold_low`
- `trend_threshold`
- `volume_threshold`
- `cooldown_hours`
- All scalping/swing target/stop/hold parameters