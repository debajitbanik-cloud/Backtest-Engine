"""
Python Bridge Server
Provides a REST API for the TypeScript engine to query Python agent system state,
trade signals, and shared market data.
"""
from __future__ import annotations
import asyncio
import json
import sys
import os
from pathlib import Path

# Add agent_system to path for imports
agent_system_path = Path(__file__).parent.parent / "agent_system"
if str(agent_system_path) not in sys.path:
    sys.path.insert(0, str(agent_system_path))

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional
from aiohttp import web
from aiohttp.web import middleware


@middleware
async def cors_middleware(request: web.Request, handler):
    """Add CORS headers for cross-origin UI requests."""
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

from core.event_bus import EventBus, Event, EventType, event_bus
from core.metrics_engine import MetricsEngine, metrics_engine, _sanitize
from core.strategy_deployment import StrategyDeploymentManager, strategy_manager
from core.margin_allocation_engine import MarginAllocationEngine, margin_engine
from core.strategy_execution_engine import StrategyExecutionEngine, execution_engine
from core.options_engine import OptionsScanner, options_scanner, PayoffEngine, payoff_engine
from data.delta_api_client import DeltaAPIClient, delta_client, DeltaAPIMode
from data.ccxt_delta_provider import CCXTDeltaProvider, ccxt_delta_provider
from data.xau_ai_integration import XAUAIIntegration, xau_ai_integration


@dataclass
class BridgeConfig:
    """Configuration for the bridge server."""
    host: str = "127.0.0.1"
    port: int = 8080
    shared_data_dir: str = "./data/shared"
    enable_events_stream: bool = True


class PythonBridge:
    """
    Bridge server that exposes Python agent system to TypeScript engine.
    
    Endpoints:
    - GET /health - Health check
    - GET /status - Agent system status
    - GET /signals - Latest trade signals
    - GET /data/{symbol}/{timeframe} - OHLCV data
    - GET /events - SSE stream of events
    - POST /command - Send command to Python system
    """
    
    def __init__(self, config: BridgeConfig, event_bus: EventBus = None):
        self.config = config
        self.event_bus = event_bus or event_bus
        self.app = web.Application(middlewares=[cors_middleware])
        self._setup_routes()
        self._signals: List[Dict] = []
        self._status: Dict[str, Any] = {"running": False, "agents": {}}
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribed = False
    
    def _setup_routes(self) -> None:
        self.app.router.add_get('/health', self.health)
        self.app.router.add_get('/status', self.status)
        self.app.router.add_get('/signals', self.signals)
        self.app.router.add_get('/data/{symbol}/{timeframe}', self.get_data)
        self.app.router.add_get('/events', self.events_stream)
        self.app.router.add_post('/command', self.command)
        self.app.router.add_get('/metrics/correlation', self.correlation)
        self.app.router.add_get('/metrics/exposure', self.exposure)
        self.app.router.add_get('/metrics/hedge', self.hedge)
        self.app.router.add_get('/metrics/performance/{symbol}', self.performance)
        self.app.router.add_get('/delta/health', self.delta_health)
        self.app.router.add_get('/delta/top-gainers', self.delta_top_gainers)
        self.app.router.add_get('/delta/balance', self.delta_balance)
        self.app.router.add_get('/delta/positions', self.delta_positions)
        self.app.router.add_get('/delta/tickers', self.delta_tickers)
        self.app.router.add_post('/delta/mode', self.delta_set_mode)
        self.app.router.add_get('/strategy/deployed', self.strategy_deployed)
        self.app.router.add_get('/ccxt/health', self.ccxt_health)
        self.app.router.add_get('/ccxt/markets', self.ccxt_markets)
        self.app.router.add_get('/ccxt/tickers', self.ccxt_tickers)
        self.app.router.add_get('/ccxt/top-gainers', self.ccxt_top_gainers)
        self.app.router.add_get('/ccxt/market-summary', self.ccxt_market_summary)
        self.app.router.add_get('/ccxt/balance', self.ccxt_balance)
        self.app.router.add_get('/ccxt/positions', self.ccxt_positions)
        self.app.router.add_get('/xau/status', self.xau_status)
        self.app.router.add_get('/xau/smc', self.xau_smc)
        self.app.router.add_get('/xau/regime', self.xau_regime)
        self.app.router.add_get('/xau/kelly', self.xau_kelly)
        self.app.router.add_get('/xau/risk', self.xau_risk)
        self.app.router.add_get('/recommendations', self.recommendations)
        self.app.router.add_get('/trading/suggestions', self.trading_suggestions)
        self.app.router.add_get('/trading/allocations', self.trading_allocations)
        self.app.router.add_post('/deploy', self.deploy_strategy)
        self.app.router.add_get('/execution/status', self.execution_status)
        self.app.router.add_post('/execution/stop', self.execution_stop)
        self.app.router.add_get('/options/scan', self.options_scan)
        self.app.router.add_get('/options/payoff', self.options_payoff)
        self.app.router.add_get('/debug/events', self.debug_events)
        self.app.router.add_post('/debug/trigger-bias', self.debug_trigger_bias)
        self.app.router.add_get('/delta/top-gainer-chart', self.delta_top_gainer_chart)
    
    async def start(self) -> None:
        """Start the bridge server."""
        await self._subscribe_to_events()
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        self._status["running"] = True
        print(f"Python bridge server running at http://{self.config.host}:{self.config.port}")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant events."""
        if self._subscribed:
            return
        
        await self.event_bus.subscribe(EventType.TRADE_LOG, self._on_trade_log, "PythonBridge")
        await self.event_bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert, "PythonBridge")
        await self.event_bus.subscribe(EventType.MODE_SWITCH, self._on_mode_switch, "PythonBridge")
        await self.event_bus.subscribe(EventType.AGENT_HEARTBEAT, self._on_heartbeat, "PythonBridge")
        self._subscribed = True
    
    async def _on_trade_log(self, event: Event) -> None:
        """Store trade signals."""
        await self._event_queue.put(event)
        self._signals.append({
            "type": "trade",
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload
        })
        if len(self._signals) > 100:
            self._signals = self._signals[-100:]
    
    async def _on_risk_alert(self, event: Event) -> None:
        """Forward risk alerts."""
        await self._event_queue.put(event)
    
    async def _on_mode_switch(self, event: Event) -> None:
        """Forward mode switches."""
        await self._event_queue.put(event)
    
    async def _on_heartbeat(self, event: Event) -> None:
        """Update status from heartbeats."""
        payload = event.payload
        agent = payload.get("agent")
        if agent:
            self._status["agents"][agent] = {
                "timestamp": event.timestamp.isoformat(),
                "metrics": payload
            }
    
    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "running": self._status["running"]
        })
    
    async def status(self, request: web.Request) -> web.Response:
        return web.json_response(self._status)
    
    async def signals(self, request: web.Request) -> web.Response:
        limit = int(request.query.get('limit', '50'))
        return web.json_response({
            "signals": self._signals[-limit:],
            "count": len(self._signals)
        })
    
    async def get_data(self, request: web.Request) -> web.Response:
        symbol = request.match_info['symbol']
        timeframe = request.match_info['timeframe']
        limit = int(request.query.get('limit', '1000'))
        
        file_path = Path(self.config.shared_data_dir) / f"{symbol}_{timeframe}.json"
        
        if not file_path.exists():
            return web.json_response({"error": "Data not found"}, status=404)
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            if limit:
                data = data[-limit:]
            
            return web.json_response({
                "symbol": symbol,
                "timeframe": timeframe,
                "count": len(data),
                "data": data
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    async def events_stream(self, request: web.Request) -> web.Response:
        """Server-sent events stream."""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        await response.prepare(request)
        
        try:
            while True:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30)
                data = json.dumps({
                    "type": event.type.value,
                    "source": event.source_agent,
                    "timestamp": event.timestamp.isoformat(),
                    "payload": event.payload
                })
                await response.write(f"data: {data}\n\n".encode())
        except asyncio.TimeoutError:
            # Send keepalive
            await response.write(f"data: {json.dumps({'type': 'keepalive'})}\n\n".encode())
        except Exception as e:
            print(f"SSE error: {e}")
        else:
            await response.drain()
        finally:
            pass
    
    async def command(self, request: web.Request) -> web.Response:
        """Receive commands from TypeScript engine."""
        body = await request.json()
        command = body.get("command")
        params = body.get("params", {})
        
        if command == "tune_agent":
            # Publish tuning event
            await self.event_bus.publish(Event(
                type=EventType.AGENT_TUNING,
                payload=params,
                source_agent="PythonBridge"
            ))
            return web.json_response({"status": "tuning_sent"})
        
        elif command == "halt":
            return web.json_response({"status": "halt_requested"})
        
        return web.json_response({"error": "Unknown command"}, status=400)
    
    async def correlation(self, request: web.Request) -> web.Response:
        """Get crypto-RWA correlation metrics."""
        try:
            corr = metrics_engine.compute_correlation('SOLUSDT', 'XAUTUSDT')
            return web.json_response({
                'symbol_a': _sanitize(corr.symbol_a),
                'symbol_b': _sanitize(corr.symbol_b),
                'correlation_1h': _sanitize(corr.correlation_1h),
                'correlation_4h': _sanitize(corr.correlation_4h),
                'correlation_1d': _sanitize(corr.correlation_1d),
                'correlation_7d': _sanitize(corr.correlation_7d),
                'current': _sanitize(corr.current),
                'trend': _sanitize(corr.trend),
                'updated': _sanitize(corr.updated)
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def exposure(self, request: web.Request) -> web.Response:
        """Get crypto vs RWA exposure metrics."""
        try:
            exp = metrics_engine.compute_exposure(
                crypto_symbols=['SOLUSDT'],
                rwa_symbols=['XAUTUSDT']
            )
            return web.json_response({k: _sanitize(v) for k, v in {
                'total_crypto_exposure': exp.total_crypto_exposure,
                'total_rwa_exposure': exp.total_rwa_exposure,
                'crypto_allocation_pct': exp.crypto_allocation_pct,
                'rwa_allocation_pct': exp.rwa_allocation_pct,
                'net_exposure': exp.net_exposure,
                'gross_exposure': exp.gross_exposure,
                'leverage_ratio': exp.leverage_ratio,
                'concentration_risk': exp.concentration_risk,
                'updated': exp.updated
            }.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def hedge(self, request: web.Request) -> web.Response:
        """Get hedge effectiveness metrics."""
        try:
            h = metrics_engine.compute_hedge_metrics('SOLUSDT', 'XAUTUSDT')
            return web.json_response({k: _sanitize(v) for k, v in {
                'hedge_ratio': h.hedge_ratio,
                'hedge_effectiveness': h.hedge_effectiveness,
                'beta': h.beta,
                'alpha': h.alpha,
                'net_delta_exposure': h.net_delta_exposure,
                'optimal_hedge_ratio': h.optimal_hedge_ratio,
                'rebalance_signal': h.rebalance_signal,
                'confidence': h.confidence,
                'updated': h.updated
            }.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def performance(self, request: web.Request) -> web.Response:
        """Get performance metrics for a symbol."""
        symbol = request.match_info['symbol']
        try:
            perf = metrics_engine.compute_performance(symbol, '15m')
            return web.json_response({k: _sanitize(v) for k, v in {
                'total_return_pct': perf.total_return_pct,
                'sharpe_ratio': perf.sharpe_ratio,
                'sortino_ratio': perf.sortino_ratio,
                'max_drawdown_pct': perf.max_drawdown_pct,
                'current_drawdown_pct': perf.current_drawdown_pct,
                'win_rate': perf.win_rate,
                'profit_factor': perf.profit_factor,
                'avg_win_loss_ratio': perf.avg_win_loss_ratio,
                'consecutive_wins': perf.consecutive_wins,
                'consecutive_losses': perf.consecutive_losses,
                'weekly_pnl': perf.weekly_pnl,
                'updated': perf.updated
            }.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def delta_health(self, request: web.Request) -> web.Response:
        """Get Delta API connection status."""
        try:
            health = await delta_client.health_check()
            return web.json_response({k: _sanitize(v) for k, v in health.items()})
        except Exception as e:
            return web.json_response({'error': str(e), 'mode': delta_client.mode, 'connected': False}, status=500)
    
    async def delta_top_gainers(self, request: web.Request) -> web.Response:
        """Get top gaining assets from Delta."""
        try:
            limit = int(request.query.get('limit', '10'))
            gainers = await delta_client.get_top_gainers(limit)
            return web.json_response({'gainers': [{k: _sanitize(v) for k, v in g.items()} for g in gainers]})
        except Exception as e:
            # Return empty list instead of error when Delta is unreachable
            return web.json_response({'gainers': [], 'note': f'Delta API unavailable: {str(e)[:100]}'})
    
    async def delta_top_gainer_chart(self, request: web.Request) -> web.Response:
        """Get OHLCV chart data for the highest gaining Delta asset using CCXT."""
        try:
            # Use CCXT provider (fast, no sequential ticker fetches)
            gainers = ccxt_delta_provider.get_top_gainers(5)
            if not gainers:
                return web.json_response({'error': 'No gainers available'}, status=404)
            
            top = gainers[0]
            symbol = top.get('symbol', '')
            change = top.get('change_24h', 0)
            
            # Fetch OHLCV for top gainer (swap market preferred)
            candles = []
            try:
                candles = ccxt_delta_provider.fetch_ohlcv(symbol, '15m', limit=100)
            except Exception:
                candles = []
            
            return web.json_response({
                'symbol': symbol,
                'change_24h': _sanitize(change),
                'candles': [_sanitize(c) for c in candles] if candles else [],
                'count': len(candles),
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def delta_balance(self, request: web.Request) -> web.Response:
        """Get account balance from Delta."""
        try:
            balance = await delta_client.get_balance()
            if isinstance(balance, dict) and 'error' in balance:
                return web.json_response(balance, status=400)
            return web.json_response({k: _sanitize(v) for k, v in balance.items()} if balance else {})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def delta_positions(self, request: web.Request) -> web.Response:
        """Get open positions from Delta."""
        try:
            positions = await delta_client.get_positions()
            return web.json_response({'positions': [{k: _sanitize(v) for k, v in p.items()} for p in positions]})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def delta_tickers(self, request: web.Request) -> web.Response:
        """Get all tickers from Delta."""
        try:
            symbols = request.query.get('symbols', None)
            sym_list = symbols.split(',') if symbols else None
            tickers = await delta_client.get_tickers(sym_list)
            return web.json_response({'tickers': [{k: _sanitize(v) for k, v in t.items()} for t in tickers]})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def delta_set_mode(self, request: web.Request) -> web.Response:
        """Switch Delta API mode (read_only/trading)."""
        try:
            body = await request.json()
            mode = body.get('mode', 'read_only')
            
            if mode not in ['read_only', 'trading']:
                return web.json_response({'error': 'Invalid mode. Use read_only or trading'}, status=400)
            
            if mode == 'trading' and not delta_client.credentials.has_auth:
                return web.json_response({'error': 'Trading mode requires API keys. Set DELTA_API_KEY and DELTA_API_SECRET'}, status=400)
            
            delta_client.set_mode(mode)
            return web.json_response({'status': 'ok', 'mode': delta_client.mode})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def strategy_deployed(self, request: web.Request) -> web.Response:
        """Get optimized strategy deployment info."""
        try:
            deployable = strategy_manager.get_deployable()
            best = strategy_manager.get_best_overall()
            return web.json_response({
                'deployed': best,
                'deployable': deployable,
                'all': strategy_manager.get_all()
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def ccxt_health(self, request: web.Request) -> web.Response:
        """Get CCXT Delta provider health."""
        try:
            health = ccxt_delta_provider.health_check()
            return web.json_response({k: _sanitize(v) for k, v in health.items()})
        except Exception as e:
            return web.json_response({'error': str(e), 'connected': False}, status=500)
    
    async def ccxt_markets(self, request: web.Request) -> web.Response:
        """Get markets from CCXT Delta."""
        try:
            markets = ccxt_delta_provider.fetch_markets()
            symbols = list(markets.keys()) if isinstance(markets, dict) else []
            return web.json_response({
                'count': len(symbols),
                'symbols': symbols[:200],  # Limit response size
                'spot_vs_derivatives': ccxt_delta_provider.get_spot_vs_derivatives(),
            })
        except Exception as e:
            return web.json_response({'error': str(e), 'count': 0, 'symbols': []}, status=500)
    
    async def ccxt_tickers(self, request: web.Request) -> web.Response:
        """Get tickers from CCXT Delta."""
        try:
            symbols = request.query.get('symbols', None)
            sym_list = symbols.split(',') if symbols else None
            tickers = ccxt_delta_provider.fetch_tickers(sym_list)
            
            # Convert to list of dicts for JSON
            ticker_list = []
            for sym, t in tickers.items():
                ticker_list.append({
                    'symbol': sym,
                    'last': _sanitize(t.get('last', 0)),
                    'change_24h': _sanitize(t.get('percentage', 0)),
                    'volume_24h': _sanitize(t.get('quoteVolume', 0)),
                    'bid': _sanitize(t.get('bid', 0)),
                    'ask': _sanitize(t.get('ask', 0)),
                    'high_24h': _sanitize(t.get('high', 0)),
                    'low_24h': _sanitize(t.get('low', 0)),
                    'vwap': _sanitize(t.get('vwap', 0)),
                })
            
            return web.json_response({'tickers': ticker_list})
        except Exception as e:
            return web.json_response({'error': str(e), 'tickers': []}, status=500)
    
    async def ccxt_top_gainers(self, request: web.Request) -> web.Response:
        """Get top gainers from CCXT Delta."""
        try:
            limit = int(request.query.get('limit', '10'))
            gainers = ccxt_delta_provider.get_top_gainers(limit)
            return web.json_response({'gainers': [{k: _sanitize(v) for k, v in g.items()} for g in gainers]})
        except Exception as e:
            return web.json_response({'gainers': [], 'error': str(e)})
    
    async def ccxt_market_summary(self, request: web.Request) -> web.Response:
        """Get market summary from CCXT Delta."""
        try:
            summary = ccxt_delta_provider.get_market_summary()
            return web.json_response({k: _sanitize(v) for k, v in summary.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def ccxt_balance(self, request: web.Request) -> web.Response:
        """Get balance from CCXT Delta."""
        try:
            balance = ccxt_delta_provider.fetch_balance()
            if isinstance(balance, dict) and 'error' in balance:
                return web.json_response(balance, status=400)
            
            # Normalize CCXT balance format
            normalized = {
                'free': {},
                'used': {},
                'total': {},
            }
            if isinstance(balance, dict):
                for currency, amount in balance.get('free', {}).items():
                    if amount > 0:
                        normalized['free'][currency] = float(amount)
                for currency, amount in balance.get('used', {}).items():
                    if amount > 0:
                        normalized['used'][currency] = float(amount)
                for currency, amount in balance.get('total', {}).items():
                    if amount > 0:
                        normalized['total'][currency] = float(amount)
            
            return web.json_response(normalized)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def ccxt_positions(self, request: web.Request) -> web.Response:
        """Get positions from CCXT Delta."""
        try:
            positions = ccxt_delta_provider.fetch_positions()
            normalized = []
            for p in positions:
                normalized.append({
                    'symbol': _sanitize(p.get('symbol', '')),
                    'side': _sanitize(p.get('side', '')),
                    'contracts': _sanitize(p.get('contracts', 0)),
                    'entry_price': _sanitize(p.get('entryPrice', 0)),
                    'mark_price': _sanitize(p.get('markPrice', 0)),
                    'liquidation_price': _sanitize(p.get('liquidationPrice', 0)),
                    'unrealized_pnl': _sanitize(p.get('unrealizedPnl', 0)),
                    'leverage': _sanitize(p.get('leverage', 0)),
                    'percentage': _sanitize(p.get('percentage', 0)),
                })
            return web.json_response({'positions': normalized})
        except Exception as e:
            return web.json_response({'positions': [], 'error': str(e)})
    
    async def close(self) -> None:
        """Clean up resources."""
        await ccxt_delta_provider.exchange.close() if ccxt_delta_provider.exchange else None
    
    async def recommendations(self, request: web.Request) -> web.Response:
        """Get timeframe recommendations from the recommendation agent."""
        try:
            import sys
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from core.agent_registry import agent_registry
            rec_agent = agent_registry.get_agent("TimeframeRecommendationAgent")
            
            if not rec_agent:
                return web.json_response({'error': 'Recommendation agent not running'}, status=503)
            
            recommendations = rec_agent.get_all_recommendations()
            return web.json_response({'recommendations': recommendations})
        except Exception as e:
            return web.json_response({'error': str(e), 'recommendations': {}}, status=500)
    
    async def trading_suggestions(self, request: web.Request) -> web.Response:
        """Get real-time suggestions combined with open positions and market data."""
        try:
            import sys
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from core.agent_registry import agent_registry
            rec_agent = agent_registry.get_agent("TimeframeRecommendationAgent")
            recommendations = rec_agent.get_all_recommendations() if rec_agent else {}
            
            # Get open positions
            positions = await delta_client.get_positions()
            positions_by_symbol = {p['symbol']: p for p in positions}
            
            # Get CCXT top gainers for real-time market pulse
            ccxt_gainers = ccxt_delta_provider.get_top_gainers(10)
            
            # Build enriched suggestions
            suggestions = []
            
            for symbol, rec in recommendations.items():
                suggestion = dict(rec)
                position = positions_by_symbol.get(symbol)
                if position:
                    suggestion['position'] = position
                    suggestion['has_position'] = True
                else:
                    suggestion['has_position'] = False
                
                # Attach real-time ticker if available
                for g in ccxt_gainers:
                    if g['symbol'].startswith(symbol.split('USDT')[0]):
                        suggestion['change_24h'] = g.get('change_24h', 0)
                        suggestion['mark_price'] = g.get('mark_price', 0)
                        break
                
                suggestions.append(suggestion)
            
            # Add ETH/SOL recommendations from CCXT gainers if not already present
            for sym in ['ETH/USDT:USDT', 'SOL/USDT:USDT']:
                base = sym.split('/')[0]
                if not any(s['symbol'].startswith(base) for s in suggestions):
                    gainer = next((g for g in ccxt_gainers if g['symbol'] == sym), None)
                    if gainer:
                        suggestions.append({
                            'symbol': base + 'USDT',
                            'direction': 'long' if gainer['change_24h'] > 0 else 'short',
                            'confidence': 0.5,
                            'recommended_timeframe': '15m',
                            'confluence_score': 0.3,
                            'bias_score': 0.5,
                            'risk_score': 0.9,
                            'change_24h': gainer.get('change_24h', 0),
                            'mark_price': gainer.get('mark_price', 0),
                            'has_position': False,
                            'source': 'market_momentum'
                        })
            
            return web.json_response({
                'suggestions': suggestions,
                'open_positions': positions,
                'recommendations_count': len(recommendations),
                'updated': datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return web.json_response({'error': str(e), 'suggestions': []}, status=500)
    
    async def trading_allocations(self, request: web.Request) -> web.Response:
        """Get margin allocations and profit potential for each recommendation."""
        try:
            import sys
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from core.agent_registry import agent_registry
            rec_agent = agent_registry.get_agent("TimeframeRecommendationAgent")
            recommendations = rec_agent.get_all_recommendations() if rec_agent else {}
            
            # Get balance
            balance_data = await delta_client.get_balance()
            account_equity = float(balance_data.get("total_equity", 0) or 0) if isinstance(balance_data, dict) and "error" not in balance_data else 0
            available_margin = float(balance_data.get("available_margin", 0) or 0) if isinstance(balance_data, dict) and "error" not in balance_data else 0
            
            # Get positions
            positions = await delta_client.get_positions()
            positions_by_symbol = {p['symbol']: p for p in positions}
            
            # Get CCXT gainers
            ccxt_gainers = ccxt_delta_provider.get_top_gainers(10)
            
            # Build allocation list
            allocations = []
            for symbol, rec in recommendations.items():
                allocation = margin_engine.analyze_recommendation(
                    symbol=symbol,
                    direction=rec.get("direction", "flat"),
                    confidence=rec.get("confidence", 0.5),
                    account_equity=account_equity,
                    available_margin=available_margin,
                    timeframe=rec.get("recommended_timeframe", "15m"),
                    has_position=symbol in positions_by_symbol,
                    position=positions_by_symbol.get(symbol),
                )
                allocations.append(allocation)
            
            # Add ETH/SOL momentum allocations
            for sym in ['ETH/USDT:USDT', 'SOL/USDT:USDT']:
                base = sym.split('/')[0]
                if not any(a.symbol.startswith(base) for a in allocations):
                    gainer = next((g for g in ccxt_gainers if g['symbol'] == sym), None)
                    if gainer:
                        allocation = margin_engine.analyze_recommendation(
                            symbol=base + 'USDT',
                            direction='long' if gainer['change_24h'] > 0 else 'short',
                            confidence=0.5,
                            account_equity=account_equity,
                            available_margin=available_margin,
                            timeframe='15m',
                        )
                        allocations.append(allocation)
            
            # Generate summary
            summary = margin_engine._summarize_recommendations(allocations, recommendations)
            
            return web.json_response({
                'allocations': [self._allocation_to_dict(a) for a in allocations],
                'summary': summary,
                'account_equity': account_equity,
                'available_margin': available_margin,
                'updated': datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return web.json_response({'error': str(e), 'allocations': []}, status=500)
    
    async def _allocation_to_dict(self, a) -> Dict:
        """Convert MarginAllocation to JSON-safe dict."""
        return {
            'symbol': _sanitize(a.symbol),
            'direction': _sanitize(a.direction),
            'confidence': _sanitize(a.confidence),
            'recommended_margin_pct': _sanitize(a.recommended_margin_pct),
            'recommended_margin_usd': _sanitize(a.recommended_margin_usd),
            'max_margin_usd': _sanitize(a.max_margin_usd),
            'leverage': _sanitize(a.leverage),
            'estimated_profit_usd': _sanitize(a.estimated_profit_usd),
            'estimated_risk_usd': _sanitize(a.estimated_risk_usd),
            'risk_reward_ratio': _sanitize(a.risk_reward_ratio),
            'profit_probability': _sanitize(a.profit_probability),
            'timeframe': _sanitize(a.timeframe),
            'volatility_atr_pct': _sanitize(a.volatility_atr_pct),
            'volume_ratio': _sanitize(a.volume_ratio),
            'liquidity_depth_usd': _sanitize(a.liquidity_depth_usd),
            'funding_rate_pct': _sanitize(a.funding_rate_pct),
            'open_interest': _sanitize(a.open_interest),
            'reasoning': [_sanitize(r) for r in a.reasoning],
        }
    
    async def options_scan(self, request: web.Request) -> web.Response:
        """Scan Delta options for inflated OTM contracts."""
        try:
            limit = int(request.query.get('limit', '30'))
            candidates = options_scanner.scan(limit)
            return web.json_response({'candidates': candidates, 'count': len(candidates)})
        except Exception as e:
            return web.json_response({'candidates': [], 'error': str(e)}, status=500)
    
    async def options_payoff(self, request: web.Request) -> web.Response:
        """Generate payoff simulation for an option."""
        try:
            spot = float(request.query.get('spot', '0'))
            strike = float(request.query.get('strike', '0'))
            premium = float(request.query.get('premium', '0'))
            option_type = request.query.get('option_type', 'call')
            range_pct = float(request.query.get('range_pct', '0.25'))
            
            if spot <= 0 or strike <= 0 or premium <= 0:
                return web.json_response({'error': 'spot, strike, and premium are required'}, status=400)
            
            simulation = payoff_engine.simulate(spot, strike, premium, option_type, range_pct)
            return web.json_response({
                'spot_prices': [_sanitize(p) for p in simulation.spot_prices],
                'long_call_pnl': [_sanitize(p) for p in simulation.long_call_pnl],
                'short_call_pnl': [_sanitize(p) for p in simulation.short_call_pnl],
                'long_put_pnl': [_sanitize(p) for p in simulation.long_put_pnl],
                'short_put_pnl': [_sanitize(p) for p in simulation.short_put_pnl],
                'break_even_long_call': _sanitize(simulation.break_even_long_call),
                'break_even_short_call': _sanitize(simulation.break_even_short_call),
                'max_profit_short_call': _sanitize(simulation.max_profit_short_call),
                'max_loss_short_call': 'infinite',
                'max_profit_short_put': _sanitize(simulation.max_profit_short_put),
                'max_loss_short_put': _sanitize(simulation.max_loss_short_put),
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def deploy_strategy(self, request: web.Request) -> web.Response:
        """Deploy the optimized strategy for live execution."""
        try:
            body = await request.json()
            strategy = body.get('strategy', strategy_manager.get_best_overall() or {})
            result = await execution_engine.deploy(strategy)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def execution_status(self, request: web.Request) -> web.Response:
        """Get execution engine status."""
        try:
            return web.json_response(await execution_engine.status())
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def execution_stop(self, request: web.Request) -> web.Response:
        """Stop live execution."""
        try:
            result = await execution_engine.stop()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_trigger_bias(self, request: web.Request) -> web.Response:
        """Debug: manually trigger bias analysis."""
        try:
            import sys
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from core.agent_registry import agent_registry
            bias_agent = agent_registry.get_agent("BiasDeterminingAgent")
            
            if not bias_agent:
                return web.json_response({'error': 'Bias agent not found'}, status=404)
            
            for symbol in bias_agent._price_history.keys():
                await bias_agent._analyze_bias(symbol)
            
            return web.json_response({
                'status': 'triggered',
                'bias_signals': {k: str(v) for k, v in bias_agent._current_bias.items()},
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_events(self, request: web.Request) -> web.Response:
        """Debug: show recent events and agent signal state."""
        try:
            import sys
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from core.event_bus import event_bus
            from core.agent_registry import agent_registry
            
            # Recent event types
            recent = event_bus.get_recent_events(limit=5000)
            event_types = {}
            for e in recent:
                event_types[e.type.value] = event_types.get(e.type.value, 0) + 1
            
            # Agent signal state
            rec_agent = agent_registry.get_agent("TimeframeRecommendationAgent")
            bias_agent = agent_registry.get_agent("BiasDeterminingAgent")
            confluence_agent = agent_registry.get_agent("MultiTimeframeConfluenceAgent")
            
            signal_state = {}
            if bias_agent:
                signal_state['bias_signals'] = {k: v for k, v in bias_agent._current_bias.items()}
                signal_state['bias_price_history_keys'] = {s: {tf: len(deq) for tf, deq in bias_agent._price_history.get(s, {}).items()} for s in bias_agent._price_history}
            if confluence_agent:
                signal_state['confluence_signals'] = confluence_agent._last_confluence
            if rec_agent:
                signal_state['rec_bias_signals'] = rec_agent._bias_signals
                signal_state['rec_confluence_signals'] = rec_agent._confluence_signals
                signal_state['rec_recommendations'] = rec_agent._recommendations
            
            return web.json_response({
                'event_types': event_types,
                'signal_state': signal_state,
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def xau_status(self, request: web.Request) -> web.Response:
        """Get XAU AI integration status."""
        try:
            status = xau_ai_integration.status()
            return web.json_response({k: _sanitize(v) for k, v in status.items()})
        except Exception as e:
            return web.json_response({'error': str(e), 'available': False}, status=500)
    
    async def xau_smc(self, request: web.Request) -> web.Response:
        """Run SMC analysis on shared data."""
        try:
            # Load candles from shared data
            import json as json_module
            data_dir = Path(__file__).parent.parent / "data" / "shared"
            symbol = request.query.get('symbol', 'XAUTUSDT')
            timeframe = request.query.get('timeframe', '15m')
            file_path = data_dir / f"{symbol}_{timeframe}.json"
            
            if not file_path.exists():
                return web.json_response({'error': f'No data for {symbol} {timeframe}'}, status=404)
            
            with open(file_path, 'r') as f:
                candles = json_module.load(f)
            
            # Limit to last 500 candles for analysis
            candles = candles[-500:]
            result = xau_ai_integration.run_smc_analysis(candles)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def xau_regime(self, request: web.Request) -> web.Response:
        """Detect market regime using XAU AI HMM."""
        try:
            import json as json_module
            data_dir = Path(__file__).parent.parent / "data" / "shared"
            symbol = request.query.get('symbol', 'XAUTUSDT')
            timeframe = request.query.get('timeframe', '15m')
            file_path = data_dir / f"{symbol}_{timeframe}.json"
            
            if not file_path.exists():
                return web.json_response({'error': f'No data for {symbol} {timeframe}'}, status=404)
            
            with open(file_path, 'r') as f:
                candles = json_module.load(f)
            
            candles = candles[-500:]
            result = xau_ai_integration.detect_regime(candles)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def xau_kelly(self, request: web.Request) -> web.Response:
        """Calculate Kelly criterion position size."""
        try:
            win_rate = float(request.query.get('win_rate', '0.55'))
            avg_win = float(request.query.get('avg_win', '8.0'))
            avg_loss = float(request.query.get('avg_loss', '4.0'))
            kelly_fraction = float(request.query.get('kelly_fraction', '0.5'))
            
            result = xau_ai_integration.kelly_position_size(win_rate, avg_win, avg_loss, kelly_fraction)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def xau_risk(self, request: web.Request) -> web.Response:
        """Calculate risk analytics from equity curve."""
        try:
            equity = request.query.get('equity', None)
            if equity:
                equity_curve = [float(x) for x in equity.split(',')]
            else:
                # Use XAUTUSD performance as proxy
                import json as json_module
                data_dir = Path(__file__).parent.parent / "data" / "shared"
                file_path = data_dir / "XAUTUSDT_15m.json"
                with open(file_path, 'r') as f:
                    candles = json_module.load(f)
                equity_curve = [float(c.get('close', 0)) for c in candles[-200:]]
            
            result = xau_ai_integration.risk_analytics(equity_curve)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
