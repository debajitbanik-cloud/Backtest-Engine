"""
Phase E — Enhanced Monitoring and Metrics.

Provides Prometheus-compatible metrics for the trading system:
- Process metrics (CPU, memory)
- System health metrics
- Data flow metrics (ingestion rates, stream lengths)
- Execution metrics (orders, fills, PnL)
- Agent performance metrics
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from prometheus_client import Counter, Histogram, Gauge, Summary, start_http_server

# ── Core System Metrics ──────────────────────────────────────────────────

# Process metrics
process_start_time = time.time()
process_cpu_start = time.process_time()

# System health
system_uptime = Gauge("trading_system_uptime_seconds", "System uptime in seconds")
system_start_time = Gauge(
    "trading_system_start_time_seconds",
    "System start time as Unix timestamp",
    [],
    registry=None,  # Will be set default registry
)

# Data flow metrics
data_ingestion_events_total = Counter(
    "trading_data_ingestion_events_total",
    "Total number of ingestion events by type and venue",
    ["venue", "event_type"],
)
data_ingestion_latency = Histogram(
    "trading_data_ingestion_latency_seconds",
    "Latency of data ingestion from venue to backbone",
    ["venue", "event_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

# Event backbone metrics
redis_stream_length = Gauge(
    "trading_redis_stream_length",
    "Current length of Redis stream",
    ["stream"],
)
redis_consumer_lag = Gauge(
    "trading_redis_consumer_lag",
    "Lag of consumer group in Redis stream",
    ["stream"],
)

# Execution metrics
orders_submitted_total = Counter(
    "trading_orders_submitted_total",
    "Total number of orders submitted by venue and status",
    ["venue", "status"],
)
orders_filled_total = Counter(
    "trading_orders_filled_total",
    "Total number of orders filled by venue",
    ["venue"],
)
orders_cancelled_total = Counter(
    "trading_orders_cancelled_total",
    "Total number of orders cancelled by venue",
    ["venue"],
)

fill_events_total = Counter(
    "trading_fill_events_total",
    "Total number of fill events by venue",
    ["venue"],
)

pnl_gauge = Gauge(
    "trading_portfolio_pnl_total",
    "Current total portfolio PnL",
    ["venue"],
)

margin_gauge = Gauge(
    "trading_portfolio_margin_total",
    "Current portfolio margin usage",
    ["venue"],
)

# Agent metrics
agent_signal_processing_latency = Histogram(
    "trading_agent_signal_processing_latency_seconds",
    "Latency of agent signal processing",
    ["agent"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
)

agent_decisions_total = Counter(
    "trading_agent_decisions_total",
    "Total number of agent decisions by agent and outcome",
    ["agent", "outcome"],
)

# Signal metrics
signal_received_total = Counter(
    "trading_signals_received_total",
    "Total number of signals received by strategy",
    ["strategy"],
)

signal_processed_total = Counter(
    "trading_signals_processed_total",
    "Total number of signals processed successfully",
    ["strategy"],
)

signal_rejected_total = Counter(
    "trading_signals_rejected_total",
    "Total number of signals rejected (risk, gates)",
    ["strategy", "reason"],
)


# ── Metric Update Functions ────────────────────────────────────────────────

def update_ingestion_metrics(venue: str, event_type: str, count: int = 1) -> None:
    """Increment ingestion event counter."""
    data_ingestion_events_labels = {"venue": venue, "event_type": event_type}
    data_ingestion_events_total.labels(**data_ingestion_events_labels).inc(count)


def update_ingestion_latency(venue: str, event_type: str, latency: float) -> None:
    """Record ingestion latency."""
    data_ingestion_latency.labels(venue=venue, event_type=event_type).observe(latency)


def update_redis_stream_length(stream: str, length: int) -> None:
    """Update Redis stream length gauge."""
    redis_stream_length.labels(stream=stream).set(length)


def update_redis_consumer_lag(stream: str, lag: int) -> None:
    """Update Redis consumer group lag gauge."""
    redis_consumer_lag.labels(stream=stream).set(lag)


def record_order_submission(venue: str, status: str) -> None:
    """Record order submission."""
    orders_submitted_total.labels(venue=venue, status=status).inc()


def record_order_fill(venue: str) -> None:
    """Record order fill."""
    orders_filled_total.labels(venue=venue).inc()


def record_order_cancellation(venue: str) -> None:
    """Record order cancellation."""
    orders_cancelled_total.labels(venue=venue).inc()


def record_fill_event(fill: Any, venue: str) -> None:
    """Record fill event."""
    fill_events_total.labels(venue=venue).inc()


def update_portfolio_metrics(portfolio: Any, venue: str = "default") -> None:
    """Update portfolio PnL and margin gauges."""
    if hasattr(portfolio, "daily_pnl") and portfolio.daily_pnl is not None:
        pnl_gauge.labels(venue=venue).set(float(portfolio.daily_pnl))
    
    if hasattr(portfolio, "used_margin") and hasattr(portfolio, "available_margin"):
        used = float(portfolio.used_margin) if portfolio.used_margin else 0
        available = float(portfolio.available_margin) if portfolio.available_margin else 1
        margin_pct = (used / available) * 100 if available > 0 else 0
        margin_gauge.labels(venue=venue).set(margin_pct)


def increment_agent_metrics(agent_name: str, outcome: str = "processed", count: int = 1) -> None:
    """Increment agent decision counter."""
    agent_decisions_total.labels(agent=agent_name, outcome=outcome).inc(count)


def record_signal_received(strategy: str) -> None:
    """Record signal receipt."""
    signal_received_total.labels(strategy=strategy).inc()


def record_signal_processed(strategy: str) -> None:
    """Record signal processed successfully."""
    signal_processed_total.labels(strategy=strategy).inc()


def record_signal_rejected(strategy: str, reason: str) -> None:
    """Record signal rejection."""
    signal_rejected_total.labels(strategy=strategy, reason=reason).inc()


def update_process_metrics() -> None:
    """Update process CPU and memory metrics."""
    current_time = time.time()
    uptime = current_time - process_start_time
    system_uptime.set(uptime)
    
    # Process memory (RSS in bytes) - try psutil first
    try:
        import psutil
        proc = psutil.Process()
        memory_mb = proc.memory_info().rss / (1024 * 1024)
        # Would set a gauge here if we had one
        # For now just log
        # print(f"Process memory: {memory_mb:.1f} MB")
        pass
    except ImportError:
        pass


# ── Metrics Collection Task ────────────────────────────────────────────────

async def metrics_collection_loop(stop_event: asyncio.Event) -> None:
    """
    Background task that periodically collects and updates all metrics.
    Runs every 15 seconds.
    """
    while not stop_event.is_set():
        try:
            # Update process metrics
            update_process_metrics()
            
            # Update Redis stream lengths if backbone exists
            from data.ingestion import get_event_backbone
            try:
                backbone = await get_event_backbone()
                if backbone and backbone._redis:
                    streams = [
                        "market:ticks",
                        "market:candles",
                        "execution:orders",
                        "execution:fills",
                        "execution:positions",
                    ]
                    for stream in streams:
                        try:
                            length = await backbone._redis.xlen(stream)
                            update_redis_stream_length(stream, length)
                            
                            # Calculate consumer lag
                            try:
                                group_info = await backbone._redis.xinfo_groups(stream)
                                our_group = next(
                                    (g for g in group_info if g["name"] == "trading-system"),
                                    None,
                                )
                                if our_group:
                                    lag = our_group.get("messages", 0)
                                    update_redis_consumer_lag(stream, lag)
                            except Exception:
                                pass
                        except Exception:
                            pass
            except Exception:
                pass
            
            # Wait for next collection
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
            
        except asyncio.TimeoutError:
            # Timeout means the wait was interrupted, continue loop
            continue
        except Exception as e:
            print(f"Metrics collection error: {e}")
            await asyncio.sleep(5)


# ── Export ─────────────────────────────────────────────────────────────────

__all__ = [
    "update_ingestion_metrics",
    "update_ingestion_latency",
    "update_redis_stream_length",
    "update_redis_consumer_lag",
    "record_order_submission",
    "record_order_fill",
    "record_order_cancellation",
    "record_fill_event",
    "update_portfolio_metrics",
    "increment_agent_metrics",
    "record_signal_received",
    "record_signal_processed",
    "record_signal_rejected",
    "update_process_metrics",
    "metrics_collection_loop",
    "system_uptime",
]

if __name__ == "__main__":
    # Start Prometheus HTTP server on port 9090
    start_http_server(9090)
    print("Prometheus metrics server started on port 9090")
    
    # Keep running
    import signal as sig_module
    stop_event = asyncio.Event()
    
    loop = asyncio.new_event_loop()
    task = loop.create_task(metrics_collection_loop(stop_event))
    
    def shutdown():
        stop_event.set()
        task.cancel()
        loop.stop()
    
    # Handle SIGINT/SIGTERM
    for sig in (sig_module.SIGINT, sig_module.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
    
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(stop_event.wait())
        loop.close()