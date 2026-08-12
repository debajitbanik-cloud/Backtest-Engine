"""
Backtest Runner - Runs backtests on all timeframes and optimizes indicator settings
"""
from __future__ import annotations
import sys
import json
import itertools
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
from backtesting import Backtest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_system.backtest.indicators import calculate_all_indicators
from agent_system.backtest.strategy import SuperTrendBBStrategy


def load_candles_from_json(symbol: str, timeframe: str, data_dir: str = None) -> pd.DataFrame:
    """Load aggregated candle data from JSON files."""
    if data_dir is None:
        data_dir = str(Path(__file__).parent.parent.parent / "data" / "shared")
    
    filepath = Path(data_dir) / f"{symbol}_{timeframe}.json"
    
    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    
    # Convert timestamp to datetime index
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Rename columns to match backtesting.py format
    df = df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    })
    
    # Ensure numeric types
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna()
    
    return df


def run_backtest(df: pd.DataFrame, strategy_class, params: Dict[str, Any],
                 cash: float = 10000, commission: float = 0.0006,
                 verbose: bool = False) -> Dict[str, Any]:
    """
    Run a single backtest with given parameters.
    
    Args:
        df: OHLCV DataFrame
        strategy_class: Strategy class to use
        params: Strategy parameters
        cash: Starting capital
        commission: Commission rate (0.06% for crypto)
        verbose: Print detailed output
    
    Returns:
        Dictionary with backtest results
    """
    bt = Backtest(df, strategy_class, cash=cash, commission=commission)
    results = bt.run(**params)
    
    return {
        'params': params,
        'total_return': results['Return [%]'],
        'buy_hold_return': results['Buy & Hold Return [%]'],
        'sharpe': results.get('Sharpe Seq', 0),
        'max_drawdown': results['Max. Drawdown [%]'],
        'win_rate': results['Win Rate [%]'],
        'trades': results['# Trades'],
        'profit_factor': results.get('Profit Factor', 0),
        'avg_trade': results['Avg. Trade [%]'],
        'equity_final': results['Equity Final [$]'],
        'duration': results['Duration'],
    }


def optimize_parameters(df: pd.DataFrame, symbol: str, timeframe: str,
                        cash: float = 10000, top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Optimize strategy parameters using grid search.
    
    Args:
        df: OHLCV DataFrame
        symbol: Symbol name (for logging)
        timeframe: Timeframe (for logging)
        cash: Starting capital
        top_n: Number of top results to return
    
    Returns:
        List of top N parameter sets with results
    """
    print(f"\n{'='*70}")
    print(f"OPTIMIZING {symbol} {timeframe}")
    print(f"{'='*70}")
    print(f"Data points: {len(df)}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    
    # Parameter grid for optimization
    param_grid = {
        'st_atr_period': [7, 10, 14],
        'st_multiplier': [2.0, 2.5, 3.0, 3.5],
        'bb_period': [15, 20, 25],
        'bb_std': [1.5, 2.0, 2.5],
        'atr_period': [10, 14, 20],
        'atr_sl_multiplier': [1.0, 1.5, 2.0],
        'atr_tp_multiplier': [2.0, 2.5, 3.0],
    }
    
    # Generate all combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    
    print(f"Total combinations: {len(combinations)}")
    print(f"Running backtests...")
    
    results = []
    
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        
        try:
            result = run_backtest(df, SuperTrendBBStrategy, params, cash=cash, verbose=False)
            results.append(result)
            
            if (i + 1) % 50 == 0:
                print(f"  Completed {i+1}/{len(combinations)}...")
        except Exception as e:
            # Skip invalid parameter combinations
            continue
    
    # Sort by total return (could also use Sharpe ratio)
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    # Return top N results
    return results[:top_n]


def print_results(results: List[Dict[str, Any]], symbol: str, timeframe: str, top_n: int = 5):
    """Print formatted optimization results."""
    print(f"\n{'='*70}")
    print(f"TOP {top_n} RESULTS FOR {symbol} {timeframe}")
    print(f"{'='*70}\n")
    
    for i, result in enumerate(results[:top_n], 1):
        print(f"#{i}:")
        print(f"  Total Return: {result['total_return']:.2f}%")
        print(f"  Buy & Hold: {result['buy_hold_return']:.2f}%")
        print(f"  Sharpe Ratio: {result['sharpe']:.2f}")
        print(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
        print(f"  Win Rate: {result['win_rate']:.1f}%")
        print(f"  Trades: {result['trades']}")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        print(f"  Final Equity: ${result['equity_final']:.2f}")
        print(f"  Parameters:")
        for k, v in result['params'].items():
            print(f"    {k}: {v}")
        print()


def run_all_timeframes(symbols: List[str], timeframes: List[str],
                       optimize_on: List[str] = None, cash: float = 10000):
    """
    Run backtests on all symbol/timeframe combinations.
    
    Args:
        symbols: List of symbols to test
        timeframes: List of timeframes to test
        optimize_on: List of timeframes to run optimization on (default: all)
        cash: Starting capital
    """
    if optimize_on is None:
        optimize_on = timeframes
    
    all_results = {}
    best_params = {}
    
    for symbol in symbols:
        all_results[symbol] = {}
        best_params[symbol] = {}
        
        for timeframe in timeframes:
            try:
                df = load_candles_from_json(symbol, timeframe)
                
                if timeframe in optimize_on:
                    # Run full optimization
                    results = optimize_parameters(df, symbol, timeframe, cash=cash)
                    all_results[symbol][timeframe] = results
                    
                    if results:
                        best_params[symbol][timeframe] = results[0]['params']
                        print_results(results, symbol, timeframe, top_n=3)
                else:
                    # Run with default parameters only
                    default_params = {
                        'st_atr_period': 10,
                        'st_multiplier': 3.0,
                        'bb_period': 20,
                        'bb_std': 2.0,
                        'atr_period': 14,
                        'atr_sl_multiplier': 1.5,
                        'atr_tp_multiplier': 2.5,
                    }
                    result = run_backtest(df, SuperTrendBBStrategy, default_params, cash=cash)
                    all_results[symbol][timeframe] = [result]
                    
                    print(f"\n{symbol} {timeframe} (default params):")
                    print(f"  Return: {result['total_return']:.2f}% | Buy&Hold: {result['buy_hold_return']:.2f}%")
                    print(f"  Sharpe: {result['sharpe']:.2f} | Max DD: {result['max_drawdown']:.2f}%")
                    print(f"  Win Rate: {result['win_rate']:.1f}% | Trades: {result['trades']}")
            
            except FileNotFoundError as e:
                print(f"\nSkipping {symbol} {timeframe}: {e}")
            except Exception as e:
                print(f"\nError on {symbol} {timeframe}: {e}")
    
    return all_results, best_params


def main():
    """Main entry point for backtest runner."""
    symbols = ['SOLUSDT', 'XAUTUSDT']
    timeframes = ['3m', '5m', '15m', '1h']
    optimize_on = ['15m', '1h']  # Focus optimization on these
    cash = 10000
    
    print("="*70)
    print("BACKTEST ENGINE - ATR + SuperTrend + Bollinger Bands Strategy")
    print("="*70)
    print(f"\nSymbols: {', '.join(symbols)}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Optimizing on: {', '.join(optimize_on)}")
    print(f"Starting Capital: ${cash:,.2f}")
    
    all_results, best_params = run_all_timeframes(symbols, timeframes, 
                                                    optimize_on=optimize_on, 
                                                    cash=cash)
    
    # Save results
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)
    
    # Save best parameters
    best_params_file = output_dir / "best_parameters.json"
    with open(best_params_file, 'w') as f:
        json.dump(best_params, f, indent=2, default=str)
    
    print(f"\n{'='*70}")
    print(f"OPTIMIZATION COMPLETE")
    print(f"{'='*70}")
    print(f"\nBest parameters saved to: {best_params_file}")
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"SUMMARY OF BEST PARAMETERS")
    print(f"{'='*70}\n")
    
    for symbol in best_params:
        print(f"\n{symbol}:")
        for tf in best_params[symbol]:
            params = best_params[symbol][tf]
            print(f"  {tf}: ST({params['st_atr_period']}, {params['st_multiplier']}) "
                  f"BB({params['bb_period']}, {params['bb_std']}) "
                  f"ATR({params['atr_period']}, SL={params['atr_sl_multiplier']}, TP={params['atr_tp_multiplier']})")


if __name__ == '__main__':
    main()
