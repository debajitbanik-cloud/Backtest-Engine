# Manager Agent

## Purpose
Master orchestrator that manages all sub-agents, tunes parameters based on performance, receives daily reports, and makes high-level strategic decisions.

## Responsibilities
- Monitor health and performance of all sub-agents
- Receive and analyze daily reports from TradeMasterAgent
- Tune agent parameters based on performance data
- Manage system-wide trading modes (normal/cautious/aggressive/defensive)
- Coordinate emergency responses to risk events
- Generate manager summaries for human oversight

## Configuration
```yaml
manager:
  report_dir: "reports/manager"       # Manager summary output
  tuning_enabled: true                # Enable parameter tuning
  tuning_interval_hours: 6            # Tuning frequency
  min_confidence_for_tuning: 0.70     # Min confidence to apply tuning
```

## System Modes
| Mode | Description | Risk Parameters | Use Case |
|------|-------------|-----------------|----------|
| **Normal** | Balanced | Drawdown 10%, Daily Loss 3%, Risk/Trade 2% | Default operation |
| **Cautious** | Reduced risk | Drawdown 8%, Daily Loss 2%, Risk/Trade 1.5% | After losses, uncertain markets |
| **Aggressive** | Increased risk | Drawdown 15%, Daily Loss 5%, Risk/Trade 3% | Strong performance, trending markets |
| **Defensive** | Capital preservation | Drawdown 5%, Daily Loss 1.5%, Risk/Trade 1% | Critical risk alerts, high uncertainty |

## Event Subscriptions
- `AGENT_HEARTBEAT` - Monitor all agent health
- `AGENT_REGISTERED` - Track agent registration
- `DAILY_REPORT` - Receive daily performance from TradeMasterAgent
- `OPTIMIZATION_UPDATE` - Receive optimization suggestions
- `RISK_ALERT` - React to risk events
- `MODE_SWITCH` - Track StyleManagingAgent mode changes
- `LEVERAGE_ADJUSTMENT` - Monitor leverage changes
- `SYSTEM_SHUTDOWN` - Graceful shutdown

## Event Publications
- `AGENT_TUNING` - Parameter updates to sub-agents
  ```json
  {
    "target_agent": "RiskCheckingAgent",
    "parameters": {
      "max_portfolio_drawdown": 0.05,
      "max_daily_loss": 0.015
    },
    "source": "manager_defensive_mode",
    "reasoning": "Critical risk alert triggered defensive mode",
    "confidence": 0.9
  }
  ```
- `AGENT_HEARTBEAT` - Manager status and system mode

## Management Loop (Every 5 Minutes)
```
1. Check agent health (heartbeat freshness)
2. Evaluate system mode based on recent performance
3. If tuning enabled and interval passed:
   Run tuning cycle for each agent
4. Publish manager heartbeat
```

## Daily Report Analysis
```
Receive DAILY_REPORT from TradeMasterAgent:
  - Extract win_rate, total_pnl, mode_performance
  - Extract optimization_suggestions
  - Log summary
  - Apply immediate tunings for high-confidence suggestions
  - Generate manager summary report
```

## Tuning Decision Process
```
For each optimization suggestion from TradeMasterAgent:
  1. Map parameter to target agent
  2. Check confidence >= min_confidence_for_tuning (0.70)
  3. Check tuning cooldown (6 hours)
  4. Apply tuning via AGENT_TUNING event
  5. Record in tuning history
  6. Log decision
```

## Agent Performance Tracking
Tracks per-agent metrics from heartbeats:
- Health status (running/stale)
- Agent-specific metrics (leverages, biases, confluences, etc.)
- Performance trends (improving/degrading/stable)

## Emergency Responses
### On CRITICAL Risk Alert
```
1. Set system_mode = "defensive"
2. Tune RiskCheckingAgent: max_drawdown=5%, daily_loss=1.5%
3. Tune PositionSizingAgent: max_risk_per_trade=1%
4. Log emergency action
```

### On HIGH Risk Alert (in normal mode)
```
1. Set system_mode = "cautious"
2. Tune RiskCheckingAgent: max_drawdown=8%, daily_loss=2%
3. Tune PositionSizingAgent: max_risk_per_trade=1.5%
```

### On Leverage Adjustment (liquidation_risk/critical_margin)
```
1. Escalate to RiskCheckingAgent via RISK_ALERT
2. Consider defensive mode if multiple symbols affected
```

## Manager Summary Report
Generated daily, saved to `reports/manager/manager_summary_YYYY-MM-DD.json`:
```json
{
  "date": "2024-01-15",
  "system_mode": "normal",
  "daily_pnl": 1247.50,
  "daily_win_rate": 0.667,
  "agent_health": {
    "LeverageAdjustmentAgent": 1.0,
    "BiasDeterminingAgent": 1.0,
    "MultiTimeframeConfluenceAgent": 1.0,
    "PositionSizingAgent": 1.0,
    "StyleManagingAgent": 1.0,
    "RiskCheckingAgent": 1.0,
    "TradeMasterAgent": 1.0
  },
  "recent_tunings": 3,
  "open_positions": 5
}
```

## State Persistence
Saves to `reports/manager/manager_state.json`:
- Current system mode
- Tuning history (last 100)
- Agent performance metrics
- Loaded on startup for continuity

## Integration Points
- **All agents**: Receives heartbeats, sends tunings
- **TradeMasterAgent**: Primary performance data source
- **RiskCheckingAgent**: Emergency coordination
- **StyleManagingAgent**: Mode change awareness
- **Human operators**: Manager summaries for oversight

## Tuning Parameters (from ManagerAgent - self-tuning)
- `tuning_enabled` - Enable/disable auto-tuning
- `tuning_interval_hours` - 1-24
- `min_confidence_for_tuning` - 0.5-0.9
- System mode thresholds (performance triggers)