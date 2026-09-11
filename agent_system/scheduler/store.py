"""Scheduler Store — SQLite persistence for scheduled jobs and runs.

Tables live in data/scheduler.db (WAL mode). All new tables include user_id
for tenant scoping. bot_backtests lives in trade_journal.db (Task 3), never here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.path.join(os.path.dirname(__file__), "..", "..", "data", "scheduler.db")).resolve()

_VALID_KINDS = {"backtest", "optimize"}
_VALID_METRICS = {"sharpe", "total_return_pct", "profit_factor"}


def _now() -> float:
    return time.time()


class SchedulerStore:
    """SQLite store for scheduler jobs and runs."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                bot_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('backtest','optimize')),
                cadence_cron TEXT NOT NULL DEFAULT '@weekly',
                metric TEXT NOT NULL DEFAULT 'sharpe'
                    CHECK(metric IN ('sharpe','total_return_pct','profit_factor')),
                grid_json TEXT DEFAULT '{}',
                auto_adopt INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, enabled)")
            c.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'default',
                started_at REAL NOT NULL,
                finished_at REAL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','running','ok','partial','failed_fetch','error')),
                result_json TEXT DEFAULT '{}',
                promoted INTEGER DEFAULT 0
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_runs_job ON runs(job_id, started_at)")

    # ── Jobs CRUD ─────────────────────────────────────────────────────────────
    def create_job(self, bot_id: str, kind: str = "backtest",
                   cadence_cron: str = "@weekly", metric: str = "sharpe",
                   grid: Optional[Dict[str, Any]] = None,
                   auto_adopt: bool = False, user_id: str = "default") -> Dict[str, Any]:
        if kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS}")
        if metric not in _VALID_METRICS:
            raise ValueError(f"metric must be one of {_VALID_METRICS}")
        job_id = uuid.uuid4().hex[:12]
        now = _now()
        with self._conn() as c:
            c.execute(
                """INSERT INTO jobs (id, user_id, bot_id, kind, cadence_cron, metric,
                   grid_json, auto_adopt, enabled, created_at)
                   VALUES (?,?,?,?,?,?,?,?,1,?)""",
                (job_id, user_id, bot_id, kind, cadence_cron, metric,
                 json.dumps(grid or {}), int(auto_adopt), now))
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["grid"] = json.loads(d.pop("grid_json", "{}"))
        d["auto_adopt"] = bool(d["auto_adopt"])
        d["enabled"] = bool(d["enabled"])
        return d

    def list_jobs(self, user_id: str = "default", enabled_only: bool = False) -> List[Dict[str, Any]]:
        q = "SELECT * FROM jobs WHERE user_id=?"
        args: list = [user_id]
        if enabled_only:
            q += " AND enabled=1"
        q += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["grid"] = json.loads(d.pop("grid_json", "{}"))
            d["auto_adopt"] = bool(d["auto_adopt"])
            d["enabled"] = bool(d["enabled"])
            out.append(d)
        return out

    def update_job(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {"bot_id", "kind", "cadence_cron", "metric", "grid_json",
                    "auto_adopt", "enabled"}
        sets, args = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                args.append(json.dumps(v) if k == "grid_json" else (int(v) if isinstance(v, bool) else v))
        if not sets:
            return self.get_job(job_id)
        args.append(job_id)
        with self._conn() as c:
            c.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", args)
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        return cur.rowcount > 0

    # ── Runs CRUD ─────────────────────────────────────────────────────────────
    def start_run(self, job_id: str, user_id: str = "default") -> Dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        now = _now()
        with self._conn() as c:
            c.execute(
                """INSERT INTO runs (id, job_id, user_id, started_at, status)
                   VALUES (?,?,?,?,'running')""",
                (run_id, job_id, user_id, now))
        return {"id": run_id, "job_id": job_id, "user_id": user_id,
                "started_at": now, "finished_at": None, "status": "running",
                "result": {}, "promoted": False}

    def finish_run(self, run_id: str, status: str = "ok",
                   result: Optional[Dict[str, Any]] = None,
                   promoted: bool = False) -> Optional[Dict[str, Any]]:
        now = _now()
        with self._conn() as c:
            c.execute(
                """UPDATE runs SET finished_at=?, status=?, result_json=?, promoted=?
                   WHERE id=?""",
                (now, status, json.dumps(result or {}), int(promoted), run_id))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["result"] = json.loads(d.pop("result_json", "{}"))
        d["promoted"] = bool(d["promoted"])
        return d

    def list_runs(self, job_id: Optional[str] = None, user_id: str = "default",
                  limit: int = 50) -> List[Dict[str, Any]]:
        q = "SELECT * FROM runs WHERE user_id=?"
        args: list = [user_id]
        if job_id:
            q += " AND job_id=?"
            args.append(job_id)
        q += " ORDER BY started_at DESC LIMIT ?"
        args.append(int(limit))
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["result"] = json.loads(d.pop("result_json", "{}"))
            d["promoted"] = bool(d["promoted"])
            out.append(d)
        return out
