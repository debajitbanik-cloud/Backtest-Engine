# Implementation Plan: MT5 Flow pack (F, A, B, C, D, E)

Specs: `docs/superpowers/specs/2026-09-10-scheduler-optimizer-design.md`,
`docs/superpowers/specs/2026-09-10-pine-indicator-design.md`.
Worktree: `.worktrees/mt5-flow-build`, branch `build/mt5-flow-pack`.
All file paths below are relative to the worktree root.

## Global Constraints (binding on every task)
1. **Core-protection rule (user-mandated):** DO NOT change existing behavior in
   core money/risk paths: `bridge/python_bridge.py` order/mode/auth handlers,
   `agent_system/data/delta_api_client.py` validation, `agent_system/execution/`,
   existing `trade_journal` tables/queries, order sizing/leverage math. Additive
   only: new files, new endpoints, new UI components, new optional params.
   If a task cannot be done without altering core behavior: STOP, do not
   improvise — return BLOCKED with the exact conflict.
2. Every new bridge endpoint that writes state or triggers compute requires
   the existing Bearer auth check (`_check_auth`).
3. No secrets in code or logs. No hardcoded tokens.
4. Python: follow existing module patterns (imports from `core.*`, `data.*`).
   UI: single-file `ui/app.jsx` React (no build step), `const API = ''`
   relative URLs only.
5. Verify with the project's suites: `python3 -m pytest agent_system/tests/ -q`
   and `npm test`, plus the render-harness pattern for UI work
   (transpile `ui/app.jsx` with babel, execute all components with stubs,
   assert zero ReferenceError on all 10 `?tab=` tabs).
6. Commit per task on branch `build/mt5-flow-pack`. Work ONLY inside the worktree.

## Task 1 (F): Forward/back navigation polish
Files: `ui/app.jsx` only.
- Add `→` button next to existing `←` in header; calls `history.forward()`.
  Enabled always (harmless at history end); `←` keeps existing `canGoBack` gate.
- Keep 0.18s fadeIn on `<main>`; confirm `?tab=` deep-link restores each tab.
- Verify: render harness over all 10 tabs, zero ReferenceError; `node --check` clean.

## Task 2 (A1): Bot logic explanations (data + display, no behavior change)
Files: `ui/app.jsx` only (BOTS data + BotsView detail pane).
- For each of the 26 runnable bots add `entry`, `exit`, `risk` short strings
  derived from its existing `desc`/`logic`/`params` (do not invent strategies;
  paraphrase what the fields say).
- Detail pane gets a "Logic" block rendering entry/exit/risk + existing params.
- Verify: harness zero ReferenceError; `npm test` green (unaffected).

## Task 3 (A2): Per-bot backtest persistence + display
Files: `agent_system/core/trade_journal.py` (new `bot_backtests` table only),
`bridge/python_bridge.py` (extend `POST /backtest/run` with optional `bot_id`;
new `GET /backtest/bot/<bot_id>` history), `ui/app.jsx` (BotsView detail:
last result + history list).
- Table: `(bot_id, user_id DEFAULT 'default', ran_at, params_json, metrics_json, source)`.
- Existing `/backtest/run` behavior unchanged when `bot_id` absent.
- Verify: pytest green + manual curl round-trip (run with bot_id → history shows it).

## Task 4 (B1): Scheduler store + optimizer pure functions
Files: NEW `agent_system/scheduler/__init__.py, store.py, optimizer.py`,
NEW `agent_system/tests/test_scheduler.py`. No wiring to main/bridge yet.
- `store.py`: SQLite `data/scheduler.db` (WAL), `jobs` + `runs` + `bot_backtests`
  tables per spec (all with `user_id`), CRUD helpers.
- `optimizer.py`: `build_grid(bot_params)` (unknown keys rejected),
  `evaluate()` via `strategy_library.run_backtest` with 70/30 split,
  `promotion_policy()` per spec thresholds.
- Tests: policy matrix, grid rejection, store round-trip.
- Verify: new tests pass + full pytest green.

## Task 5 (B2): Scheduler service loop + bridge endpoints + main wiring
Files: NEW `agent_system/scheduler/service.py`; `bridge/python_bridge.py`
(new `/scheduler/jobs` CRUD, `/scheduler/runs`, adopt/reject — auth enforced);
`agent_system/main.py` (start service loop as background task; do NOT reorder
existing startup); `agent_system/requirements.txt` (+`croniter`).
- Cron support: `@weekly/@daily/@hourly` + croniter passthrough.
- Heavy compute via `asyncio.to_thread`. SSE event `optimizer_run` on completion.
- Core-protection: main.py change is start-one-task only; any deeper change → BLOCKED.
- Verify: pytest green; live: create hourly job via curl, observe a run row + SSE.

## Task 6 (B3): Scheduler UI (BotsView + Settings)
Files: `ui/app.jsx` only.
- Per-bot: cadence select, metric select, enable toggle, last-run + history,
  Adopt/Reject buttons for staged candidates.
- Settings: Scheduling section (defaults, max concurrent jobs, job list).
- Verify: harness zero ReferenceError; manual click-through against live bridge.

## Task 7 (C1): Pine parser + evaluator + fixtures
Files: NEW `agent_system/indicators/__init__.py, pine_parser.py, pine_evaluator.py`,
NEW `agent_system/tests/test_pine.py` + fixture scripts. No endpoints yet.
- Subset per spec: indicator(), input.int/float/bool/source, plot(),
  hline(), series builtins, ta.sma/ema/rsi/macd (+v4 aliases).
- Parser returns IR or per-line errors; evaluator computes columns from OHLCV.
  NEVER eval/exec user code.
- Verify: fixture tests (valid v4+v5, every rejected construct errors).

## Task 8 (C2): Indicator endpoints + storage
Files: NEW storage under `data/indicators/` (spec JSON + source, gitignored);
`bridge/python_bridge.py` (POST upload w/ auth + 200KB cap + extension check,
GET list, GET series, DELETE).
- Series endpoint reuses existing candle fetch; unknown inputs rejected.
- Verify: pytest green; curl upload→list→series→delete round-trip.

## Task 9 (C3): PineBlock + IndicatorChart UI
Files: `ui/app.jsx` only.
- Revive `PriceChart` on lightweight-charts with `addLineSeries` overlays +
  one separate pane + markers; `PineBlock`: file picker, per-line error list,
  active-indicator select, auto sliders from spec inputs, debounced (300ms)
  recompute with stale-fetch abort.
- Verify: harness zero ReferenceError; manual upload of EMA script shows overlay.

## Task 10 (D): Homepage blocks below chart
Files: `ui/app.jsx` only (DashboardView below-chart row).
- Block 1: Pine importer (Task 9 components, compact variant).
- Block 2: Bot Performance leaderboard (top bots by latest `bot_backtests`:
  return/win-rate + one-click backtest). Reads Task 3 endpoint; no new API.
- Verify: harness zero ReferenceError; manual check with seeded backtest rows.

## Task 11 (E): Settings overhaul
Files: `ui/app.jsx` SettingsView only (+ new bridge endpoint ONLY for token
  rotation if needed — else UI-only).
- Sections: Account Keys (exists, keep) · Bridge Token (show masked + rotate;
  rotation must update server-side source of truth — if this requires touching
  auth core, STOP and return BLOCKED per constraint 1) · Bots (global risk cap,
  per-bot enable/disable) · Runtime (poll intervals, feed source, default cash) ·
  Scheduling (defaults + job list, reads Task 5 endpoints) · Notifications
  (Telegram stub section, disabled, no backend) · Appearance (exists) · Data &
  Cache (exists + backtest-cache clear).
- Verify: harness zero ReferenceError; settings persist to localStorage as today.

## Task 12: Full verification
- `python3 -m pytest agent_system/tests/ -q`, `npm test`, render harness all tabs.
- `git log --oneline` review of the branch; report commits + residual concerns.
