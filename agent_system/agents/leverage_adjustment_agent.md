# Leverage Adjustment Agent

## Purpose
Dynamically adjusts leverage based on margin requirements and market conditions to prevent liquidation and optimize capital efficiency.

## Responsibilities
- Track margin usage across all positions in real-time
- Detect high margin requirement periods before they become critical
- Reduce leverage proactively when margin ratios exceed thresholds
- Increase leverage when margin is healthy and opportunities exist
- Coordinate with RiskCheckingAgent for emergency leverage reductions

## Configuration
```yaml
leverage:
  max_leverage: 20.0           # Maximum allowed leverage
  min_leverage: 1.0            # Minimum leverage (spot)
  margin_warning_threshold: 0.70    # 70% margin used - warning
  margin_critical_threshold: 0.85   # 85% margin used - reduce leverage
  margin_liquidation_threshold: 0.95 # 95% margin used - emergency
  adjustment_step: 0.5         # Leverage change per adjustment
  cooldown_seconds: 60         # Minimum time between adjustments
  lookback_periods: 20         # Periods for volatility calculation
```

## Event Subscriptions
- `MARKET_TICK` - Recalculate margin on price changes
- `POSITION_UPDATE` - Update position margin snapshots
- `MARGIN_CALL` - Emergency leverage reduction
- `RISK_ALERT` - Reduce leverage on risk alerts
- `AGENT_TUNING` - Receive parameter updates from ManagerAgent

## Event Publications
- `LEVERAGE_ADJUSTMENT` - Published when leverage changes
  ```json
  {
    "symbol": "BTCUSDT",
    "old_leverage": 10.0,
    "new_leverage": 5.0,
    "reason": "critical_margin",
    "margin_ratio": 0.87
  }
  ```
- `AGENT_HEARTBEAT` - Periodic status with current leverages

## Logic Flow
```
Market Tick / Position Update
         │
         ▼
Recalculate Margin Ratio
         │
         ▼
Check Thresholds:
  >= 95% (liquidation)  -> Reduce to 30% of current
  >= 85% (critical)     -> Reduce to 60% of current
  >= 70% (warning)      -> Reduce to 85% of current
  < 30% (healthy)       -> Increase by step (max 20x)
         │
         ▼
Apply Cooldown Check (60s default)
         │
         ▼
Publish LEVERAGE_ADJUSTMENT event
```

## Integration Points
- **PositionSizingAgent**: Receives leverage updates for position sizing calculations
- **RiskCheckingAgent**: Triggers emergency reductions on margin calls
- **ManagerAgent**: Receives tuning parameters for thresholds

## Metrics Tracked
- Current leverage per symbol
- Margin ratio per symbol
- Last adjustment timestamp and reason
- Adjustment frequency

## Tuning Parameters (from ManagerAgent)
- `margin_warning_threshold`
- `margin_critical_threshold`
- `margin_liquidation_threshold`
- `adjustment_step`
- `cooldown_seconds`
- `max_leverage` / `min_leverage`