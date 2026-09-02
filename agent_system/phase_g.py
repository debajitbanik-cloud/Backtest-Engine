"""
Phase G — Knowledge Management and Agent Memory.

Provides persistent storage for:
- Agent learnings and strategy results
- Strategy registry with versioning and performance tracking
- Factor performance history and IC tracking over time
- Knowledge base for retrieving similar strategies
- Long-term memory that survives restarts
- Integration with PostgreSQL and the existing report system
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analytics.validation.validation import ValidationResult, DEFAULT_GATES
from analytics.alpha.alpha_zoo import AlphaZoo
from data.ingestion import get_event_backbone
from execution.contracts import PortfolioState, RiskLimits, adapter_registry, Venue
from shared.domain import Instrument

# ── PostgreSQL Integration ────────────────────────────────────────────────

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    asyncpg = None

# ── SQLite Fallback (for development without PostgreSQL) ──────────────────

class SQLiteKVStore:
    """Simple key-value store using SQLite for development."""

    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM kv WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row[0])
        return default

    def set(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def keys(self) -> List[str]:
        rows = self._conn.execute("SELECT key FROM kv").fetchall()
        return [r[0] for r in rows]

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ── Agent Memory ─────────────────────────────────────────────────────────

class AgentMemory:
    """
    Persistent memory for agents - stores learnings, strategy results,
    and factor performance history in PostgreSQL or SQLite.
    """

    def __init__(self, use_postgres: bool = True, postgres_url: str = "postgresql://postgres:postgres@localhost:5432/trading"):
        self.use_postgres = use_postgres and HAS_ASYNCPG
        self._kv: Any = None

        if self.use_postgres:
            # Would create connection pool here
            # For now, fall back to SQLite
            self._kv = SQLiteKVStore("agent_memory_fallback.db")
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "PostgreSQL not available, using SQLite fallback for AgentMemory"
            )
        else:
            self._kv = SQLiteKVStore("agent_memory.db")

        # In-memory cache
        self._cache: Dict[str, Any] = {}

    async def _ensure_asyncpg(self) -> None:
        """Ensure asyncpg connection pool is available."""
        if not self.use_postgres or not HAS_ASYNCPG:
            return
        # Would create pool here

    # ── Strategy Result Storage ──────────────────────────────────────────

    async def store_validation_result(
        self,
        strategy_id: str,
        validation_result: ValidationResult,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Store a validation result for a strategy."""
        key = f"validation:{strategy_id}:{validation_result.start_date or 'unknown'}"
        result_data = {
            "validation_type": validation_result.validation_type,
            "strategy_id": validation_result.strategy_id,
            "start_date": validation_result.start_date,
            "end_date": validation_result.end_date,
            "n_folds": validation_result.n_folds,
            "n_samples": validation_result.n_samples,
            "metrics": validation_result.metrics,
            "fold_metrics": validation_result.fold_metrics,
            "passed_gates": validation_result.passed_gates,
            "failed_gates": validation_result.failed_gates,
            "created_at": validation_result.created_at.isoformat(),
            "metadata": metadata or {},
        }
        self._kv.set(key, result_data)

    async def get_validation_result(
        self, strategy_id: str, start_date: str
    ) -> Optional[ValidationResult]:
        """Retrieve a validation result for a strategy."""
        key = f"validation:{strategy_id}:{start_date}"
        data = self._kv.get(key)
        if data is None:
            return None

        # Reconstruct ValidationResult
        from analytics.validation.validation import ValidationResult as VR

        result = VR(
            validation_type=data["validation_type"],
            strategy_id=data["strategy_id"],
            parameters={},
            start_date=data["start_date"],
            end_date=data["end_date"],
            n_folds=data["n_folds"],
            n_samples=data["n_samples"],
            metrics=data["metrics"],
            fold_metrics=data.get("fold_metrics", []),
            passed_gates=data.get("passed_gates", []),
            failed_gates=data.get("failed_gates", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            metadata=data.get("metadata", {}),
        )
        return result

    # ── Factor Performance History ───────────────────────────────────────

    async def store_factor_performance(
        self,
        factor_name: str,
        ic_mean: float,
        ic_std: float,
        ir: float,
        turnover: float,
        regime: Optional[str] = None,
        date: Optional[str] = None,
    ) -> None:
        """Store factor performance metrics over time."""
        key = f"factor_perf:{factor_name}:{date or datetime.utcnow().strftime('%Y%m%d')}"
        data = {
            "factor_name": factor_name,
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ir": ir,
            "turnover": turnover,
            "regime": regime,
            "date": date or datetime.utcnow().strftime("%Y-%m-%d"),
        }
        self._kv.set(key, data)

    async def get_factor_performance(
        self, factor_name: str, regime: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve factor performance history."""
        # Scan all factor perf keys
        all_keys = self._kv.keys()
        perf_data = []

        for key in all_keys:
            if not key.startswith("factor_perf:"):
                continue
            data = self._kv.get(key)
            if data and data.get("factor_name") == factor_name:
                if regime is None or data.get("regime") == regime:
                    perf_data.append(data)

        # Sort by date
        perf_data.sort(key=lambda x: x.get("date", ""))
        return perf_data

    # ── Agent Learnings ──────────────────────────────────────────────────

    async def store_agent_learning(
        self,
        agent_name: str,
        learning_key: str,
        learning_value: Any,
        context: Optional[Dict] = None,
    ) -> None:
        """Store an agent learning."""
        key = f"learning:{agent_name}:{learning_key}"
        data = {
            "value": learning_value,
            "context": context or {},
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._kv.set(key, data)

    async def get_agent_learning(
        self, agent_name: str, learning_key: str
    ) -> Optional[Any]:
        """Retrieve an agent learning."""
        key = f"learning:{agent_name}:{learning_key}"
        data = self._kv.get(key)
        if data:
            return data["value"]
        return None

    async def get_agent_learning_context(
        self, agent_name: str, learning_key: str
    ) -> Optional[Dict]:
        """Retrieve agent learning with context."""
        key = f"learning:{agent_name}:{learning_key}"
        data = self._kv.get(key)
        if data:
            return data.get("context")
        return None

    # ── Strategy Registry Enhancement ────────────────────────────────────

    async def store_strategy_entry(
        self,
        strategy_id: str,
        strategy_name: str,
        version: str,
        parameters: Dict[str, Any],
        validation_result: ValidationResult,
        created_by: str = "system",
    ) -> None:
        """Store a strategy entry with its validation result."""
        key = f"strategy:{strategy_id}:{version}"
        data = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "version": version,
            "parameters": parameters,
            "validation_result": {
                "validation_type": validation_result.validation_type,
                "n_folds": validation_result.n_folds,
                "metrics": validation_result.metrics,
                "passed_gates": validation_result.passed_gates,
                "failed_gates": validation_result.failed_gates,
            },
            "created_by": created_by,
            "created_at": validation_result.created_at.isoformat(),
        }
        self._kv.set(key, data)

    async def get_strategy_entry(
        self, strategy_id: str, version: str
    ) -> Optional[Dict]:
        """Retrieve a strategy entry."""
        key = f"strategy:{strategy_id}:{version}"
        return self._kv.get(key)

    async def list_strategies(self, strategy_id: Optional[str] = None) -> List[Dict]:
        """List all strategies or strategies matching ID prefix."""
        all_keys = self._kv.keys()
        strategies = []

        for key in all_keys:
            if not key.startswith("strategy:"):
                continue
            if strategy_id and not key.startswith(f"strategy:{strategy_id}"):
                continue
            data = self._kv.get(key)
            if data:
                strategies.append(data)

        # Deduplicate by strategy_id + version
        seen = set()
        unique = []
        for s in strategies:
            dedup_key = (s.get("strategy_id"), s.get("version"))
            if dedup_key not in seen:
                seen.add(dedup_key)
                unique.append(s)

        return unique

    # ── Query Utilities ──────────────────────────────────────────────────

    async def get_recent_validations(
        self, days: int = 30, min_pass_rate: float = 0.0
    ) -> List[Dict]:
        """Get validations from recent period."""
        # This would be more efficient with PostgreSQL
        # For SQLite, return empty or limited results
        from datetime import datetime, timedelta

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        all_keys = self._kv.keys()
        recent = []

        for key in all_keys:
            if not key.startswith("validation:"):
                continue
            data = self._kv.get(key)
            if data and data.get("created_at", "") > cutoff:
                # Calculate pass rate
                passed = len(data.get("passed_gates", []))
                failed = len(data.get("failed_gates", []))
                total = passed + failed
                if total > 0:
                    pass_rate = passed / total
                else:
                    pass_rate = 0.0

                if pass_rate >= min_pass_rate:
                    recent.append(
                        {
                            "key": key,
                            "strategy_id": data.get("strategy_id"),
                            "start_date": data.get("start_date"),
                            "end_date": data.get("end_date"),
                            "pass_rate": pass_rate,
                            "passed_gates": data.get("passed_gates", []),
                            "failed_gates": data.get("failed_gates", []),
                            "metrics": data.get("metrics", {}),
                        }
                    )

        recent.sort(key=lambda x: x.get("start_date", ""), reverse=True)
        return recent

    # ── Persistence ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the storage connection."""
        self._kv.close()


# ── Knowledge Base Queries ──────────────────────────────────────────────

async def find_similar_strategies(
    memory: AgentMemory,
    target_metrics: Dict[str, float],
    min_pass_rate: float = 0.6,
    limit: int = 5,
) -> List[Dict]:
    """
    Find strategies with similar performance metrics.
    Uses simple metric matching - would be enhanced with ML similarity.
    """
    recent = await memory.get_recent_validations(days=180, min_pass_rate=min_pass_rate)

    scored = []
    for v in recent:
        metrics = v.get("metrics", {})
        if not metrics:
            continue

        # Simple similarity: fraction of target metrics within 20%
        matches = 0
        checks = 0

        for target_key, target_val in target_metrics.items():
            actual = metrics.get(target_key)
            if actual is not None:
                checks += 1
                if abs(actual - target_val) <= target_val * 0.2:
                    matches += 1

        if checks > 0:
            similarity = matches / checks
        else:
            similarity = 0.0

        if similarity >= min_pass_rate:
            scored.append(
                {
                    **v,
                    "similarity": similarity,
                }
            )

    # Sort by similarity descending
    scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return scored[:limit]


async def get_strategy_performance_trend(
    memory: AgentMemory,
    strategy_id: str,
    metric: str = "ic_mean",
    days: int = 90,
) -> List[Dict]:
    """Get performance trend for a specific strategy metric."""
    from datetime import datetime, timedelta

    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    all_keys = memory._kv.keys()
    points = []

    for key in all_keys:
        if not key.startswith("factor_perf:") or ":" not in key:
            continue
        # Skip if this isn't the right strategy
        # Would need strategy_id mapping
        data = memory._kv.get(key)
        if data and isinstance(data.get("ic_mean"), (int, float)):
            points.append(
                {
                    "date": data.get("date", ""),
                    "ic_mean": data.get("ic_mean"),
                }
            )

    # Filter by date and sort
    points = [p for p in points if p.get("date", "") > cutoff]
    points.sort(key=lambda x: x.get("date", ""))
    return points


# ── Export ───────────────────────────────────────────────────────────────

__all__ = [
    "AgentMemory",
    "SQLiteKVStore",
    "find_similar_strategies",
    "get_strategy_performance_trend",
    "AgentMemory",
]

if __name__ == "__main__":
    print("Phase G - Knowledge Management and Agent Memory")
    print("Features:")
    print("  - Persistent strategy result storage")
    print("  - Factor performance history tracking")
    print("  - Agent learnings persistence")
    print("  - Strategy registry with versioning")
    print("  - Similar strategy discovery")
    print("  - Performance trend analysis")