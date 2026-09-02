"""
Execution API — REST API layer for the trading system.

Provides HTTP endpoints for:
- Order management (submit/cancel/get status)
- Portfolio state queries
- Position and fill retrieval
- Risk status
- System health checks
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from execution.contracts import (
    PortfolioState,
    RiskLimits,
    RiskCheckResult,
    adapter_registry,
    Venue,
)
from execution.engine import get_execution_engine, ExecutionConfig, DefaultRiskOverlay
from shared.domain import Instrument, OrderSide, OrderType, SignalType
from data.ingestion import get_event_backbone, get_normalizer

# Create FastAPI app
app = FastAPI(
    title="Trading Agent System API",
    description="REST API for the MT5_FLOW trading system",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global references
_execution_engine: Optional[ExecutionEngine] = None
_portfolio_state: Optional[PortfolioState] = None


def set_execution_engine(engine: ExecutionEngine, portfolio: PortfolioState) -> None:
    """Set the global execution engine and portfolio state."""
    global _execution_engine, _portfolio_state
    _execution_engine = engine
    _portfolio_state = portfolio


@app.get("/health", tags=["system"])
async def health_check() -> Dict[str, str]:
    """System health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/status", tags=["system"])
async def system_status() -> Dict[str, Any]:
    """Get comprehensive system status."""
    if not _execution_engine or not _portfolio_state:
        return {"error": "System not initialized", "status": "stopped"}
    
    engine = _execution_engine
    portfolio = _portfolio_state
    
    # Get positions from all adapters
    all_positions: List[Dict] = []
    for adapter in engine.adapter_registry.all():
        try:
            positions = await adapter.get_positions()
            for pos in positions:
                all_positions.append({
                    "symbol": pos.instrument.symbol if pos.instrument else "unknown",
                    "side": pos.side.value if pos.side else "unknown",
                    "quantity": float(pos.quantity) if pos.quantity else 0,
                    "entry_price": float(pos.entry_price) if pos.entry_price else 0,
                    "current_price": float(pos.current_price) if pos.current_price else 0,
                    "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl else 0,
                    "venue": adapter.venue.value,
                })
        except Exception as e:
            print(f"Error getting positions from {adapter.venue}: {e}")
    
    # Get fills
    all_fills: List[Dict] = []
    try:
        fills = await engine.get_fills(since=datetime.utcnow() - timedelta(hours=24))
        for fill in all_fills:
            all_fills.append({
                "id": fill.id[:20] if len(fill.id) > 20 else fill.id,
                "symbol": fill.instrument.symbol if fill.instrument else "unknown",
                "side": fill.side.value if fill.side else "unknown",
                "quantity": float(fill.quantity) if fill.quantity else 0,
                "price": float(fill.price) if fill.price else 0,
                "commission": float(fill.commission) if fill.commission else 0,
                "timestamp": fill.timestamp.isoformat() if fill.timestamp else "",
                "venue": fill.venue.value,
            })
    except Exception as e:
        print(f"Error getting fills: {e}")
    
    # Risk status
    risk_checks: Dict[str, Any] = {}
    if portfolio and portfolio.risk_limits:
        # Calculate current risk metrics
        total_pos_value = sum(
            (float(p.current_price) * float(p.quantity) 
             for p in [Instrument(symbol="BTC/USDT")] if p.quantity) or 0
        )
        
        used_margin = portfolio.used_margin or Decimal("0")
        available_margin = portfolio.available_margin or Decimal("0")
        total_equity = portfolio.total_equity or Decimal("1")
        
        margin_ratio = (used_margin / available_margin * 100) if available_margin > 0 else 0
        
        risk_checks = {
            "margin_ratio_pct": float(margin_ratio),
            "max_drawdown_pct": float(portfolio.risk_limits.max_portfolio_drawdown * 100),
            "max_daily_loss_pct": float(portfolio.risk_limits.max_daily_loss * 100),
            "max_position_size_pct": float(portfolio.risk_limits.max_position_size_pct * 100),
            "leverage": float(portfolio.risk_limits.max_leverage),
            "daily_pnl": float(portfolio.daily_pnl or 0),
            "total_equity": float(total_equity),
        }
    
    return {
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "venues": [adapter.venue.value for adapter in engine.adapter_registry.all()],
        "positions": all_positions,
        "open_orders": len(all_fills),  # Simplified
        "risk": risk_checks,
        "data_feed": "delta_exchange" if engine else "unknown",
    }


@app.get("/positions", tags=["execution"])
async def get_all_positions() -> List[Dict[str, Any]]:
    """Get all current positions across all venues."""
    if not _execution_engine or not _portfolio_state:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    engine = _execution_engine
    positions: List[Dict[str, Any]] = []
    
    # From portfolio state
    for symbol, pos in _portfolio_state.positions.items():
        positions.append({
            "symbol": symbol,
            "side": pos.side.value if pos.side else "unknown",
            "quantity": float(pos.quantity) if pos.quantity else 0,
            "entry_price": float(pos.entry_price) if pos.entry_price else 0,
            "current_price": float(pos.current_price) if pos.current_price else 0,
            "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl else 0,
            "margin_used": float(pos.margin_used) if pos.margin_used else 0,
            "leverage": float(pos.leverage) if pos.leverage else 1,
        })
    
    # From adapters
    for adapter in engine.adapter_registry.all():
        try:
            adapter_positions = await adapter.get_positions()
            for pos in adapter_positions:
                positions.append({
                    "symbol": pos.instrument.symbol if pos.instrument else "unknown",
                    "side": pos.side.value if pos.side else "unknown",
                    "quantity": float(pos.quantity) if pos.quantity else 0,
                    "venue": adapter.venue.value,
                })
        except Exception as e:
            print(f"Error getting positions from {adapter.venue}: {e}")
    
    return positions


@app.get("/fills", tags=["execution"])
async def get_recent_fills(
    hours: int = Query(default=24, ge=1, le=168),
    venue: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    """Get recent fills from the last N hours."""
    if not _execution_engine:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    since = datetime.utcnow() - timedelta(hours=hours)
    all_fills = await _execution_engine.get_fills(since=since)
    
    fills: List[Dict[str, Any]] = []
    for fill in all_fills:
        fills.append({
            "id": fill.id[:20] if len(fill.id) > 20 else fill.id,
            "symbol": fill.instrument.symbol if fill.instrument else "unknown",
            "side": fill.side.value if fill.side else "unknown",
            "quantity": float(fill.quantity) if fill.quantity else 0,
            "price": float(fill.price) if fill.price else 0,
            "commission": float(fill.commission) if fill.commission else 0,
            "timestamp": fill.timestamp.isoformat() if fill.timestamp else "",
            "venue": fill.venue.value,
            "strategy_id": fill.strategy_id,
        })
    
    # Filter by venue if specified
    if venue:
        fills = [f for f in fills if f["venue"] == venue]
    
    return fills


@app.post("/orders", tags=["execution"])
async def submit_order(
    symbol: str = Query(...),
    side: str = Query(...),
    quantity: float = Query(...),
    order_type: str = Query(default="market"),
    price: Optional[float] = Query(default=None),
) -> Dict[str, Any]:
    """Submit a new order."""
    if not _execution_engine:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    from execution.contracts import Venue, Order, OrderStatus, OrderSide as OS, OrderType as OT
    from decimal import Decimal
    
    # Determine venue from symbol or default
    venue = Venue.DELTA  # Default
    
    # Create instrument
    instrument = Instrument(symbol=symbol)
    
    # Create signal
    from execution.contracts import Signal, ExecutionIntent
    from shared.domain import OrderSide, OrderType
    
    signal = Signal(
        id=str(abs(hash((symbol, side, quantity)))),
        strategy_id="api-request",
        instrument=instrument,
        signal_type=SignalType.ENTRY,
        side=OS(side.upper()),
        quantity=Decimal(str(quantity)),
        price=Decimal(str(price)) if price else None,
    )
    
    # Process through execution engine
    intent = await _execution_engine.process_signal(signal)
    
    if not intent:
        raise HTTPException(status_code=400, detail="Order rejected by risk overlay")
    
    # Execute intent
    order = await _execution_engine.execute_intent(intent)
    
    return {
        "order_id": order.id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "price": price,
        "status": order.status.value if order.status else "pending",
        "venue": venue.value,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/risk", tags=["risk"])
async def get_risk_status() -> Dict[str, Any]:
    """Get current risk status and checks."""
    if not _execution_engine or not _portfolio_state:
        return {"error": "System not initialized", "status": "stopped"}
    
    portfolio = _portfolio_state
    risk_checks: Dict[str, Any] = {}
    
    if portfolio.risk_limits:
        used_margin = portfolio.used_margin or Decimal("0")
        available_margin = portfolio.available_margin or Decimal("1")
        total_equity = portfolio.total_equity or Decimal("1")
        
        margin_ratio = (used_margin / available_margin * 100) if available_margin > 0 else 0
        
        risk_checks = {
            "margin_ratio_pct": float(margin_ratio),
            "margin_warning": float(margin_ratio) >= float(portfolio.risk_limits.margin_warning * 100),
            "margin_critical": float(margin_ratio) >= float(portfolio.risk_limits.margin_critical * 100),
            "max_drawdown_pct": float(portfolio.risk_limits.max_portfolio_drawdown * 100),
            "max_daily_loss_pct": float(portfolio.risk_limits.max_daily_loss * 100),
            "max_position_size_pct": float(portfolio.risk_limits.max_position_size_pct * 100),
            "leverage": float(portfolio.risk_limits.max_leverage),
            "daily_pnl": float(portfolio.daily_pnl or 0),
            "total_equity": float(total_equity),
            "position_pct_by_symbol": {},  # Would need per-symbol calc
        }
    
    # Run risk overlay evaluation
    if portfolio and portfolio.risk_limits:
        from shared.domain import Signal, SignalType, OrderSide, OrderType
        from decimal import Decimal
        
        test_signal = Signal(
            id="risk-check",
            strategy_id="risk-check",
            instrument=portfolio.positions.keys().__iter__().__next__() if portfolio.positions else Instrument(symbol="BTC/USDT"),
            signal_type=SignalType.ENTRY,
            side=OrderSide.BUY,
            quantity=Decimal("1"),
        )
        
        risk_result = await _execution_engine.risk_overlay.evaluate_signal(
            test_signal, portfolio
        )
        
        risk_checks["signal_checks_passed"] = risk_result.passed
        risk_checks["signal_check_notes"] = risk_result.notes
    
    return {
        "status": "active",
        "timestamp": datetime.utcnow().isoformat(),
        "risk": risk_checks,
    }


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the API with the execution engine."""
    # This would be called from main.py with the actual engine instance
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)