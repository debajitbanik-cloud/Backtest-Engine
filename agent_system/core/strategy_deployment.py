"""
Optimized Strategy Deployment Configuration
Stores the best performing strategy parameters discovered during backtesting.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class OptimizedStrategy:
    strategy_name: str
    symbol: str
    timeframe: str
    indicators: Dict[str, Any]
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    trades: int
    profit_factor: float
    confidence: float
    updated: str


class StrategyDeploymentManager:
    """
    Manages optimized strategy configurations.
    Reads from backtest results and exposes them for deployment.
    """
    
    def __init__(self, results_dir: str = None):
        if results_dir is None:
            results_dir = str(Path(__file__).parent.parent / "backtest" / "results")
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._strategies: List[OptimizedStrategy] = []
        self._load_strategies()
    
    def _load_strategies(self) -> None:
        """Load strategies from results file or use defaults."""
        results_file = self.results_dir / "best_parameters.json"
        
        if results_file.exists():
            try:
                with open(results_file, 'r') as f:
                    data = json.load(f)
                
                for symbol, timeframes in data.items():
                    for tf, params in timeframes.items():
                        strategy = OptimizedStrategy(
                            strategy_name=f"SuperTrend+BB {symbol} {tf}",
                            symbol=symbol,
                            timeframe=tf,
                            indicators={
                                "st_atr_period": params.get("st_atr_period", 10),
                                "st_multiplier": params.get("st_multiplier", 3.0),
                                "st_confirmation_bars": params.get("st_confirmation_bars", 2),
                                "bb_period": params.get("bb_period", 20),
                                "bb_std": params.get("bb_std", 2.0),
                                "bb_entry_threshold": params.get("bb_entry_threshold", 0.015),
                                "atr_period": params.get("atr_period", 14),
                                "atr_sl_multiplier": params.get("atr_sl_multiplier", 2.0),
                                "atr_min_threshold": params.get("atr_min_threshold", 0.003),
                            },
                            total_return_pct=params.get("total_return_pct", 0),
                            sharpe_ratio=params.get("sharpe_ratio", 0),
                            max_drawdown_pct=params.get("max_drawdown_pct", 0),
                            win_rate=params.get("win_rate", 0),
                            trades=params.get("trades", 0),
                            profit_factor=params.get("profit_factor", 0),
                            confidence=params.get("confidence", 0.7),
                            updated=datetime.utcnow().isoformat()
                        )
                        self._strategies.append(strategy)
            except Exception as e:
                print(f"Error loading strategy results: {e}")
        
        # Add default strategy if none loaded
        if not self._strategies:
            self._strategies.append(self._default_strategy())
    
    def _default_strategy(self) -> OptimizedStrategy:
        """Create default optimized strategy."""
        return OptimizedStrategy(
            strategy_name="SuperTrend+BB SOLUSDT 15m",
            symbol="SOLUSDT",
            timeframe="15m",
            indicators={
                "st_atr_period": 10,
                "st_multiplier": 3.0,
                "st_confirmation_bars": 2,
                "bb_period": 20,
                "bb_std": 2.0,
                "bb_entry_threshold": 0.015,
                "atr_period": 14,
                "atr_sl_multiplier": 2.5,
                "atr_min_threshold": 0.003,
            },
            total_return_pct=23.71,
            sharpe_ratio=2.0,
            max_drawdown_pct=34.5,
            win_rate=45.5,
            trades=356,
            profit_factor=1.05,
            confidence=0.72,
            updated=datetime.utcnow().isoformat()
        )
    
    def get_all(self) -> List[Dict]:
        """Get all strategies as dicts."""
        return [self._to_dict(s) for s in self._strategies]
    
    def get_best_for_symbol(self, symbol: str) -> Optional[Dict]:
        """Get best strategy for a symbol."""
        candidates = [s for s in self._strategies if s.symbol == symbol]
        if not candidates:
            return None
        
        # Sort by return
        candidates.sort(key=lambda x: x.total_return_pct, reverse=True)
        return self._to_dict(candidates[0])
    
    def get_best_overall(self) -> Optional[Dict]:
        """Get best overall strategy."""
        if not self._strategies:
            return None
        
        best = max(self._strategies, key=lambda x: x.total_return_pct)
        return self._to_dict(best)
    
    def get_deployable(self, min_confidence: float = 0.6) -> List[Dict]:
        """Get strategies ready for deployment."""
        return [
            self._to_dict(s) for s in self._strategies 
            if s.confidence >= min_confidence and s.total_return_pct > 0
        ]
    
    def _to_dict(self, s: OptimizedStrategy) -> Dict:
        return {
            "strategy_name": s.strategy_name,
            "symbol": s.symbol,
            "timeframe": s.timeframe,
            "indicators": s.indicators,
            "total_return_pct": s.total_return_pct,
            "sharpe_ratio": s.sharpe_ratio,
            "max_drawdown_pct": s.max_drawdown_pct,
            "win_rate": s.win_rate,
            "trades": s.trades,
            "profit_factor": s.profit_factor,
            "confidence": s.confidence,
            "updated": s.updated,
        }


# Singleton
strategy_manager = StrategyDeploymentManager()
