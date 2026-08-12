"""
Combined Strategy using ATR, SuperTrend, and Bollinger Bands
Final version with trend filter and improved entry logic
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

from .indicators import calculate_atr, calculate_supertrend, calculate_bollinger_bands


class SuperTrendBBStrategy(Strategy):
    """
    Combined SuperTrend + Bollinger Bands strategy with trend filter.
    
    Key Improvements:
    1. Long-term trend filter (200-period SMA)
    2. Only trade in direction of major trend
    3. Use SuperTrend as trailing stop after entry
    4. Tighter entry conditions near Bollinger Bands
    
    Entry Conditions (Long):
    - Price above 200 SMA (uptrend)
    - SuperTrend direction is bullish (1) for at least N bars
    - Price touches or dips below lower Bollinger Band (oversold pullback)
    - Price closes above SuperTrend line
    
    Entry Conditions (Short):
    - Price below 200 SMA (downtrend)
    - SuperTrend direction is bearish (-1) for at least N bars
    - Price touches or rises above upper Bollinger Band (overbought rally)
    - Price closes below SuperTrend line
    
    Exit Conditions:
    - SuperTrend direction reversal (trailing stop)
    - Price crosses middle Bollinger Band (mean reversion)
    - ATR-based stop loss
    """
    
    # Trend filter
    trend_sma_period = 200
    
    # SuperTrend parameters
    st_atr_period = 10
    st_multiplier = 3.0
    st_confirmation_bars = 2  # Require N bars of same direction
    
    # Bollinger Bands parameters
    bb_period = 20
    bb_std = 2.0
    bb_entry_threshold = 0.015  # Price must be within 1.5% of band
    
    # ATR parameters
    atr_period = 14
    atr_sl_multiplier = 2.0  # Wider stops to avoid whipsaws
    atr_min_threshold = 0.003  # Minimum ATR as % of price (0.3%)
    
    # Position sizing
    risk_per_trade = 0.02  # 2% risk per trade
    
    def init(self):
        # Calculate indicators
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        close = pd.Series(self.data.Close)
        
        # Trend filter SMA
        self.trend_sma = self.I(lambda x: x.rolling(self.trend_sma_period).mean(), close, name='Trend_SMA')
        
        # ATR
        self.atr = self.I(calculate_atr, high, low, close, self.atr_period, name='ATR')
        
        # SuperTrend
        st_line, st_dir = calculate_supertrend(high, low, close, 
                                                atr_period=self.st_atr_period,
                                                multiplier=self.st_multiplier)
        self.supertrend = self.I(lambda x: x, st_line, name='SuperTrend')
        self.st_direction = self.I(lambda x: x, st_dir, name='ST_Direction')
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close, 
                                                                    period=self.bb_period,
                                                                    std_dev=self.bb_std)
        self.bb_upper = self.I(lambda x: x, bb_upper, name='BB_Upper')
        self.bb_middle = self.I(lambda x: x, bb_middle, name='BB_Middle')
        self.bb_lower = self.I(lambda x: x, bb_lower, name='BB_Lower')
        
        # Track direction changes for confirmation
        self.st_direction_history = []
    
    def next(self):
        # Skip if not enough data
        if len(self.data) < self.trend_sma_period + 20:
            return
        
        current_close = self.data.Close[-1]
        current_atr = self.atr[-1]
        current_st_dir = self.st_direction[-1]
        current_st = self.supertrend[-1]
        current_bb_upper = self.bb_upper[-1]
        current_bb_middle = self.bb_middle[-1]
        current_bb_lower = self.bb_lower[-1]
        current_trend_sma = self.trend_sma[-1]
        
        # Skip if indicators are NaN
        if np.isnan(current_atr) or np.isnan(current_st) or np.isnan(current_bb_upper) or np.isnan(current_trend_sma):
            return
        
        # Track SuperTrend direction history
        self.st_direction_history.append(current_st_dir)
        if len(self.st_direction_history) > self.st_confirmation_bars + 1:
            self.st_direction_history.pop(0)
        
        # Check if SuperTrend has been consistent for N bars
        if len(self.st_direction_history) < self.st_confirmation_bars:
            return
        
        consistent_direction = all(
            d == current_st_dir 
            for d in self.st_direction_history[-self.st_confirmation_bars:]
        )
        
        # ATR volatility filter (ATR must be > 0.3% of price)
        atr_pct = current_atr / current_close if current_close > 0 else 0
        if atr_pct < self.atr_min_threshold:
            return
        
        # Use fixed fraction of equity for position sizing (backtesting.py requirement)
        position_size = 0.95  # Use 95% of equity
        
        # Determine trend direction
        uptrend = current_close > current_trend_sma
        downtrend = current_close < current_trend_sma
        
        # === LONG ENTRY ===
        if not self.position:
            # Long: Uptrend + SuperTrend bullish + price near/below lower BB
            if (uptrend and
                current_st_dir == 1 and 
                consistent_direction and
                current_close <= current_bb_lower * (1 + self.bb_entry_threshold) and  # Near or below lower band
                current_close > current_st):  # Above SuperTrend line
                
                sl = current_close - (current_atr * self.atr_sl_multiplier)
                # Use middle BB as take-profit, but ensure it's above entry
                tp = max(current_close * 1.02, current_bb_middle)  # At least 2% profit
                self.buy(size=position_size, sl=sl, tp=tp)
            
            # Short: Downtrend + SuperTrend bearish + price near/above upper BB
            elif (downtrend and
                  current_st_dir == -1 and 
                  consistent_direction and
                  current_close >= current_bb_upper * (1 - self.bb_entry_threshold) and  # Near or above upper band
                  current_close < current_st):  # Below SuperTrend line
                
                sl = current_close + (current_atr * self.atr_sl_multiplier)
                # Use middle BB as take-profit, but ensure it's below entry
                tp = min(current_close * 0.98, current_bb_middle)  # At least 2% profit
                self.sell(size=position_size, sl=sl, tp=tp)
        
        # === EXIT CONDITIONS ===
        elif self.position.is_long:
            # Exit long if SuperTrend reverses
            if current_st_dir == -1:
                self.position.close()
        
        elif self.position.is_short:
            # Exit short if SuperTrend reverses
            if current_st_dir == 1:
                self.position.close()
