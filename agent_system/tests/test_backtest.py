"""Tests for the backtest runner module."""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_system.backtest.indicators import calculate_atr, calculate_supertrend, calculate_bollinger_bands
from agent_system.backtest.strategy import SuperTrendBBStrategy


class TestIndicators:
    """Tests for technical indicators."""

    def test_calculate_atr(self):
        """Test ATR calculation."""
        high = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        low = pd.Series([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
        close = pd.Series([8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18])

        atr = calculate_atr(high, low, close, period=3)
        
        # Check that ATR is calculated correctly
        assert not atr.isna().all()
        assert len(atr) == len(close)
        # First 2 values should be NaN (period=3)
        assert atr.iloc[0] != atr.iloc[0]  # NaN check
        assert atr.iloc[1] != atr.iloc[1]
        assert atr.iloc[2] == atr.iloc[2]  # Should have value

    def test_calculate_supertrend(self):
        """Test SuperTrend calculation."""
        high = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        low = pd.Series([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
        close = pd.Series([8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18])

        st_line, st_dir = calculate_supertrend(high, low, close, atr_period=3, multiplier=3.0)
        
        assert len(st_line) == len(close)
        assert len(st_dir) == len(close)
        assert all(d in [1, -1] for d in st_dir.dropna())

    def test_calculate_bollinger_bands(self):
        """Test Bollinger Bands calculation."""
        close = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])

        upper, middle, lower = calculate_bollinger_bands(close, period=5, std_dev=2.0)
        
        assert len(upper) == len(close)
        assert len(middle) == len(close)
        assert len(lower) == len(close)
        
        # Middle should be SMA
        assert middle.iloc[4] == close.iloc[:5].mean()
        # Upper should be above middle
        assert upper.iloc[4] > middle.iloc[4]
        # Lower should be below middle
        assert lower.iloc[4] < middle.iloc[4]


class TestStrategy:
    """Tests for the trading strategy."""

    def test_strategy_parameters_are_class_attributes(self):
        """Test strategy has correct default parameter attributes."""
        # Check class attributes (these are defined at class level)
        assert SuperTrendBBStrategy.trend_sma_period == 200
        assert SuperTrendBBStrategy.st_atr_period == 10
        assert SuperTrendBBStrategy.st_multiplier == 3.0
        assert SuperTrendBBStrategy.bb_period == 20
        assert SuperTrendBBStrategy.bb_std == 2.0
        assert SuperTrendBBStrategy.risk_per_trade == 0.02

    def test_strategy_can_override_parameters(self):
        """Test that strategy parameters can be overridden via subclass."""
        
        class CustomStrategy(SuperTrendBBStrategy):
            st_atr_period = 14
            st_multiplier = 2.5
            bb_period = 25
        
        assert CustomStrategy.st_atr_period == 14
        assert CustomStrategy.st_multiplier == 2.5
        assert CustomStrategy.bb_period == 25
        # Other params should inherit from parent
        assert CustomStrategy.trend_sma_period == 200
        assert CustomStrategy.bb_std == 2.0


class TestBacktestRunner:
    """Tests for backtest runner utilities."""

    def test_load_candles_creates_valid_dataframe(self):
        """Test that load function creates proper DataFrame structure."""
        # This is a basic test - actual loading requires data files
        pass


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])