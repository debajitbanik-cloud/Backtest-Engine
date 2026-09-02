"""
Strategy Registry — persistence and API for StrategyIdentity.

Provides CRUD operations, versioning, and seeding from existing
backtest results (best_parameters.json, backtrader, agentm adapters).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.domain import StrategyIdentity


class StrategyRegistry:
    """
    SQLite-backed strategy registry with versioning.
    Can be swapped for PostgreSQL in production.
    """

    def __init__(self, db_path: str = "data/strategies.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    parameters TEXT NOT NULL,  -- JSON
                    tags TEXT DEFAULT '[]',    -- JSON
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'  -- JSON
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_name_version
                ON strategies (name, version)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_performance (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    metrics TEXT NOT NULL,  -- JSON
                    trades_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (strategy_id) REFERENCES strategies (id)
                )
            """)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create(self, strategy: StrategyIdentity) -> StrategyIdentity:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO strategies (id, name, version, description, parameters, tags, is_active, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy.id,
                    strategy.name,
                    strategy.version,
                    strategy.description,
                    json.dumps(strategy.parameters),
                    json.dumps(strategy.tags),
                    strategy.is_active,
                    strategy.created_at.isoformat(),
                    strategy.updated_at.isoformat(),
                    json.dumps(strategy.metadata),
                ),
            )
        return strategy

    def get(self, strategy_id: str) -> Optional[StrategyIdentity]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
            ).fetchone()
        return self._row_to_strategy(row) if row else None

    def get_by_name_version(self, name: str, version: str) -> Optional[StrategyIdentity]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM strategies WHERE name = ? AND version = ?", (name, version)
            ).fetchone()
        return self._row_to_strategy(row) if row else None

    def list(self, active_only: bool = True) -> List[StrategyIdentity]:
        with self._conn() as conn:
            query = "SELECT * FROM strategies"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY name, version"
            rows = conn.execute(query).fetchall()
        return [self._row_to_strategy(r) for r in rows]

    def update(self, strategy: StrategyIdentity) -> StrategyIdentity:
        strategy.updated_at = datetime.utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE strategies
                SET name = ?, version = ?, description = ?, parameters = ?, tags = ?,
                    is_active = ?, updated_at = ?, metadata = ?
                WHERE id = ?
                """,
                (
                    strategy.name,
                    strategy.version,
                    strategy.description,
                    json.dumps(strategy.parameters),
                    json.dumps(strategy.tags),
                    strategy.is_active,
                    strategy.updated_at.isoformat(),
                    json.dumps(strategy.metadata),
                    strategy.id,
                ),
            )
        return strategy

    def delete(self, strategy_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
            return cur.rowcount > 0

    # ── Seeding from backtest results ──────────────────────────────────────

    def seed_from_backtest_results(self, results_dir: str = "backtest/results") -> List[StrategyIdentity]:
        """
        Scan backtest results directory and create StrategyIdentity entries
        for each unique strategy/symbol/timeframe combination with good metrics.
        """
        results_path = Path(results_dir)
        if not results_path.exists():
            return []

        created = []
        for result_file in results_path.glob("*_results.json"):
            try:
                with open(result_file) as f:
                    data = json.load(f)

                # Extract strategy name from filename or data
                strategy_name = result_file.stem.replace("_results", "")
                if "strategy_name" in data:
                    strategy_name = data["strategy_name"].lower().replace(" ", "_")

                # Get metrics
                metrics = data.get("metrics", {})
                if isinstance(metrics, dict) and "conservative" in metrics:
                    # agentm format has profile metrics
                    profile_metrics = metrics.get("conservative", {})
                else:
                    profile_metrics = metrics

                # Only seed if meets minimum criteria
                win_rate = profile_metrics.get("win_rate", 0)
                profit_factor = profile_metrics.get("profit_factor", 0) or 0
                trades = profile_metrics.get("trades", profile_metrics.get("executed", 0))

                if trades >= 10 and win_rate >= 40 and profit_factor >= 1.0:
                    # Determine version from parameters
                    params = data.get("params", data.get("config", {}))
                    param_hash = self._hash_params(params)
                    version = f"1.0.{param_hash[:4]}"

                    existing = self.get_by_name_version(strategy_name, version)
                    if not existing:
                        strategy = StrategyIdentity(
                            name=strategy_name,
                            version=version,
                            description=f"Auto-seeded from {result_file.name}",
                            parameters=params,
                            tags=["auto-seeded", result_file.stem],
                        )
                        self.create(strategy)
                        created.append(strategy)

            except Exception as e:
                print(f"Failed to seed from {result_file}: {e}")
                continue

        return created

    def _hash_params(self, params: Dict[str, Any]) -> str:
        import hashlib
        serialized = json.dumps(params, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    # ── Performance tracking ───────────────────────────────────────────────

    def record_performance(
        self,
        strategy_id: str,
        symbol: str,
        timeframe: str,
        period_start: str,
        period_end: str,
        metrics: Dict[str, Any],
        trades_count: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO strategy_performance (id, strategy_id, symbol, timeframe, period_start, period_end, metrics, trades_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    strategy_id,
                    symbol,
                    timeframe,
                    period_start,
                    period_end,
                    json.dumps(metrics),
                    trades_count,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_performance(self, strategy_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM strategy_performance WHERE strategy_id = ? ORDER BY created_at DESC",
                (strategy_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Helpers ────────────────────────────────────────────────────────────

    def _row_to_strategy(self, row: sqlite3.Row) -> StrategyIdentity:
        return StrategyIdentity(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            description=row["description"],
            parameters=json.loads(row["parameters"]),
            tags=json.loads(row["tags"]),
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata"]),
        )


# Global registry instance
_strategy_registry: Optional[StrategyRegistry] = None


def get_strategy_registry(db_path: str = "data/strategies.db") -> StrategyRegistry:
    global _strategy_registry
    if _strategy_registry is None:
        _strategy_registry = StrategyRegistry(db_path)
    return _strategy_registry


import uuid