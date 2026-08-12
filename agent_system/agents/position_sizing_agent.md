# Position Sizing Agent

## Purpose
Calculates optimal position sizes based on risk parameters, confluence signals, account state, and selected sizing methodology.

## Responsibilities
- Calculate position size using configured method
- Incorporate confluence strength for dynamic sizing
- Respect risk limits (per-trade, portfolio, correlation)
- Coordinate with LeverageAdjustmentAgent for margin-aware sizing
- Publish sizing decisions for trade execution

## Configuration
```yaml
sizing:
  default_method: "confluence_weighted"  # fixed_risk, kelly, vol_adjusted, confluence_weighted
  max_risk_per_trade: 0.02               # 2% of account per trade
  max_portfolio_risk: 0.10               # 10% total portfolio risk
  max_leverage: 20.0
  min_leverage: 1.0
  kelly_win_rate: 0.55                   # For Kelly calculation
  kelly_win_loss_ratio: 1.5              # Avg win / avg loss
  atr_multiplier: 2.0                    # For volatility-adjusted
  atr_period: 14
  confluence_boost: 1.5                  # Multiplier for strong confluence
  max_position_pct: 0.20                 # Max 20% in single position
  correlation_limit: 0.7                 # Max correlation between positions
```

## Sizing Methods

### 1. Fixed Risk (`fixed_risk`)
```
size = (account_equity * max_risk_per_trade) / stop_loss_distance
```
Simple, consistent risk per trade.

### 2. Kelly Criterion (`kelly`)
```
kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
size = base_size * kelly_fraction * 0.25  # 25% Kelly for safety
```
Requires 20+ trades history. Capped at 50% of base.

### 3. Volatility Adjusted (`vol_adjusted`)
```
vol_adjustment = min(1.0, (price * 0.02) / ATR)
size = base_size * vol_adjustment
```
Reduces size in high volatility, increases in low volatility.

### 4. Confluence Weighted (`confluence_weighted`) - DEFAULT
```
strong_bullish/bearish: size = base * confluence_boost * confluence_confidence
bullish/bearish:        size = base * confluence_confidence
neutral:                size = base * 0.5
```
Dynamically scales with signal quality.

## Constraints Applied (in order)
1. **Margin constraint**: `notional <= available_margin * leverage`
2. **Max position %**: `notional <= account_equity * max_position_pct`
3. **Portfolio risk limit**: Sum of all position risks <= `max_portfolio_risk`
4. **Correlation limit**: Max 3 positions in same direction (simplified)

## Event Subscriptions
- `CONFLUENCE_SIGNAL` - Confluence result for sizing boost
- `BIAS_SIGNAL` - Bias direction/confidence
- `LEVERAGE_ADJUSTMENT` - Current leverage per symbol
- `POSITION_OPEN` / `POSITION_CLOSE` / `POSITION_UPDATE` - Track portfolio
- `MARKET_TICK` - Current prices for notional calculation
- `AGENT_TUNING` - Parameter updates from ManagerAgent

## Event Publications
- `POSITION_SIZING` - Published when sizing calculated (on request)
  ```json
  {
    "symbol": "BTCUSDT",
    "side": "long",
    "size": 0.15,
    "notional_value": 6750.0,
    "risk_amount": 135.0,
    "risk_pct": 0.0135,
    "leverage": 10.0,
    "entry_price": 45000.0,
    "stop_loss": 44100.0,
    "take_profit": 45450.0,
    "method": "confluence_weighted",
    "confidence": 0.78,
    "reasoning": "Base risk: $200.00, SL distance: $900.00 | Confluence: bullish (0.78) | Capped by margin"
  }
  ```
- `AGENT_HEARTBEAT` - Account equity, open positions, current method

## Integration Points
- **MultiTimeframeConfluenceAgent**: Primary sizing driver
- **LeverageAdjustmentAgent**: Receives leverage for margin calc
- **RiskCheckingAgent**: Portfolio risk limits enforced
- **StyleManagingAgent**: Mode affects sizing method selection
- **ManagerAgent**: Tunes risk parameters based on performance

## Public Interface
```python
# Other agents can request sizing directly
result = await position_sizing_agent.request_sizing(
    symbol="BTCUSDT",
    side="long",
    entry=45000.0,
    sl=44100.0,
    tp=45450.0
)
```

## Tuning Parameters (from ManagerAgent)
- `default_method` - Switch sizing methodology
- `max_risk_per_trade` - 0.01-0.05
- `max_portfolio_risk` - 0.05-0.20
- `confluence_boost` - 1.0-2.0
- `max_position_pct` - 0.10-0.30
- `kelly_win_rate`, `kelly_win_loss_ratio` - For Kelly method