"""Trade Journal — persistent trades, sessions, session-log and notifications.

SQLite-backed. Used by the bridge to:
  * auto-capture session activity (bridge events + UI-reported events),
  * record trades (manual entries + engine TRADE_LOG events),
  * compute journal stats (win rate, profit factor, streaks, equity curve…),
  * evaluate a user-configurable set of notification rules.

Everything is stored under data/trade_journal.db (gitignored ecosystem data).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.path.join(os.path.dirname(__file__), "..", "..", "data", "trade_journal.db")).resolve()

DEFAULT_RULES: List[Dict[str, Any]] = [
    {"trigger": "trade.closed", "title": "Trade Closed",
     "message": "Trade closed: {symbol} closed for {pnl} ({pnl_pct}).",
     "priority": "normal", "threshold": 0, "threshold_units": "none", "cooldown_sec": 60, "enabled": True},
    {"trigger": "trade.win", "title": "Winning Trade",
     "message": "Winning trade closed: {symbol} +{pnl}.", "priority": "high",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 30, "enabled": True},
    {"trigger": "trade.loss", "title": "Losing Trade",
     "message": "Losing trade closed: {symbol} {pnl}.", "priority": "high",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 30, "enabled": True},
    {"trigger": "position.opened", "title": "Position Opened",
     "message": "New position detected: {symbol} (size {size}).", "priority": "normal",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 120, "enabled": True},
    {"trigger": "pnl.threshold", "title": "Daily PnL Threshold",
     "message": "Daily PnL reached {amount} USD.", "priority": "urgent",
     "threshold": 100, "threshold_units": "usd", "cooldown_sec": 900, "enabled": False},
    {"trigger": "loss.streak", "title": "Loss Streak Alert",
     "message": "{streak} consecutive losses — review the current strategy.", "priority": "urgent",
     "threshold": 3, "threshold_units": "streak", "cooldown_sec": 600, "enabled": True},
    {"trigger": "win.streak", "title": "Win Streak",
     "message": "{streak} consecutive wins — nice run.", "priority": "normal",
     "threshold": 3, "threshold_units": "streak", "cooldown_sec": 600, "enabled": False},
    {"trigger": "drawdown.threshold", "title": "Drawdown Alert",
     "message": "Drawdown from equity peak reached {dd}%.", "priority": "urgent",
     "threshold": 10, "threshold_units": "percent", "cooldown_sec": 1800, "enabled": True},
    {"trigger": "calendar.high", "title": "High-Impact News",
     "message": "High-impact release next: {title} ({currency}) in {minutes} min.", "priority": "high",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 7200, "enabled": True},
    {"trigger": "session.started", "title": "Session Started",
     "message": "Trading session started (source: {source}).", "priority": "normal",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 0, "enabled": True},
    {"trigger": "session.ended", "title": "Session Ended",
     "message": "Session ended — {trades} trades, {pnl} USD net.", "priority": "normal",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 0, "enabled": True},
    {"trigger": "strategy.started", "title": "Strategy Started",
     "message": "Strategy {strategy} started.", "priority": "normal",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 60, "enabled": False},
    {"trigger": "strategy.stopped", "title": "Strategy Stopped",
     "message": "Strategy {strategy} stopped.", "priority": "normal",
     "threshold": 0, "threshold_units": "none", "cooldown_sec": 60, "enabled": False},
]

_CATEGORIES = {"info", "trade", "system", "risk", "ui", "calendar", "error", "strategy"}


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else _now(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(r: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(r) if r is not None else None


def _fmt(msg: str, ctx: Dict[str, Any]) -> str:
    """Format a message template, filling in any {key}s with ctx values."""
    def repl(m):
        return str(ctx.get(m.group(1), "{" + m.group(1) + "}"))
    try:
        return msg.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return re.sub(r"\{(\w+)\}", repl, msg)


class TradeJournal:
    """SQLite trade journal store."""

    def __init__(self, db_path: str | Path = DB_PATH, auto_seed: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_session: Optional[str] = None
        self._init_db()
        if auto_seed:
            self._seed_rules()

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

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY, symbol TEXT NOT NULL, asset TEXT, side TEXT,
                qty REAL DEFAULT 0, size_usd REAL DEFAULT 0,
                entry_price REAL DEFAULT 0, exit_price REAL DEFAULT 0,
                pnl_usd REAL DEFAULT 0, pnl_pct REAL DEFAULT 0, fees REAL DEFAULT 0,
                status TEXT DEFAULT 'open', strategy TEXT DEFAULT '',
                notes TEXT DEFAULT '', tags TEXT DEFAULT '[]',
                opened_at REAL NOT NULL, closed_at REAL,
                session_id TEXT, source TEXT DEFAULT 'manual')""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_at)")
            c.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, started_at REAL NOT NULL, ended_at REAL,
                source TEXT DEFAULT 'system', summary TEXT DEFAULT '',
                events_count INTEGER DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS session_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                ts REAL NOT NULL, category TEXT DEFAULT 'info',
                level TEXT DEFAULT 'INFO', message TEXT NOT NULL, detail TEXT DEFAULT '{}')""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_log_ts ON session_log(ts)")
            c.execute("""CREATE TABLE IF NOT EXISTS notification_rules (
                id TEXT PRIMARY KEY, trigger TEXT NOT NULL, title TEXT NOT NULL,
                message TEXT DEFAULT '', priority TEXT DEFAULT 'normal',
                threshold REAL DEFAULT 0, threshold_units TEXT DEFAULT 'none',
                cooldown_sec INTEGER DEFAULT 60, enabled INTEGER DEFAULT 1,
                last_triggered_at REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
                rule_id TEXT, trigger TEXT, priority TEXT DEFAULT 'normal',
                title TEXT, message TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_notif_ts ON notification_log(ts)")
            c.execute("""CREATE TABLE IF NOT EXISTS bot_backtests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                user_id TEXT DEFAULT 'default',
                ran_at REAL NOT NULL,
                params_json TEXT DEFAULT '{}',
                metrics_json TEXT DEFAULT '{}',
                source TEXT DEFAULT 'manual'
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_bot_backtests_bot ON bot_backtests(bot_id, ran_at DESC)")

    def _seed_rules(self) -> None:
        with self._conn() as c:
            count = c.execute("SELECT COUNT(*) AS n FROM notification_rules").fetchone()["n"]
            if count == 0:
                for r in DEFAULT_RULES:
                    c.execute("""INSERT INTO notification_rules
                        (id, trigger, title, message, priority, threshold, threshold_units, cooldown_sec, enabled)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex[:12], r["trigger"], r["title"], r["message"],
                         r["priority"], r["threshold"], r["threshold_units"],
                         r["cooldown_sec"], 1 if r["enabled"] else 0))

    # ── Session / log capture ────────────────────────────────────────────────
    def start_session(self, source: str = "ui") -> str:
        with self._conn() as c:
            row = c.execute(
                "SELECT id FROM sessions WHERE source=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (source,)).fetchone()
            if row:
                sid = row["id"]
                self._current_session = sid
                return sid
            sid = uuid.uuid4().hex[:12]
            c.execute("INSERT INTO sessions (id, started_at, source) VALUES (?,?,?)", (sid, _now(), source))
        self._current_session = sid
        return sid

    def end_session(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        sid = session_id or self._current_session
        if not sid:
            return None
        now = _now()
        with self._conn() as c:
            c.execute("UPDATE sessions SET ended_at=? WHERE id=?", (now, sid))
        if sid == self._current_session:
            self._current_session = None
        return self.get_session(sid)

    def log(self, message: str, category: str = "info", level: str = "INFO",
            detail: Optional[Dict[str, Any]] = None,
            session_id: Optional[str] = None, ts: Optional[float] = None) -> None:
        category = category if category in _CATEGORIES else "info"
        level = (level or "INFO").upper()[:10]
        sid = session_id or self._current_session
        ts = ts or _now()
        with self._conn() as c:
            c.execute("""INSERT INTO session_log (session_id, ts, category, level, message, detail)
                         VALUES (?,?,?,?,?,?)""",
                      (sid, ts, category, level, message[:500],
                       json.dumps(detail or {})))
            if sid:
                c.execute("UPDATE sessions SET events_count = (SELECT COUNT(*) FROM session_log WHERE session_id=?) WHERE id=?",
                          (sid, sid))

    def capture_event(self, trigger: str, message: str, category: str = "system",
                      level: str = "INFO", detail: Optional[Dict[str, Any]] = None,
                      source_agent: str = "bridge") -> Dict[str, Any]:
        """Log an event and evaluate notification rules for it."""
        self.log(f"[{source_agent}] {message}", category=category, level=level, detail=detail)
        return self.evaluate(trigger, detail or {}, {"source": source_agent})

    def get_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["events_count"] = int(r["events_count"] or 0)
            d["duration_min"] = round((r["ended_at"] - r["started_at"]) / 60, 1) if r["ended_at"] else None
            out.append(d)
        return out

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(r) if r else None

    def get_log(self, category: Optional[str] = None, session_id: Optional[str] = None,
                level: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        q = "SELECT id, session_id, ts, category, level, message, detail FROM session_log WHERE 1=1"
        args: List[Any] = []
        if category and category != "ALL":
            q += " AND category=?"; args.append(category)
        if session_id and session_id != "ALL":
            q += " AND session_id=?"; args.append(session_id)
        if level and level != "ALL":
            q += " AND level=?"; args.append(level)
        q += " ORDER BY ts DESC LIMIT ?"; args.append(int(limit))
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ── Trades ───────────────────────────────────────────────────────────────
    def add_trade(self, symbol: str, side: str = "buy", qty: float = 0.0,
                  size_usd: float = 0.0, entry_price: float = 0.0,
                  exit_price: Optional[float] = None, strategy: str = "",
                  notes: str = "", tags: Optional[List[str]] = None,
                  opened_at: Optional[float] = None, source: str = "manual",
                  session_id: Optional[str] = None) -> Dict[str, Any]:
        tid = uuid.uuid4().hex[:12]
        opened_at = opened_at or _now()
        pnl_usd, pnl_pct, status, closed_at = 0.0, 0.0, "open", None
        if exit_price is not None:
            status = "closed"
            closed_at = _now()
            if entry_price and entry_price > 0 and qty > 0:
                if side == "buy":
                    pnl_usd = (exit_price - entry_price) * qty
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    pnl_usd = (entry_price - exit_price) * qty
                    pnl_pct = (entry_price - exit_price) / entry_price * 100
        with self._conn() as c:
            c.execute("""INSERT INTO trades
                (id, symbol, asset, side, qty, size_usd, entry_price, exit_price,
                 pnl_usd, pnl_pct, fees, status, strategy, notes, tags, opened_at, closed_at, session_id, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?)""",
                (tid, symbol.upper(), symbol.upper()[:3], side, qty, size_usd, entry_price,
                 exit_price or 0, pnl_usd, pnl_pct, status, strategy, notes,
                 json.dumps(tags or []), opened_at, closed_at, session_id, source))
        trade = self.get_trade(tid)
        if status == "closed":
            self.log(f"Trade {symbol} closed {pnl_usd:+.2f} USD ({pnl_pct:+.2f}%)",
                     category="trade", level="INFO",
                     detail={"trade_id": tid, "symbol": symbol, "pnl_usd": pnl_usd})
            self.evaluate("trade.closed" if pnl_usd < 0 else "trade.win",
                          {"symbol": symbol, "pnl": f"{pnl_usd:.2f}", "pnl_pct": f"{pnl_pct:+.2f}%"}, {})
        return trade

    def close_trade(self, trade_id: str, exit_price: Optional[float] = None,
                    exit_price_delta: float = 0.0, fees: float = 0.0,
                    notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not r:
            return None
        t = dict(r)
        if t["status"] == "closed":
            return t
        price = exit_price if exit_price and exit_price > 0 else (t["entry_price"] + exit_price_delta)
        if price <= 0 or t["entry_price"] <= 0 or t["qty"] <= 0:
            pnl_usd = pnl_pct = 0.0
        elif t["side"] == "buy":
            pnl_usd = (price - t["entry_price"]) * t["qty"] - fees
            pnl_pct = (price - t["entry_price"]) / t["entry_price"] * 100
        else:
            pnl_usd = (t["entry_price"] - price) * t["qty"] - fees
            pnl_pct = (t["entry_price"] - price) / t["entry_price"] * 100
        closed_at = _now()
        with self._conn() as c:
            c.execute("""UPDATE trades SET status='closed', exit_price=?, pnl_usd=?, pnl_pct=?,
                         fees=?, closed_at=? WHERE id=?""",
                      (price, pnl_usd, pnl_pct, fees, closed_at, trade_id))
        if notes is not None:
            with self._conn() as c:
                c.execute("UPDATE trades SET notes=? WHERE id=?", (notes, trade_id))
        self.log(f"Trade {t['symbol']} closed {pnl_usd:+.2f} USD ({pnl_pct:+.2f}%)",
                 category="trade", level="INFO",
                 detail={"trade_id": trade_id, "symbol": t["symbol"], "pnl_usd": pnl_usd})
        self.evaluate("trade.win" if pnl_usd >= 0 else "trade.loss",
                      {"symbol": t["symbol"], "pnl": f"{pnl_usd:.2f}", "pnl_pct": f"{pnl_pct:+.2f}%"}, {})
        return self.get_trade(trade_id)

    def update_trade(self, trade_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {"notes", "tags", "strategy", "symbol", "source"}
        sets, args = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                args.append(json.dumps(v) if k == "tags" else v)
        if not sets:
            return self.get_trade(trade_id)
        args.append(trade_id)
        with self._conn() as c:
            c.execute(f"UPDATE trades SET {', '.join(sets)} WHERE id=?", args)
        return self.get_trade(trade_id)

    def delete_trade(self, trade_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM trades WHERE id=?", (trade_id,))
        return cur.rowcount > 0

    def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["tags"] = json.loads(d.get("tags") or "[]")
        return d

    def get_trades(self, status: Optional[str] = None, symbol: Optional[str] = None,
                   strategy: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        q = "SELECT * FROM trades WHERE 1=1"
        args: List[Any] = []
        if status and status != "ALL":
            q += " AND status=?"; args.append(status)
        if symbol and symbol != "ALL":
            q += " AND symbol LIKE ?"; args.append(f"%{symbol}%")
        if strategy and strategy != "ALL":
            q += " AND strategy=?"; args.append(strategy)
        q += " ORDER BY opened_at DESC LIMIT ?"; args.append(int(limit))
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ────────────────────────────────────────────────────────────────
    def stats(self, days: Optional[int] = None, symbol: Optional[str] = None,
              strategy: Optional[str] = None) -> Dict[str, Any]:
        trades = self.get_trades(status="closed")
        if days:
            cutoff = _now() - days * 86400
            trades = [t for t in trades if (t["closed_at"] or 0) >= cutoff]
        if symbol and symbol != "ALL":
            trades = [t for t in trades if symbol.lower() in t["symbol"].lower()]
        if strategy and strategy != "ALL":
            trades = [t for t in trades if t["strategy"] == strategy]
        trades.sort(key=lambda t: t["closed_at"] or 0)
        closed = trades
        open_trades = self.get_trades(status="open")

        def agg(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
            n = len(rows)
            wins = [t for t in rows if t["pnl_usd"] >= 0]
            losses = [t for t in rows if t["pnl_usd"] < 0]
            gross_profit = sum(t["pnl_usd"] for t in wins)
            gross_loss = abs(sum(t["pnl_usd"] for t in losses))
            net = gross_profit - gross_loss
            pnls = [t["pnl_usd"] for t in rows]
            holds = [(t["closed_at"] or 0) - (t["opened_at"] or 0) for t in rows if t["closed_at"]]
            # equity curve + max drawdown
            curve, cum, peak, mdd = [], 0.0, 0.0, 0.0
            for t in rows:
                cum += t["pnl_usd"]
                curve.append({"ts": t["closed_at"], "pnl": round(cum, 2)})
                peak = max(peak, cum)
                if peak > 0:
                    mdd = max(mdd, (peak - cum))
            # daily pnl
            by_day: Dict[str, float] = {}
            for t in rows:
                day = datetime.fromtimestamp(t["closed_at"] or 0, tz=timezone.utc).strftime("%Y-%m-%d")
                by_day[day] = by_day.get(day, 0.0) + t["pnl_usd"]
            # streaks
            streaks = {"wins": 0, "losses": 0}
            cur = None; cur_n = 0
            for t in rows:
                kind = 1 if t["pnl_usd"] >= 0 else -1
                if kind == cur:
                    cur_n += 1
                else:
                    cur, cur_n = kind, 1
            if cur == 1 and cur_n: streaks["wins"] = cur_n
            if cur == -1 and cur_n: streaks["losses"] = cur_n
            day_pnls = [v for _, v in sorted(by_day.items())]
            mean = sum(pnls) / n if n else 0.0
            var = sum((p - mean) ** 2 for p in pnls) / n if n else 0.0
            std = var ** 0.5
            daily_mean = sum(day_pnls) / len(day_pnls) if day_pnls else 0.0
            daily_var = sum((p - daily_mean) ** 2 for p in day_pnls) / len(day_pnls) if day_pnls else 0.0
            daily_std = daily_var ** 0.5
            return {
                "trades": n,
                "wins": len(wins), "losses": len(losses),
                "win_rate": round(len(wins) / n * 100, 1) if n else 0,
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "net_pnl": round(net, 2),
                "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if n else 0),
                "avg_win": round(sum(t["pnl_usd"] for t in wins) / len(wins), 2) if wins else 0,
                "avg_loss": round(sum(t["pnl_usd"] for t in losses) / len(losses), 2) if losses else 0,
                "expectancy": round(mean, 2),
                "best_trade": round(max(pnls), 2) if pnls else 0,
                "worst_trade": round(min(pnls), 2) if pnls else 0,
                "avg_hold_min": round(sum(holds) / len(holds) / 60, 1) if holds else 0,
                "max_drawdown_usd": round(mdd, 2),
                "sharpe_daily": round(daily_mean / daily_std * (365 ** 0.5), 2) if daily_std > 0 else 0,
                "equity_curve": curve,
                "daily_pnl": [{"date": d, "pnl": round(v, 2)} for d, v in sorted(by_day.items())],
                "streaks": streaks,
            }

        total = agg(closed)
        # breakdowns
        by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        by_strategy: Dict[str, List[Dict[str, Any]]] = {}
        for t in closed:
            by_symbol.setdefault(t["symbol"], []).append(t)
            by_strategy.setdefault(t["strategy"] or "manual", []).append(t)
        sym_rows = [{"group": k, **agg(v)} for k, v in sorted(by_symbol.items(),
                    key=lambda kv: agg(kv[1])["net_pnl"], reverse=True)]
        strat_rows = [{"group": k, **agg(v)} for k, v in sorted(by_strategy.items(),
                      key=lambda kv: agg(kv[1])["net_pnl"], reverse=True)]
        return {
            "total": total,
            "by_symbol": sym_rows,
            "by_strategy": strat_rows,
            "open_positions": len(open_trades),
            "generated_at": _iso(),
            "days": days, "symbol": symbol, "strategy": strategy,
        }

    # ── Notifications ────────────────────────────────────────────────────────
    def get_rules(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM notification_rules ORDER BY priority, title").fetchall()
        return [dict(r) for r in rows]

    def save_rule(self, rule_id: Optional[str], trigger: str, title: str, message: str,
                  priority: str = "normal", threshold: float = 0,
                  threshold_units: str = "none", cooldown_sec: int = 60,
                  enabled: bool = True) -> Dict[str, Any]:
        rid = rule_id or uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO notification_rules
                (id, trigger, title, message, priority, threshold, threshold_units, cooldown_sec, enabled)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    trigger=excluded.trigger, title=excluded.title, message=excluded.message,
                    priority=excluded.priority, threshold=excluded.threshold,
                    threshold_units=excluded.threshold_units, cooldown_sec=excluded.cooldown_sec,
                    enabled=excluded.enabled""",
                (rid, trigger, title, message, priority, threshold, threshold_units,
                 int(cooldown_sec), 1 if enabled else 0))
        return {"id": rid, "trigger": trigger, "title": title,
                "message": message, "priority": priority, "threshold": threshold,
                "threshold_units": threshold_units, "cooldown_sec": int(cooldown_sec),
                "enabled": enabled}

    def delete_rule(self, rule_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM notification_rules WHERE id=?", (rule_id,))
        return cur.rowcount > 0

    def _rule_allowed(self, rule: Dict[str, Any], now: float) -> bool:
        if not rule["enabled"]:
            return False
        last = rule["last_triggered_at"]
        return last is None or (now - last) >= (rule["cooldown_sec"] or 0)

    def _mark_triggered(self, rule_id: str, now: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE notification_rules SET last_triggered_at=? WHERE id=?", (now, rule_id))

    def evaluate(self, trigger: str, ctx: Dict[str, Any],
                 state: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all enabled rules for a given trigger + context.

        Returns {'triggered': [..], 'trigger': trigger}.
        """
        triggered: List[Dict[str, Any]] = []
        now = _now()
        rules = [r for r in self.get_rules() if r["trigger"] == trigger and self._rule_allowed(r, now)]
        for rule in rules:
            hit = False
            th = rule["threshold"] or 0
            if trigger in ("trade.closed", "trade.win", "trade.loss", "position.opened",
                           "session.started", "session.ended", "strategy.started", "strategy.stopped"):
                hit = True
            elif trigger == "pnl.threshold":
                hit = state.get("daily_pnl_usd", 0) >= th
            elif trigger == "loss.streak":
                hit = state.get("losses_streak", 0) >= (int(th) if th else 3)
            elif trigger == "win.streak":
                hit = state.get("wins_streak", 0) >= (int(th) if th else 3)
            elif trigger == "drawdown.threshold":
                hit = state.get("drawdown_pct", 0) >= th
            elif trigger == "calendar.high":
                hit = bool(state.get("next_event"))
            if hit:
                msg = _fmt(rule["message"], ctx)
                triggered.append({"rule_id": rule["id"], "title": rule["title"],
                                  "message": msg, "trigger": trigger,
                                  "priority": rule["priority"], "ts": now})
                self._mark_triggered(rule["id"], now)
                with self._conn() as c:
                    c.execute("""INSERT INTO notification_log (ts, rule_id, trigger, priority, title, message)
                                 VALUES (?,?,?,?,?,?)""",
                              (now, rule["id"], trigger, rule["priority"], rule["title"], msg))
                self.log(f"Notification: {rule['title']} — {msg}", category="info",
                         level="INFO", detail={"rule_id": rule["id"], "trigger": trigger})
        return {"triggered": triggered, "trigger": trigger}

    def check_all(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run a full sweep against engine state (positions, stats, calendar)."""
        ne = state.get("next_event") or {}
        ctx = {
            "streak": state.get("losses_streak", state.get("wins_streak", 0)),
            "dd": round(state.get("drawdown_pct", 0), 1),
            "amount": round(state.get("daily_pnl_usd", 0), 2),
            "title": ne.get("title", "unknown"),
            "currency": ne.get("currency", "USD"),
            "minutes": ne.get("time_until_min", "—"),
        }
        state["ctx"] = ctx
        triggered: List[Dict[str, Any]] = []
        triggers = ["pnl.threshold", "loss.streak", "win.streak",
                    "drawdown.threshold", "calendar.high"]
        for trig in triggers:
            res = self.evaluate(trig, ctx, state)
            triggered.extend(res["triggered"])
        return {"triggered": triggered}

    # ── Bot Backtests ──────────────────────────────────────────────────────
    def save_bot_backtest(self, bot_id: str, params: Dict[str, Any],
                          metrics: Dict[str, Any], source: str = "manual",
                          user_id: str = "default") -> Dict[str, Any]:
        ran_at = _now()
        with self._conn() as c:
            c.execute(
                """INSERT INTO bot_backtests (bot_id, user_id, ran_at, params_json, metrics_json, source)
                   VALUES (?,?,?,?,?,?)""",
                (bot_id, user_id, ran_at, json.dumps(params), json.dumps(metrics), source))
        return {"bot_id": bot_id, "ran_at": ran_at, "params": params, "metrics": metrics, "source": source}

    def get_bot_backtests(self, bot_id: str, user_id: str = "default",
                          limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM bot_backtests WHERE bot_id=? AND user_id=?
                   ORDER BY ran_at DESC LIMIT ?""",
                (bot_id, user_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d.get("params_json") or "{}")
            d["metrics"] = json.loads(d.get("metrics_json") or "{}")
            out.append(d)
        return out

    def notification_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM notification_log ORDER BY ts DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]


trade_journal = TradeJournal()