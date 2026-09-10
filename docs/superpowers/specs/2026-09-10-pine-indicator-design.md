# Spec: Pine Script Import → Custom Indicator (v1: plots + inputs)

Date: 2026-09-10. Status: design approved in chat; awaiting spec review.

## Goal
User uploads a `.pinescript` file on the homepage; v1-supported indicators
compile to overlays rendered on our own chart, with `input.*` knobs as live
sliders. Explicitly NOT TradingView parity.

## Hard constraint (verified)
The main chart is a TradingView iframe (`embed-widget-advanced-chart.js`) —
no API exists to inject custom studies. All custom rendering happens on our
lightweight-charts panel (`PriceChart`, `lightweight-charts@4.1.3`, revived
from dead code with line/histogram series support added).

## v1 language subset
- Header: `//@version=4|5`, `indicator(title, shorttitle, overlay=true|false)`.
  `overlay=false` renders in a separate pane below candles; only one
  separate pane in v1 (first non-overlay plot wins, rest error).
- Inputs: `input.int/defval/minval/maxval`, `input.float`, `input.bool`,
  `input.source` (fixed menu: open/high/low/close/hl2/hlc3/ohlc4).
- Series builtins: `open/high/low/close/volume/hl2/hlc3/ohlc4`, `nz()`.
- Functions: `ta.sma`, `ta.ema`, `ta.rsi`, `ta.macd` (and bare `sma/ema/rsi`
  aliases for v4 style). No `request.*`, no `strategy.*`, no loops, no
  `varip`, no multi-timeframe.
- Plots: `plot(series, title, color, linewidth, style=[line|circles|cross|histogram])`,
  `plotshape`/`plotchar` limited to datapoint markers on the main pane,
  `hline(price)` single level. `fill`, `bgcolor`, `barcolor` rejected in v1.
- Anything outside the subset → `400` with per-line errors
  `[{line, code, reason}]`. Never silently mis-plot.

## Architecture
New `agent_system/indicators/` package:
- `pine_parser.py` — line-oriented parser → IR `{meta, inputs[], plots[]}`.
  No eval/exec of user code, ever — only the whitelist above constructs calls.
- `pine_evaluator.py` — pure functions over OHLCV lists: `series_funcs` +
  rolling sma/ema/rsi/macd (pandas, seeded by existing analytics code style).
- Storage: `data/indicators/<name>.pinescript` + `<name>.spec.json` (IR +
  compile hash + created_by user_id-ready field defaulting `'default'`).
- Bridge endpoints: `POST /indicators/upload` (multipart, auth enforced,
  200KB cap, `.pinescript`/`.pine` extension), `GET /indicators` (list specs),
  `GET /indicators/<name>/series?symbol=&timeframe=&inputs={...}` (fetches
  candles via existing `_fetch_ohlcv`, evaluates, returns `{inputs, columns:
  {plot: [...]}, spec_hash}`), `DELETE /indicators/<name>`.
- UI (`ui/app.jsx`): homepage block `PineBlock` — file picker + error list +
  active-indicator selector + auto-rendered sliders from spec inputs +
  `IndicatorChart` (lightweight-charts: candlesticks + `addLineSeries` per
  overlay plot + optional separate pane + markers). Recompute debounced 300ms
  on slider input; abort stale fetches.

## Data flow
upload → parse (errors? show lines) → store spec → select → fetch candles +
series (inputs in query) → render overlays → slider → re-fetch (debounced).

## Error handling
- Parse errors: blocking, listed per line; nothing stored.
- Eval errors (e.g. length > candle count): `400 {error, line}`; chart keeps
  last good render.
- Candle fetch failure: chart shows cached/empty state with retry, never blank-crashes.
- Upload abuse: size cap, extension check, max 20 stored scripts per tenant.

## Testing
- Unit: parser fixtures (valid v4 + v5 samples, each rejected construct).
- Unit: evaluator vs hand-computed sma/ema/rsi on fixture candles.
- Integration: upload → series round-trip; slider change alters output.
- Harness: render-body smoke test extended to new components (existing pattern).
- Live: pytest green; manual upload of an EMA-cross script, overlay visible.
