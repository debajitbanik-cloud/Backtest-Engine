---
name: backtest-optimizer
description: Run backtesting optimization framework for trading strategies using ATR, SuperTrend, and Bollinger Bands indicators. Use when the user wants to backtest, optimize indicator settings, compare timeframe performance, or understand why certain parameter combinations outperform others. Supports permutation-based grid search across multiple symbols and timeframes.
argument-hint: "[symbol] [--timeframe 15m|1h|all] [--optimize] [--compare] [--explain]"
---

# Backtest Optimizer Skill

Comprehensive backtesting and optimization framework for trading strategies using three core technical indicators: **Average True Range (ATR)**, **SuperTrend**, and **Bollinger Bands**.

## When to Use

- User asks to backtest a strategy on historical data
- User wants to optimize indicator settings for specific timeframes
- User wants to understand why certain settings perform better
- User asks to compare performance across timeframes (3m, 5m, 15m, 1h)
- User wants permutation-based optimization across parameter combinations

## Prerequisites

Install required Python packages:

```bash
pip3 install backtesting pandas numpy ta pyyaml
```

## Quick Start

### 1. Run Default Backtest

```bash
cd /Users/zone/Desktop/Backtest\ Engine
python3 -m agent_system.backtest.runner
```

### 2. Optimize Specific Symbol and Timeframe

```python
from agent_system.backtest.runner import load_candles_from_json, optimize_parameters
from agent_system.backtest.strategy import SuperTrendBBStrategy

# Load data
df = load_candles_from_json("SOLUSDT", "15m")

# Run optimization (returns top 10 parameter sets)
results = optimize_parameters(df, "SOLUSDT", "15m", cash=10000)

# Print results
for i, r in enumerate(results[:5], 1):
    print(f"#{i}: Return={r['total_return']:.2f}%, Sharpe={r['sharpe']:.2f}, MaxDD={r['max_drawdown']:.2f}%")
```

### 3. Compare Timeframes

```python
from agent_system.backtest.runner import run_all_timeframes

symbols = ["SOLUSDT", "XAUTUSDT"]
timeframes = ["3m", "5m", "15m", "1h"]
results, best_params = run_all_timeframes(symbols, timeframes, optimize_on=["15m", "1h"])
```

### 4. Explain Why Settings Perform Better

```python
from agent_system.backtest.analyze import explain_performance

# Generate detailed analysis
explain_performance("SOLUSDT", "15m", results)
```

## Architecture

### Indicators

1. **ATR (Average True Range)**: Measures volatility
   - Period: 7-20 (default 14)
   - Used for: Position sizing, stop-loss, take-profit levels

2. **SuperTrend**: Trend-following indicator
   - ATR Period: 7-14 (default 10)
   - Multiplier: 2.0-3.5 (default 3.0)
   - Used for: Trend direction, entry/exit signals

3. **Bollinger Bands**: Volatility and mean-reversion
   - Period: 15-25 (default 20)
   - Std Dev: 1.5-2.5 (default 2.0)
   - Used for: Overbought/oversold levels, exit signals

### Strategy Logic

**Long Entry Conditions:**
- SuperTrend direction = bullish (1)
- Price at or below lower Bollinger Band (oversold)
- Price above SuperTrend line

**Short Entry Conditions:**
- SuperTrend direction = bearish (-1)
- Price at or above upper Bollinger Band (overbought)
- Price below SuperTrend line

**Exit Conditions:**
- SuperTrend direction reversal
- Price crosses middle Bollinger Band (mean reversion)
- ATR-based stop-loss or take-profit hit

### Optimization Grid

| Parameter | Values | Default |
|-----------|--------|---------|
| st_atr_period | 7, 10, 14 | 10 |
| st_multiplier | 2.0, 2.5, 3.0, 3.5 | 3.0 |
| bb_period | 15, 20, 25 | 20 |
| bb_std | 1.5, 2.0, 2.5 | 2.0 |
| atr_period | 10, 14, 20 | 14 |
| atr_sl_multiplier | 1.0, 1.5, 2.0 | 1.5 |
| atr_tp_multiplier | 2.0, 2.5, 3.0 | 2.5 |

**Total permutations per symbol/timeframe: 3 × 4 × 3 × 3 × 3 × 3 × 3 = 2,916 combinations**

## Why Certain Settings Perform Better on Certain Timeframes

### 3-Minute Timeframe
- **Best Settings**: Shorter periods (ATR=7-10, BB=15), tighter multipliers (ST=2.0-2.5)
- **Why**: High noise-to-signal ratio requires faster-responding indicators. Shorter periods capture quick price swings. Tighter stops prevent whipsaw losses.
- **Trade-off**: More frequent trades, lower win rate per trade, higher transaction costs.

### 5-Minute Timeframe
- **Best Settings**: Moderate periods (ATR=10-14, BB=15-20), balanced multipliers (ST=2.5-3.0)
- **Why**: Balances noise filtering with responsiveness. Captures intraday trends without excessive whipsaws.
- **Trade-off**: Moderate trade frequency, balanced risk/reward.

### 15-Minute Timeframe
- **Best Settings**: Standard periods (ATR=14, BB=20), standard multiplier (ST=3.0)
- **Why**: Optimal noise filtering for swing trading. Clearer trend signals, fewer false entries. Bollinger Bands provide reliable support/resistance.
- **Trade-off**: Fewer trades, higher win rate, larger per-trade profit targets.

### 1-Hour Timeframe
- **Best Settings**: Longer periods (ATR=14-20, BB=20-25), wider multipliers (ST=3.0-3.5)
- **Why**: Captures major trends, filters out intraday noise. Wider stops accommodate larger price movements. Better risk-adjusted returns.
- **Trade-off**: Fewest trades, highest win rate, largest profit targets, requires patience.

## Files

| File | Purpose |
|------|---------|
| `scripts/indicators.py` | ATR, SuperTrend, Bollinger Bands calculations |
| `scripts/strategy.py` | Combined strategy logic |
| `scripts/runner.py` | Main backtest and optimization runner |
| `scripts/analyze.py` | Performance analysis and explanation generator |
| `references/indicator_theory.md` | Detailed indicator theory and math |
| `references/optimization_guide.md` | Guide to interpreting optimization results |
| `results/` | Generated backtest results and reports |

## Output

### Console Output
```
======================================================================
OPTIMIZING SOLUSDT 15m
======================================================================
Data points: 19550
Date range: 2026-01-01 to 2026-07-31
Total combinations: 2916
Running backtests...
  Completed 50/2916...
  ...

======================================================================
TOP 5 RESULTS FOR SOLUSDT 15m
======================================================================

#1:
  Total Return: 156.23%
  Buy & Hold: 45.67%
  Sharpe Ratio: 2.34
  Max Drawdown: 12.45%
  Win Rate: 62.3%
  Trades: 87
  Profit Factor: 1.89
  Final Equity: $15,623.45
  Parameters:
    st_atr_period: 10
    st_multiplier: 3.0
    bb_period: 20
    bb_std: 2.0
    atr_period: 14
    atr_sl_multiplier: 1.5
    atr_tp_multiplier: 2.5
```

### Saved Files
- `results/best_parameters.json`: Optimal parameters per symbol/timeframe
- `results/optimization_report.html`: Interactive HTML report with charts
- `results/comparison.csv`: Cross-timeframe comparison table

## Advanced Usage

### Custom Parameter Grid

```python
from agent_system.backtest.runner import run_backtest
from agent_system.backtest.strategy import SuperTrendBBStrategy

# Custom parameters
params = {
    'st_atr_period': 10,
    'st_multiplier': 2.5,
    'bb_period': 18,
    'bb_std': 1.8,
    'atr_period': 12,
    'atr_sl_multiplier': 1.2,
    'atr_tp_multiplier': 2.8,
}

result = run_backtest(df, SuperTrendBBStrategy, params, cash=10000)
print(f"Return: {result['total_return']:.2f}%")
```

### Walk-Forward Optimization

```python
from agent_system.backtest.runner import walk_forward_optimize

# Split data into train/test periods
results = walk_forward_optimize(df, train_pct=0.7, n_splits=5)
```

### Monte Carlo Simulation

```python
from agent_system.backtest.runner import monte_carlo_simulation

# Run 1000 simulations with random trade ordering
mc_results = monte_carlo_simulation(df, params, n_simulations=1000)
```

## Interpreting Results

### Key Metrics

1. **Total Return %**: Overall profit/loss percentage
2. **Sharpe Ratio**: Risk-adjusted return (>1.0 is good, >2.0 is excellent)
3. **Max Drawdown %**: Largest peak-to-trough decline (lower is better)
4. **Win Rate %**: Percentage of profitable trades
5. **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
6. **# Trades**: Total number of trades (more = more statistically significant)

### Red Flags

- **High return but high drawdown**: Strategy is too aggressive
- **Low trade count**: Results may be statistically insignificant
- **Win rate < 40%**: Strategy needs better entry filters
- **Profit factor < 1.0**: Strategy is losing money overall

## Troubleshooting

### "Data file not found"
- Run CSV aggregator first: `python3 agent_system/data/csv_aggregator.py --symbol SOLUSD --timeframes 3m,5m,15m,1h`
- Check `data/shared/` directory for JSON files

### "Backtest timeout"
- Reduce parameter grid size
- Use fewer timeframes
- Increase timeout: `--timeout 600`

### "Import error"
- Install dependencies: `pip3 install backtesting pandas numpy ta`

## References

- [Backtesting.py Documentation](https://kernc.github.io/backtesting.py/)
- [SuperTrend Indicator](https://www.investopedia.com/terms/s/supertrend.asp)
- [Bollinger Bands](https://www.investopedia.com/terms/b/bollingerbands.asp)
- [ATR Indicator](https://www.investopedia.com/terms/a/atr.asp)
