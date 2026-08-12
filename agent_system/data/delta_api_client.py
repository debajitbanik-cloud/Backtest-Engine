"""
Delta Exchange API Client with read-only and trading mode support.
Handles balance, positions, products, tickers, and authentication.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import aiohttp
import yaml


class DeltaAPIMode(str, Enum):
    READ_ONLY = "read_only"
    TRADING = "trading"


@dataclass
class DeltaCredentials:
    api_key: str = ""
    api_secret: str = ""
    mode: DeltaAPIMode = DeltaAPIMode.READ_ONLY
    environment: str = "production"  # production or testnet

    @property
    def has_auth(self) -> bool:
        return bool(self.api_key and self.api_secret)


@dataclass
class DeltaBalance:
    total_equity: float = 0.0
    available_margin: float = 0.0
    used_margin: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl_24h: float = 0.0
    margin_ratio: float = 0.0
    currency: str = "USDT"
    updated: str = ""


@dataclass
class DeltaPosition:
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    liquidation_price: float
    margin: float
    leverage: float
    unrealized_pnl: float
    realized_pnl: float
    margin_ratio: float
    updated: str


@dataclass
class DeltaProduct:
    symbol: str
    description: str
    quote_asset: str
    underlying_asset: str
    mark_price: float
    change_24h: float
    volume_24h: float
    open_interest: float
    funding_rate: float
    max_leverage: float
    contract_type: str
    is_active: bool
    updated: str


@dataclass
class DeltaTicker:
    symbol: str
    price: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h: float
    open_interest: float
    funding_rate: float
    updated: str


class DeltaAPIClient:
    """
    Delta Exchange API client supporting both read-only and trading modes.
    
    Read-only mode: Only market data endpoints (tickers, products, candles)
    Trading mode: Requires API keys; enables balance, positions, orders
    """
    
    def __init__(self, credentials: DeltaCredentials = None):
        self.credentials = credentials or DeltaCredentials()
        self._session: Optional[aiohttp.ClientSession] = None
        
        self.production_rest = "https://api.delta.exchange"
        self.testnet_rest = "https://cdn-ind.testnet.deltaex.org"
        # Allow override from config
        self.rest_url_override: Optional[str] = None
        
        self._last_request_time = 0
        self._rate_limit_interval = 0.2  # 5 requests per second
    
    @property
    def rest_base(self) -> str:
        if self.rest_url_override:
            return self.rest_url_override
        return self.testnet_rest if self.credentials.environment == "testnet" else self.production_rest
    
    @property
    def mode(self) -> DeltaAPIMode:
        return self.credentials.mode
    
    def set_mode(self, mode: str) -> bool:
        """Switch between read-only and trading mode."""
        try:
            self.credentials.mode = DeltaAPIMode(mode)
            return True
        except ValueError:
            return False
    
    def set_credentials(self, api_key: str, api_secret: str) -> None:
        """Set API credentials and switch to trading mode."""
        self.credentials.api_key = api_key
        self.credentials.api_secret = api_secret
        self.credentials.mode = DeltaAPIMode.TRADING
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def _rate_limit(self) -> None:
        """Simple rate limiting."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_interval:
            await asyncio.sleep(self._rate_limit_interval - elapsed)
        self._last_request_time = time.monotonic()
    
    def _sign_request(self, timestamp: str, method: str, path: str, query: str = "", body: str = "") -> str:
        """Generate HMAC SHA256 signature using Delta's canonical format."""
        auth = method + timestamp + path
        if method == "GET" and query:
            auth += query
        elif body:
            auth += body
        return hmac.new(
            self.credentials.api_secret.encode(),
            auth.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def _auth_headers(self, method: str, path: str, query: str = "", body: str = "") -> Dict[str, str]:
        """Generate authenticated headers."""
        if not self.credentials.has_auth:
            return {}
        
        timestamp = str(int(time.time()))
        signature = self._sign_request(timestamp, method, path, query, body)
        
        return {
            "api-key": self.credentials.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "Content-Type": "application/json",
        }
    
    async def _get(self, path: str, params: Dict = None, authenticated: bool = False) -> Dict:
        """GET request with optional auth."""
        await self._rate_limit()
        session = await self._ensure_session()
        
        query = urlencode(params) if params else ""
        url = f"{self.rest_base}{path}"
        if query:
            url += f"?{query}"
        
        # For authenticated requests, the query string includes the leading '?'
        auth_query = f"?{query}" if query else ""
        headers = self._auth_headers("GET", path, auth_query) if authenticated else {}
        
        async with session.get(url, headers=headers) as resp:
            if resp.status == 401:
                return {"error": "unauthorized", "message": "Invalid API credentials"}
            if resp.status == 403:
                return {"error": "forbidden", "message": "API key lacks permission for this endpoint"}
            if resp.status != 200:
                return {"error": f"http_{resp.status}", "message": await resp.text()}
            return await resp.json()
    
    async def _post(self, path: str, body: Dict = None) -> Dict:
        """POST request with auth."""
        await self._rate_limit()
        session = await self._ensure_session()
        
        body_str = json.dumps(body) if body else ""
        headers = self._auth_headers("POST", path, body=body_str)
        
        async with session.post(f"{self.rest_base}{path}", headers=headers, data=body_str) as resp:
            if resp.status == 401:
                return {"error": "unauthorized"}
            if resp.status != 200:
                return {"error": f"http_{resp.status}"}
            return await resp.json()
    
    async def health_check(self) -> Dict:
        """Check API health and auth status."""
        result = {
            "mode": self.credentials.mode,
            "environment": self.credentials.environment,
            "has_auth": self.credentials.has_auth,
            "connected": False,
            "error": None,
        }
        
        try:
            data = await self._get("/v2/products", {"page_size": 1})
            if "error" in data:
                result["error"] = data.get("error")
            else:
                result["connected"] = True
        except Exception as e:
            result["error"] = str(e)
        
        # If in trading mode, verify balance access
        if result["connected"] and self.credentials.mode == DeltaAPIMode.TRADING:
            if not self.credentials.has_auth:
                result["error"] = "Trading mode requires API keys"
                result["mode"] = "read_only"
                self.credentials.mode = DeltaAPIMode.READ_ONLY
        
        return result
    
    async def get_products(self, limit: int = 100) -> List[Dict]:
        """Get available products."""
        data = await self._get("/v2/products", {"page_size": limit})
        if "error" in data:
            return []
        return data.get("result", [])
    
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker for a single symbol."""
        data = await self._get(f"/v2/tickers/{symbol}")
        if "error" in data:
            return None
        return data.get("result", {})
    
    async def get_tickers(self, symbols: List[str] = None) -> List[Dict]:
        """Get tickers for multiple symbols."""
        if symbols:
            results = []
            for sym in symbols:
                ticker = await self.get_ticker(sym)
                if ticker:
                    results.append(ticker)
            return results
        
        # Get all tickers via products
        products = await self.get_products(100)
        results = []
        for p in products:
            sym = p.get("symbol", "")
            if sym:
                ticker = await self.get_ticker(sym)
                if ticker:
                    results.append(ticker)
        return results
    
    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Get top gaining assets."""
        products = await self.get_products(100)
        tickers = await self.get_tickers()
        
        # Combine product and ticker data
        combined = []
        ticker_map = {t.get("symbol", ""): t for t in tickers if t}
        
        for p in products:
            sym = p.get("symbol", "")
            ticker = ticker_map.get(sym, {})
            change = float(ticker.get("change_24h", 0) or 0)
            volume = float(ticker.get("volume", 0) or 0)
            
            if volume > 0:  # Only include actively traded
                combined.append({
                    "symbol": sym,
                    "change_24h": change,
                    "volume_24h": volume,
                    "mark_price": float(ticker.get("close", ticker.get("mark_price", 0)) or 0),
                    "funding_rate": float(p.get("funding_rate", 0) or 0),
                    "open_interest": float(ticker.get("open_interest", 0) or 0),
                    "max_leverage": float(p.get("max_leverage", 0) or 0),
                })
        
        # Sort by 24h change descending
        combined.sort(key=lambda x: x["change_24h"], reverse=True)
        return combined[:limit]
    
    async def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """Get top losing assets."""
        gainers = await self.get_top_gainers(100)
        gainers.sort(key=lambda x: x["change_24h"])
        return gainers[:limit]
    
    async def get_balance(self) -> Optional[Dict]:
        """Get account balance (requires trading mode)."""
        if self.credentials.mode != DeltaAPIMode.TRADING:
            return {"error": "Trading mode required for balance"}
        
        if not self.credentials.has_auth:
            return {"error": "API keys required"}
        
        data = await self._get("/v2/wallet/balances", authenticated=True)
        if "error" in data:
            return data
        
        result = data.get("result", {})
        meta = data.get("meta", {})
        
        # Delta Exchange balance structure varies; normalize
        balance = DeltaBalance()
        balance.updated = datetime.utcnow().isoformat()
        
        if isinstance(result, list):
            for entry in result:
                asset = entry.get("asset_symbol", entry.get("currency", ""))
                if asset in ("USD", "USDT", "USDC", "BTC"):
                    balance.available_margin += float(entry.get("available_balance", 0) or 0)
                    # blocked_margin already includes position + order margin
                    balance.used_margin += float(entry.get("blocked_margin", 0) or 0)
                    balance.total_equity = float(entry.get("balance", 0) or 0)
        elif isinstance(result, dict):
            balance.total_equity = float(result.get("equity", result.get("total_equity", 0)) or 0)
            balance.available_margin = float(result.get("available_balance", result.get("available_margin", 0)) or 0)
            balance.used_margin = float(result.get("margin_used", result.get("used_margin", 0)) or 0)
            balance.unrealized_pnl = float(result.get("unrealized_pnl", 0) or 0)
        
        # Delta meta often has net_equity
        if meta and meta.get("net_equity"):
            balance.total_equity = float(meta.get("net_equity", balance.total_equity))
        
        if balance.total_equity > 0:
            balance.margin_ratio = (balance.used_margin / balance.total_equity) * 100
        
        return {
            "total_equity": balance.total_equity,
            "available_margin": balance.available_margin,
            "used_margin": balance.used_margin,
            "unrealized_pnl": balance.unrealized_pnl,
            "realized_pnl_24h": balance.realized_pnl_24h,
            "margin_ratio": balance.margin_ratio,
            "currency": balance.currency,
            "updated": balance.updated,
        }
    
    async def get_positions(self) -> List[Dict]:
        """Get open positions (requires trading mode)."""
        if self.credentials.mode != DeltaAPIMode.TRADING:
            return []
        
        if not self.credentials.has_auth:
            return []
        
        positions = []
        
        # Delta requires product_id or underlying_asset_symbol
        # First get products, then query positions for each underlying
        products = await self.get_products(100)
        underlyings = set()
        for p in products:
            underlying = p.get("underlying_asset", {}).get("symbol")
            if underlying:
                underlyings.add(underlying)
        
        for underlying in underlyings:
            params = {"underlying_asset_symbol": underlying}
            data = await self._get("/v2/positions", params=params, authenticated=True)
            if "error" in data:
                continue
            
            result = data.get("result", [])
            if isinstance(result, dict):
                result = [result]
            
            for p in result:
                symbol = p.get("product_symbol", p.get("symbol", underlying))
                size = float(p.get("size", 0) or 0)
                side = "long" if size >= 0 else "short"
                abs_size = abs(size)
                
                # Fetch live ticker for mark price
                mark_price = 0.0
                liquidation_price = 0.0
                unrealized_pnl = 0.0
                leverage = 0.0
                position_margin = 0.0
                
                try:
                    ticker_data = await self._get(f"/v2/tickers/{symbol}")
                    if "error" not in ticker_data:
                        ticker_result = ticker_data.get("result", {})
                        mark_price = float(ticker_result.get("mark_price", 0) or 0)
                        entry_price = float(p.get("entry_price", 0) or 0)
                        if mark_price > 0 and entry_price > 0:
                            price_diff = mark_price - entry_price
                            direction_mult = 1 if side == "long" else -1
                            unrealized_pnl = direction_mult * price_diff * abs_size
                except Exception:
                    pass
                
                positions.append({
                    "symbol": symbol,
                    "side": side,
                    "size": abs_size,
                    "entry_price": float(p.get("entry_price", 0) or 0),
                    "mark_price": mark_price,
                    "liquidation_price": liquidation_price,
                    "margin": position_margin,
                    "leverage": leverage,
                    "unrealized_pnl": unrealized_pnl,
                    "realized_pnl": float(p.get("realized_pnl", 0) or 0),
                    "margin_ratio": float(p.get("margin_ratio", 0) or 0),
                    "updated": datetime.utcnow().isoformat(),
                })
        
        return positions
    
    async def get_orders(self) -> List[Dict]:
        """Get open orders (requires trading mode)."""
        if self.credentials.mode != DeltaAPIMode.TRADING:
            return []
        
        if not self.credentials.has_auth:
            return []
        
        data = await self._get("/v2/orders", authenticated=True)
        if "error" in data:
            return []
        
        return data.get("result", [])
    
    async def close(self) -> None:
        """Close session."""
        if self._session and not self._session.closed:
            await self._session.close()


# Load credentials from settings.yaml
def load_delta_credentials() -> DeltaCredentials:
    """Load Delta credentials from settings or environment."""
    settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    
    api_key = ""
    api_secret = ""
    environment = "production"
    rest_url = None
    
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            config = yaml.safe_load(f)
            delta_cfg = config.get("data_feed", {}).get("delta_exchange", {})
            api_key = delta_cfg.get("api_key", "")
            api_secret = delta_cfg.get("api_secret", "")
            environment = delta_cfg.get("environment", "production")
            rest_url = delta_cfg.get("rest_url")
    
    # Override from environment
    import os
    api_key = os.environ.get("DELTA_API_KEY", api_key)
    api_secret = os.environ.get("DELTA_API_SECRET", api_secret)
    
    mode = DeltaAPIMode.TRADING if (api_key and api_secret) else DeltaAPIMode.READ_ONLY
    
    creds = DeltaCredentials(
        api_key=api_key,
        api_secret=api_secret,
        mode=mode,
        environment=environment
    )
    
    # Set rest URL override after credentials load
    delta_client.rest_url_override = rest_url
    
    return creds


# Singleton client
delta_client = DeltaAPIClient()
delta_client.credentials = load_delta_credentials()
