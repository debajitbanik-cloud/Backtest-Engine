"""
Trading Metrics Engine
Computes correlation, exposure, hedge metrics, and performance analytics.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore', message='Degrees of freedom')
warnings.filterwarnings('ignore', message='divide by zero')
np.seterr(all='ignore')


def _sanitize(v: Any) -> Any:
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isnan(v) or np.isinf(v):
            return 0.0
        return float(v)
    if isinstance(v, float):
        import math
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.ndarray):
        return [_sanitize(x) for x in v.tolist()]
    return v


@dataclass
class CorrelationResult:
    symbol_a: str
    symbol_b: str
    correlation_1h: float
    correlation_4h: float
    correlation_1d: float
    correlation_7d: float
    current: float
    trend: str  # rising, falling, stable
    updated: str


@dataclass
class ExposureMetrics:
    total_crypto_exposure: float  # in quote currency
    total_rwa_exposure: float
    crypto_allocation_pct: float
    rwa_allocation_pct: float
    net_exposure: float
    gross_exposure: float
    leverage_ratio: float
    concentration_risk: float  # Herfindahl index
    updated: str


@dataclass
class HedgeMetrics:
    hedge_ratio: float
    hedge_effectiveness: float  # R² of regression
    beta: float
    alpha: float
    net_delta_exposure: float
    optimal_hedge_ratio: float
    rebalance_signal: bool
    confidence: float
    updated: str


@dataclass
class PerformanceSnapshot:
    total_return_pct: float
    daily_returns: List[float]
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    win_rate: float
    profit_factor: float
    avg_win_loss_ratio: float
    consecutive_wins: int
    consecutive_losses: int
    weekly_pnl: List[float]
    updated: str


class MetricsEngine:
    """
    Computes all trading metrics: correlation, exposure, hedge effectiveness, performance.
    Reads from shared data directory.
    """
    
    def __init__(self, data_dir: str = "./data/shared"):
        self.data_dir = Path(data_dir)
    
    def _load_candles(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load candle data from JSON files."""
        file_path = self.data_dir / f"{symbol}_{timeframe}.json"
        if not file_path.exists():
            return None
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        return df.dropna()
    
    def compute_correlation(self, symbol_a: str, symbol_b: str, 
                            lookback_days: int = 30) -> CorrelationResult:
        """
        Compute correlation between two assets across multiple timeframes.
        
        Crypto-RWA correlation measures how closely crypto (SOL, BTC) tracks 
        real-world assets (XAUT - gold) — critical for portfolio diversification.
        """
        correlations = {}
        
        df_a = self._load_candles(symbol_a, '1h')
        df_b = self._load_candles(symbol_b, '1h')
        
        if df_a is None or df_b is None:
            return CorrelationResult(
                symbol_a=symbol_a, symbol_b=symbol_b,
                correlation_1h=0, correlation_4h=0, correlation_1d=0,
                correlation_7d=0, current=0, trend='stable',
                updated=datetime.utcnow().isoformat()
            )
        
        # Align timestamps
        common_idx = df_a.index.intersection(df_b.index)
        if len(common_idx) < 10:
            return CorrelationResult(
                symbol_a=symbol_a, symbol_b=symbol_b,
                correlation_1h=0, correlation_4h=0, correlation_1d=0,
                correlation_7d=0, current=0, trend='stable',
                updated=datetime.utcnow().isoformat()
            )
        
        returns_a = df_a['close'].pct_change().dropna()
        returns_b = df_b['close'].pct_change().dropna()
        
        common = returns_a.index.intersection(returns_b.index)
        ret_a = returns_a[common]
        ret_b = returns_b[common]
        
        # Compute correlation at different windows
        for window, label in [(1, '1h'), (4, '4h'), (24, '1d'), (168, '7d')]:
            if len(ret_a) >= window:
                correlations[label] = float(ret_a.tail(window).corr(ret_b.tail(window)))
            else:
                correlations[label] = 0
        
        # Current correlation (last period)
        current = correlations.get('1d', correlations.get('4h', 0))
        if np.isnan(current):
            current = 0.0
        
        # Correlation trend
        if '1d' in correlations and '7d' in correlations:
            if abs(correlations['7d']) > abs(correlations['1d']) + 0.1:
                trend = 'rising'
            elif abs(correlations['7d']) < abs(correlations['1d']) - 0.1:
                trend = 'falling'
            else:
                trend = 'stable'
        else:
            trend = 'stable'
        
        return CorrelationResult(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            correlation_1h=correlations.get('1h', 0),
            correlation_4h=correlations.get('4h', 0),
            correlation_1d=correlations.get('1d', 0),
            correlation_7d=correlations.get('7d', 0),
            current=current,
            trend=trend,
            updated=datetime.utcnow().isoformat()
        )
    
    def compute_exposure(self, crypto_symbols: List[str], rwa_symbols: List[str],
                         crypto_quantity: Dict[str, float] = None,
                         rwa_quantity: Dict[str, float] = None) -> ExposureMetrics:
        """
        Compute crypto vs RWA portfolio exposure.
        
        Measures how much capital is allocated to crypto vs real-world assets (gold, etc).
        """
        if crypto_quantity is None:
            crypto_quantity = {}
        if rwa_quantity is None:
            rwa_quantity = {}
        # Load latest prices
        crypto_value = 0
        for sym in crypto_symbols:
            df = self._load_candles(sym, '1h')
            if df is not None and len(df) > 0:
                price = float(df['close'].iloc[-1])
                qty = crypto_quantity.get(sym, 1.0)
                crypto_value += price * qty
        
        rwa_value = 0
        for sym in rwa_symbols:
            df = self._load_candles(sym, '1h')
            if df is not None and len(df) > 0:
                price = float(df['close'].iloc[-1])
                qty = rwa_quantity.get(sym, 1.0)
                rwa_value += price * qty
        
        total_value = crypto_value + rwa_value
        
        if total_value <= 0:
            return ExposureMetrics(
                total_crypto_exposure=0, total_rwa_exposure=0,
                crypto_allocation_pct=0, rwa_allocation_pct=0,
                net_exposure=0, gross_exposure=0,
                leverage_ratio=0, concentration_risk=0,
                updated=datetime.utcnow().isoformat()
            )
        
        crypto_pct = (crypto_value / total_value) * 100
        rwa_pct = (rwa_value / total_value) * 100
        net_exposure = crypto_value - rwa_value
        gross_exposure = crypto_value + rwa_value
        
        # Concentration risk (Herfindahl index)
        allocations = [crypto_value / total_value, rwa_value / total_value]
        herfindahl = sum(a ** 2 for a in allocations)
        concentration_risk = herfindahl  # 0.5 = perfectly balanced, 1.0 = fully concentrated
        
        return ExposureMetrics(
            total_crypto_exposure=crypto_value,
            total_rwa_exposure=rwa_value,
            crypto_allocation_pct=crypto_pct,
            rwa_allocation_pct=rwa_pct,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            leverage_ratio=1.0,  # No leverage by default
            concentration_risk=concentration_risk,
            updated=datetime.utcnow().isoformat()
        )
    
    def compute_hedge_metrics(self, primary_symbol: str, hedge_symbol: str,
                               hedge_ratio: float = 1.0) -> HedgeMetrics:
        """
        Compute hedge effectiveness metrics.
        
        Measures how well a hedge asset (XAUT/gold) offsets risk in the primary asset (SOL).
        Uses rolling regression to estimate beta and hedge effectiveness.
        """
        df_primary = self._load_candles(primary_symbol, '1h')
        df_hedge = self._load_candles(hedge_symbol, '1h')
        
        if df_primary is None or df_hedge is None:
            return HedgeMetrics(
                hedge_ratio=0, hedge_effectiveness=0.0,
                beta=0, alpha=0, net_delta_exposure=0,
                optimal_hedge_ratio=0, rebalance_signal=False,
                confidence=0, updated=datetime.utcnow().isoformat()
            )
        
        # Align data
        common_idx = df_primary.index.intersection(df_hedge.index)
        if len(common_idx) < 20:
            return HedgeMetrics(
                hedge_ratio=hedge_ratio, hedge_effectiveness=0.0,
                beta=0, alpha=0, net_delta_exposure=0,
                optimal_hedge_ratio=0, rebalance_signal=False,
                confidence=0, updated=datetime.utcnow().isoformat()
            )
        
        ret_primary = df_primary['close'].pct_change().dropna()[common_idx[1:]]
        ret_hedge = df_hedge['close'].pct_change().dropna()[common_idx[1:]]
        
        common = ret_primary.index.intersection(ret_hedge.index)
        rp = ret_primary[common]
        rh = ret_hedge[common]
        
        if len(rp) < 20:
            return HedgeMetrics(
                hedge_ratio=hedge_ratio, hedge_effectiveness=0.0,
                beta=0, alpha=0, net_delta_exposure=0,
                optimal_hedge_ratio=0, rebalance_signal=False,
                confidence=0, updated=datetime.utcnow().isoformat()
            )
        
        # Linear regression: rp = alpha + beta * rh
        cov_matrix = np.cov(rp, rh)
        beta = cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] > 0 else 0
        alpha = rp.mean() - beta * rh.mean()
        
        # Hedge effectiveness (R²)
        residuals = rp - (alpha + beta * rh)
        ss_total = np.sum((rp - rp.mean()) ** 2)
        ss_residual = np.sum(residuals ** 2)
        r_squared = 1 - (ss_residual / ss_total) if ss_total > 0 else 0
        
        # Optimal hedge ratio (minimum variance hedge)
        optimal_ratio = beta if beta > 0 else 0
        
        # Net delta exposure (how much unhedged exposure remains)
        last_primary = float(df_primary['close'].iloc[-1])
        last_hedge = float(df_hedge['close'].iloc[-1])
        net_delta = last_primary - (optimal_ratio * last_hedge)
        
        # Rebalance signal if current ratio deviates > 20% from optimal
        rebalance = abs(hedge_ratio - optimal_ratio) / optimal_ratio > 0.2 if optimal_ratio > 0 else False
        
        return HedgeMetrics(
            hedge_ratio=hedge_ratio,
            hedge_effectiveness=r_squared,
            beta=beta,
            alpha=alpha,
            net_delta_exposure=net_delta,
            optimal_hedge_ratio=optimal_ratio,
            rebalance_signal=rebalance,
            confidence=min(1.0, len(rp) / 100),
            updated=datetime.utcnow().isoformat()
        )
    
    def compute_performance(self, symbol: str, timeframe: str = '1h') -> PerformanceSnapshot:
        """Compute comprehensive performance metrics."""
        df = self._load_candles(symbol, timeframe)
        
        if df is None or len(df) < 2:
            return PerformanceSnapshot(
                total_return_pct=0, daily_returns=[], sharpe_ratio=0,
                sortino_ratio=0, max_drawdown_pct=0, current_drawdown_pct=0,
                win_rate=0, profit_factor=0, avg_win_loss_ratio=0,
                consecutive_wins=0, consecutive_losses=0,
                weekly_pnl=[], updated=datetime.utcnow().isoformat()
            )
        
        close = df['close']
        
        # Daily returns
        daily_close = close.resample('D').last().dropna()
        daily_returns_pct = daily_close.pct_change().dropna()
        
        # Total return
        total_return = ((close.iloc[-1] - close.iloc[0]) / close.iloc[0]) * 100
        
        # Sharpe ratio (assuming 0% risk-free rate for crypto)
        if len(daily_returns_pct) > 1 and daily_returns_pct.std() > 0:
            sharpe = (daily_returns_pct.mean() / daily_returns_pct.std()) * np.sqrt(365)
        else:
            sharpe = 0
        
        # Sortino ratio
        downside = daily_returns_pct[daily_returns_pct < 0]
        if len(downside) > 1 and downside.std() > 0:
            sortino = (daily_returns_pct.mean() / downside.std()) * np.sqrt(365)
        else:
            sortino = 0
        
        # Max drawdown
        cumulative = (1 + daily_returns_pct).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = (cumulative - rolling_max) / rolling_max
        max_dd = drawdowns.min() * 100
        current_dd = (drawdowns.iloc[-1] if len(drawdowns) > 0 else 0) * 100
        
        # Win/Loss analysis (simple: up day = win)
        wins = (daily_returns_pct > 0).sum()
        total = len(daily_returns_pct)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # Profit factor
        gross_profit = daily_returns_pct[daily_returns_pct > 0].sum()
        gross_loss = abs(daily_returns_pct[daily_returns_pct < 0].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Avg win/loss ratio
        avg_win = daily_returns_pct[daily_returns_pct > 0].mean() if wins > 0 else 0
        avg_loss = abs(daily_returns_pct[daily_returns_pct < 0].mean()) if total - wins > 0 else 0
        avg_wl = avg_win / avg_loss if avg_loss > 0 else 0
        
        # Consecutive wins/losses
        signs = (daily_returns_pct > 0).astype(int)
        cons_wins = cons_losses = 0
        cw = cl = 0
        for s in signs:
            if s == 1:
                cw += 1
                cl = 0
            else:
                cl += 1
                cw = 0
            cons_wins = max(cons_wins, cw)
            cons_losses = max(cons_losses, cl)
        
        # Weekly PnL
        weekly_pnl = daily_returns_pct.resample('W').sum().tolist()
        
        return PerformanceSnapshot(
            total_return_pct=total_return,
            daily_returns=daily_returns_pct.tolist(),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_pct=max_dd,
            current_drawdown_pct=current_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win_loss_ratio=avg_wl,
            consecutive_wins=cons_wins,
            consecutive_losses=cons_losses,
            weekly_pnl=weekly_pnl[-8:],  # Last 8 weeks
            updated=datetime.utcnow().isoformat()
        )
    
    def compute_all(self) -> Dict[str, Any]:
        """Compute all metrics for the dashboard."""
        result = {}
        
        # Correlation: SOL-XAUT
        result['correlation_sol_xaut'] = self.compute_correlation('SOLUSDT', 'XAUTUSDT')
        
        # Exposure
        result['exposure'] = self.compute_exposure(
            crypto_symbols=['SOLUSDT'],
            rwa_symbols=['XAUTUSDT']
        )
        
        # Hedge
        result['hedge'] = self.compute_hedge_metrics('SOLUSDT', 'XAUTUSDT')
        
        # Performance
        result['performance_sol'] = self.compute_performance('SOLUSDT', '15m')
        result['performance_xaut'] = self.compute_performance('XAUTUSDT', '15m')
        
        return result


# Singleton
metrics_engine = MetricsEngine(data_dir=str(Path(__file__).parent.parent.parent / "data" / "shared"))
