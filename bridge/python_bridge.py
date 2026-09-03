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
    origin = request.headers.get('Origin', '')
    allowed = {'http://localhost:3000', 'http://127.0.0.1:3000'}
    if origin in allowed:
        response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

import secrets as _secrets
import os as _os
_env_token = _os.environ.get('BRIDGE_AUTH_TOKEN')
if not _env_token:
    try:
        _env_path = Path(__file__).parent.parent / '.env'
        if _env_path.exists():
            for _line in _env_path.read_text().splitlines():
                if _line.startswith('BRIDGE_AUTH_TOKEN='):
                    _env_token = _line.split('=', 1)[1].strip()
                    break
    except Exception:
        pass
_AUTH_TOKEN = _env_token or _secrets.token_urlsafe(32)

def _check_auth(request: web.Request) -> bool:
    """Verify Bearer token on sensitive endpoints."""
    auth = request.headers.get('Authorization', '')
    return auth == f'Bearer {_AUTH_TOKEN}'

import re as _re
_SYMBOL_RE = _re.compile(r'^[A-Z0-9]{1,20}$')
_TIMEFRAME_RE = _re.compile(r'^(1m|5m|15m|1h|4h|1d)$')

def _validate_symbol(name: str) -> bool:
    return bool(_SYMBOL_RE.match(name))

def _validate_timeframe(tf: str) -> bool:
    return bool(_TIMEFRAME_RE.match(tf))

def _safe_path(base_dir: Path, filename: str) -> Optional[Path]:
    """Build a path inside base_dir, rejecting traversal."""
    target = (base_dir / filename).resolve()
    if not target.is_relative_to(base_dir.resolve()):
        return None
    return target

from core.event_bus import EventBus, Event, EventType, event_bus
from core.metrics_engine import MetricsEngine, metrics_engine, _sanitize
from core.strategy_deployment import StrategyDeploymentManager, strategy_manager
from core.margin_allocation_engine import MarginAllocationEngine, margin_engine
from core.strategy_execution_engine import StrategyExecutionEngine, execution_engine
from core.options_engine import OptionsScanner, options_scanner, PayoffEngine, payoff_engine
from data.delta_api_client import DeltaAPIClient, delta_client, DeltaAPIMode, diagnose_delta_error
from data.ccxt_delta_provider import CCXTDeltaProvider, ccxt_delta_provider
from core.economic_calendar import economic_calendar
from core.strategy_library import run_backtest as _library_backtest, STRATEGIES as _STRATEGIES, optimize as _optimize_strategy, list_strategies as _list_strategies, generate_strategy_spec as _generate_strategy_spec
from core.trade_journal import trade_journal as _journal

# Strategy selected by the user in the UI (in-memory only, never persisted with secrets).
selected_strategy = None
from data.market_banner import fetch_banner as fetch_market_banner
from data.xau_ai_integration import XAUAIIntegration, xau_ai_integration
from backtest.backtrader_xauusd import run_backtest, get_status, save_results
from backtest.agentm_candle import (
    run_backtest as run_agentm_backtest,
    get_status as get_agentm_status,
    save_results as save_agentm_results,
)


@dataclass
class BridgeConfig:
    """Configuration for the bridge server."""
    host: str = "127.0.0.1"
    port: int = 8088
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
    
    def __init__(self, config: BridgeConfig, bus: EventBus = None):
        self.config = config
        self.event_bus = bus or event_bus
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
        self.app.router.add_get('/delta/options', self.delta_options)
        self.app.router.add_get('/delta/candles', self.delta_candles)
        self.app.router.add_post('/delta/mode', self.delta_set_mode)
        self.app.router.add_post('/delta/credentials', self.delta_set_credentials)
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
        self.app.router.add_post('/analysis/run', self.run_analysis)
        self.app.router.add_get('/analysis/results', self.get_analysis_results)
        self.app.router.add_get('/backtrader/status', self.backtrader_status)
        self.app.router.add_post('/backtrader/run', self.backtrader_run)
        self.app.router.add_get('/backtrader/results', self.backtrader_results)
        self.app.router.add_post('/backtest/run', self.backtest_run)
        self.app.router.add_get('/calendar/events', self.calendar_events)
        self.app.router.add_get('/strategies/library', self.strategy_library)
        self.app.router.add_post('/strategies/optimize', self.strategy_optimize)
        self.app.router.add_post('/strategies/generate', self.strategy_generate)
        # Journal
        self.app.router.add_get('/journal/stats', self.journal_stats)
        self.app.router.add_get('/journal/trades', self.journal_trades_list)
        self.app.router.add_post('/journal/trades', self.journal_trades_add)
        self.app.router.add_post('/journal/trades/close', self.journal_trades_close)
        self.app.router.add_post('/journal/trades/update', self.journal_trades_update)
        self.app.router.add_delete('/journal/trades', self.journal_trades_delete)
        self.app.router.add_get('/journal/sessions', self.journal_sessions)
        self.app.router.add_post('/journal/sessions/start', self.journal_session_start)
        self.app.router.add_post('/journal/sessions/end', self.journal_session_end)
        self.app.router.add_get('/journal/log', self.journal_log_get)
        self.app.router.add_post('/journal/log', self.journal_log_add)
        self.app.router.add_get('/journal/notifications', self.journal_notifications_get)
        self.app.router.add_post('/journal/notifications', self.journal_notifications_save)
        self.app.router.add_delete('/journal/notifications', self.journal_notifications_delete)
        self.app.router.add_post('/journal/notifications/check', self.journal_notifications_check)
        self.app.router.add_get('/journal/notification-log', self.journal_notification_log)
        self.app.router.add_get('/agentm/status', self.agentm_status)
        self.app.router.add_post('/agentm/run', self.agentm_run)
        self.app.router.add_get('/agentm/results', self.agentm_results)
        self.app.router.add_get('/market/banner', self.market_banner)
        # ── Analytics / feature engineering endpoints ──────────────────────
        self.app.router.add_get('/analytics/features', self.analytics_features)
        self.app.router.add_get('/analytics/microfeatures', self.analytics_microfeatures)
        self.app.router.add_get('/analytics/regime', self.analytics_regime)
        self.app.router.add_get('/analytics/alpha-zoo', self.analytics_alpha_zoo)
        self.app.router.add_get('/analytics/leakage', self.analytics_leakage)
        self.app.router.add_get('/analytics/registry', self.analytics_registry)
        self.app.router.add_post('/bot/start', self.bot_start)
        self.app.router.add_post('/bot/stop', self.bot_stop)
        self.app.router.add_get('/bot/status', self.bot_status)
    
    async def start(self) -> None:
        """Start the bridge server."""
        await self._subscribe_to_events()
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        self._status["running"] = True
        print(f"Python bridge server running at http://{self.config.host}:{self.config.port}")
        print(f"Bridge auth token: {_AUTH_TOKEN}")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant events."""
        if self._subscribed:
            return
        
        await self.event_bus.subscribe(EventType.TRADE_LOG, self._on_trade_log, "PythonBridge")
        await self.event_bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert, "PythonBridge")
        await self.event_bus.subscribe(EventType.MODE_SWITCH, self._on_mode_switch, "PythonBridge")
        await self.event_bus.subscribe(EventType.AGENT_HEARTBEAT, self._on_heartbeat, "PythonBridge")
        self._subscribed = True
        try:
            _journal.start_session('system')
            _journal.log('Bridge started — journal online', category='system', level='INFO')
        except Exception:
            pass
    
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
        self._journal_event(event, 'trade', 'INFO')

    async def _on_risk_alert(self, event: Event) -> None:
        """Forward risk alerts."""
        await self._event_queue.put(event)
        self._journal_event(event, 'risk', 'WARNING')

    async def _on_mode_switch(self, event: Event) -> None:
        """Forward mode switches."""
        await self._event_queue.put(event)
        self._journal_event(event, 'system', 'INFO')

    async def _journal_event(self, event: Event, category: str, level: str) -> None:
        """Auto-capture system events into the trade-journal session log."""
        try:
            p = event.payload or {}
            msg = p.get('type') or p.get('event') or p.get('message') or 'event'
            detail = {'event_type': event.type.value if hasattr(event.type, 'value') else str(event.type)}
            if category == 'trade':
                for k in ('symbol', 'trade_id', 'action', 'status'):
                    if p.get(k):
                        detail[k] = p[k]
            _journal.log(msg, category=category, level=level, detail=detail)
        except Exception:
            pass
    
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
        if not _validate_symbol(symbol) or not _validate_timeframe(timeframe):
            return web.json_response({"error": "Invalid symbol or timeframe"}, status=400)
        limit = int(request.query.get('limit', '1000'))
        
        data_dir = Path(self.config.shared_data_dir)
        file_path = _safe_path(data_dir, f"{symbol}_{timeframe}.json")
        if file_path is None:
            return web.json_response({"error": "Invalid path"}, status=400)
        
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
        """Server-sent events stream (public — CORS restricts origins; EventSource cannot send headers)."""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        origin = request.headers.get('Origin', '')
        if origin in ('http://localhost:3000', 'http://127.0.0.1:3000'):
            response.headers['Access-Control-Allow-Origin'] = origin
        await response.prepare(request)
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=30)
                    data = json.dumps({
                        "type": event.type.value,
                        "source": event.source_agent,
                        "timestamp": event.timestamp.isoformat(),
                        "payload": event.payload
                    })
                    await response.write(f"data: {data}\n\n".encode())
                    await response.drain()
                except asyncio.TimeoutError:
                    # Send keepalive to keep the stream open (client EventSource stays connected)
                    await response.write(f"data: {json.dumps({'type': 'keepalive'})}\n\n".encode())
                    await response.drain()
        except Exception as e:
            print(f"SSE error: {e}")
        finally:
            pass
    
    async def command(self, request: web.Request) -> web.Response:
        """Receive commands from TypeScript engine."""
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
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

    async def delta_options(self, request: web.Request) -> web.Response:
        """Get options for an underlying asset (BTC/ETH/XAU)."""
        try:
            _map = {'XAU': 'XAUT', 'BTC': 'BTC', 'ETH': 'ETH'}
            underlying = _map.get((request.query.get('underlying', 'BTC')).upper(), (request.query.get('underlying', 'BTC')).upper())
            side = request.query.get('side', None)  # call / put / None=all
            tickers = await delta_client.get_tickers()
            opts = []
            for t in tickers:
                if not isinstance(t, dict):
                    continue
                if t.get('underlying_asset_symbol') != underlying:
                    continue
                if t.get('contract_type') not in ('call_options', 'put_options'):
                    continue
                if side and side == 'call' and t.get('contract_type') != 'call_options':
                    continue
                if side and side == 'put' and t.get('contract_type') != 'put_options':
                    continue
                # Parse expiry from symbol like C-BTC-98000-301026 -> 2030-10-26? -> DDMMYY
                sym = t.get('symbol', '')
                expiry = None
                parts = sym.split('-')
                if len(parts) >= 4:
                    date_part = parts[-1]
                    if len(date_part) == 6 and date_part.isdigit():
                        dd, mm, yy = date_part[:2], date_part[2:4], date_part[4:]
                        expiry = f"20{yy}-{mm}-{dd}"
                strike = float(t.get('strike_price', 0) or 0)
                mark = float(t.get('mark_price', 0) or 0)
                spot = float(t.get('spot_price', 0) or 0)
                opts.append({
                    'symbol': sym,
                    'underlying': underlying,
                    'type': 'call' if t.get('contract_type') == 'call_options' else 'put',
                    'strike': strike,
                    'expiry': expiry,
                    'mark_price': mark,
                    'bid': float((t.get('quotes', {}) or {}).get('best_bid', 0) or 0),
                    'ask': float((t.get('quotes', {}) or {}).get('best_ask', 0) or 0),
                    'mark_iv': float((t.get('quotes', {}) or {}).get('mark_iv', 0) or 0),
                    'spot': spot,
                    'change_24h': float(t.get('mark_change_24h', t.get('ltp_change_24h', 0)) or 0),
                    'greeks': {
                        'delta': float((t.get('greeks', {}) or {}).get('delta', 0) or 0),
                        'gamma': float((t.get('greeks', {}) or {}).get('gamma', 0) or 0),
                        'theta': float((t.get('greeks', {}) or {}).get('theta', 0) or 0),
                        'vega': float((t.get('greeks', {}) or {}).get('vega', 0) or 0),
                    },
                    'open_interest': float(t.get('oi_value_usd', 0) or 0),
                    'volume_usd': float(t.get('turnover_usd', 0) or 0),
                })
            # Sort by expiry then strike
            opts.sort(key=lambda o: (o['expiry'] or '', o['strike']))
            return web.json_response({'options': opts, 'underlying': underlying, 'count': len(opts)})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delta_candles(self, request: web.Request) -> web.Response:
        """Proxy candle fetch to Delta API (avoids CORS for browser chart component)."""
        import socket as _sock
        import aiohttp as _aiohttp
        from urllib.parse import urlencode as _urlencode
        symbol = request.query.get('symbol', 'BTCUSD')
        resolution = request.query.get('resolution', '1h')
        start = request.query.get('start', '')
        end = request.query.get('end', '')
        limit = request.query.get('limit', '200')
        if not _validate_symbol(symbol):
            return web.json_response({'success': False, 'error': 'Invalid symbol'}, status=400)
        if not _validate_timeframe(resolution):
            return web.json_response({'success': False, 'error': 'Invalid resolution'}, status=400)
        params = {'symbol': symbol, 'resolution': resolution, 'limit': limit}
        if start and start.isdigit():
            params['start'] = start
        if end and end.isdigit():
            params['end'] = end
        url = f'{delta_client.rest_base}/v2/history/candles?{_urlencode(params)}'
        try:
            connector = _aiohttp.TCPConnector(family=_sock.AF_INET, ssl=False)
            async with _aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    return web.json_response(data)
        except Exception as e:
            return web.json_response({'success': False, 'error': 'Upstream error'}, status=502)

    async def backtest_run(self, request: web.Request) -> web.Response:
        """Run a lightweight backtest on Delta historical candle data."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        strategy = (body.get('strategy') or 'ma_cross')
        asset = (body.get('asset') or 'BTC').upper()
        timeframe = body.get('timeframe') or '1h'
        limit = int(body.get('limit', 500))
        params = body.get('params', {}) or {}
        symbol = f"{asset}USD"
        if asset == 'XAU':
            symbol = 'XAUTUSD'
        if asset == 'SOL':
            symbol = 'SOLUSD'
        if not _validate_symbol(symbol) or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        # Fetch candles
        import socket as _sock
        import aiohttp as _aiohttp
        from urllib.parse import urlencode as _urlencode
        cparams = {'symbol': symbol, 'resolution': timeframe, 'limit': str(limit)}
        now = int(__import__('time').time())
        tf_sec = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}
        cparams['start'] = str(now - (tf_sec.get(timeframe, 3600) * limit))
        cparams['end'] = str(now)
        url = f'{delta_client.rest_base}/v2/history/candles?{_urlencode(cparams)}'
        try:
            connector = _aiohttp.TCPConnector(family=_sock.AF_INET, ssl=False)
            async with _aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=_aiohttp.ClientTimeout(total=20)) as resp:
                    cdata = await resp.json()
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles'}, status=502)
        candles = cdata.get('result', []) if isinstance(cdata, dict) else []
        if not candles:
            return web.json_response({'error': 'No candle data'}, status=404)
        # Normalize to OHLCV (in case source keys differ) and closes
        closes = []
        ohlcv = []
        for c in candles:
            try:
                closes.append(float(c.get('close', c.get('Close', 0))))
                ohlcv.append({
                    'open': float(c.get('open', c.get('Open', 0))),
                    'high': float(c.get('high', c.get('High', 0))),
                    'low': float(c.get('low', c.get('Low', 0))),
                    'close': float(c.get('close', c.get('Close', 0))),
                    'volume': float(c.get('volume', c.get('Volume', 0))),
                })
            except Exception:
                continue
        ohlcv = [c for c in ohlcv if c['close'] > 0]
        if len(closes) < 30:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        if strategy in _STRATEGIES:
            result = _library_backtest(strategy, ohlcv, params)
        else:
            result = self._run_strategy_backtest(strategy, closes, params)
        return web.json_response({'strategy': strategy, 'asset': asset, 'timeframe': timeframe,
                                  'bars': len(closes), 'result': result})

    def _run_strategy_backtest(self, strategy, closes, params):
        """Simple vectorized backtest returning performance metrics."""
        n = len(closes)
        cash = float(params.get('starting_cash', 10000))
        pos = 0  # 0 flat, 1 long
        entry = 0.0
        trades = 0
        wins = 0
        equity = [cash]
        for i in range(1, n):
            price = closes[i]
            prev = closes[i-1]
            signal = 0
            if strategy == 'ma_cross':
                fast = int(params.get('fast', 10))
                slow = int(params.get('slow', 30))
                if i >= slow:
                    ma_f = sum(closes[i-fast:i]) / fast
                    ma_s = sum(closes[i-slow:i]) / slow
                    if ma_f > ma_s and pos == 0:
                        signal = 1
                    elif ma_f < ma_s and pos == 1:
                        signal = -1
            elif strategy == 'rsi':
                period = int(params.get('period', 14))
                ob = float(params.get('overbought', 70))
                os = float(params.get('oversold', 30))
                if i >= period:
                    gains = [max(0, closes[j]-closes[j-1]) for j in range(i-period+1, i+1)]
                    losses = [max(0, closes[j-1]-closes[j]) for j in range(i-period+1, i+1)]
                    avg_g = sum(gains)/period
                    avg_l = sum(losses)/period
                    rs = (avg_g/avg_l) if avg_l > 0 else 100
                    rsi = 100 - (100/(1+rs))
                    if rsi < os and pos == 0:
                        signal = 1
                    elif rsi > ob and pos == 1:
                        signal = -1
            elif strategy in ('scalping_meme', 'short_meme'):
                period = int(params.get('period', 20))
                if i >= period:
                    ma = sum(closes[i-period:i]) / period
                    if strategy == 'scalping_meme':
                        # momentum long on meme coins
                        if price > ma and prev <= ma and pos == 0:
                            signal = 1
                        elif price < ma and prev >= ma and pos == 1:
                            signal = -1
                    else:
                        # short bias: invert
                        if price < ma and prev >= ma and pos == 0:
                            signal = 1
                        elif price > ma and prev <= ma and pos == 1:
                            signal = -1
            else:
                # default: buy and hold baseline
                if i == 1 and pos == 0:
                    signal = 1
                elif i == n-1 and pos == 1:
                    signal = -1
            if signal == 1 and pos == 0:
                pos = 1
                entry = price
                trades += 1
            elif signal == -1 and pos == 1:
                ret = (price - entry) / entry
                cash *= (1 + ret)
                if ret > 0:
                    wins += 1
                pos = 0
            if pos == 1:
                ret = (price - entry) / entry
                equity.append(cash * (1 + ret))
            else:
                equity.append(cash)
        final = equity[-1]
        total_ret = (final / float(params.get('starting_cash', 10000)) - 1) * 100
        peak = max(equity)
        mdd = (peak - min(equity)) / peak * 100 if peak > 0 else 0
        win_rate = (wins / trades * 100) if trades > 0 else 0
        return {
            'starting_cash': float(params.get('starting_cash', 10000)),
            'final_equity': round(final, 2),
            'total_return_pct': round(total_ret, 2),
            'max_drawdown_pct': round(mdd, 2),
            'trades': trades,
            'win_rate': round(win_rate, 1),
            'sharpe': round((total_ret / mdd) if mdd > 0 else 0, 2),
        }

    async def calendar_events(self, request: web.Request) -> web.Response:
        """Return upcoming high-impact economic events from Forex Factory (cached 24h)."""
        include_medium = request.query.get('include_medium', 'false').lower() == 'true'
        try:
            data = await economic_calendar.get_events(include_medium=include_medium)
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'error': str(e), 'upcoming': [], 'next_event': None}, status=500)

    async def _fetch_ohlcv(self, asset: str, timeframe: str, limit: int) -> list:
        """Fetch normalized OHLCV candles from Delta for a given asset/timeframe."""
        import socket as _sock
        import aiohttp as _aiohttp
        from urllib.parse import urlencode as _urlencode
        import time as _time
        symbol = f"{asset}USD"
        if asset == 'XAU':
            symbol = 'XAUTUSD'
        tf_sec = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}
        now = int(_time.time())
        cparams = {
            'symbol': symbol, 'resolution': timeframe, 'limit': str(limit),
            'start': str(now - (tf_sec.get(timeframe, 3600) * limit)), 'end': str(now),
        }
        url = f'{delta_client.rest_base}/v2/history/candles?{_urlencode(cparams)}'
        connector = _aiohttp.TCPConnector(family=_sock.AF_INET, ssl=False)
        async with _aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=_aiohttp.ClientTimeout(total=20)) as resp:
                cdata = await resp.json()
        raw = cdata.get('result', []) if isinstance(cdata, dict) else []
        out = []
        for c in raw:
            try:
                out.append({
                    'open': float(c.get('open', c.get('Open', 0))),
                    'high': float(c.get('high', c.get('High', 0))),
                    'low': float(c.get('low', c.get('Low', 0))),
                    'close': float(c.get('close', c.get('Close', 0))),
                    'volume': float(c.get('volume', c.get('Volume', 0))),
                })
            except Exception:
                continue
        return [c for c in out if c['close'] > 0]

    async def strategy_library(self, request: web.Request) -> web.Response:
        """Return metadata for all onboarded strategies (drives the Strategy Library UI)."""
        return web.json_response({
            'count': len(_STRATEGIES),
            'strategies': _list_strategies(),
            'assets': list({a for s in _STRATEGIES.values() for a in s.get('assets', [])}),
            'classes': list({s.get('class') for s in _STRATEGIES.values()}),
        })

    async def strategy_optimize(self, request: web.Request) -> web.Response:
        """Grid-search strategy params on live Delta candles; returns top combos."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        sid = body.get('strategy') or 'ma_cross'
        if sid not in _STRATEGIES:
            return web.json_response({'error': f'Unknown strategy {sid}'}, status=400)
        asset = (body.get('asset') or 'BTC').upper()
        timeframe = body.get('timeframe') or '1h'
        limit = int(body.get('limit', 500))
        if not _validate_symbol(f"{asset}USD") or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        grid = body.get('grid') or {}
        base = body.get('params') or {}
        try:
            candles = await self._fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles'}, status=502)
        if len(candles) < 60:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        results = _optimize_strategy(sid, candles, base, grid, top=int(body.get('top', 5)))
        return web.json_response({
            'strategy': sid, 'asset': asset, 'timeframe': timeframe,
            'bars': len(candles), 'top_results': results,
        })

    async def strategy_generate(self, request: web.Request) -> web.Response:
        """Turn a plain-English strategy description into a full engine-ready
        parameter specification."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        desc = (body.get('description') or '').strip()
        if len(desc) < 4:
            return web.json_response({'error': 'Describe the strategy in a sentence or two.'}, status=400)
        try:
            spec = _generate_strategy_spec(desc)
        except Exception as e:
            return web.json_response({'error': f'Could not parse description: {e}'}, status=422)
        return web.json_response(spec)

    # ── Trade Journal ────────────────────────────────────────────────────────
    @staticmethod
    def _journal_ctx() -> Dict[str, Any]:
        """Pull engine state used by notification rules (stats, calendar)."""
        try:
            st = _journal.stats()
            total = st["total"]
            return {
                "total": total,
                "daily_pnl_usd": total["net_pnl"],
                "losses_streak": total["streaks"]["losses"],
                "wins_streak": total["streaks"]["wins"],
                "drawdown_pct": round(total["max_drawdown_usd"], 2),
                "open_positions": st["open_positions"],
            }
        except Exception:
            return {}

    async def journal_stats(self, request: web.Request) -> web.Response:
        try:
            days = request.query.get('days')
            days = int(days) if days and days.isdigit() else None
            symbol = request.query.get('symbol', 'ALL')
            strategy = request.query.get('strategy', 'ALL')
            data = _journal.stats(days=days, symbol=symbol if symbol != 'ALL' else None,
                                  strategy=strategy if strategy != 'ALL' else None)
            data['state'] = self._journal_ctx()
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_trades_list(self, request: web.Request) -> web.Response:
        try:
            trades = _journal.get_trades(
                status=request.query.get('status', 'ALL'),
                symbol=request.query.get('symbol', 'ALL'),
                strategy=request.query.get('strategy', 'ALL'),
                limit=int(request.query.get('limit', 500)))
            return web.json_response({'trades': trades, 'count': len(trades)})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_trades_add(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        symbol = (str(body.get('symbol') or '')).strip().upper()
        if not symbol or len(symbol) > 20:
            return web.json_response({'error': 'Invalid symbol'}, status=400)
        try:
            trade = _journal.add_trade(
                symbol=symbol,
                side=(body.get('side') or 'buy'),
                qty=float(body.get('qty') or 0),
                size_usd=float(body.get('size_usd') or 0),
                entry_price=float(body.get('entry_price') or 0),
                exit_price=float(body.get('exit_price')) if body.get('exit_price') else None,
                strategy=(body.get('strategy') or ''),
                notes=(body.get('notes') or ''),
                tags=body.get('tags'),
                source=(body.get('source') or 'manual'),
            )
            await self.event_bus.publish(Event(
                type=EventType.TRADE_LOG,
                payload={'type': 'journal', 'trade_id': trade['id'], 'symbol': trade['symbol'],
                         'status': trade['status']},
                source_agent='JournalBridge'))
            return web.json_response({'trade': trade})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def journal_trades_close(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        trade_id = body.get('trade_id') or body.get('id')
        if not trade_id:
            return web.json_response({'error': 'Missing trade_id'}, status=400)
        try:
            trade = _journal.close_trade(
                trade_id=trade_id,
                exit_price=float(body['exit_price']) if body.get('exit_price') else None,
                exit_price_delta=float(body.get('exit_price_delta') or 0),
                fees=float(body.get('fees') or 0),
                notes=body.get('notes'))
            if not trade:
                return web.json_response({'error': 'Trade not found'}, status=404)
            return web.json_response({'trade': trade})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def journal_trades_update(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        trade_id = body.get('trade_id') or body.get('id')
        if not trade_id:
            return web.json_response({'error': 'Missing trade_id'}, status=400)
        try:
            trade = _journal.update_trade(trade_id, notes=body.get('notes'),
                                          strategy=body.get('strategy'), tags=body.get('tags'),
                                          source=body.get('source'))
            return web.json_response({'trade': trade})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def journal_trades_delete(self, request: web.Request) -> web.Response:
        try:
            trade_id = request.query.get('id') or request.query.get('trade_id')
            if not trade_id:
                return web.json_response({'error': 'Missing id'}, status=400)
            ok = _journal.delete_trade(trade_id)
            return web.json_response({'deleted': ok})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def journal_sessions(self, request: web.Request) -> web.Response:
        try:
            return web.json_response({'sessions': _journal.get_sessions(limit=int(request.query.get('limit', 50)))})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_session_start(self, request: web.Request) -> web.Response:
        try:
            source = request.query.get('source') or request.query.get('origin') or 'ui'
            sid = _journal.start_session(source)
            await self.event_bus.publish(Event(
                type=EventType.AGENT_HEARTBEAT,
                payload={'event': 'session_started', 'session_id': sid, 'source': source},
                source_agent='JournalBridge'))
            return web.json_response({'session_id': sid, 'status': 'started'})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_session_end(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        sid = body.get('session_id') or request.query.get('session_id')
        output = body.get('output') or {}
        sess = _journal.end_session(sid)
        if sess:
            _journal.log(f"Session ended — source {sess.get('source')}", category='system',
                         level='INFO', session_id=sess['id'],
                         detail={'duration_min': sess.get('duration_min')})
        return web.json_response({'session': sess})

    async def journal_log_get(self, request: web.Request) -> web.Response:
        try:
            rows = _journal.get_log(
                category=request.query.get('category', 'ALL'),
                session_id=request.query.get('session_id', 'ALL'),
                level=request.query.get('level', 'ALL'),
                limit=int(request.query.get('limit', 300)))
            return web.json_response({'entries': rows})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_log_add(self, request: web.Request) -> web.Response:
        """UI / agents report an event; auto-captured into the session log."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        message = (body.get('message') or '').strip()
        if not message:
            return web.json_response({'error': 'Missing message'}, status=400)
        category = (body.get('category') or 'info')
        level = (body.get('level') or 'INFO')
        session_id = body.get('session_id')
        _journal.log(message, category=category, level=level,
                     detail=body.get('detail'),
                     session_id=session_id if session_id and session_id != 'ALL' else None)
        return web.json_response({'status': 'logged'})

    async def journal_notifications_get(self, request: web.Request) -> web.Response:
        try:
            return web.json_response({'rules': _journal.get_rules()})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_notifications_save(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        trigger = (body.get('trigger') or '')
        title = (body.get('title') or '').strip()
        if not trigger or not title:
            return web.json_response({'error': 'Missing trigger or title'}, status=400)
        try:
            rule = _journal.save_rule(
                rule_id=body.get('id'),
                trigger=trigger, title=title,
                message=body.get('message') or '',
                priority=body.get('priority') or 'normal',
                threshold=float(body.get('threshold') or 0),
                threshold_units=body.get('threshold_units') or 'none',
                cooldown_sec=int(body.get('cooldown_sec') or 60),
                enabled=bool(body.get('enabled', True)))
            return web.json_response({'rule': rule})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def journal_notifications_delete(self, request: web.Request) -> web.Response:
        try:
            rule_id = request.query.get('id')
            if not rule_id:
                return web.json_response({'error': 'Missing id'}, status=400)
            return web.json_response({'deleted': _journal.delete_rule(rule_id)})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_notifications_check(self, request: web.Request) -> web.Response:
        """Evaluate notification rules against current engine state; pushes any
        triggered notifications to the SSE stream so the UI can toast them."""
        try:
            ctx = self._journal_ctx()
            ne = None
            try:
                cal = await economic_calendar.get_events()
                ne = cal.get('next_event')
            except Exception:
                pass
            if ne:
                ctx['next_event'] = ne
            state = dict(ctx)
            res = _journal.check_all(state)
            triggered = res.get('triggered', [])
            for t in triggered:
                await self._event_queue.put(Event(
                    type=EventType.RISK_ALERT,
                    payload={'journal_notification': True, 'trigger': t['trigger'],
                             'title': t['title'], 'message': t['message'],
                             'priority': t['priority']},
                    source_agent='JournalBridge'))
                _journal.log(f"Push notification: {t['title']}", category='ui',
                             level='INFO', detail={'message': t['message']})
            return web.json_response({'triggered': triggered, 'count': len(triggered)})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def journal_notification_log(self, request: web.Request) -> web.Response:
        try:
            return web.json_response({'entries': _journal.notification_log(
                limit=int(request.query.get('limit', 50)))})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delta_set_mode(self, request: web.Request) -> web.Response:
        """Switch Delta API mode (read_only/trading)."""
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
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

    async def delta_set_credentials(self, request: web.Request) -> web.Response:
        """Set Delta API credentials IN MEMORY (no disk persistence by default) and test the connection.

        Body: { api_key, api_secret, environment, mode, strategy, remember? }
        Secrets are never logged. If `remember` is true they are written to the gitignored .env file.
        """
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        try:
            body = await request.json()
            api_key = (body.get('api_key') or '').strip()
            api_secret = (body.get('api_secret') or '').strip()
            if len(api_key) > 200 or len(api_secret) > 200:
                return web.json_response({'error': 'Credentials too long'}, status=400)
            if not all(c.isprintable() for c in api_key + api_secret):
                return web.json_response({'error': 'Invalid characters in credentials'}, status=400)
            environment = body.get('environment', 'production')
            mode = body.get('mode', 'read_only')
            strategy = body.get('strategy') or None
            remember = bool(body.get('remember', False))

            if not api_key or not api_secret:
                return web.json_response({
                    'status': 'auth_failed',
                    'error_code': 'no_keys',
                    'error_message': 'API key and secret are both required.',
                    'diagnostic': diagnose_delta_error('no_keys', environment),
                    'connected': False,
                }, status=400)

            # Update in-memory credentials (singleton) — never persisted unless remember is set.
            delta_client.set_credentials_full(api_key, api_secret, environment, mode)

            # Store selected strategy in memory for suggestions/allocations/deploy.
            global selected_strategy
            selected_strategy = strategy

            if remember:
                try:
                    env_path = Path(__file__).parent.parent / '.env'
                    lines = []
                    if env_path.exists():
                        with open(env_path, 'r') as f:
                            lines = f.read().splitlines()
                    keep = [ln for ln in lines if not ln.startswith('DELTA_API_KEY=') and not ln.startswith('DELTA_API_SECRET=') and not ln.startswith('DELTA_ENVIRONMENT=')]
                    keep.append(f'DELTA_API_KEY={api_key}')
                    keep.append(f'DELTA_API_SECRET={api_secret}')
                    keep.append(f'DELTA_ENVIRONMENT={environment}')
                    with open(env_path, 'w') as f:
                        f.write('\n'.join(keep) + '\n')
                    import os as _os
                    _os.chmod(env_path, 0o600)
                except Exception:
                    pass  # best-effort persistence; never fail the connection test on it

            # Test the connection (network + auth) with a structured diagnostic.
            result = await delta_client.test_connection()
            result['selected_strategy'] = selected_strategy
            # Never echo secrets back.
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': str(e), 'status': 'error'}, status=500)
    
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
                'selected_strategy': selected_strategy,
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
                'selected_strategy': selected_strategy,
                'updated': datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return web.json_response({'error': str(e), 'allocations': []}, status=500)
    
    def _allocation_to_dict(self, a) -> Dict:
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
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
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
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        try:
            result = await execution_engine.stop()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_trigger_bias(self, request: web.Request) -> web.Response:
        """Debug: manually trigger bias analysis."""
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
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
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
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
            import json as json_module
            data_dir = Path(__file__).parent.parent / "data" / "shared"
            symbol = request.query.get('symbol', 'XAUTUSDT')
            timeframe = request.query.get('timeframe', '15m')
            if not _validate_symbol(symbol) or not _validate_timeframe(timeframe):
                return web.json_response({'error': 'Invalid symbol or timeframe'}, status=400)
            file_path = _safe_path(data_dir, f"{symbol}_{timeframe}.json")
            if file_path is None:
                return web.json_response({'error': 'Invalid path'}, status=400)
            
            if not file_path.exists():
                return web.json_response({'error': 'No data available'}, status=404)
            
            with open(file_path, 'r') as f:
                candles = json_module.load(f)
            
            candles = candles[-500:]
            result = xau_ai_integration.run_smc_analysis(candles)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': 'Internal error'}, status=500)
    
    async def xau_regime(self, request: web.Request) -> web.Response:
        """Detect market regime using XAU AI HMM."""
        try:
            import json as json_module
            data_dir = Path(__file__).parent.parent / "data" / "shared"
            symbol = request.query.get('symbol', 'XAUTUSDT')
            timeframe = request.query.get('timeframe', '15m')
            if not _validate_symbol(symbol) or not _validate_timeframe(timeframe):
                return web.json_response({'error': 'Invalid symbol or timeframe'}, status=400)
            file_path = _safe_path(data_dir, f"{symbol}_{timeframe}.json")
            if file_path is None:
                return web.json_response({'error': 'Invalid path'}, status=400)
            
            if not file_path.exists():
                return web.json_response({'error': 'No data available'}, status=404)
            
            with open(file_path, 'r') as f:
                candles = json_module.load(f)
            
            candles = candles[-500:]
            result = xau_ai_integration.detect_regime(candles)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': 'Internal error'}, status=500)
    
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
                equity_curve = [float(x) for x in equity.split(',') if x.strip()]
                if len(equity_curve) > 10000:
                    return web.json_response({'error': 'Equity curve too large'}, status=400)
            else:
                import json as json_module
                data_dir = Path(__file__).parent.parent / "data" / "shared"
                file_path = _safe_path(data_dir, "XAUTUSDT_15m.json")
                if file_path is None or not file_path.exists():
                    return web.json_response({'error': 'No data available'}, status=404)
                with open(file_path, 'r') as f:
                    candles = json_module.load(f)
                equity_curve = [float(c.get('close', 0)) for c in candles[-200:]]
            
            result = xau_ai_integration.risk_analytics(equity_curve)
            return web.json_response({k: _sanitize(v) for k, v in result.items()})
        except Exception as e:
            return web.json_response({'error': 'Internal error'}, status=500)

    async def run_analysis(self, request: web.Request) -> web.Response:
        """Run performance analysis on backtest results."""
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        try:
            import sys
            import json as json_module
            from pathlib import Path
            agent_system_path = Path(__file__).parent.parent / "agent_system"
            if str(agent_system_path) not in sys.path:
                sys.path.insert(0, str(agent_system_path))
            
            from backtest.analyze import explain_performance, generate_comparison_report
            
            body = await request.json()
            symbol = body.get('symbol', 'SOLUSDT')
            timeframe = body.get('timeframe', '15m')
            if not _validate_symbol(symbol) or not _validate_timeframe(timeframe):
                return web.json_response({'error': 'Invalid symbol or timeframe'}, status=400)
            
            results_dir = Path(__file__).parent.parent / "agent_system" / "backtest" / "results"
            results_path = _safe_path(results_dir, f"{symbol}_{timeframe}_results.json")
            if results_path is None:
                return web.json_response({'error': 'Invalid path'}, status=400)
            
            if not results_path.exists():
                return web.json_response({'error': 'Results not found'}, status=404)
            
            with open(results_path, 'r') as f:
                data = json_module.load(f)
            
            # data should be a list of results
            if isinstance(data, dict) and 'results' in data:
                results = data['results']
            else:
                results = data
            
            analysis = explain_performance(symbol, timeframe, results, top_n=body.get('top_n', 5))
            
            return web.json_response({
                'symbol': symbol,
                'timeframe': timeframe,
                'analysis': analysis,
                'results_count': len(results)
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_analysis_results(self, request: web.Request) -> web.Response:
        """Get available analysis results."""
        try:
            import json as json_module
            results_dir = Path(__file__).parent.parent / "agent_system" / "backtest" / "results"
            if not results_dir.exists():
                return web.json_response({'results': []})
            
            files = list(results_dir.glob("*_results.json"))
            results = []
            for f in files:
                try:
                    with open(f, 'r') as fp:
                        data = json_module.load(fp)
                        count = len(data.get('results', [])) if isinstance(data, dict) else (len(data) if isinstance(data, list) else 0)
                        results.append({
                            'file': f.name,
                            'symbol_timeframe': f.name.replace('_results.json', ''),
                            'results_count': count
                        })
                except Exception:
                    pass
            
            return web.json_response({'results': results})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def backtrader_status(self, request: web.Request) -> web.Response:
        """Get backtrader strategy integration status + cached results."""
        try:
            return web.json_response(get_status())
        except Exception as e:
            return web.json_response({'error': str(e), 'available': False}, status=500)

    async def backtrader_results(self, request: web.Request) -> web.Response:
        """Get cached backtrader backtest results."""
        try:
            from backtest.backtrader_xauusd import load_cached_results
            results = load_cached_results()
            if results is None:
                return web.json_response({'has_results': False, 'results': None})
            return web.json_response({'has_results': True, 'results': results})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def backtrader_run(self, request: web.Request) -> web.Response:
        """Run the backtrader XAUUSD pullback strategy backtest.

        Body:
            {
              "params": {...strategy overrides...},
              "starting_cash": 100000.0,
              "limit_bars": 0,
              "sync": false   // if true, run in foreground and return results
            }
        """
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        try:
            body = await request.json()
        except Exception:
            body = {}

        params = body.get('params') or {}
        starting_cash = float(body.get('starting_cash', 100000.0))
        limit_bars = int(body.get('limit_bars', 0))
        sync = bool(body.get('sync', False))

        if not sync:
            asyncio.create_task(self._run_backtest_task(
                params, starting_cash, limit_bars
            ))
            return web.json_response({
                'status': 'started',
                'message': 'Backtest running in background. Poll /backtrader/results.'
            })

        # Foreground run (blocking) - used for one-shot testing
        try:
            result = await asyncio.to_thread(
                run_backtest, params, starting_cash, limit_bars, True
            )
            save_results(result)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)

    async def _run_backtest_task(
        self, params: dict, starting_cash: float, limit_bars: int
    ) -> None:
        """Run backtest in a background thread and persist results."""
        try:
            result = await asyncio.to_thread(
                run_backtest, params, starting_cash, limit_bars, True
            )
            save_results(result)
            await self.event_bus.publish(Event(
                type=EventType.TRADE_LOG,
                payload={
                    'type': 'backtest',
                    'strategy': result.get('strategy_name'),
                    'metrics': result.get('metrics'),
                    'updated': result.get('updated'),
                },
                source_agent="BacktraderBridge",
            ))
        except Exception as e:
            print(f"Backtrader backtest error: {e}")
            await self.event_bus.publish(Event(
                type=EventType.RISK_ALERT,
                payload={'type': 'backtest_error', 'error': str(e)},
                source_agent="BacktraderBridge",
            ))

    async def agentm_status(self, request: web.Request) -> web.Response:
        """Get Agent M candle-signal integration status + cached results."""
        try:
            return web.json_response(get_agentm_status())
        except Exception as e:
            return web.json_response({'error': str(e), 'available': False}, status=500)

    async def agentm_results(self, request: web.Request) -> web.Response:
        """Get cached Agent M backtest results."""
        try:
            from backtest.agentm_candle import load_cached_results
            results = load_cached_results()
            if results is None:
                return web.json_response({'has_results': False, 'results': None})
            return web.json_response({'has_results': True, 'results': results})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def agentm_run(self, request: web.Request) -> web.Response:
        """Run the Agent M candle-signal strategy backtest.

        Body:
            {
              "ticker": "AAPL",
              "start": "2024-01-01",
              "end": "2025-01-01",
              "account_bp": 10000.0,
              "profiles": ["conservative", "aggressive"],
              "limit_days": 0,
              "sync": false   // if true, run in foreground and return results
            }
        """
        if not _check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        try:
            body = await request.json()
        except Exception:
            body = {}

        ticker = body.get('ticker', 'AAPL')
        start = body.get('start', '2024-01-01')
        end = body.get('end', '2025-01-01')
        account_bp = float(body.get('account_bp', 10000.0))
        profiles = body.get('profiles') or None
        limit_days = int(body.get('limit_days', 0))
        sync = bool(body.get('sync', False))

        if not sync:
            asyncio.create_task(self._run_agentm_task(
                ticker, start, end, account_bp, profiles, limit_days
            ))
            return web.json_response({
                'status': 'started',
                'message': 'Agent M backtest running in background. Poll /agentm/results.'
            })

        try:
            result = await asyncio.to_thread(
                run_agentm_backtest, ticker, start, end, account_bp, profiles, limit_days
            )
            save_agentm_results(result)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)

    async def _run_agentm_task(
        self, ticker: str, start: str, end: str,
        account_bp: float, profiles: Optional[List[str]], limit_days: int,
    ) -> None:
        """Run Agent M backtest in a background thread and persist results."""
        try:
            result = await asyncio.to_thread(
                run_agentm_backtest, ticker, start, end, account_bp, profiles, limit_days
            )
            save_agentm_results(result)
            await self.event_bus.publish(Event(
                type=EventType.TRADE_LOG,
                payload={
                    'type': 'backtest',
                    'strategy': result.get('strategy_name'),
                    'metrics': result.get('metrics'),
                    'updated': result.get('updated'),
                },
                source_agent="AgentMBridge",
            ))
        except Exception as e:
            print(f"Agent M backtest error: {e}")
            await self.event_bus.publish(Event(
                type=EventType.RISK_ALERT,
                payload={'type': 'backtest_error', 'error': str(e)},
                source_agent="AgentMBridge",
            ))

    # ── Analytics / feature engineering endpoints ──────────────────────────

    def _candles_to_df(self, candles: List[Dict]) -> "pd.DataFrame":
        """Convert normalized OHLCV candle dicts to a pandas DataFrame with a datetime index."""
        import pandas as _pd
        if not candles:
            return _pd.DataFrame()
        df = _pd.DataFrame(candles)
        idx = _pd.date_range(end=_pd.Timestamp.utcnow(), periods=len(df), freq="h")
        df.index = idx
        return df

    async def analytics_features(self, request: web.Request) -> web.Response:
        """Compute the full FeatureFactory feature set on live OHLCV data.

        Query params: asset (BTC/ETH/XAU/...), timeframe, limit, categories (comma sep).
        """
        asset = (request.query.get('asset') or 'BTC').upper()
        timeframe = request.query.get('timeframe') or '1h'
        limit = int(request.query.get('limit', 300))
        cats = request.query.get('categories')
        if not _validate_symbol(f"{asset}USD") or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        try:
            candles = await self._fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles: ' + str(e)}, status=502)
        if len(candles) < 30:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        try:
            import pandas as _pd
            from analytics.features import get_feature_factory, FeatureCategory
            df = self._candles_to_df(candles)
            ff = get_feature_factory()
            categories = [c for c in (cats or '').split(',') if c]
            result = ff.compute_all(df, categories or None)
            latest = result.iloc[-1].copy()
            features = []
            for name in result.columns:
                if name in ('open', 'high', 'low', 'close', 'volume'):
                    continue
                meta = ff.registry.get(name)
                features.append({
                    'name': name,
                    'category': meta.category.value if meta else 'unknown',
                    'value': _sanitize(float(latest[name])) if _pd.notna(latest[name]) else None,
                    'lookback': meta.lookback if meta else 1,
                    'normalization': meta.normalization.value if meta else 'none',
                    'formula': meta.formula if meta else '',
                })
            return web.json_response({
                'asset': asset, 'timeframe': timeframe, 'bars': len(df),
                'count': len(features),
                'features': features,
                'categories': sorted({f['category'] for f in features}),
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def analytics_registry(self, request: web.Request) -> web.Response:
        """List every registered feature with its metadata."""
        try:
            from analytics.features import get_feature_registry
            reg = get_feature_registry()
            feats = []
            for m in reg.list():
                feats.append({
                    'name': m.name, 'category': m.category.value, 'formula': m.formula,
                    'source_data': m.source_data, 'lookback': m.lookback,
                    'normalization': m.normalization.value, 'version': m.version,
                    'fingerprint': m.fingerprint,
                })
            return web.json_response({'count': len(feats), 'features': feats})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def bot_start(self, request: web.Request) -> web.Response:
        """Start a trading bot by ID with given params."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON body'}, status=400)
        bot_id = body.get('bot_id')
        category = body.get('category', 'btc')
        params = body.get('params', {})
        if not bot_id:
            return web.json_response({'error': 'bot_id required'}, status=400)
        # In a full implementation, this would spawn a background task
        # For now, return success with a mock PID
        import os, time
        mock_pid = os.getpid() + hash(bot_id) % 10000
        return web.json_response({
            'status': 'ok',
            'bot_id': bot_id,
            'category': category,
            'pid': mock_pid,
            'params': params,
            'started_at': time.time(),
            'message': f'Bot {bot_id} started (simulated)'
        })

    async def bot_stop(self, request: web.Request) -> web.Response:
        """Stop a running bot by ID."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON body'}, status=400)
        bot_id = body.get('bot_id')
        if not bot_id:
            return web.json_response({'error': 'bot_id required'}, status=400)
        return web.json_response({
            'status': 'ok',
            'bot_id': bot_id,
            'message': f'Bot {bot_id} stopped (simulated)'
        })

    async def bot_status(self, request: web.Request) -> web.Response:
        """Get status of all bots or a specific bot."""
        bot_id = request.query.get('bot_id')
        # Mock status for demonstration
        return web.json_response({
            'bots': {
                'btc_ma_trend': {'running': False, 'category': 'btc'},
                'xau_spot_fut_arb': {'running': False, 'category': 'xau_arb'},
                'sol_ma_scalp': {'running': False, 'category': 'sol_scalp'},
            }
        })

    async def _get_options_chain(self, underlying: str) -> List[Dict]:
        """Fetch and normalize an options chain for a given underlying."""
        _map = {'XAU': 'XAUT', 'BTC': 'BTC', 'ETH': 'ETH'}
        u = _map.get(underlying, underlying)
        tickers = await delta_client.get_tickers()
        opts = []
        for t in tickers:
            if not isinstance(t, dict):
                continue
            if t.get('underlying_asset_symbol') != u:
                continue
            if t.get('contract_type') not in ('call_options', 'put_options'):
                continue
            sym = t.get('symbol', '')
            expiry = None
            parts = sym.split('-')
            if len(parts) >= 4:
                date_part = parts[-1]
                if len(date_part) == 6 and date_part.isdigit():
                    dd, mm, yy = date_part[:2], date_part[2:4], date_part[4:]
                    expiry = f"20{yy}-{mm}-{dd}"
            opts.append({
                'symbol': sym, 'underlying': u,
                'type': 'call' if t.get('contract_type') == 'call_options' else 'put',
                'strike': float(t.get('strike_price', 0) or 0),
                'expiry': expiry,
                'mark_price': float(t.get('mark_price', 0) or 0),
                'mark_iv': float((t.get('quotes', {}) or {}).get('mark_iv', 0) or 0),
                'spot': float(t.get('spot_price', 0) or 0),
                'open_interest': float(t.get('oi_value_usd', 0) or 0),
                'greeks': {k: float((t.get('greeks', {}) or {}).get(k, 0) or 0)
                           for k in ('delta', 'gamma', 'theta', 'vega')},
            })
        return opts

    async def analytics_microfeatures(self, request: web.Request) -> web.Response:
        """Compute cross-sectional micro-features (derivatives, options IV,
        cross-asset, journal behavior, event context) from live data.

        Query params: symbol (single perp for derivative detail), underlying (options).
        """
        symbol = (request.query.get('symbol') or '').upper()
        underlying = (request.query.get('underlying') or 'BTC').upper()
        try:
            tickers = await delta_client.get_tickers()
        except Exception as e:
            tickers = []
        import asyncio as _aio
        opts = await self._get_options_chain(underlying) if underlying in ('BTC', 'ETH', 'XAU') else []
        # journal + calendar + account (non-blocking, tolerate failures)
        journal = {}
        calendar = {}
        account = {}
        try:
            journal = _journal.stats()
        except Exception:
            journal = {}
        try:
            calendar = await economic_calendar.get_events(include_medium=False)
        except Exception:
            calendar = {}
        try:
            account = await delta_client.get_balance()
            if isinstance(account, dict) and 'error' in account:
                account = {}
        except Exception:
            account = {}
        try:
            from analytics.microfeatures import compute_all
            result = await _aio.to_thread(
                compute_all, tickers, symbol, opts, journal, calendar, account
            )
            result = {k: _sanitize(v) for k, v in result.items()}
            return web.json_response({'asset': underlying, 'symbol': symbol, **result})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def analytics_regime(self, request: web.Request) -> web.Response:
        """Detect the live market regime using the RegimeDetector on OHLCV."""
        asset = (request.query.get('asset') or 'BTC').upper()
        timeframe = request.query.get('timeframe') or '1h'
        limit = int(request.query.get('limit', 300))
        if not _validate_symbol(f"{asset}USD") or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        try:
            candles = await self._fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles: ' + str(e)}, status=502)
        if len(candles) < 30:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        try:
            from analytics.regime import get_regime_detector
            detector = get_regime_detector()
            df = self._candles_to_df(candles)
            state = await asyncio.to_thread(detector.detect, df)
            return web.json_response({
                'asset': asset, 'timeframe': timeframe, 'bars': len(df),
                'trend': state.trend_direction.value,
                'trend_strength': _sanitize(state.trend_strength),
                'volatility': state.volatility_regime.value,
                'vol_percentile': _sanitize(state.vol_percentile),
                'liquidity': state.liquidity_regime.value,
                'momentum': _sanitize(state.momentum_score),
                'session': state.session,
                'stress': state.stress_level.value,
                'dominant': state.dominant_regime.value,
                'confidence': _sanitize(state.confidence),
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def analytics_alpha_zoo(self, request: web.Request) -> web.Response:
        """Run a set of factors through the AlphaZoo ranking engine on live OHLCV."""
        asset = (request.query.get('asset') or 'BTC').upper()
        timeframe = request.query.get('timeframe') or '1h'
        limit = int(request.query.get('limit', 300))
        if not _validate_symbol(f"{asset}USD") or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        try:
            candles = await self._fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles: ' + str(e)}, status=502)
        if len(candles) < 40:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        try:
            from analytics.alpha.alpha_zoo import AlphaZoo, assign_market_regime
            from analytics.features import get_feature_factory
            import pandas as _pd
            df = self._candles_to_df(candles)
            ff = get_feature_factory()
            future_ret = df['close'].pct_change().shift(-1).to_numpy()
            returns = df['close'].pct_change().to_numpy()
            regimes = assign_market_regime(returns)
            zoo = AlphaZoo(ic_threshold=0.01)
            factor_names = ['rsi_14', 'macd', 'adx_14', 'mfi_14', 'obv_slope', 'atr_14', 'bb_width', 'price_dist_sma50', 'willr_14', 'close_position', 'momentum_10', 'zscore20']
            results = []
            for name in factor_names:
                try:
                    series = ff.compute(df, [name])[name]
                    vals = series.to_numpy()
                    mask = ~_pd.isna(vals) & ~_pd.isna(future_ret)
                    if mask.sum() < 30:
                        continue
                    decision = zoo.add_factor(name, vals[mask], future_ret[mask], regimes[mask])
                    results.append({
                        'name': name,
                        'accepted': decision.get('accepted', False),
                        'ic_mean': _sanitize(decision.get('metrics', {}).get('ic_mean', 0)),
                        'ic_sharpe': _sanitize(decision.get('metrics', {}).get('ic_sharpe', 0)),
                        'stability': _sanitize(decision.get('metrics', {}).get('stability', {}).get('stability_score', 0)),
                        'turnover': _sanitize(decision.get('metrics', {}).get('ic_turnover', 0)),
                        'reasons': decision.get('reasons', []) if not decision.get('accepted') else [],
                    })
                except Exception:
                    continue
            return web.json_response({
                'asset': asset, 'timeframe': timeframe, 'bars': len(df),
                'count': len(results), 'results': results,
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def analytics_leakage(self, request: web.Request) -> web.Response:
        """Run leakage checks on a features DataFrame built from live OHLCV."""
        asset = (request.query.get('asset') or 'BTC').upper()
        timeframe = request.query.get('timeframe') or '1h'
        limit = int(request.query.get('limit', 300))
        if not _validate_symbol(f"{asset}USD") or not _validate_timeframe(timeframe):
            return web.json_response({'error': 'Invalid asset or timeframe'}, status=400)
        try:
            candles = await self._fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            return web.json_response({'error': 'Failed to fetch candles: ' + str(e)}, status=502)
        if len(candles) < 40:
            return web.json_response({'error': 'Insufficient data'}, status=400)
        try:
            from analytics.leakage import get_leakage_sentinel
            from analytics.features import get_feature_factory
            import pandas as _pd
            df = self._candles_to_df(candles)
            ff = get_feature_factory()
            feats = ff.compute_all(df, ['momentum', 'volatility', 'volume'])
            labels = _pd.DataFrame({'fwd_ret': df['close'].pct_change().shift(-1)})
            sentinel = get_leakage_sentinel()
            checks = sentinel.check_all(feats, labels)
            return web.json_response({
                'asset': asset, 'timeframe': timeframe,
                'total_checks': len(checks),
                'passed': sum(1 for c in checks if c.passed),
                'failed': sum(1 for c in checks if not c.passed),
                'details': [
                    {'check': c.check_name, 'type': c.leakage_type.value, 'severity': c.severity.value,
                     'passed': c.passed, 'message': c.message}
                    for c in checks
                ],
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def market_banner(self, request: web.Request) -> web.Response:
        """Get realtime asset class price banner. Query: ?slim=true for 4-asset marquee."""
        try:
            slim = request.query.get('slim', 'false').lower() == 'true'
            data = await asyncio.to_thread(fetch_market_banner, slim=slim)
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'error': str(e), 'assets': [], 'count': 0}, status=500)
