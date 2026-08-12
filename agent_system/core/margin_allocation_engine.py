"""
Margin Allocation & Profit Potential Engine
===========================================
Aligns margin allotment with agent recommendations and estimates
profit potential using CCXT market analytics: volatility, volume,
liquidity (order book depth), funding rates, and open interest.

This is the analytics layer that bridges the recommendation agents
to the live Delta account.
"""
from __future__ import annotations
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from data.ccxt_delta_provider import ccxt_delta_provider


@dataclass
class MarginAllocation:
    symbol: str
    direction: str
    confidence: float
    recommended_margin_pct: float
    recommended_margin_usd: float
    max_margin_usd: float
    leverage: float
    estimated_profit_usd: float
    estimated_risk_usd: float
    risk_reward_ratio: float
    profit_probability: float
    timeframe: str
    volatility_atr_pct: float
    volume_ratio: float
    liquidity_depth_usd: float
    funding_rate_pct: float
    open_interest: float
    reasoning: List[str]


class MarginAllocationEngine:
    """
    Calculates margin allocation and profit potential for each recommendation.
    
    Uses CCXT analytics:
    - ATR for volatility-based stop/target distances
    - Volume ratio for confirmation strength
    - Order book depth for liquidity assessment
    - Funding rate for carry cost
    - Open interest for crowding/participation
    """

    def __init__(self, max_portfolio_risk: float = 0.10, risk_per_trade: float = 0.02,
                 max_leverage: float = 100.0, base_atr_multiplier: float = 2.0):
        self.max_portfolio_risk = max_portfolio_risk
        self.risk_per_trade = risk_per_trade
        self.max_leverage = max_leverage
        self.base_atr_multiplier = base_atr_multiplier

    def analyze_recommendation(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        account_equity: float,
        available_margin: float,
        timeframe: str = "15m",
        has_position: bool = False,
        position: Optional[Dict] = None,
    ) -> MarginAllocation:
        """
        Analyze a recommendation and compute margin allocation + profit potential.
        """
        reasoning = []
        
        # Fetch market analytics from CCXT
        analytics = self._fetch_market_analytics(symbol, timeframe)
        
        atr_pct = analytics["atr_pct"]
        volume_ratio = analytics["volume_ratio"]
        liquidity_depth = analytics["liquidity_depth"]
        funding_rate_pct = analytics["funding_rate_pct"]
        open_interest = analytics["open_interest"]
        
        # Volatility-based risk
        if atr_pct <= 0:
            atr_pct = 0.003  # Default 0.3% for crypto
        reasoning.append(f"ATR volatility: {atr_pct*100:.2f}%")
        
        # Volume confirmation
        if volume_ratio > 1.5:
            confidence_boost = 0.10
            reasoning.append(f"High volume ({volume_ratio:.1f}x avg) boosts confidence")
        elif volume_ratio < 0.5:
            confidence_boost = -0.15
            reasoning.append(f"Low volume ({volume_ratio:.1f}x avg) reduces confidence")
        else:
            confidence_boost = 0.0
        
        # Liquidity depth penalty
        if liquidity_depth > 0:
            reasoning.append(f"Order book depth: ${liquidity_depth:,.0f}")
            if liquidity_depth < 100000:
                confidence_boost -= 0.10
                reasoning.append("Thin liquidity reduces confidence")
            elif liquidity_depth > 500000:
                confidence_boost += 0.05
                reasoning.append("Deep liquidity supports entry")
        
        # Funding rate
        if funding_rate_pct is not None:
            reasoning.append(f"Funding rate: {funding_rate_pct*100:.4f}%")
        
        # Open interest
        if open_interest is not None:
            reasoning.append(f"Open interest: {open_interest:,.0f} contracts")
        
        # Effective confidence
        effective_confidence = min(0.95, max(0.05, confidence + confidence_boost))
        reasoning.append(f"Effective confidence: {effective_confidence*100:.1f}%")
        
        # Position sizing
        # Use a meaningful base allocation: 5% to 15% of equity scaled by confidence
        base_margin_pct = 0.05 + effective_confidence * 0.10  # 5% to 15%
        
        # Volatility adjustment: higher volatility reduces allocation
        if atr_pct < 0.001:
            atr_pct = 0.001  # Floor at 0.1% to avoid unrealistic numbers
        
        volatility_factor = min(1.2, max(0.6, 0.001 / atr_pct))
        base_margin_pct *= volatility_factor
        
        # Cap at 15% per trade
        base_margin_pct = min(base_margin_pct, 0.15)
        
        # If existing position, reduce additional allocation
        if has_position and position:
            existing_pct = position.get("size", 0) * position.get("entry_price", 0) / account_equity if account_equity > 0 else 0
            base_margin_pct *= max(0.3, 1.0 - existing_pct)
            reasoning.append("Existing position reduces additional allocation")
        
        # Margin allocation
        recommended_margin_usd = account_equity * base_margin_pct
        recommended_margin_usd = min(recommended_margin_usd, available_margin * 0.95)
        recommended_margin_pct = recommended_margin_usd / account_equity * 100 if account_equity > 0 else 0
        
        # Leverage: volatility-based, now targeted to 50-100x range
        leverage = min(self.max_leverage, max(50.0, 5.0 / (atr_pct * 100 + 0.5)))
        leverage = min(leverage, 100.0)  # Hard cap 100x
        reasoning.append(f"Suggested leverage: {leverage:.1f}x")
        
        # Profit potential
        # Estimated target = entry ± ATR * multiplier
        # Use direction and confidence to estimate
        if direction == "long":
            target_pct = atr_pct * self.base_atr_multiplier
            stop_pct = -atr_pct * 1.0
        elif direction == "short":
            target_pct = -atr_pct * self.base_atr_multiplier
            stop_pct = atr_pct * 1.0
        else:
            target_pct = 0.0
            stop_pct = 0.0
        
        # Profit/risk is calculated on margin used, not leveraged notional.
        # Leverage reduces required margin, but profit on the allocated margin
        # scales only with price movement.
        estimated_profit_usd = recommended_margin_usd * target_pct
        estimated_risk_usd = recommended_margin_usd * abs(stop_pct)
        
        # Risk/reward
        risk_reward_ratio = abs(target_pct / stop_pct) if stop_pct != 0 else 0
        
        # Profit probability (based on confidence and volume)
        profit_probability = min(0.85, max(0.10, effective_confidence * 0.6 + (volume_ratio - 1.0) * 0.15))
        
        reasoning.append(f"Target: {abs(target_pct)*100:.2f}% move, Stop: {abs(stop_pct)*100:.2f}% move")
        reasoning.append(f"Estimated profit potential: ${estimated_profit_usd:,.2f}")
        reasoning.append(f"Estimated risk: ${estimated_risk_usd:,.2f}")
        
        return MarginAllocation(
            symbol=symbol,
            direction=direction,
            confidence=effective_confidence,
            recommended_margin_pct=recommended_margin_pct,
            recommended_margin_usd=recommended_margin_usd,
            max_margin_usd=account_equity * 0.15,
            leverage=leverage,
            estimated_profit_usd=estimated_profit_usd,
            estimated_risk_usd=estimated_risk_usd,
            risk_reward_ratio=risk_reward_ratio,
            profit_probability=profit_probability,
            timeframe=timeframe,
            volatility_atr_pct=atr_pct * 100,
            volume_ratio=volume_ratio,
            liquidity_depth_usd=liquidity_depth,
            funding_rate_pct=(funding_rate_pct * 100) if funding_rate_pct is not None else 0,
            open_interest=open_interest,
            reasoning=reasoning,
        )

    def _fetch_market_analytics(self, symbol: str, timeframe: str) -> Dict[str, float]:
        """Fetch market analytics from CCXT."""
        result = {
            "atr_pct": 0.0,
            "volume_ratio": 1.0,
            "liquidity_depth": 0.0,
            "funding_rate_pct": None,
            "open_interest": None,
        }
        
        try:
            # Normalize symbol for CCXT
            ccxt_symbol = symbol
            if not symbol.endswith(":USDT") and symbol.endswith("USDT"):
                ccxt_symbol = f"{symbol[:-4]}/USDT:{symbol[-4:]}"
            
            # Try OHLCV for ATR/volume
            try:
                candles = ccxt_delta_provider.fetch_ohlcv(ccxt_symbol, timeframe, limit=100)
                if candles and len(candles) >= 14:
                    result["atr_pct"], result["volume_ratio"] = self._calc_atr_volume(candles)
            except Exception:
                pass
            
            # Try order book for liquidity
            try:
                orderbook = ccxt_delta_provider.fetch_order_book(ccxt_symbol, 20)
                if orderbook:
                    result["liquidity_depth"] = self._calc_liquidity_depth(orderbook)
            except Exception:
                pass
            
            # Try funding rate
            try:
                funding = ccxt_delta_provider.fetch_funding_rate(ccxt_symbol)
                if funding:
                    result["funding_rate_pct"] = float(funding.get("fundingRate", 0) or 0)
            except Exception:
                pass
            
            # Try open interest
            try:
                oi = ccxt_delta_provider.fetch_open_interest(ccxt_symbol)
                if oi:
                    result["open_interest"] = float(oi)
            except Exception:
                pass
            
        except Exception:
            pass
        
        return result

    def _calc_atr_volume(self, candles: List[List]) -> Tuple[float, float]:
        """Calculate ATR% and volume ratio from OHLCV candles."""
        if len(candles) < 15:
            return 0.003, 1.0
        
        highs = np.array([c[2] for c in candles], dtype=float)
        lows = np.array([c[3] for c in candles], dtype=float)
        closes = np.array([c[4] for c in candles], dtype=float)
        volumes = np.array([c[5] for c in candles], dtype=float)
        
        # True range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        current_price = closes[-1] if closes[-1] > 0 else 1
        atr_pct = atr / current_price
        
        # Volume ratio (recent vs average)
        avg_volume = np.mean(volumes[:-5]) if len(volumes) > 5 else np.mean(volumes)
        recent_volume = np.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        return float(atr_pct), float(volume_ratio)

    def _calc_liquidity_depth(self, orderbook: Dict) -> float:
        """Calculate total liquidity depth from order book."""
        total = 0.0
        try:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            
            for side in [bids, asks]:
                for level in side[:10]:
                    if len(level) >= 2:
                        price = float(level[0])
                        amount = float(level[1])
                        total += price * amount
        except Exception:
            pass
        return total

    def _summarize_recommendations(
        self,
        allocations: List[MarginAllocation],
        recommendations: Dict[str, Any],
    ) -> str:
        """Generate a human-readable summary of why agents made these recommendations."""
        if not allocations:
            return "No recommendations available."
        
        parts = []
        
        # Aggregate market context
        avg_confidence = statistics.mean([a.confidence for a in allocations]) if allocations else 0
        avg_volume = statistics.mean([a.volume_ratio for a in allocations]) if allocations else 1
        avg_vol = statistics.mean([a.volatility_atr_pct for a in allocations]) if allocations else 0
        
        market_bias = "bullish" if sum(1 for a in allocations if a.direction == "long") > len(allocations) / 2 else \
                      "bearish" if sum(1 for a in allocations if a.direction == "short") > len(allocations) / 2 else "mixed"
        
        parts.append(f"Market bias: {market_bias}")
        parts.append(f"Average confidence: {avg_confidence*100:.1f}%")
        parts.append(f"Average volume ratio: {avg_volume:.1f}x")
        parts.append(f"Average volatility: {avg_vol:.2f}%")
        
        # Per-symbol reasoning
        for a in allocations:
            direction_text = "buy" if a.direction == "long" else "sell" if a.direction == "short" else "hold"
            parts.append(
                f"{a.symbol}: {direction_text} with {a.confidence*100:.1f}% confidence "
                f"(margin ${a.recommended_margin_usd:,.2f}, est. profit ${a.estimated_profit_usd:,.2f})"
            )
            for r in a.reasoning[:3]:  # Top 3 reasons
                parts.append(f"  - {r}")
        
        return "\n".join(parts)


# Global engine
margin_engine = MarginAllocationEngine()
