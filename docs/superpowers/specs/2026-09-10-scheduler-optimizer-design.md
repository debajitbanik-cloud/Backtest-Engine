# Spec: Scheduled Backtest + Parameter Optimizer Service

Date: 2026-09-10. Status: design approved in chat; awaiting spec review.

## Goal
Run backtests and parameter-only tuning on a schedule (default weekly per bot),
persist versioned results, and auto-promote improved parameters — without ever
touching bot core logic. Must run 24/7 on a client VM and be ready for 50–100
users (tenant-scoped schema from day one, single tenant `'default'` today).

## Non-goals
- No change to strategy/entry/exit code paths. Only the params dict flows into
  the existing optimizers.
- No live auto-deployment of new params to real orders in v1 (promotion stages
  params as `candidate`; UI shows Adopt/Reject; auto-adopt is a per-job flag
  defaulting OFF).
- No multi-process workers in v1 (asyncio loop in main process; one VM = one tenant).

## Architecture
New package `agent_system/scheduler/` with three units:

- `store.py` — SQLite `data/scheduler.db`, tables:
  - `jobs(id, user_id, bot_id, kind[backtest|optimize], cadence_cron, metric, grid_json, auto_adopt, enabled, created_at)` with `INDEX(user_id, enabled)`.
  - `runs(id, job_id, user_id, started_at, finished_at, status, result_json, promoted)` with `INDEX(job_id, started_at)`.
  - `bot_backtests(bot_id, user_id, ran_at, params_json, metrics_json, source[job|manual])` — also written by `POST /backtest/run` when `bot_id` is passed (piece A).
- `optimizer.py` — pure functions, no I/O:
  - `build_grid(bot_params)` — grid from the bot's declared params (numeric ranges ±2 steps around current; categorical as listed).
  - `evaluate(bot_id, params, candles)` — calls existing `strategy_library.run_backtest`; splits candles 70/30 in-sample/out-of-sample, returns both metric sets.
  - `promotion_policy(current, candidate)` — promote iff OOS Sharpe > current OOS Sharpe AND candidate trades ≥ 30 AND max drawdown ≤ current + 5pp. Returns (promote: bool, reason: str).
- `service.py` — asyncio loop: every 60s, load due enabled jobs (`cadence_cron` evaluated minimally: support `@weekly`, `@daily`, `@hourly` + `cron()` passthrough to croniter — croniter added to requirements), run backtest or optimize off the event loop via `asyncio.to_thread` (blocking pandas work must never stall the bridge), write run rows, stage promotions.

## Bridge endpoints (`bridge/python_bridge.py`)
- `POST /backtest/run` extended with optional `bot_id` → also writes `bot_backtests` row. (Auth: already enforced.)
- `GET/POST/DELETE /scheduler/jobs` — CRUD, auth enforced. POST validates: known bot_id, kind, metric in {sharpe, total_return_pct, profit_factor}, grid params ⊆ bot's declared params (reject unknown keys — this is the params-only guarantee, enforced server-side, not just UI).
- `GET /scheduler/runs?job_id=&limit=` — history for UI.
- `POST /scheduler/runs/<id>/adopt|reject` — explicit promotion control.

## Data flow
tick (60s) → due jobs → fetch candles (existing `_fetch_ohlcv`) → to_thread(evaluate) →
write run → policy check → stage candidate (never auto-trade in v1) → SSE event
`optimizer_run` on `/events` so UI updates live.

## Error handling
- Candle fetch failure → run status `failed_fetch`, retry next tick (no tight loop).
- Optimize crash on one grid point → skip point, continue; run marked `partial` if >0 points done.
- Promotion never raises: policy exceptions → `promoted=false, reason=error`.
- DB locked (SQLite + threads): single writer via service lock; WAL mode on.

## Testing
- Unit: policy matrix (improve/no-improve/min-trades/drawdown-guard/error) with synthetic metrics.
- Unit: grid builder rejects unknown param keys.
- Integration: run one backtest job + one optimize job against cached candles, assert rows in all three tables and SSE event emitted.
- Live: existing pytest suite stays green; manual: schedule hourly job, watch a run land in BotsView.

## Open (deferred, not v1)
Per-user Delta creds + per-user worker processes for the 50–100-user fleet; auto-adopt default policy per client.
