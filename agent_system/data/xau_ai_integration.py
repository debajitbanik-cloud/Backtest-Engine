"""
XAU AI Trading Bot Integration (Optional)
=========================================
Optional integration with https://github.com/0xagarg/xau-ai-trading-bot

The external repo is an MT5-based XAUUSD bot with:
- Smart Money Concepts (SMC): Order Blocks, FVG, BOS, CHoCH
- HMM Market Regime Detection
- Kelly Criterion Position Scaling
- Risk Analytics (VaR, Sharpe, Sortino, Calmar)
- Feature Engineering (37 ML features)
- XGBoost ML signal generation

Integration strategy:
- MT5 execution layer is EXCLUDED (Windows-only)
- Reusable strategy/analytics modules are IMPORTED when available
- The bridge exposes these as optional analytics endpoints
- UI shows XAU strategy insights when repo is installed
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Optional repo location (user can clone anywhere)
DEFAULT_REPO_PATH = Path.home() / "xau-ai-trading-bot"
REPO_ENV_VAR = "XAU_AI_REPO_PATH"


class XAUAIIntegration:
    """
    Optional wrapper for XAU AI Trading Bot modules.
    Handles graceful degradation when repo or dependencies are missing.
    """
    
    def __init__(self, repo_path: str = None):
        self.repo_path = Path(repo_path or __import__('os').environ.get(REPO_ENV_VAR, DEFAULT_REPO_PATH))
        self.available = False
        self.modules = {}
        self.error = None
        self._check_availability()
    
    def _check_availability(self) -> None:
        """Check if repo and its dependencies are available."""
        if not self.repo_path.exists():
            self.error = f"XAU AI repo not found at {self.repo_path}. Clone with: git clone https://github.com/0xagarg/xau-ai-trading-bot.git"
            return
        
        src_path = self.repo_path / "src"
        if not src_path.exists():
            self.error = f"XAU AI src directory not found in {self.repo_path}"
            return
        
        # Add src to path
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        
        # Try importing reusable modules (non-MT5)
        try:
            from smc_polars import SMCAnalyzer, SMCSignal
            self.modules['smc'] = SMCAnalyzer
        except ImportError as e:
            self.modules['smc'] = None
        
        try:
            from regime_detector import MarketRegimeDetector, MarketRegime
            self.modules['regime'] = MarketRegimeDetector
            self.modules['regime_enum'] = MarketRegime
        except ImportError as e:
            self.modules['regime'] = None
        
        try:
            from kelly_position_scaler import KellyPositionScaler
            self.modules['kelly'] = KellyPositionScaler
        except ImportError as e:
            self.modules['kelly'] = None
        
        try:
            from risk_metrics import RiskAnalytics
            self.modules['risk_analytics'] = RiskAnalytics
        except ImportError as e:
            self.modules['risk_analytics'] = None
        
        try:
            from risk_engine import RiskEngine
            self.modules['risk_engine'] = RiskEngine
        except ImportError as e:
            self.modules['risk_engine'] = None
        
        try:
            from feature_eng import FeatureEngineer
            self.modules['feature_eng'] = FeatureEngineer
        except ImportError as e:
            self.modules['feature_eng'] = None
        
        # Available if at least one module loaded
        self.available = any(self.modules.values())
        
        if not self.available:
            self.error = "No importable modules found. Check dependencies: pip install polars hmmlearn xgboost scikit-learn"
    
    def status(self) -> Dict:
        """Get integration status."""
        return {
            'available': self.available,
            'repo_path': str(self.repo_path),
            'modules': {k: (v is not None) for k, v in self.modules.items()},
            'error': self.error,
        }
    
    def run_smc_analysis(self, candles: List[Dict]) -> Dict:
        """
        Run Smart Money Concepts analysis on OHLCV data.
        
        Args:
            candles: List of OHLCV dicts with 'high', 'low', 'close', 'open'
        
        Returns:
            SMC signals (order blocks, FVG, BOS, CHoCH)
        """
        if not self.modules.get('smc'):
            return {'error': 'SMC module not available'}
        
        try:
            import polars as pl
            
            df = pl.DataFrame(candles)
            analyzer = self.modules['smc']()
            
            # The external SMC analyzer expects specific columns
            # We adapt to our candle format
            result = analyzer.analyze(df) if hasattr(analyzer, 'analyze') else None
            
            if result is None:
                # Fallback: manually extract key SMC levels
                return self._extract_smc_levels(candles)
            
            return result
        except Exception as e:
            return {'error': str(e)}
    
    def _extract_smc_levels(self, candles: List[Dict]) -> Dict:
        """Fallback SMC extraction when external analyzer fails."""
        if not candles:
            return {'order_blocks': [], 'fvg': [], 'swing_points': []}
        
        highs = [c.get('high', 0) for c in candles]
        lows = [c.get('low', 0) for c in candles]
        closes = [c.get('close', 0) for c in candles]
        
        # Simple swing detection
        swing_highs = []
        swing_lows = []
        for i in range(2, len(candles) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append({'index': i, 'price': highs[i]})
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append({'index': i, 'price': lows[i]})
        
        return {
            'swing_highs': swing_highs[-5:],
            'swing_lows': swing_lows[-5:],
            'current_price': closes[-1] if closes else 0,
        }
    
    def detect_regime(self, candles: List[Dict]) -> Dict:
        """Detect market regime using HMM (if available)."""
        if not self.modules.get('regime'):
            return {'error': 'Regime detection module not available'}
        
        try:
            import polars as pl
            import numpy as np
            
            df = pl.DataFrame(candles)
            detector = self.modules['regime']()
            
            # Adapt to external detector's expected interface
            # The repo uses OHLCV with specific feature columns
            if hasattr(detector, 'detect'):
                result = detector.detect(df)
                return result
            
            return {'error': 'Detector interface not recognized'}
        except Exception as e:
            return {'error': str(e)}
    
    def kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float, kelly_fraction: float = 0.5) -> Dict:
        """Calculate Kelly criterion position size."""
        if not self.modules.get('kelly'):
            # Fallback calculation
            if avg_loss <= 0:
                return {'error': 'avg_loss must be positive'}
            b = avg_win / avg_loss
            q = 1 - win_rate
            f_star = (win_rate * b - q) / b if b > 0 else 0
            f_star = max(0, min(f_star * kelly_fraction, 1.0))
            return {
                'kelly_fraction': f_star,
                'full_kelly': f_star / kelly_fraction if kelly_fraction > 0 else f_star,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'recommendation': 'INCREASE' if f_star > 0.15 else 'REDUCE' if f_star > 0.05 else 'MINIMAL',
            }
        
        try:
            scaler = self.modules['kelly'](
                base_win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                kelly_fraction=kelly_fraction,
            )
            
            # Try the actual method name with correct arguments
            if hasattr(scaler, 'calculate_optimal_fraction'):
                # External API requires exit_confidence, current_profit, target_profit
                fraction = scaler.calculate_optimal_fraction(
                    exit_confidence=0.5,
                    current_profit=0.0,
                    target_profit=10.0
                )
                return {
                    'kelly_fraction': float(fraction),
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'recommendation': 'INCREASE' if fraction > 0.15 else 'REDUCE' if fraction > 0.05 else 'MINIMAL',
                }
            
            # Fallback calculation using the scaler's parameters
            if avg_loss <= 0:
                return {'error': 'avg_loss must be positive'}
            b = avg_win / avg_loss
            q = 1 - win_rate
            f_star = (win_rate * b - q) / b if b > 0 else 0
            f_star = max(0, min(f_star * kelly_fraction, 1.0))
            return {
                'kelly_fraction': f_star,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
            }
        except Exception as e:
            return {'error': str(e)}
    
    def risk_analytics(self, equity_curve: List[float]) -> Dict:
        """Calculate risk metrics (Sharpe, Sortino, VaR, drawdown)."""
        if not self.modules.get('risk_analytics'):
            return self._fallback_risk_analytics(equity_curve)
        
        try:
            analyzer = self.modules['risk_analytics']()
            
            # Try comprehensive report first
            if hasattr(analyzer, 'get_comprehensive_report'):
                report = analyzer.get_comprehensive_report(equity_curve)
                return report
            
            # Fallback to individual methods
            result = {}
            
            if hasattr(analyzer, 'sharpe_ratio'):
                result['sharpe'] = analyzer.sharpe_ratio(equity_curve)
            if hasattr(analyzer, 'sortino_ratio'):
                result['sortino'] = analyzer.sortino_ratio(equity_curve)
            if hasattr(analyzer, 'calmar_ratio'):
                result['calmar'] = analyzer.calmar_ratio(equity_curve)
            if hasattr(analyzer, 'maximum_drawdown'):
                result['max_drawdown'] = analyzer.maximum_drawdown(equity_curve)
            if hasattr(analyzer, 'value_at_risk'):
                result['var_95'] = analyzer.value_at_risk(equity_curve, 0.95)
                result['var_99'] = analyzer.value_at_risk(equity_curve, 0.99)
            if hasattr(analyzer, 'profit_factor'):
                returns = analyzer.calculate_returns(equity_curve)
                result['profit_factor'] = analyzer.profit_factor(returns)
            if hasattr(analyzer, 'win_rate'):
                returns = analyzer.calculate_returns(equity_curve)
                result['win_rate'] = analyzer.win_rate(returns)
            
            return result
        except Exception as e:
            return self._fallback_risk_analytics(equity_curve)
    
    def _fallback_risk_analytics(self, equity_curve: List[float]) -> Dict:
        """Fallback risk analytics."""
        import numpy as np
        
        if len(equity_curve) < 2:
            return {'error': 'Need at least 2 points'}
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        downside = returns[returns < 0]
        sortino = (returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 1 and downside.std() > 0 else 0
        
        # Max drawdown
        cum = np.array(equity_curve)
        running_max = np.maximum.accumulate(cum)
        drawdown = (cum - running_max) / running_max
        max_dd = drawdown.min()
        
        # VaR
        var_95 = np.percentile(returns, 5)
        var_99 = np.percentile(returns, 1)
        
        return {
            'sharpe': float(sharpe),
            'sortino': float(sortino),
            'max_drawdown_pct': float(max_dd * 100),
            'var_95': float(var_95 * 100),
            'var_99': float(var_99 * 100),
        }
    
    def feature_engineering(self, candles: List[Dict]) -> Dict:
        """Run feature engineering on candles."""
        if not self.modules.get('feature_eng'):
            return {'error': 'Feature engineering module not available'}
        
        try:
            import polars as pl
            df = pl.DataFrame(candles)
            engineer = self.modules['feature_eng']()
            result = engineer.calculate_all(df)
            return {
                'features_count': len(result.columns),
                'features': result.columns[:20],
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_scalp_signal(self, candles_1m: List[Dict], candles_5m: List[Dict]) -> Dict:
        """
        Generate a short-term scalp signal for XAUUSD using available modules
        or fallback logic based on swing levels + ATR bands + volume.
        """
        if not candles_1m or not candles_5m:
            return {'direction': 'flat', 'confidence': 0.0, 'reason': 'insufficient candles'}
        
        # Prefer external feature engineering / regime if available
        regime = self.detect_regime(candles_5m)
        smc = self.run_smc_analysis(candles_5m)
        
        # Fallback technical logic
        closes_1m = [c.get('close', 0) for c in candles_1m]
        highs_1m = [c.get('high', 0) for c in candles_1m]
        lows_1m = [c.get('low', 0) for c in candles_1m]
        volumes_1m = [c.get('volume', 0) for c in candles_1m]
        
        if len(closes_1m) < 20:
            return {'direction': 'flat', 'confidence': 0.0, 'reason': 'not enough 1m data'}
        
        import numpy as np
        current = closes_1m[-1]
        atr = self._atr(highs_1m, lows_1m, closes_1m, period=14)
        ema_fast = self._ema(closes_1m, period=9)
        ema_slow = self._ema(closes_1m, period=21)
        
        avg_volume = np.mean(volumes_1m[-20:]) if volumes_1m else 0
        volume_spike = (volumes_1m[-1] / avg_volume) if avg_volume > 0 else 1.0
        
        # Swing levels from fallback SMC
        swing_highs = smc.get('swing_highs', []) if isinstance(smc, dict) else []
        swing_lows = smc.get('swing_lows', []) if isinstance(smc, dict) else []
        recent_high = swing_highs[-1]['price'] if swing_highs else max(highs_1m[-20:])
        recent_low = swing_lows[-1]['price'] if swing_lows else min(lows_1m[-20:])
        
        regime_label = 'unknown'
        if isinstance(regime, dict):
            regime_label = regime.get('regime', regime.get('current_regime', 'unknown'))
        
        direction = 'flat'
        confidence = 0.0
        reason = 'no clear setup'
        
        # Long scalp: price near recent low, EMA crossover, volume spike
        if current <= recent_low + atr * 0.3 and ema_fast > ema_slow and volume_spike > 1.3:
            direction = 'long'
            confidence = min(0.9, 0.55 + (volume_spike - 1.3) * 0.2 + (0.1 if regime_label == 'bullish' else 0))
            reason = f"bounce off recent low {recent_low:.2f}, 9/21 EMA bullish, volume {volume_spike:.1f}x"
        
        # Short scalp: price near recent high, EMA bearish, volume spike
        elif current >= recent_high - atr * 0.3 and ema_fast < ema_slow and volume_spike > 1.3:
            direction = 'short'
            confidence = min(0.9, 0.55 + (volume_spike - 1.3) * 0.2 + (0.1 if regime_label == 'bearish' else 0))
            reason = f"rejection at recent high {recent_high:.2f}, 9/21 EMA bearish, volume {volume_spike:.1f}x"
        
        entry = current
        stop_loss = entry - atr * 1.5 if direction == 'long' else entry + atr * 1.5
        take_profit = entry + atr * 2.5 if direction == 'long' else entry - atr * 2.5
        
        return {
            'symbol': 'XAUTUSDT',
            'timeframe': '1m',
            'direction': direction,
            'entry': round(entry, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'confidence': round(confidence, 3),
            'atr': round(atr, 2),
            'regime': regime_label,
            'reason': reason,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    @staticmethod
    def _ema(values: List[float], period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0.0
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(highs) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1]),
            )
            trs.append(tr)
        return sum(trs[-period:]) / period


# Global integration
xau_ai_integration = XAUAIIntegration()
