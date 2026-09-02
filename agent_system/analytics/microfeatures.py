"""
Micro-Feature Engine.

Computes cross-sectional "micro" features from live exchange data that the
standard OHLCV FeatureFactory cannot produce: derivative metrics (funding, open
interest, basis), options-implied volatility surface features, cross-asset
correlations/dominance/sector momentum, journal/account behavior features, and
event/context features from the economic calendar.

All functions accept plain dicts/lists (as returned by the bridge) and return a
flat {name: value} dict grouped by category. No pandas time-index is required;
each family is independent so it can be computed lazily in the bridge.

These plug into the `FeatureCategory.DERIVATIVES`, `.CROSS_ASSET`, `.TIME`, and
`.MICROSTRUCTURE` slots that the FeatureFactory leaves as placeholders.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


def _f(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b is None or b == 0 or not math.isfinite(b):
        return default
    return a / b if math.isfinite(a) else default


# ─────────────────────────────────────────────────────────────────────────────
# 1. Derivative features (B1) — from a list of perpetual tickers
# ─────────────────────────────────────────────────────────────────────────────
def derivative_features(
    tickers: Sequence[Dict[str, Any]],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract derivative micro-features from perpetual futures tickers.

    When `symbol` is given, features are computed for that single perpetual.
    When omitted, cross-sectional stats across all perpetuals are computed.
    """
    perps = [t for t in tickers if isinstance(t, dict) and t.get("symbol")]
    if not perps:
        return {"category": "derivatives", "available": False, "features": {}}

    feats: Dict[str, Any] = {}

    if symbol:
        t = next((x for x in perps if x.get("symbol") == symbol), None)
        if t is None:
            return {"category": "derivatives", "available": False, "features": {}}
        spot = _f(t.get("mark_price", t.get("close", 0)))
        feats["funding_rate"] = _f(t.get("funding_rate"))
        feats["open_interest"] = _f(t.get("oi_value_usd"))
        feats["oi_contracts"] = _f(t.get("oi_contracts"))
        feats["oi_change_6h"] = _f(t.get("oi_change_usd_6h"))
        feats["mark_basis"] = _f(t.get("mark_basis"))
        feats["basis_pct"] = _safe_div(_f(t.get("mark_basis")), spot) * 100
        feats["leverage"] = _f(t.get("leverage"))
        feats["turnover_24h"] = _f(t.get("turnover_usd"))
        feats["oi_to_turnover"] = _safe_div(feats["open_interest"], feats["turnover_24h"])
        feats["funding_oi_product"] = feats["funding_rate"] * feats["open_interest"]
        feats["spot"] = spot
        return {
            "category": "derivatives",
            "available": True,
            "symbol": symbol,
            "features": feats,
        }

    # Cross-sectional stats across all perpetuals
    funds = [_f(t.get("funding_rate")) for t in perps]
    ois = [_f(t.get("oi_value_usd")) for t in perps]
    bases = [_f(t.get("mark_basis")) for t in perps]
    turnovers = [_f(t.get("turnover_usd")) for t in perps]

    def stdev(xs: List[float]) -> float:
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

    n = len(perps)
    feats = {
        "num_perps": n,
        "avg_funding_rate": sum(funds) / n,
        "max_funding_rate": max(funds),
        "min_funding_rate": min(funds),
        "pct_positive_funding": round(100 * sum(1 for f in funds if f > 0) / n, 2),
        "std_funding_rate": round(stdev(funds), 6),
        "total_open_interest_usd": sum(ois),
        "max_open_interest_usd": max(ois),
        "total_turnover_24h": sum(turnovers),
        "avg_basis_pct": 0.0 if not bases else _safe_div(sum(bases), len(bases)),
        "percentile_basis_99": 0.0,
    }
    # basis percentile (only for perps that expose mark basis)
    valid_bases = [b for b in bases if b != 0]
    if len(valid_bases) >= 20:
        valid_bases.sort()
        feats["percentile_basis_99"] = valid_bases[int(0.99 * (len(valid_bases) - 1))]

    return {"category": "derivatives", "available": True, "symbol": None, "features": feats}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Options implied-vol features (B2) — from an options chain list
# ─────────────────────────────────────────────────────────────────────────────
def _ttm(expiry: Optional[str]) -> Optional[float]:
    """Years to expiration from 'YYYY-MM-DD'."""
    if not expiry:
        return None
    try:
        exp = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (exp - now).total_seconds() / 86400.0
        return max(days / 365.0, 1e-6)
    except (TypeError, ValueError):
        return None


def options_iv_features(chain: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract implied-volatility surface features from an options chain.

    `chain` items: {type, strike, expiry, mark_iv, mark_price, greeks:{...}, open_interest}.
    """
    calls = [c for c in chain if isinstance(c, dict) and c.get("type") == "call"]
    puts = [c for c in chain if isinstance(c, dict) and c.get("type") == "put"]
    if not calls and not puts:
        return {"category": "options_iv", "available": False, "features": {}}

    feats: Dict[str, Any] = {}
    feats["num_calls"] = len(calls)
    feats["num_puts"] = len(puts)
    feats["put_call_ratio"] = _safe_div(len(puts), len(calls)) if calls else 0.0

    def iv_stats(items: List[Dict]) -> Dict[str, float]:
        ivals = [_f(x.get("mark_iv")) for x in items]
        ivals = [v for v in ivals if v > 0]
        if not ivals:
            return {"iv": 0.0, "max_iv": 0.0, "min_iv": 0.0, "std_iv": 0.0}
        m = sum(ivals) / len(ivals)
        sd = math.sqrt(sum((v - m) ** 2 for v in ivals) / len(ivals)) if len(ivals) > 1 else 0.0
        return {"iv": m, "max_iv": max(ivals), "min_iv": min(ivals), "std_iv": sd}

    c = iv_stats(calls)
    p = iv_stats(puts)
    feats["call_iv"] = round(c["iv"] * 100, 2)
    feats["put_iv"] = round(p["iv"] * 100, 2)
    feats["iv_skew"] = round((p["iv"] - c["iv"]) * 100, 2)  # positive = puts more expensive
    feats["call_iv_std"] = round(c["std_iv"] * 100, 2)
    feats["put_iv_std"] = round(p["std_iv"] * 100, 2)

    # Term structure: avg IV by expiry bucket (near vs far)
    ivs = [_f(x.get("mark_iv")) for x in chain if _f(x.get("mark_iv")) > 0]
    feats["avg_iv"] = round((sum(ivs) / len(ivs)) * 100, 2) if ivs else 0.0

    # Put-call IV ratio (skew proxy averaged over strikes)
    if c["iv"] > 0:
        feats["put_call_iv_ratio"] = round(_safe_div(p["iv"], c["iv"]), 3)
    else:
        feats["put_call_iv_ratio"] = 0.0

    # Open interest by side
    oi_call = sum(_f(x.get("open_interest")) for x in calls)
    oi_put = sum(_f(x.get("open_interest")) for x in puts)
    feats["put_call_oi_ratio"] = _safe_div(oi_put, oi_call) if oi_call else 0.0

    # ATM-implied 1-day move (using nearest strike to spot)
    try:
        mids = [(x, abs(_f(x.get("strike")) - _f(x.get("spot", 0)))) for x in chain if _f(x.get("strike")) > 0]
        if mids:
            atm = min(mids, key=lambda p: p[1])[0]
            t = _ttm(atm.get("expiry"))
            iv = _f(atm.get("mark_iv"))
            spot = _f(atm.get("spot", 0))
            if t and iv > 0 and spot > 0:
                feats["atm_iv_1d_move_pct"] = round(iv * math.sqrt(t) * 100, 2)
                feats["atm_expiry_years"] = round(t, 4)
    except Exception:
        pass

    return {"category": "options_iv", "available": True, "features": feats}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cross-asset features (B3) — from a list of all tickers (perps+spot)
# ─────────────────────────────────────────────────────────────────────────────
def cross_asset_features(tickers: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Cross-asset correlations, BTC dominance, and sector momentum.

    `tickers`: mixed list of perpetuals/spot; each has symbol, mark_price/close,
    mark_change_24h, top_tag.
    """
    rows = [t for t in tickers if isinstance(t, dict) and t.get("symbol")]
    if len(rows) < 5:
        return {"category": "cross_asset", "available": False, "features": {}}

    # Price lookup by base symbol (strip trailing USD)
    def base(sym: str) -> str:
        s = sym.upper()
        for suf in ("USD", "USDT", "USDC"):
            if s.endswith(suf):
                return s[: -len(suf)]
        if s.endswith("USDTPERP"):
            return s[: -len("USDTPERP")]
        return s

    prices = {}
    memes = []
    sectors: Dict[str, List[float]] = {}
    _METALS = {"XAU", "XAG"}

    for t in rows:
        b = base(t.get("symbol", ""))
        spot = _f(t.get("mark_price", t.get("close", 0)))
        chg = _f(t.get("mark_change_24h", t.get("ltp_change_24h", 0)))
        if spot <= 0:
            continue
        if b not in _METALS:
            prices.setdefault(b, spot)
        tag = t.get("top_tag") or "crypto"
        sectors.setdefault(tag, []).append(chg)
        if b in ("DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "MEME"):
            memes.append(chg)

    feats: Dict[str, Any] = {}
    feats["num_assets"] = len(prices)

    btc = prices.get("BTC", 0)
    eth = prices.get("ETH", 0)
    # "dominance" is a price-weighted share of BTC/ETH within the crypto universe
    # (metals excluded) — useful as a momentum/rotation gauge, NOT a market-cap metric.
    total_crypto = sum(prices.values())
    feats["btc_price"] = btc
    feats["eth_price"] = eth
    feats["btc_dominance"] = round(_safe_div(btc, total_crypto) * 100, 2)
    feats["eth_btc_ratio"] = round(_safe_div(eth, btc), 4)
    feats["eth_dominance"] = round(_safe_div(eth, total_crypto) * 100, 2)

    def avg(xs: List[float]) -> float:
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    feats["avg_crypto_24h"] = avg([chg for tag, chgs in sectors.items() if tag == "crypto" for chg in chgs])
    feats["avg_meme_24h"] = avg(memes) if memes else 0.0
    feats["avg_meme_btc_spread"] = round(feats.get("avg_meme_24h", 0) - feats.get("avg_crypto_24h", 0), 2)

    sector_avg = {tag: round(sum(chgs) / len(chgs), 2) for tag, chgs in sectors.items() if chgs}
    feats["sector_momentum"] = sector_avg
    feats["num_sectors"] = len(sector_avg)

    return {
        "category": "cross_asset",
        "available": True,
        "features": feats,
        "sector_breakdown": sector_avg,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Journal / account behavior features (D) — from journal stats + account
# ─────────────────────────────────────────────────────────────────────────────
def journal_features(stats: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Behavioral micro-features derived from the trade journal.

    `stats`: the JSON shape returned by /journal/stats.
    """
    if not stats:
        return {"category": "journal", "available": False, "features": {}}

    feats: Dict[str, Any] = {}

    def g(*keys: str) -> Any:
        cur = stats
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur

    total = g("total")
    wins = g("wins")
    losses = g("losses")
    feats["total_trades"] = _f(total)
    feats["wins"] = _f(wins)
    feats["losses"] = _f(losses)
    feats["win_rate"] = round(_safe_div(feats["wins"], feats["total_trades"]) * 100, 1)
    feats["profit_factor"] = _f(g("profit_factor"))
    feats["avg_win_r"] = _f(g("avg_win"))
    feats["avg_loss_r"] = _f(g("avg_loss"))
    feats["total_pnl"] = _f(g("net_pnl", "pnl"))
    feats["max_drawdown"] = _f(g("max_drawdown"))
    if feats["avg_loss_r"] != 0:
        feats["expectancy_r"] = round(
            feats["win_rate"] / 100 * feats["avg_win_r"]
            - (1 - feats["win_rate"] / 100) * feats["avg_loss_r"], 3
        )
    else:
        feats["expectancy_r"] = 0.0

    return {"category": "journal", "available": True, "features": feats}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Event / context features (E) — from economic calendar + account
# ─────────────────────────────────────────────────────────────────────────────
def event_features(
    calendar: Optional[Dict[str, Any]],
    account: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Context micro-features from the upcoming-events calendar and account state."""
    feats: Dict[str, Any] = {}
    upcoming = (calendar or {}).get("upcoming") or []
    feats["num_upcoming_events"] = len(upcoming)

    high_next = None
    next_event = (calendar or {}).get("next_event")
    if next_event:
        ts = _f(next_event.get("timestamp"))
        ttm_secs = _f(next_event.get("time_until_min")) * 60 if next_event.get("time_until_min") is not None else None
        if ttm_secs is None and ts:
            ttm_secs = max(ts - datetime.now(timezone.utc).timestamp(), 0)
        feats["next_event_title"] = next_event.get("title", "")
        feats["next_event_minutes"] = round(_f(ttm_secs) / 60, 1) if ttm_secs is not None else 0.0
        feats["next_event_impact"] = next_event.get("impact", "")

    for ev in upcoming:
        imp = (ev or {}).get("impact")
        if imp and (imp == "High" or imp == "high"):
            high_next = ev
            break
    if high_next:
        ttm_secs = _f(high_next.get("time_until_min")) * 60
        feats["high_impact_event_minutes"] = round(ttm_secs / 60, 1)
        feats["high_impact_event_title"] = high_next.get("title", "")
    else:
        feats["high_impact_event_minutes"] = 0.0
        feats["high_impact_event_title"] = ""

    # Account-derived context
    if account:
        feats["account_equity"] = _f(account.get("equity", account.get("balance")))
        feats["account_free_margin"] = _f(account.get("free_margin"))
        feats["account_used_margin_pct"] = round(_f(account.get("used_margin_pct")), 2)
        u = _f(account.get("unrealized_pnl"))
        ref = feats.get("account_equity") or _f(account.get("balance"))
        feats["account_unreal_pnl"] = u
        feats["account_unreal_pnl_pct"] = round(_safe_div(u, ref) * 100, 2)

    return {"category": "event", "available": True, "features": feats}


def compute_all(
    tickers: Optional[Sequence[Dict[str, Any]]] = None,
    symbol: Optional[str] = None,
    options_chain: Optional[Sequence[Dict[str, Any]]] = None,
    journal_stats: Optional[Dict[str, Any]] = None,
    calendar: Optional[Dict[str, Any]] = None,
    account: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute all available cross-sectional micro-feature families at once."""
    result: Dict[str, Any] = {}

    if tickers:
        result["derivatives"] = derivative_features(tickers, symbol)
        result["cross_asset"] = cross_asset_features(tickers)
        # Also add a single-symbol derivative view when symbol requested
        if symbol:
            result["derivatives_symbol"] = derivative_features(tickers, symbol)
            base = symbol.replace("USD", "")
            for fam in (result.get("cross_asset") or {}).get("sector_breakdown") or {}:
                pass
    if options_chain:
        result["options_iv"] = options_iv_features(options_chain)
    if journal_stats:
        result["journal"] = journal_features(journal_stats)
    if calendar:
        result["event"] = event_features(calendar, account)

    return result
