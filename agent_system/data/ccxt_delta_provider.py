"""
Unified CCXT Delta Exchange Provider
Wraps CCXT's native Delta exchange for market data, balance, positions, orders,
and adds derivative/options-specific features.
"""
from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ccxt
import ccxt.async_support as ccxt_async


@dataclass
class CCXTDeltaConfig:
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = False
    environment: str = "testnet"
    rest_url: str = ""
    timeout: int = 30000
    enable_rate_limit: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


class CCXTDeltaProvider:
    """
    CCXT wrapper for Delta Exchange with all unified methods.
    
    Provides:
    - Market data (tickers, OHLCV, orderbook, trades)
    - Account data (balance, positions, orders) with auth
    - Funding rates, open interest, products
    - Both sync and async methods
    - Fallback to direct Delta API when CCXT lacks a method
    """
    
    def __init__(self, config: CCXTDeltaConfig = None):
        self.config = config or CCXTDeltaConfig()
        self.exchange: Optional[ccxt.delta] = None
        self._init_exchange()
    
    def _init_exchange(self) -> None:
        """Initialize CCXT delta exchange instance."""
        params = {
            'apiKey': self.config.api_key,
            'secret': self.config.api_secret,
            'timeout': self.config.timeout,
            'enableRateLimit': self.config.enable_rate_limit,
            'options': self.config.options,
        }
        
        if self.config.sandbox or self.config.environment == "testnet":
            params['options'] = {**params.get('options', {}), 'sandbox': True}
        
        self.exchange = getattr(ccxt, 'delta')(params)
        
        # Route to India testnet when configured
        if self.config.environment == "testnet" and self.config.rest_url:
            self.exchange.urls['api'] = {
                **self.exchange.urls.get('api', {}),
                'rest': self.config.rest_url,
            }
    
    def set_credentials(self, api_key: str, api_secret: str) -> None:
        """Set API credentials."""
        self.config.api_key = api_key
        self.config.api_secret = api_secret
        self.exchange.apiKey = api_key
        self.exchange.secret = api_secret
    
    def is_authenticated(self) -> bool:
        return bool(self.config.api_key and self.config.api_secret)
    
    def set_environment(self, environment: str, rest_url: str = "") -> None:
        """Update environment and reinitialize exchange if needed."""
        self.config.environment = environment
        if rest_url:
            self.config.rest_url = rest_url
        self._init_exchange()
    
    # ============ MARKET DATA (read-only, no auth) ============
    
    def fetch_markets(self) -> Dict[str, Any]:
        """Load and return all markets."""
        return self.exchange.load_markets()
    
    def fetch_ticker(self, symbol: str) -> Dict:
        """Fetch ticker for a single symbol."""
        return self.exchange.fetch_ticker(symbol)
    
    def fetch_tickers(self, symbols: List[str] = None) -> Dict:
        """Fetch tickers for multiple symbols."""
        return self.exchange.fetch_tickers(symbols)
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 500, since: int = None) -> List[List]:
        """Fetch OHLCV candles."""
        # Normalize symbol: try direct first, then swap format
        markets = self.exchange.load_markets()
        candidates = [symbol, f"{symbol}:{symbol.split('/')[1]}" if '/' in symbol else symbol]
        
        for candidate in candidates:
            if candidate in markets:
                try:
                    return self.exchange.fetch_ohlcv(candidate, timeframe, since=since, limit=limit)
                except Exception:
                    continue
        
        return self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
    
    def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """Fetch order book."""
        return self.exchange.fetch_order_book(symbol, limit)
    
    def fetch_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Fetch recent trades."""
        return self.exchange.fetch_trades(symbol, limit=limit)
    
    def fetch_funding_rate(self, symbol: str) -> Dict:
        """Fetch current funding rate."""
        return self.exchange.fetch_funding_rate(symbol)
    
    def fetch_funding_rates(self, symbols: List[str] = None) -> Dict:
        """Fetch funding rates for multiple symbols."""
        return self.exchange.fetch_funding_rates(symbols)
    
    def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest for a symbol."""
        return self.exchange.fetch_open_interest(symbol)
    
    def fetch_currencies(self) -> Dict:
        """Fetch available currencies."""
        return self.exchange.fetch_currencies()
    
    def fetch_products(self) -> List[Dict]:
        """Fetch all products with additional info."""
        markets = self.exchange.load_markets()
        products = []
        for symbol, market in markets.items():
            products.append({
                'symbol': symbol,
                'base': market.get('base', ''),
                'quote': market.get('quote', ''),
                'type': market.get('type', 'spot'),
                'active': market.get('active', True),
                'spot': market.get('spot', False),
                'swap': market.get('swap', False),
                'option': market.get('option', False),
                'contract': market.get('contract', False),
                'expiry': market.get('expiry', None),
                'strike': market.get('strike', None),
                'option_type': market.get('optionType', None),
            })
        return products
    
    # ============ ACCOUNT DATA (requires auth) ============
    
    def fetch_balance(self) -> Dict:
        """Fetch account balance."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.fetch_balance()
    
    def fetch_positions(self, symbols: List[str] = None) -> List[Dict]:
        """Fetch open positions."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_positions(symbols)
    
    def fetch_open_orders(self, symbol: str = None) -> List[Dict]:
        """Fetch open orders."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_open_orders(symbol)
    
    def fetch_order(self, order_id: str, symbol: str = None) -> Dict:
        """Fetch a specific order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.fetch_order(order_id, symbol)
    
    def fetch_orders(self, symbol: str = None, since: int = None, limit: int = 100) -> List[Dict]:
        """Fetch order history."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_orders(symbol, since=since, limit=limit)
    
    def fetch_closed_orders(self, symbol: str = None) -> List[Dict]:
        """Fetch closed orders."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_closed_orders(symbol)
    
    def fetch_my_trades(self, symbol: str = None, since: int = None, limit: int = 100) -> List[Dict]:
        """Fetch user trades."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_my_trades(symbol, since=since, limit=limit)
    
    def fetch_deposits(self) -> List[Dict]:
        """Fetch deposit history."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_deposits()
    
    def fetch_withdrawals(self) -> List[Dict]:
        """Fetch withdrawal history."""
        if not self.is_authenticated():
            return []
        return self.exchange.fetch_withdrawals()
    
    # ============ TRADING METHODS (requires auth) ============
    
    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = None) -> Dict:
        """Create a new order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.create_order(symbol, type, side, amount, price, params or {})
    
    def create_market_buy_order(self, symbol: str, amount: float, params: Dict = None) -> Dict:
        """Create a market buy order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.create_market_buy_order(symbol, amount, params or {})
    
    def create_market_sell_order(self, symbol: str, amount: float, params: Dict = None) -> Dict:
        """Create a market sell order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.create_market_sell_order(symbol, amount, params or {})
    
    def create_limit_buy_order(self, symbol: str, amount: float, price: float, params: Dict = None) -> Dict:
        """Create a limit buy order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.create_limit_buy_order(symbol, amount, price, params or {})
    
    def create_limit_sell_order(self, symbol: str, amount: float, price: float, params: Dict = None) -> Dict:
        """Create a limit sell order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.create_limit_sell_order(symbol, amount, price, params or {})
    
    def cancel_order(self, order_id: str, symbol: str = None) -> Dict:
        """Cancel an order."""
        if not self.is_authenticated():
            return {'error': 'API keys required'}
        return self.exchange.cancel_order(order_id, symbol)
    
    def cancel_all_orders(self, symbol: str = None) -> List[Dict]:
        """Cancel all open orders."""
        if not self.is_authenticated():
            return []
        return self.exchange.cancel_all_orders(symbol)
    
    # ============ ANALYTICS HELPERS ============
    
    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Get top gaining assets by 24h change."""
        try:
            tickers = self.fetch_tickers()
            gainers = []
            for symbol, ticker in tickers.items():
                change = ticker.get('percentage', 0) or 0
                if change is not None:
                    gainers.append({
                        'symbol': symbol,
                        'change_24h': float(change),
                        'mark_price': float(ticker.get('last', ticker.get('close', 0)) or 0),
                        'volume_24h': float(ticker.get('quoteVolume', 0) or 0),
                        'bid': float(ticker.get('bid', 0) or 0),
                        'ask': float(ticker.get('ask', 0) or 0),
                        'high_24h': float(ticker.get('high', 0) or 0),
                        'low_24h': float(ticker.get('low', 0) or 0),
                        'vwap': float(ticker.get('vwap', 0) or 0),
                        'open_interest': float(ticker.get('info', {}).get('open_interest', 0) or 0) if isinstance(ticker.get('info'), dict) else 0,
                    })
            gainers.sort(key=lambda x: x['change_24h'], reverse=True)
            return gainers[:limit]
        except Exception:
            return []
    
    def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """Get top losing assets by 24h change."""
        try:
            tickers = self.fetch_tickers()
            losers = []
            for symbol, ticker in tickers.items():
                change = ticker.get('percentage', 0) or 0
                if change is not None:
                    losers.append({
                        'symbol': symbol,
                        'change_24h': float(change),
                        'mark_price': float(ticker.get('last', ticker.get('close', 0)) or 0),
                        'volume_24h': float(ticker.get('quoteVolume', 0) or 0),
                    })
            losers.sort(key=lambda x: x['change_24h'])
            return losers[:limit]
        except Exception:
            return []
    
    def get_market_summary(self) -> Dict:
        """Get market-wide summary statistics."""
        try:
            tickers = self.fetch_tickers()
            total_volume = 0
            gainers = 0
            losers = 0
            for symbol, ticker in tickers.items():
                vol = ticker.get('quoteVolume', 0) or 0
                total_volume += float(vol)
                change = ticker.get('percentage', 0) or 0
                if change > 0:
                    gainers += 1
                elif change < 0:
                    losers += 1
            
            return {
                'total_symbols': len(tickers),
                'gainers': gainers,
                'losers': losers,
                'total_volume': total_volume,
                'avg_change': sum(t.get('percentage', 0) or 0 for t in tickers.values()) / len(tickers) if tickers else 0,
            }
        except Exception:
            return {'total_symbols': 0, 'gainers': 0, 'losers': 0, 'total_volume': 0, 'avg_change': 0}
    
    def get_spot_vs_derivatives(self) -> Dict:
        """Get spot vs derivatives breakdown."""
        try:
            markets = self.exchange.load_markets()
            spot = sum(1 for m in markets.values() if m.get('spot'))
            swap = sum(1 for m in markets.values() if m.get('swap'))
            option = sum(1 for m in markets.values() if m.get('option'))
            future = sum(1 for m in markets.values() if m.get('future'))
            
            return {
                'spot': spot,
                'swap': swap,
                'option': option,
                'future': future,
                'total': len(markets),
            }
        except Exception:
            return {'spot': 0, 'swap': 0, 'option': 0, 'future': 0, 'total': 0}
    
    def health_check(self) -> Dict:
        """Check exchange health and auth status."""
        result = {
            'provider': 'ccxt',
            'exchange': 'delta',
            'connected': False,
            'authenticated': self.is_authenticated(),
            'error': None,
        }
        
        try:
            self.fetch_markets()
            result['connected'] = True
        except Exception as e:
            result['error'] = str(e)
        
        return result


# Load credentials from settings.yaml, allow env override
def _load_ccxt_delta_config() -> CCXTDeltaConfig:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import config_loader
        cfg = config_loader.get_delta_config()
    except Exception:
        cfg = {}
    
    import os
    return CCXTDeltaConfig(
        api_key=os.environ.get('DELTA_API_KEY', cfg.get('api_key', '')),
        api_secret=os.environ.get('DELTA_API_SECRET', cfg.get('api_secret', '')),
        environment=os.environ.get('DELTA_ENVIRONMENT', cfg.get('environment', 'testnet')),
        rest_url=cfg.get('rest_url', ''),
        sandbox=cfg.get('environment', 'testnet') == 'testnet',
    )


# Global provider
ccxt_delta_provider = CCXTDeltaProvider(_load_ccxt_delta_config())
