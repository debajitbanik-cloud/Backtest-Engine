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
import socket

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


def diagnose_delta_error(error_code: str, environment: str = "production") -> Dict[str, Any]:
    """Cloud-agent style diagnosis: explanation, likely causes, and fix steps."""
    host = "cdn-ind.testnet.deltaex.org" if environment == "testnet" else "api.india.delta.exchange"
    guides = {
        "connected": {
            "level": "success",
            "title": "Connection successful",
            "explanation": "Your API key and secret were accepted by Delta Exchange and live account data is available.",
            "causes": [],
            "steps": [
                "You can now switch to Trading mode and view balance, positions, and run the selected strategy.",
            ],
        },
        "connected_readonly": {
            "level": "info",
            "title": "Connected (read-only)",
            "explanation": "Delta Exchange is reachable. No API key was provided, so the system is using public market data only.",
            "causes": [],
            "steps": [
                "Enter your API key and secret below and click Connect & Test to enable Trading mode.",
            ],
        },
        "delta_unreachable": {
            "level": "error",
            "title": "Delta Exchange API unreachable",
            "explanation": "The bridge could not reach Delta's REST API. This is a network/connectivity issue, not an authentication problem.",
            "causes": [
                "No outbound internet access from this host/container.",
                "Firewall or proxy blocking https://" + host,
                "Temporary Delta outage or DNS failure.",
            ],
            "steps": [
                "Verify reachability: curl -s https://" + host + "/v2/products?page_size=1",
                "If running in Docker, ensure the container has network access (not --network=none) and DNS works.",
                "Check any corporate firewall / VPN that may block the endpoint.",
            ],
        },
        "unauthorized": {
            "level": "error",
            "title": "API key or secret rejected",
            "explanation": (
                "Delta Exchange returned an authentication failure. Importantly, Delta returns the SAME generic error "
                "for a wrong key/secret, an inactive key, AND an IP-address whitelist mismatch -- so the exact cause "
                "cannot be determined from the response alone. Walk through the checklist below."
            ),
            "causes": [
                "The API key or secret was copied incorrectly (extra spaces, missing characters).",
                "The key is not yet activated -- Delta often requires email confirmation after creation.",
                "IP whitelist: your key is restricted to specific IPs and this host's IP is not on the list.",
                "Environment mismatch: a Testnet key used against Production (or vice-versa) -- they are separate.",
                "The key was deleted or regenerated on Delta's side.",
            ],
            "steps": [
                "Re-copy the API key and secret exactly (no leading/trailing spaces), then test again.",
                "Confirm the key matches the selected Environment (Production vs Testnet).",
                "On Delta's API management page, check the key status and confirm any 'Activate' email.",
                "For testing, set the IP whitelist to 0.0.0.0/0 (allow all), then tighten it after verifying.",
                "Find this host's public IP and add it to the whitelist: https://api.ipify.org",
                "If all else fails, create a fresh key and repeat the test.",
            ],
        },
        "forbidden": {
            "level": "error",
            "title": "API key lacks permission",
            "explanation": "Authentication succeeded but the key does not have permission for trading/account endpoints.",
            "causes": [
                "The key was created with read-only scope and cannot access wallet/positions.",
                "Required permissions (read wallet / trade) were not enabled at creation.",
            ],
            "steps": [
                "On Delta, edit the API key and enable 'Read Wallet' and 'Trade' permissions.",
                "Create a new key with the required scopes and test again.",
            ],
        },
        "no_keys": {
            "level": "warn",
            "title": "No credentials provided",
            "explanation": "API key and secret are both required to enable Trading mode.",
            "causes": ["One or both fields were left empty."],
            "steps": ["Enter both your API key and secret, then click Connect & Test."],
        },
    }
    return guides.get(error_code, {
        "level": "error",
        "title": "Unknown error",
        "explanation": f"Unrecognized error code: {error_code}.",
        "causes": [],
        "steps": ["Check the bridge logs for details."],
    })


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
        
        self.production_rest = "https://api.india.delta.exchange"
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

    def set_credentials_full(self, api_key: str = "", api_secret: str = "", environment: str = "production", mode: str = "read_only") -> None:
        """Set API credentials, environment and mode IN MEMORY only (no disk persistence)."""
        self.credentials.api_key = api_key or ""
        self.credentials.api_secret = api_secret or ""
        if environment in ("production", "testnet"):
            self.credentials.environment = environment
        try:
            self.credentials.mode = DeltaAPIMode(mode)
        except ValueError:
            self.credentials.mode = DeltaAPIMode.READ_ONLY

    async def test_connection(self) -> Dict[str, Any]:
        """Test Delta connectivity and authentication. Returns a structured diagnostic (no secrets)."""
        result: Dict[str, Any] = {
            "status": "unknown",
            "connected": False,
            "has_auth": self.credentials.has_auth,
            "environment": self.credentials.environment,
            "mode": self.credentials.mode,
            "balance_preview": None,
            "error_code": None,
            "error_message": None,
            "diagnostic": None,
        }

        # 1) Public connectivity test (no auth required)
        try:
            public = await self._get("/v2/products", {"page_size": 1})
        except Exception as e:  # network/DNS failure
            public = {"error": f"network: {str(e)}"}

        if "error" in public:
            result["status"] = "unreachable"
            result["error_code"] = "delta_unreachable"
            result["error_message"] = "Delta Exchange API is not reachable from this host."
            result["diagnostic"] = diagnose_delta_error("delta_unreachable", self.credentials.environment)
            return result

        result["connected"] = True

        # 2) No keys -> read-only connected
        if not self.credentials.has_auth:
            result["status"] = "connected_readonly"
            result["diagnostic"] = diagnose_delta_error("connected_readonly", self.credentials.environment)
            return result

        # 3) Authenticated test
        self.credentials.mode = DeltaAPIMode.TRADING
        balance = await self.get_balance()
        if isinstance(balance, dict) and "error" in balance:
            err = balance.get("error", "")
            if err == "unauthorized":
                code = "unauthorized"
            elif err in ("forbidden", "http_403"):
                code = "forbidden"
            else:
                code = "unauthorized"
            result["status"] = "auth_failed"
            result["error_code"] = code
            result["error_message"] = "Delta Exchange rejected the API key/secret."
            result["diagnostic"] = diagnose_delta_error(code, self.credentials.environment)
            self.credentials.mode = DeltaAPIMode.READ_ONLY
            return result

        result["status"] = "connected"
        result["mode"] = self.credentials.mode
        result["balance_preview"] = {
            "total_equity": balance.get("total_equity"),
            "available_margin": balance.get("available_margin"),
            "currency": balance.get("currency", "USDT"),
        }
        result["diagnostic"] = diagnose_delta_error("connected", self.credentials.environment)
        return result
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context, family=socket.AF_INET)
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
            "User-Agent": "mt5-flow-trading-system/1.0",
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
                try:
                    detail = await resp.text()
                except Exception:
                    detail = ""
                return {"error": "unauthorized", "detail": detail[:400]}
            if resp.status == 403:
                return {"error": "forbidden", "message": "API key lacks permission for this endpoint"}
            if resp.status != 200:
                return {"error": f"http_{resp.status}", "message": await resp.text()}
            return await resp.json()
    
    async def _post(self, path: str, body: Dict = None) -> Dict:
        """POST request with auth. Returns the raw envelope; business errors
        arrive as 200 + {"success": false, ...}, transport errors as {"error": ...}."""
        await self._rate_limit()
        session = await self._ensure_session()

        body_str = json.dumps(body) if body else ""
        headers = self._auth_headers("POST", path, body=body_str)

        async with session.post(f"{self.rest_base}{path}", headers=headers, data=body_str) as resp:
            if resp.status == 401:
                return {"error": "unauthorized"}
            if resp.status != 200:
                try:
                    detail = await resp.text()
                except Exception:
                    detail = ""
                return {"error": f"http_{resp.status}", "detail": detail[:500]}
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
        """Get tickers for multiple symbols. Uses batch endpoint when no symbols specified."""
        if symbols:
            results = []
            for sym in symbols:
                ticker = await self.get_ticker(sym)
                if ticker:
                    results.append(ticker)
            return results
        
        data = await self._get("/v2/tickers")
        if "error" in data:
            return []
        result = data.get("result", [])
        return result if isinstance(result, list) else []
    
    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Get top gaining assets from batch ticker data."""
        tickers = await self.get_tickers()
        
        combined = []
        for t in tickers:
            if not isinstance(t, dict):
                continue
            sym = t.get("symbol", t.get("product_symbol", ""))
            change = float(t.get("mark_change_24h", t.get("change_24h", 0)) or 0)
            volume = float(t.get("turnover_usd", t.get("turnover", t.get("volume", 0))) or 0)
            
            if volume > 0:
                combined.append({
                    "symbol": sym,
                    "change_24h": change,
                    "volume_24h": volume,
                    "mark_price": float(t.get("mark_price", t.get("close", 0)) or 0),
                    "funding_rate": float(t.get("funding_rate", 0) or 0),
                    "open_interest": float(t.get("oi_value_usd", 0) or 0),
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

    async def resolve_product_id(self, symbol: str) -> Optional[int]:
        """Resolve a product symbol (e.g. BTCUSD) to its integer product id (public)."""
        try:
            data = await self._get(f"/v2/products/{symbol}")
            if isinstance(data, dict):
                res = data.get("result") or {}
                pid = res.get("id")
                if isinstance(pid, int):
                    return pid
        except Exception:
            pass
        return None

    async def set_order_leverage(self, product_id: int, leverage: int) -> Dict:
        """Set order leverage for a product. Requires trading mode + auth."""
        if self.credentials.mode != DeltaAPIMode.TRADING:
            return {"error": "read_only", "message": "Switch to TRADING mode to change leverage"}
        if not self.credentials.has_auth:
            return {"error": "no_auth", "message": "Delta API keys are not configured"}
        try:
            lev = int(leverage)
        except (TypeError, ValueError):
            return {"error": "invalid_leverage", "message": "Leverage must be an integer"}
        if lev < 1 or lev > 125:
            return {"error": "invalid_leverage", "message": "Leverage must be between 1 and 125"}
        return await self._post(f"/v2/products/{int(product_id)}/orders/leverage", {"leverage": lev})

    async def place_order(self, symbol: str, side: str, size: int,
                          order_type: str = "market_order",
                          limit_price: str = None,
                          leverage: int = None) -> Dict:
        """Place a live order. Requires trading mode + auth.

        Leverage is applied first via the per-product leverage endpoint;
        if that call is rejected the order is NOT placed.
        """
        if self.credentials.mode != DeltaAPIMode.TRADING:
            return {"error": "read_only", "message": "Switch to TRADING mode to place orders"}
        if not self.credentials.has_auth:
            return {"error": "no_auth", "message": "Delta API keys are not configured"}
        pid = await self.resolve_product_id(symbol)
        if pid is None:
            return {"error": "unknown_symbol", "message": f"Could not resolve product id for {symbol}"}
        lev_applied = None
        if leverage is not None:
            lev_res = await self.set_order_leverage(pid, leverage)
            if isinstance(lev_res, dict) and lev_res.get("success") is True:
                lev_applied = (lev_res.get("result") or {}).get("leverage", leverage)
            else:
                out = {"error": "leverage_rejected",
                       "message": "Leverage change rejected; order NOT placed",
                       "leverage_applied": None}
                if isinstance(lev_res, dict):
                    out["detail"] = lev_res
                return out
        body = {"product_id": pid, "product_symbol": symbol, "size": size,
                "side": side, "order_type": order_type, "time_in_force": "gtc"}
        if order_type == "limit_order":
            body["limit_price"] = str(limit_price)
        res = await self._post("/v2/orders", body)
        if isinstance(res, dict):
            res = dict(res)
            res["leverage_applied"] = lev_applied
        return res
    
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
    
    # Override from local .env file (gitignored; written by the UI "remember" option)
    import os
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, 'r') as ef:
                for line in ef.read().splitlines():
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k == "DELTA_API_KEY" and v:
                        api_key = v
                    elif k == "DELTA_API_SECRET" and v:
                        api_secret = v
                    elif k == "DELTA_ENVIRONMENT" and v:
                        environment = v
        except Exception:
            pass

    # Process environment takes final precedence
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
