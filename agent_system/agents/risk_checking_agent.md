# Risk Checking Agent

## Purpose
Monitors portfolio and position risk in real-time, automatically triggering mitigation actions when risk thresholds are breached.

## Responsibilities
- Track portfolio drawdown, daily P&L, position concentrations
- Detect losing streaks and losing positions held too long
- Monitor margin health across all positions
- Check position correlations and portfolio volatility
- Auto-execute mitigation: reduce/close positions, reduce leverage
- Coordinate with LeverageAdjustmentAgent and PositionSizingAgent

## Configuration
```yaml
risk:
  # Portfolio limits
  max_portfolio_drawdown: 0.10       # 10% max drawdown
  max_daily_loss: 0.03               # 3% max daily loss
  max_position_size_pct: 0.20        # 20% max per position
  max_sector_exposure: 0.40          # 40% max correlated sector
  max_leverage: 20.0
  
  # Position limits
  max_hold_time_losing_hours: 24     # Max hold losing position
  max_consecutive_losses: 5          # Max consecutive losses
  loss_streak_reduction: 0.5         # Reduce size after streak
  
  # Margin limits
  margin_warning: 0.70               # 70% margin used
  margin_critical: 0.85              # 85% margin used
  margin_liquidation: 0.95           # 95% margin used
  
  # Volatility limits
  max_portfolio_volatility: 0.05     # 5% daily vol
  var_confidence: 0.95
  var_horizon_days: 1
  
  # Correlation
  max_correlation: 0.7               # Max position correlation
  
  # Mitigation
  auto_mitigate: true                # Auto-execute mitigation
  mitigation_cooldown_minutes: 15    # Cooldown between actions
```

## Risk Checks (Every 5 Seconds)

### 1. Portfolio Drawdown
- **Critical** (>= 10%): `CLOSE_ALL` positions
- **High** (>= 7%): `REDUCE_POSITION` (50%)

### 2. Daily Loss
- **Critical** (>= 3%): `CLOSE_ALL` positions
- **High** (>= 2.1%): `REDUCE_POSITION` (30%)

### 3. Position Concentration
- **High** (>= 20% in one position): `REDUCE_POSITION` (50%)

### 4. Losing Streak
- **High** (>= 5 consecutive losses): `REDUCE_POSITION` (50% all)

### 5. Held Losers
- **Medium** (losing > 24h): `CLOSE_POSITION` (specific symbol)

### 6. Margin Health
- **Critical** (>= 95%): `CLOSE_POSITION` + `LEVERAGE_ADJUSTMENT`
- **High** (>= 85%): `REDUCE_LEVERAGE` (50%)
- **Medium** (>= 70%): `ALERT_ONLY`

### 7. Correlation
- **Medium** (>70% same direction): `REDUCE_POSITION` (30%)

### 8. Portfolio Volatility
- **High** (>= 5% daily): `REDUCE_POSITION` (30%)

## Risk Actions
| Action | Description |
|--------|-------------|
| `NONE` | No action |
| `ALERT_ONLY` | Publish alert, no position change |
| `REDUCE_POSITION` | Reduce position size by percentage |
| `CLOSE_POSITION` | Close specific position |
| `CLOSE_ALL` | Close all positions immediately |
| `REDUCE_LEVERAGE` | Reduce leverage for symbol |
| `HEDGE` | Open hedge position (future) |

## Event Subscriptions
- `POSITION_OPEN` / `POSITION_CLOSE` / `POSITION_UPDATE` - Track portfolio
- `MARKET_TICK` - Update unrealized P&L
- `LEVERAGE_ADJUSTMENT` - Track leverage changes
- `MARGIN_CALL` - Emergency margin call from exchange
- `AGENT_TUNING` - Parameter updates from ManagerAgent

## Event Publications
- `RISK_ALERT` - Published when threshold breached
  ```json
  {
    "symbol": "BTCUSDT",
    "risk_level": "high",
    "action": "reduce_position",
    "metric": "position_concentration",
    "current_value": 0.25,
    "threshold": 0.20,
    "reasoning": "Position BTCUSDT is 25% of portfolio, exceeds 20%"
  }
  ```
- `RISK_MITIGATION` - Published when auto-mitigation executes
  ```json
  {
    "symbol": "BTCUSDT",
    "action": "reduce_position",
    "triggered_by": "position_concentration",
    "reasoning": "Position BTCUSDT is 25% of portfolio, exceeds 20%",
    "reduce_pct": 0.5,
    "timestamp": "2024-01-15T10:30:00Z"
  }
  ```
- `AGENT_HEARTBEAT` - Current risk metrics

## Mitigation Logic
```
1. Collect all active alerts
2. Check cooldown (15 min default)
3. Prioritize: CRITICAL > HIGH > MEDIUM
4. For CRITICAL: Execute immediately (CLOSE_ALL or CLOSE_POSITION)
5. For HIGH: Execute highest current_value alert
6. Publish RISK_MITIGATION event
7. Clear triggered alert
8. Update cooldown timestamp
```

## Integration Points
- **LeverageAdjustmentAgent**: Receives `REDUCE_LEVERAGE` mitigations
- **PositionSizingAgent**: Portfolio risk limits constrain sizing
- **StyleManagingAgent**: Mode affects hold-time limits
- **ManagerAgent**: System mode changes adjust risk thresholds
- **TradeMasterAgent**: Logs mitigation actions for analysis

## System Mode Adjustments (from ManagerAgent)
| Mode | Max Drawdown | Daily Loss | Risk Per Trade |
|------|-------------|------------|----------------|
| Defensive | 5% | 1.5% | 1% |
| Cautious | 8% | 2% | 1.5% |
| Normal | 10% | 3% | 2% |
| Aggressive | 15% | 5% | 3% |

## Tuning Parameters (from ManagerAgent)
- All threshold values
- `auto_mitigate` - Enable/disable auto-execution
- `mitigation_cooldown_minutes`
- `max_hold_time_losing_hours`
- `max_consecutive_losses`