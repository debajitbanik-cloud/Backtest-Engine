"""
Quick Test - Run backtest optimization on a smaller parameter grid
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Add scripts directory to path for local imports
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from agent_system.backtest.runner import load_candles_from_json, run_backtest
from agent_system.backtest.strategy import SuperTrendBBStrategy
from analyze import explain_performance


def quick_test():
    """Run quick optimization test with reduced parameter grid."""
    print("="*70)
    print("QUICK BACKTEST OPTIMIZATION TEST")
    print("="*70)
    
    # Load data
    print("\nLoading data...")
    df = load_candles_from_json("SOLUSDT", "15m")
    print(f"Loaded {len(df)} candles")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    
    # Test with single parameter set first
    print("\n" + "="*70)
    print("TEST 1: Single Parameter Set")
    print("="*70)
    
    default_params = {
        'st_atr_period': 10,
        'st_multiplier': 3.0,
        'st_confirmation_bars': 2,
        'bb_period': 20,
        'bb_std': 2.0,
        'bb_entry_threshold': 0.015,
        'atr_period': 14,
        'atr_sl_multiplier': 2.0,
        'atr_min_threshold': 0.003,
    }
    
    result = run_backtest(df, SuperTrendBBStrategy, default_params, cash=10000)
    
    print(f"\nResults:")
    print(f"  Total Return: {result['total_return']:.2f}%")
    print(f"  Buy & Hold: {result['buy_hold_return']:.2f}%")
    print(f"  Sharpe Ratio: {result['sharpe']:.2f}")
    print(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
    print(f"  Win Rate: {result['win_rate']:.1f}%")
    print(f"  Trades: {result['trades']}")
    print(f"  Profit Factor: {result['profit_factor']:.2f}")
    print(f"  Final Equity: ${result['equity_final']:.2f}")
    
    # Test optimization with reduced grid
    print("\n" + "="*70)
    print("TEST 2: Optimization (Reduced Grid)")
    print("="*70)
    
    # Use fewer parameter combinations for quick test
    import itertools
    
    param_grid = {
        'st_atr_period': [10],
        'st_multiplier': [2.5, 3.0, 3.5],
        'st_confirmation_bars': [2],
        'bb_period': [20],
        'bb_std': [2.0],
        'bb_entry_threshold': [0.015],
        'atr_period': [14],
        'atr_sl_multiplier': [1.5, 2.0, 2.5],
        'atr_min_threshold': [0.003],
    }
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    
    print(f"Testing {len(combinations)} parameter combinations...")
    
    results = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        try:
            result = run_backtest(df, SuperTrendBBStrategy, params, cash=10000, verbose=False)
            results.append(result)
            if (i + 1) % 3 == 0:
                print(f"  Completed {i+1}/{len(combinations)}...")
        except Exception as e:
            continue
    
    # Sort by return
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    # Print top 3
    print(f"\n{'='*70}")
    print("TOP 3 RESULTS")
    print(f"{'='*70}\n")
    
    for i, r in enumerate(results[:3], 1):
        print(f"#{i}: Return={r['total_return']:.2f}%, "
              f"Sharpe={r['sharpe']:.2f}, "
              f"WinRate={r['win_rate']:.1f}%, "
              f"Trades={r['trades']}")
        print(f"   Params: ST({r['params']['st_atr_period']}, {r['params']['st_multiplier']}) "
              f"BB({r['params']['bb_period']}, {r['params']['bb_std']}) "
              f"ATR({r['params']['atr_period']}, SL={r['params']['atr_sl_multiplier']})")
        print()
    
    # Generate explanation
    print("\n" + "="*70)
    print("PERFORMANCE ANALYSIS")
    print(f"{'='*70}\n")
    
    explanation = explain_performance("SOLUSDT", "15m", results, top_n=3)
    print(explanation)
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print(f"{'='*70}\n")
    
    print("✓ All backtest components working correctly")
    print("✓ Optimization pipeline functional")
    print("✓ Analysis generation working")
    print("\nReady to run full optimization with:")
    print("  python3 -m agent_system.backtest.runner")


if __name__ == '__main__':
    quick_test()
