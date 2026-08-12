"""
Options Scanner & Payoff Engine
================================
Continuously scans CCXT Delta options for OTM contracts with
inflated prices that can be sold.

Also computes Black-Scholes fair value and payoff simulations
for visualization.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.stats import norm


@dataclass
class OptionCandidate:
    symbol: str
    underlying: str
    strike: float
    expiry: datetime
    option_type: str  # call / put
    mark_price: float
    fair_value: float
    premium_pct: float  # (mark - fair) / fair
    iv: Optional[float]
    spot_price: float
    otm_pct: float  # how far OTM in %
    liquidity: float
    volume_24h: float
    greeks: Dict[str, float]
    reason: str


class BlackScholesPricer:
    """Black-Scholes option pricing and Greeks for European options."""

    @staticmethod
    def price(call: bool, S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0 or sigma <= 0:
            intrinsic = max(0, S - K) if call else max(0, K - S)
            return intrinsic

        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if call:
            return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    @staticmethod
    def greeks(call: bool, S: float, K: float, T: float, r: float, sigma: float) -> Dict[str, float]:
        """Compute delta, gamma, theta, vega, rho."""
        if T <= 0 or sigma <= 0:
            delta = 1.0 if call and S > K else (-1.0 if not call and K > S else 0.0)
            return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        nd1 = norm.pdf(d1)
        if call:
            delta = norm.cdf(d1)
            theta = (-(S * nd1 * sigma) / (2 * math.sqrt(T))
                     - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365.0
            rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
        else:
            delta = norm.cdf(d1) - 1.0
            theta = (-(S * nd1 * sigma) / (2 * math.sqrt(T))
                     + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365.0
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0

        gamma = nd1 / (S * sigma * math.sqrt(T))
        vega = S * nd1 * math.sqrt(T) / 100.0

        return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": rho}

    @staticmethod
    def implied_vol(call: bool, price: float, S: float, K: float, T: float, r: float) -> float:
        """Newton-Raphson IV solve."""
        if T <= 0 or price <= 0:
            return 0.0

        sigma = 0.5
        for _ in range(50):
            try:
                d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
                vega = S * math.sqrt(T) * norm.pdf(d1)
                if vega < 1e-10:
                    break
                diff = BlackScholesPricer.price(call, S, K, T, r, sigma) - price
                sigma = sigma - diff / vega
                sigma = max(0.05, min(sigma, 3.0))
            except Exception:
                break

        return sigma


class OptionsScanner:
    """
    Scans Delta options for sellable OTM contracts.
    """

    def __init__(self, min_premium_pct: float = 0.25, min_otm_pct: float = 0.02,
                 min_days: float = 1, max_days: float = 30, risk_free_rate: float = 0.04):
        self.min_premium_pct = min_premium_pct
        self.min_otm_pct = min_otm_pct
        self.min_days = min_days
        self.max_days = max_days
        self.risk_free_rate = risk_free_rate

    def scan(self, limit: int = 50) -> List[Dict]:
        """Scan all Delta option markets for inflated OTM contracts."""
        try:
            import ccxt
            exchange = ccxt.delta()
            markets = exchange.load_markets()
        except Exception as e:
            return [{"error": f"Failed to load markets: {str(e)[:120]}"}]

        candidates = []
        option_markets = [m for m in markets.values() if m.get("option")]

        # Batch fetch all option tickers once
        option_symbols = [m.get("symbol", "") for m in option_markets]
        try:
            all_tickers = exchange.fetch_tickers(option_symbols)
        except Exception:
            all_tickers = {}

        # Cache spot tickers per underlying
        spot_cache = {}

        for market in option_markets:
            symbol = market.get("symbol", "")
            strike = market.get("strike")
            expiry_ms = market.get("expiry")
            option_type = market.get("optionType", "").lower()
            underlying = market.get("base", "")

            if not strike or not expiry_ms or not option_type:
                continue

            # Time to expiry in years
            now_ms = datetime.now(timezone.utc).timestamp() * 1000
            T_years = (expiry_ms - now_ms) / (1000 * 86400 * 365)
            days_to_expiry = T_years * 365

            if days_to_expiry < self.min_days or days_to_expiry > self.max_days:
                continue

            ticker = all_tickers.get(symbol)
            if not ticker:
                continue

            mark_price = float(ticker.get("last", ticker.get("close", 0)) or 0)
            if mark_price <= 0:
                continue

            # Get underlying spot price from cache or fetch
            spot_price = spot_cache.get(underlying)
            if spot_price is None:
                for spot_symbol in [f"{underlying}/USDT:USDT", f"{underlying}/USDT"]:
                    try:
                        spot_ticker = exchange.fetch_ticker(spot_symbol)
                        spot_price = float(spot_ticker.get("last", spot_ticker.get("close", 0)) or 0)
                        if spot_price > 0:
                            break
                    except Exception:
                        continue
                if spot_price is None:
                    spot_price = 0
                spot_cache[underlying] = spot_price

            if spot_price <= 0:
                continue

            # Calculate OTM distance
            is_call = option_type == "call"
            if is_call:
                otm_pct = (strike - spot_price) / spot_price
            else:
                otm_pct = (spot_price - strike) / spot_price

            if otm_pct < self.min_otm_pct:
                continue

            # Calculate IV from market price
            iv = BlackScholesPricer.implied_vol(is_call, mark_price, spot_price, strike, T_years, self.risk_free_rate)

            # Estimate fair value with conservative expected vol
            expected_iv = 0.35
            fair_value = BlackScholesPricer.price(is_call, spot_price, strike, T_years, self.risk_free_rate, expected_iv)

            premium_pct = (mark_price - fair_value) / fair_value if fair_value > 0 else 0

            if premium_pct < self.min_premium_pct:
                continue

            # Volume
            volume_24h = float(ticker.get("quoteVolume", 0) or 0)
            if volume_24h < 100:
                continue

            # Greeks based on market IV
            greeks = BlackScholesPricer.greeks(is_call, spot_price, strike, T_years, self.risk_free_rate, iv / 100.0 if iv else expected_iv)

            candidates.append({
                "symbol": symbol,
                "underlying": underlying,
                "strike": strike,
                "expiry": datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).isoformat(),
                "option_type": option_type,
                "mark_price": mark_price,
                "fair_value": fair_value,
                "premium_pct": premium_pct * 100,
                "iv": iv * 100,
                "spot_price": spot_price,
                "otm_pct": otm_pct * 100,
                "days_to_expiry": days_to_expiry,
                "volume_24h": volume_24h,
                "greeks": {k: round(v, 6) for k, v in greeks.items()},
                "reason": self._reason(is_call, otm_pct, premium_pct, iv),
            })

        # Sort by premium (highest inflation first)
        candidates.sort(key=lambda x: x["premium_pct"], reverse=True)
        return candidates[:limit]

    def portfolio_greeks(self, candidates: List[Dict], top_n: int = 5) -> Dict[str, float]:
        """Sum Greeks for the top N sell candidates (short positions)."""
        selected = candidates[:top_n]
        totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
        for c in selected:
            g = c.get("greeks", {})
            sign = -1.0  # short option
            for k in totals:
                totals[k] += sign * g.get(k, 0.0)
        return {k: round(v, 6) for k, v in totals.items()}

    def _reason(self, is_call: bool, otm_pct: float, premium_pct: float, iv: float) -> str:
        direction = "call" if is_call else "put"
        return (
            f"OTM {direction} {otm_pct*100:.1f}% from spot, "
            f"IV {iv*100:.0f}% appears inflated, premium {premium_pct*100:.1f}% above fair"
        )


@dataclass
class PayoffSimulation:
    spot_prices: List[float]
    long_call_pnl: List[float]
    short_call_pnl: List[float]
    long_put_pnl: List[float]
    short_put_pnl: List[float]
    break_even_long_call: float
    break_even_short_call: float
    max_profit_short_call: float
    max_loss_short_call: float
    max_profit_short_put: float
    max_loss_short_put: float


class PayoffEngine:
    """Generates option payoff simulations."""

    def simulate(self, spot: float, strike: float, premium: float, option_type: str,
                 range_pct: float = 0.25, points: int = 100) -> PayoffSimulation:
        price_range = np.linspace(spot * (1 - range_pct), spot * (1 + range_pct), points)

        if option_type == "call":
            long_call = np.maximum(price_range - strike, 0) - premium
            short_call = -long_call
            long_put = np.maximum(strike - price_range, 0) - premium
            short_put = -long_put
        else:
            long_put = np.maximum(strike - price_range, 0) - premium
            short_put = -long_put
            long_call = np.maximum(price_range - strike, 0) - premium
            short_call = -long_call

        return PayoffSimulation(
            spot_prices=price_range.tolist(),
            long_call_pnl=long_call.tolist(),
            short_call_pnl=short_call.tolist(),
            long_put_pnl=long_put.tolist(),
            short_put_pnl=short_put.tolist(),
            break_even_long_call=strike + premium,
            break_even_short_call=strike + premium,
            max_profit_short_call=premium,
            max_loss_short_call=float("inf"),
            max_profit_short_put=premium,
            max_loss_short_put=strike - premium,
        )


# Global instances
options_scanner = OptionsScanner()
payoff_engine = PayoffEngine()
