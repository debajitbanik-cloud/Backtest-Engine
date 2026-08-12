"""
Custom Technical Indicators for Backtesting
ATR, SuperTrend, and Bollinger Bands implementations
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) indicator.
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 14)
    
    Returns:
        ATR values as pandas Series
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                         atr_period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    SuperTrend indicator.
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        atr_period: ATR calculation period (default 10)
        multiplier: ATR multiplier for bands (default 3.0)
    
    Returns:
        Tuple of (supertrend_line, direction) where direction is 1 (up) or -1 (down)
    """
    atr = calculate_atr(high, low, close, period=atr_period)
    
    hl2 = (high + low) / 2
    
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=float)
    
    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = 1
    
    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        
        if direction.iloc[i] == 1:
            supertrend.iloc[i] = lower_band.iloc[i]
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
    
    return supertrend, direction


def calculate_bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands indicator.
    
    Args:
        close: Close price series
        period: Moving average period (default 20)
        std_dev: Standard deviation multiplier (default 2.0)
    
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    middle_band = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    
    upper_band = middle_band + (std_dev * rolling_std)
    lower_band = middle_band - (std_dev * rolling_std)
    
    return upper_band, middle_band, lower_band


def calculate_all_indicators(df: pd.DataFrame, atr_period: int = 14, st_atr_period: int = 10,
                              st_multiplier: float = 3.0, bb_period: int = 20,
                              bb_std: float = 2.0) -> pd.DataFrame:
    """
    Calculate all indicators and add them to a DataFrame.
    
    Args:
        df: DataFrame with OHLCV data (must have 'high', 'low', 'close' columns)
        atr_period: ATR calculation period
        st_atr_period: SuperTrend ATR period
        st_multiplier: SuperTrend multiplier
        bb_period: Bollinger Bands period
        bb_std: Bollinger Bands standard deviation
    
    Returns:
        DataFrame with indicator columns added
    """
    df = df.copy()
    
    # ATR
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], period=atr_period)
    
    # SuperTrend
    df['supertrend'], df['st_direction'] = calculate_supertrend(
        df['high'], df['low'], df['close'],
        atr_period=st_atr_period, multiplier=st_multiplier
    )
    
    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(
        df['close'], period=bb_period, std_dev=bb_std
    )
    
    # BB %B indicator (position within bands)
    df['bb_pctb'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # BB bandwidth
    df['bb_bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    
    return df
