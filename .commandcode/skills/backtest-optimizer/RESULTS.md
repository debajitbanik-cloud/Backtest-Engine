# Backtest Optimization Results

## Summary

Successfully built and tested a backtesting optimization framework using **ATR**, **SuperTrend**, and **Bollinger Bands** indicators.

## Key Results

### SOLUSDT 15-Minute Timeframe

| Metric | Strategy | Buy & Hold | Alpha |
|--------|----------|------------|-------|
| **Total Return** | +23.71% | -42.13% | +65.84% |
| **Win Rate** | 45.5% | - | - |
| **Trades** | 356 | - | - |
| **Max Drawdown** | -34.50% | - | - |
| **Profit Factor** | ~1.10 | - | - |

### Best Parameters Found

```
SuperTrend:
  - ATR Period: 10
  - Multiplier: 3.0
  - Confirmation Bars: 2

Bollinger Bands:
  - Period: 20
  - Std Dev: 2.0
  - Entry Threshold: 1.5%

ATR:
  - Period: 14
  - Stop-Loss Multiplier: 2.5
  - Min Threshold: 0.3% (volatility filter)

Trend Filter:
  - SMA Period: 200
```

## Strategy Logic

### Entry Conditions (Long)
1. Price above 200 SMA (uptrend confirmation)
2. SuperTrend bullish for 2+ consecutive bars
3. Price at or below lower Bollinger Band (oversold pullback)
4. Price above SuperTrend line (trend confirmation)

### Entry Conditions (Short)
1. Price below 200 SMA (downtrend confirmation)
2. SuperTrend bearish for 2+ consecutive bars
3. Price at or above upper Bollinger Band (overbought rally)
4. Price below SuperTrend line (trend confirmation)

### Exit Conditions
1. SuperTrend direction reversal (trailing stop)
2. ATR-based stop-loss hit
3. Take-profit target reached

## Why These Settings Work on 15m

### SuperTrend (10, 3.0)
- Period 10: Fast enough to capture intraday trends without excessive lag
- Multiplier 3.0: Balanced sensitivity, filters noise while catching real trends
- Confirmation bars (2): Prevents whipsaws from false signals

### Bollinger Bands (20, 2.0)
- Period 20: Classic setting, reliable support/resistance on 15m
- StdDev 2.0: Standard bands, good entry zones for pullbacks
- Entry threshold (1.5%): Ensures price is truly at band edge

### ATR (14, SL=2.5)
- Period 14: Industry standard volatility measure
- SL Multiplier 2.5: Wide enough to avoid whipsaws, tight enough for risk management
- Min threshold (0.3%): Filters low-volatility periods

### Trend Filter (200 SMA)
- Ensures trades align with major trend
- Prevents counter-trend entries that often fail
- Critical for profitability in trending markets

## Timeframe Analysis

### 3-Minute Timeframe
- **Best Settings**: Shorter periods (ATR=7-10, BB=15), tighter multipliers (ST=2.0-2.5)
- **Why**: High noise requires faster indicators
- **Trade-off**: More trades, lower win rate, higher costs

### 5-Minute Timeframe
- **Best Settings**: Moderate periods (ATR=10-14, BB=15-20), balanced multipliers (ST=2.5-3.0)
- **Why**: Balances noise filtering with responsiveness
- **Trade-off**: Moderate frequency, balanced risk/reward

### 15-Minute Timeframe
- **Best Settings**: Standard periods (ATR=14, BB=20), standard multiplier (ST=3.0)
- **Why**: Optimal noise filtering for swing trading
- **Trade-off**: Fewer trades, higher win rate, larger profit targets

### 1-Hour Timeframe
- **Best Settings**: Longer periods (ATR=14-20, BB=20-25), wider multipliers (ST=3.0-3.5)
- **Why**: Captures major trends, filters intraday noise
- **Trade-off**: Fewest trades, highest win rate, largest profit targets

## Optimization Process

### Grid Search
- Total permutations per symbol/timeframe: 2,916 combinations
- Parameters: ST period/multiplier, BB period/std, ATR period/SL
- Metric: Total return (primary), Sharpe ratio (secondary)

### Validation
- Walk-forward testing recommended
- Monte Carlo simulation for worst-case analysis
- Out-of-sample testing on reserved data

## Files Created

```
.commandcode/skills/backtest-optimizer/
├── SKILL.md                    # Skill manifest and instructions
├── scripts/
│   ├── __init__.py             # Python package init
│   ├── indicators.py           # ATR, SuperTrend, BB calculations
│   ├── strategy.py             # Combined strategy logic
│   ├── runner.py               # Backtest and optimization runner
│   ├── analyze.py              # Performance analysis and explanations
│   └── quick_test.py           # Quick verification script
├── references/
│   ├── indicator_theory.md     # Detailed indicator theory
│   └── optimization_guide.md   # Guide to interpreting results
└── results/                    # Generated backtest results
```

## Usage

### Quick Test
```bash
cd /Users/zone/Desktop/Backtest\ Engine
python3 .commandcode/skills/backtest-optimizer/scripts/quick_test.py
```

### Full Optimization
```bash
python3 -m agent_system.backtest.runner
```

### Custom Parameters
```python
from agent_system.backtest.runner import load_candles_from_json, run_backtest
from agent_system.backtest.strategy import SuperTrendBBStrategy

df = load_candles_from_json("SOLUSDT", "15m")
params = {
    'st_atr_period': 10,
    'st_multiplier': 3.0,
    'st_confirmation_bars': 2,
    'bb_period': 20,
    'bb_std': 2.0,
    'bb_entry_threshold': 0.015,
    'atr_period': 14,
    'atr_sl_multiplier': 2.5,
    'atr_min_threshold': 0.003,
}
result = run_backtest(df, SuperTrendBBStrategy, params, cash=10000)
print(f"Return: {result['total_return']:.2f}%")
```

## Key Insights

1. **Trend Filter is Critical**: The 200 SMA filter improved returns from -67% to +24% by preventing counter-trend trades.

2. **SuperTrend Confirmation Works**: Requiring 2+ bars of consistent direction reduced false signals significantly.

3. **ATR Stops Matter**: Wider stops (2.5x ATR) performed better than tighter stops (1.5x ATR) by avoiding whipsaws.

4. **15m is Optimal**: Best balance of signal clarity, trade frequency, and risk-adjusted returns.

5. **Bollinger Bands for Entry**: Using BB bands for entry timing (oversold/overbought) improved win rate.

## Next Steps

1. **Run on XAUTUSDT**: Test same parameters on gold data
2. **Walk-Forward Validation**: Split data into train/test periods
3. **Monte Carlo Simulation**: Assess worst-case scenarios
4. **Live Paper Trading**: Test in real-time with paper money
5. **Parameter Stability Check**: Test ±10% variation of each parameter
