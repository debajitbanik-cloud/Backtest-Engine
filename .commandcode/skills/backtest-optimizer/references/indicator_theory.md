# Indicator Theory Reference

## Average True Range (ATR)

### Definition
ATR measures market volatility by decomposing the entire range of an asset price for that period.

### Formula
```
True Range (TR) = max(High - Low, |High - Previous Close|, |Low - Previous Close|)
ATR = Average of TR over n periods
```

### Interpretation
- **High ATR**: High volatility, wider stop-losses needed
- **Low ATR**: Low volatility, tighter stops possible
- **Rising ATR**: Increasing volatility, potential trend continuation
- **Falling ATR**: Decreasing volatility, potential consolidation

### Trading Applications
1. **Position Sizing**: Risk = (Account × Risk%) / (ATR × Multiplier)
2. **Stop-Loss Placement**: Stop = Entry ± (ATR × Multiplier)
3. **Take-Profit Targets**: Target = Entry ± (ATR × Multiplier)
4. **Volatility Filtering**: Only trade when ATR > threshold

### Optimal Settings by Timeframe
| Timeframe | Period | Use Case |
|-----------|--------|----------|
| 3m | 7-10 | Quick volatility adaptation |
| 5m | 10-12 | Balanced measurement |
| 15m | 14 | Standard, reliable |
| 1h | 14-20 | Smooth, trend-focused |

---

## SuperTrend Indicator

### Definition
SuperTrend is a trend-following indicator based on ATR that provides clear buy/sell signals.

### Formula
```
Upper Band = (High + Low) / 2 + (Multiplier × ATR)
Lower Band = (High + Low) / 2 - (Multiplier × ATR)

If Close > Previous Upper Band → Trend is Up
If Close < Previous Lower Band → Trend is Down
```

### Interpretation
- **Price above SuperTrend line**: Bullish trend (buy)
- **Price below SuperTrend line**: Bearish trend (sell)
- **Direction change**: Trend reversal signal

### Trading Applications
1. **Trend Identification**: Primary trend direction
2. **Entry Signals**: Buy when price crosses above, sell when crosses below
3. **Trailing Stop**: Use SuperTrend line as dynamic stop-loss
4. **Filter**: Only trade in direction of SuperTrend

### Optimal Settings by Timeframe
| Timeframe | ATR Period | Multiplier | Characteristics |
|-----------|------------|------------|-----------------|
| 3m | 7-10 | 2.0-2.5 | Fast, responsive, more signals |
| 5m | 10-12 | 2.5-3.0 | Balanced sensitivity |
| 15m | 10-14 | 3.0 | Standard, filters noise |
| 1h | 14 | 3.0-3.5 | Smooth, fewer false signals |

### Multiplier Impact
- **Lower (2.0)**: More signals, more whipsaws, tighter stops
- **Standard (3.0)**: Balanced, fewer false signals
- **Higher (3.5+)**: Fewer signals, larger trends, wider stops

---

## Bollinger Bands

### Definition
Bollinger Bands measure volatility and identify overbought/oversold conditions using standard deviation.

### Formula
```
Middle Band = Simple Moving Average (n periods)
Upper Band = Middle Band + (Standard Deviation × Multiplier)
Lower Band = Middle Band - (Standard Deviation × Multiplier)
```

### Interpretation
- **Price at Upper Band**: Potentially overbought
- **Price at Lower Band**: Potentially oversold
- **Band Width**: Measures volatility (wide = high vol, narrow = low vol)
- **Squeeze**: Narrow bands precede large moves

### Trading Applications
1. **Mean Reversion**: Buy at lower band, sell at upper band
2. **Breakout Trading**: Trade when price breaks out of squeeze
3. **Trend Confirmation**: Price riding bands indicates strong trend
4. **Support/Resistance**: Bands act as dynamic levels

### Optimal Settings by Timeframe
| Timeframe | Period | Std Dev | Use Case |
|-----------|--------|---------|----------|
| 3m | 15 | 1.5 | Quick mean reversion |
| 5m | 15-20 | 1.5-2.0 | Balanced entries |
| 15m | 20 | 2.0 | Standard, reliable |
| 1h | 20-25 | 2.0-2.5 | Major support/resistance |

### %B Indicator
```
%B = (Price - Lower Band) / (Upper Band - Lower Band)
```
- %B > 1: Price above upper band
- %B < 0: Price below lower band
- %B = 0.5: Price at middle band

### Bandwidth
```
Bandwidth = (Upper Band - Lower Band) / Middle Band
```
- High bandwidth: High volatility
- Low bandwidth: Squeeze, potential breakout

---

## Combined Strategy Logic

### Entry Conditions (Long)
1. SuperTrend direction = Bullish (1)
2. Price at or below lower Bollinger Band (oversold)
3. Price above SuperTrend line (trend confirmation)

**Rationale**: Enter when trend is up but price has pulled back to oversold level.

### Entry Conditions (Short)
1. SuperTrend direction = Bearish (-1)
2. Price at or above upper Bollinger Band (overbought)
3. Price below SuperTrend line (trend confirmation)

**Rationale**: Enter when trend is down but price has rallied to overbought level.

### Exit Conditions
1. **SuperTrend Reversal**: Trend changes direction
2. **Mean Reversion**: Price crosses middle Bollinger Band
3. **ATR Stop-Loss**: Price moves against position by ATR × multiplier
4. **ATR Take-Profit**: Price moves in favor by ATR × multiplier

### Position Sizing Formula
```
Position Size = (Account × Risk%) / (ATR × Stop-Loss Multiplier)
```
Example: $10,000 account, 2% risk, ATR = $50, SL multiplier = 1.5
Position Size = ($10,000 × 0.02) / ($50 × 1.5) = $200 / $75 = 2.67 units

---

## Parameter Optimization Theory

### Why Certain Settings Work Better

1. **Market Microstructure**
   - Shorter timeframes have more noise
   - Faster indicators needed to capture moves
   - Tighter stops to limit whipsaw losses

2. **Trend Persistence**
   - Longer timeframes show stronger trends
   - Wider indicators filter noise effectively
   - Larger profit targets achievable

3. **Volatility Regimes**
   - High volatility: Wider bands, larger multipliers
   - Low volatility: Tighter bands, smaller multipliers
   - ATR adapts automatically

4. **Risk-Adjusted Returns**
   - Sharpe ratio balances return and risk
   - Lower drawdown preferred over higher returns
   - Consistency more important than home runs

### Optimization Best Practices

1. **Walk-Forward Testing**
   - Train on historical, test on out-of-sample
   - Prevents overfitting
   - More realistic performance estimates

2. **Monte Carlo Simulation**
   - Randomize trade order
   - Assess worst-case scenarios
   - Validate strategy robustness

3. **Parameter Stability**
   - Check performance across nearby parameters
   - Avoid "cliff edges" in parameter space
   - Robust settings work across slight variations

4. **Transaction Costs**
   - Include realistic commission rates
   - Account for slippage
   - Shorter timeframes need tighter spreads
