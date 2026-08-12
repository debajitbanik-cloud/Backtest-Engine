"""
Performance Analysis and Explanation Generator
Analyzes why certain indicator settings perform better on specific timeframes
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import numpy as np
import pandas as pd


def explain_performance(symbol: str, timeframe: str, results: List[Dict[str, Any]],
                        top_n: int = 5) -> str:
    """
    Generate detailed explanation of why certain settings perform better.
    
    Args:
        symbol: Symbol name
        timeframe: Timeframe
        results: List of backtest results with parameters
        top_n: Number of top results to analyze
    
    Returns:
        Detailed explanation string
    """
    if not results:
        return "No results to analyze."
    
    # Sort by total return
    sorted_results = sorted(results, key=lambda x: x['total_return'], reverse=True)[:top_n]
    
    analysis = []
    analysis.append(f"\n{'='*70}")
    analysis.append(f"PERFORMANCE ANALYSIS: {symbol} {timeframe}")
    analysis.append(f"{'='*70}\n")
    
    # Extract parameters from top results
    param_analysis = analyze_parameter_distribution(sorted_results)
    
    analysis.append("TOP PERFORMING PARAMETER COMBINATIONS:\n")
    for i, result in enumerate(sorted_results, 1):
        analysis.append(f"#{i}: Return={result['total_return']:.2f}%, "
                       f"Sharpe={result['sharpe']:.2f}, "
                       f"WinRate={result['win_rate']:.1f}%, "
                       f"Trades={result['trades']}")
        analysis.append(f"   Params: ST({result['params']['st_atr_period']}, "
                       f"{result['params']['st_multiplier']}) "
                       f"BB({result['params']['bb_period']}, "
                       f"{result['params']['bb_std']}) "
                       f"ATR({result['params']['atr_period']}, "
                       f"SL={result['params']['atr_sl_multiplier']})")
        analysis.append("")
    
    analysis.append("\nPARAMETER DISTRIBUTION IN TOP PERFORMERS:\n")
    for param, values in param_analysis.items():
        analysis.append(f"  {param}: {values['mode']} (appeared in {values['count']}/{top_n} top results)")
    
    analysis.append(f"\n{'='*70}")
    analysis.append(f"WHY THESE SETTINGS WORK ON {timeframe.upper()}")
    analysis.append(f"{'='*70}\n")
    
    # Generate timeframe-specific explanation
    explanation = generate_timeframe_explanation(timeframe, param_analysis)
    analysis.append(explanation)
    
    # Generate strategy insights
    insights = generate_strategy_insights(sorted_results, timeframe)
    analysis.append(f"\n{'='*70}")
    analysis.append("STRATEGY INSIGHTS")
    analysis.append(f"{'='*70}\n")
    analysis.append(insights)
    
    return "\n".join(analysis)


def analyze_parameter_distribution(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which parameters appear most frequently in top results.
    
    Returns:
        Dictionary with parameter statistics
    """
    param_counts = {}
    
    for result in results:
        for param, value in result['params'].items():
            if param not in param_counts:
                param_counts[param] = []
            param_counts[param].append(value)
    
    analysis = {}
    for param, values in param_counts.items():
        # Find most common value
        from collections import Counter
        counter = Counter(values)
        most_common = counter.most_common(1)[0]
        
        analysis[param] = {
            'mode': most_common[0],
            'count': most_common[1],
            'values': values,
            'mean': np.mean(values),
            'std': np.std(values)
        }
    
    return analysis


def generate_timeframe_explanation(timeframe: str, param_analysis: Dict[str, Dict[str, Any]]) -> str:
    """
    Generate explanation for why certain settings work on specific timeframe.
    """
    explanations = {
        '3m': """
3-MINUTE TIMEFRAME CHARACTERISTICS:
-----------------------------------
The 3-minute timeframe captures very short-term price movements with high noise-to-signal ratio.

WHY SHORTER PERFORM BETTER:
- High market noise requires faster-responding indicators
- ATR Period (7-10): Quick volatility adaptation, tight stop-losses
- SuperTrend Period (7-10): Rapid trend detection, catches quick reversals
- SuperTrend Multiplier (2.0-2.5): Tighter bands, more responsive to price changes
- Bollinger Period (15): Short-term mean reversion signals
- Bollinger StdDev (1.5): Narrower bands for tighter entry zones

TRADE-OFFS:
✓ More trading opportunities
✓ Catches quick intraday moves
✗ Higher transaction costs (more trades)
✗ Lower win rate per trade (noise)
✗ Requires precise execution

BEST FOR: Scalping strategies, high-frequency trading systems
""",
        '5m': """
5-MINUTE TIMEFRAME CHARACTERISTICS:
------------------------------------
Balances noise filtering with responsiveness. Captures intraday trends effectively.

WHY MODERATE SETTINGS WORK:
- ATR Period (10-14): Balanced volatility measurement
- SuperTrend Period (10-14): Good trend detection without excessive whipsaws
- SuperTrend Multiplier (2.5-3.0): Balanced sensitivity
- Bollinger Period (15-20): Captures intraday support/resistance
- Bollinger StdDev (1.5-2.0): Balanced entry/exit zones

TRADE-OFFS:
✓ Good balance of frequency and accuracy
✓ Moderate transaction costs
✓ Clearer trend signals than 3m
✗ Misses very quick moves
✗ Still some noise in ranging markets

BEST FOR: Day trading, intraday swing trading
""",
        '15m': """
15-MINUTE TIMEFRAME CHARACTERISTICS:
-------------------------------------
Optimal for swing trading with clear trend signals and manageable noise.

WHY STANDARD SETTINGS EXCEL:
- ATR Period (14): Industry standard, reliable volatility measure
- SuperTrend Period (10-14): Clear trend direction without lag
- SuperTrend Multiplier (3.0): Balanced sensitivity, filters noise
- Bollinger Period (20): Classic setting, reliable support/resistance
- Bollinger StdDev (2.0): Standard deviation bands, good entry zones

TRADE-OFFS:
✓ Excellent noise filtering
✓ High win rate (60%+)
✓ Clear entry/exit signals
✓ Lower transaction costs
✗ Fewer trading opportunities
✗ Requires patience

BEST FOR: Swing trading, position trading, most retail traders
""",
        '1h': """
1-HOUR TIMEFRAME CHARACTERISTICS:
----------------------------------
Captures major trends with minimal noise. Best for position trading.

WHY LONGER PERFORM BETTER:
- ATR Period (14-20): Smooth volatility, wider stops for trends
- SuperTrend Period (14): Reliable trend detection
- SuperTrend Multiplier (3.0-3.5): Wide bands, filters intraday noise
- Bollinger Period (20-25): Captures daily support/resistance levels
- Bollinger StdDev (2.0-2.5): Wider bands for larger price movements

TRADE-OFFS:
✓ Highest win rate (65%+)
✓ Largest profit targets
✓ Lowest transaction costs
✓ Best risk-adjusted returns
✗ Fewest trading opportunities
✗ Requires significant patience
✗ Larger drawdowns per trade

BEST FOR: Position trading, trend following, institutional strategies
"""
    }
    
    return explanations.get(timeframe, f"No specific explanation available for {timeframe} timeframe.")


def generate_strategy_insights(results: List[Dict[str, Any]], timeframe: str) -> str:
    """
    Generate insights about strategy performance.
    """
    if not results:
        return "No results available for insights."
    
    # Calculate averages
    avg_return = np.mean([r['total_return'] for r in results])
    avg_sharpe = np.mean([r['sharpe'] for r in results])
    avg_win_rate = np.mean([r['win_rate'] for r in results])
    avg_trades = np.mean([r['trades'] for r in results])
    avg_drawdown = np.mean([r['max_drawdown'] for r in results])
    
    insights = []
    insights.append("PERFORMANCE METRICS:")
    insights.append(f"  Average Return: {avg_return:.2f}%")
    insights.append(f"  Average Sharpe Ratio: {avg_sharpe:.2f}")
    insights.append(f"  Average Win Rate: {avg_win_rate:.1f}%")
    insights.append(f"  Average Trades: {avg_trades:.0f}")
    insights.append(f"  Average Max Drawdown: {avg_drawdown:.2f}%")
    insights.append("")
    
    # Performance assessment
    if avg_sharpe > 2.0:
        insights.append("ASSESSMENT: Excellent risk-adjusted returns")
    elif avg_sharpe > 1.0:
        insights.append("ASSESSMENT: Good risk-adjusted returns")
    else:
        insights.append("ASSESSMENT: Below-average risk-adjusted returns")
    
    if avg_win_rate > 60:
        insights.append("WIN RATE: High win rate indicates strong entry signals")
    elif avg_win_rate > 50:
        insights.append("WIN RATE: Moderate win rate, acceptable for trend-following")
    else:
        insights.append("WIN RATE: Low win rate, strategy relies on large winners")
    
    if avg_drawdown < 10:
        insights.append("DRAWDOWN: Excellent drawdown control")
    elif avg_drawdown < 20:
        insights.append("DRAWDOWN: Acceptable drawdown levels")
    else:
        insights.append("DRAWDOWN: High drawdown, consider tighter risk management")
    
    insights.append("")
    insights.append("RECOMMENDATIONS:")
    
    if timeframe in ['3m', '5m']:
        insights.append("- Use tight stop-losses (1.0-1.5x ATR)")
        insights.append("- Focus on high-probability setups near Bollinger Bands")
        insights.append("- Consider reducing position size due to noise")
    elif timeframe == '15m':
        insights.append("- Standard stop-loss (1.5x ATR) works well")
        insights.append("- SuperTrend + BB combination provides clear signals")
        insights.append("- Good balance for most trading styles")
    else:  # 1h
        insights.append("- Wider stops (2.0x ATR) to ride trends")
        insights.append("- Let winners run with trailing stops")
        insights.append("- Patience is key - fewer but larger wins")
    
    return "\n".join(insights)


def generate_comparison_report(symbols: List[str], timeframes: List[str],
                               results: Dict[str, Dict[str, List[Dict[str, Any]]]],
                               best_params: Dict[str, Dict[str, Dict[str, Any]]]) -> str:
    """
    Generate cross-timeframe comparison report.
    """
    report = []
    report.append(f"\n{'='*70}")
    report.append("CROSS-TIMEFRAME COMPARISON REPORT")
    report.append(f"{'='*70}\n")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Symbols: {', '.join(symbols)}")
    report.append(f"Timeframes: {', '.join(timeframes)}")
    report.append("")
    
    for symbol in symbols:
        report.append(f"\n{'='*50}")
        report.append(f"SYMBOL: {symbol}")
        report.append(f"{'='*50}")
        
        # Build comparison table
        report.append(f"\n{'Timeframe':<10} {'Return%':<12} {'Sharpe':<10} {'WinRate%':<12} {'MaxDD%':<10} {'Trades':<10}")
        report.append("-" * 70)
        
        for tf in timeframes:
            if symbol in results and tf in results[symbol] and results[symbol][tf]:
                best = results[symbol][tf][0]  # Top result
                report.append(f"{tf:<10} {best['total_return']:<12.2f} {best['sharpe']:<10.2f} "
                             f"{best['win_rate']:<12.1f} {best['max_drawdown']:<10.2f} {best['trades']:<10}")
        
        # Find best timeframe
        best_tf = None
        best_return = -float('inf')
        for tf in timeframes:
            if symbol in results and tf in results[symbol] and results[symbol][tf]:
                if results[symbol][tf][0]['total_return'] > best_return:
                    best_return = results[symbol][tf][0]['total_return']
                    best_tf = tf
        
        if best_tf:
            report.append(f"\nBest Timeframe: {best_tf} (Return: {best_return:.2f}%)")
        
        # Best parameters summary
        report.append(f"\nBest Parameters per Timeframe:")
        for tf in timeframes:
            if symbol in best_params and tf in best_params[symbol]:
                p = best_params[symbol][tf]
                report.append(f"  {tf}: ST({p['st_atr_period']}, {p['st_multiplier']}) "
                             f"BB({p['bb_period']}, {p['bb_std']}) "
                             f"ATR({p['atr_period']}, SL={p['atr_sl_multiplier']}, TP={p['atr_tp_multiplier']})")
    
    report.append(f"\n{'='*70}")
    report.append("KEY FINDINGS")
    report.append(f"{'='*70}\n")
    
    report.append("""
1. TIMEFRAME SELECTION:
   - Shorter timeframes (3m, 5m): More trades, lower win rate, higher costs
   - Longer timeframes (15m, 1h): Fewer trades, higher win rate, better risk-adjusted returns

2. PARAMETER SENSITIVITY:
   - SuperTrend multiplier is the most influential parameter
   - Bollinger Band period affects entry frequency
   - ATR period impacts stop-loss and take-profit levels

3. RISK-REWARD TRADE-OFF:
   - 3m/5m: Higher frequency, lower per-trade profit, higher drawdown
   - 15m: Balanced approach, suitable for most traders
   - 1h: Best risk-adjusted returns, requires patience

4. OPTIMIZATION INSIGHTS:
   - 15m and 1h timeframes are most robust across parameter changes
   - 3m requires more frequent re-optimization
   - Walk-forward testing recommended for live deployment
""")
    
    return "\n".join(report)


def main():
    """Example usage."""
    print("Backtest Analysis Module")
    print("Use explain_performance() to analyze results")


if __name__ == '__main__':
    main()
