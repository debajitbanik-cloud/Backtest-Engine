# Command Center UI Theme — Design Spec

**Date:** 2026-09-02  
**Status:** Approved for implementation  
**Scope:** Restyle the Backtest Engine trading dashboard to a "Cyber-Minimalism / Command Center" aesthetic, adding interactive terminal, command palette, ambient chrome, and audio.

---

## Motivation

The current `ui/app.jsx` is a functional dark-theme trading dashboard using inline `React.createElement` styles and no build step (Babel-standalone, hard-refresh workflow). The goal is to apply a cohesive high-end command-center aesthetic — animated chrome, typography, an interactive terminal, a global command palette, and ambient audio — while keeping every existing feature intact and the no-build workflow unbroken.

## Architecture

**Implementation approach:** Split into ordered load-into-global-scope modules (Option B), leveraging the existing Babel-standalone inline compilation.

```
index.html  (adds Google Fonts link; loads scripts in order)
  theme.js     ← tokens, shared component style primitives
  chrome.js    ← boot, overlays, particles, cursor, audio, data streams
  terminal.js  ← terminal command registry + REPL
  palette.js   ← Cmd+K command palette
  app.jsx      ← existing views (consumes new tokens, mounts chrome)
```

All files use plain `React.createElement` (no JSX, no imports/exports). Each file appends its exports to a global object (e.g., `window.Theme`, `window.Chrome`, `window.TerminalCmds`) or attaches to the DOM via `addEventListener` for global hooks. No build step is required.

**Backward compatibility:** The existing `COLORS` object, `Card`, `Metric`, `Section`, `Tab`, and all view components (`DashboardView`, `CalendarView`, `LibraryView`, `JournalView`, etc.) remain in `app.jsx` and continue to work as before. The theme layer re-tokenizes shared components at the CSS/constant level so existing views restyle automatically.

---

## S1 — Visual Foundation (`ui/theme.js`)

### Tokens

Add `window.Theme.EXTRA` alongside the existing `COLORS` object in `app.jsx`:

| Token | Value | Purpose |
|-------|-------|---------|
| `fontDisplay` | `'Space Grotesk', sans-serif` | Headings, titles, stat values |
| `fontMono` | `'JetBrains Mono', monospace` | Terminal, labels, numbers, code |
| `fontBody` | System stack (as today) | Body text |
| `lime` | `'#bef264'` | Accent highlights; contrast > 9:1 on `#0a0b0f` |
| `limeDim` | `'#bef264' + '44'` | Lime at ~27% opacity for fills/borders |
| `glass` | `'rgba(17,19,24,0.72)'` | Glassmorphism card fill |
| `glassBorder` | `'rgba(34,36,44,0.6)'` | Glassmorphism border |
| `glassBlur` | `'12px'` | backdrop-filter radius |
| `scanlineOpacity` | `0.03` | Scanline overlay strength |
| `gridOpacity` | `0.06` | Background grid strength |
| `noiseOpacity` | `0.035` | Fractal noise strength |
| `particleCount` | `40` | Ambient particle field node count |
| `streamSpeed` | `24` | Data-stream border animation duration (s) |
| `tiltMaxDeg` | `8` | Tilt card max rotation |

### Google Fonts

`index.html` adds inside `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

### Component re-tokenization

`theme.js` will override the shared component constructors (after `app.jsx` defines them) using `requestAnimationFrame(() => ...)` or by exposing style factories in `window.Theme.style.card()`, `.metric()`, `.section()`, etc., and having `app.jsx` consume them on next hard-refresh. Practically: `app.jsx`'s `Card`, `Metric`, `Section`, and `Tab` will be updated in place to read from `Theme.EXTRA` tokens instead of hard-coded hex values, so every view restyles through the shared components automatically.

Key changes to shared components:
- `Card`: `background` → `Theme.EXTRA.glass`; `border` → `Theme.EXTRA.glassBorder`; `backdrop-filter: blur(12px)`.
- `Metric`: value font → `Theme.EXTRA.fontDisplay`; label font → `Theme.EXTRA.fontMono`; add a `.tilt` class for perspective hover.
- `Section` title: `Theme.EXTRA.fontDisplay` weight-800.
- `Tab` active: active state becomes lime (`Theme.EXTRA.lime`) instead of blue.

The existing `COLORS.blue` remains the default accent for informational elements; lime is reserved for highlights, tilt glow, palette, and alerts.

### Contrast verification

- Lime `#bef264` on `#0a0b0f`: ratio **~13.2:1** (AAA).
- `#8b8fa3` (textSecondary) on `#0a0b0f`: ratio **~6.8:1** (AA for large text; acceptable for UI labels at 11–12px).
- `#5a5e6f` (textTertiary) on `#0a0b0f`: ratio **~3.2:1** — reserved for non-essential tertiary labels; not used for interactive text.

---

## S2 — Ambient Chrome (`ui/chrome.js`)

### BootSequence (`window.Chrome.BootSequence`)

A fixed full-screen overlay rendered once in `App`. Content: left-aligned monospace log lines that appear progressively (~20 lines, each delayed 60–100ms). Lines are drawn in `Theme.EXTRA.fontMono` at 12px, lime for `[OK]` prefixes. Example lines:

```
[boot] initializing kernel...
[ok]   loading delta_api_client ✓
[ok]   loading options_engine ✓
[ok]   loading event_bus ✓
[ok]   loading trade_journal ✓
[ok]   connecting to 127.0.0.1:8088...
[ok]   API status: healthy
[boot] loading UI modules...
[ok]   theme.js ✓
[ok]   chrome.js ✓
[ok]   terminal.js ✓
[ok]   palette.js ✓
[ok]   app.jsx ✓
> ACCESS GRANTED — welcome to the trading command center
```

- Skippable via `Enter`, `Space`, `Escape`, or any `click` during playback.
- Once per browser session: controlled via `sessionStorage.setItem('cc_booted', '1')`. On mount, if `sessionStorage.cc_booted` is already `'1'`, render null (no boot, instant render).
- Duration: ~2s at default type rate; fades out over 400ms after final line or skip.
- `prefers-reduced-motion`: skip immediately, render null.

### Overlays

`ScanlineOverlay` — fixed `<div>` over entire viewport: CSS `repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.03) 2px, rgba(255,255,255,0.03) 4px)`, `pointer-events:none`, z-index 9998. Respect `prefers-reduced-motion` (hidden).

`GridOverlay` — fixed: `background-image: linear-gradient(rgba(78,140,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(78,140,255,0.06) 1px, transparent 1px); background-size: 40px 40px`, `pointer-events:none`, z-index -1. Low opacity, ambient.

`NoiseOverlay` — fixed: inline SVG `feTurbulence` base64, `pointer-events:none`, `opacity: 0.035`, z-index -1. Gives texture to flat panels.

### ParticleField (`window.Chrome.ParticleField`)

Canvas element placed in `App` root (before `<main>`), `position:fixed`, z-index -1, `pointer-events:none`.

- ~40 nodes, slow velocity (`0.15–0.4 px/frame`), random initial positions.
- Draw radius 1.5px (lime at 0.18 opacity).
- Connect nodes with a line when distance < 150px (line opacity = 0.06 × (1 - dist/150)).
- Throttled to 30fps via `requestAnimationFrame` + frame interval check.
- Pauses when `document.hidden === true`.

### DataStream (`window.Chrome.DataStream`)

Applied as a pseudo-element / SVG overlay on the header bar and key cards. Implementation: a `<div>` with `position:absolute; overflow:hidden; border-radius: inherit;` containing a moving `<svg>` with a short (`40px`) horizontal line segment animated via `stroke-dashoffset` along a `<path>` tracing the perimeter. Speed: 24s per full loop. The line color: lime at 0.3 opacity. Two instances (top-left → right → down → left loop, counter-clockwise). Applied to: the sticky header, the Terminal tab card, and the `Metric` cards on hover.

### CursorFX (`window.Chrome.CursorFX`)

- Only active when `matchMedia('(pointer: fine)').matches` (non-touch).
- Hide native cursor on `body` via `cursor: none`.
- Two elements follow the mouse: (1) a 6px solid lime dot (`mix-blend-mode: difference`) and (2) a 28px crosshair ring (2px lime border, transparent fill), both `position:fixed; pointer-events:none; z-index:9999`.
- On hover over `[data-hover]`, `<button>`, `<input>`, `<textarea>`, `<select>`, `<a>`: ring scales to 1.8×, dot fills lime solid, transition 150ms.
- Tilt-enabled cards get a `data-hover` attribute.
- `Shift+X` toggles `body.style.cursor = 'auto'` and hides the custom cursor (for accessibility).
- Disabled when `prefers-reduced-motion: reduce`.

### TiltCard behavior

A delegated `mousemove` listener on `document` applies a perspective transform to any element with `[data-tilt]` (all `Metric` cards get this). Transform: `rotateX(Y) rotateX(-X)` based on mouse offset from element center, clamped to `Theme.EXTRA.tiltMaxDeg`. `rotateX`/`rotateY` capped at `±8deg`. Transitions: `0.1s ease-out` on `mousemove`; snaps back with `0.4s ease-out` on `mouseleave`. No 3D libraries — pure CSS transforms.

---

## S3 — Terminal Tab (`ui/terminal.js`)

### UI

New tab labeled "Terminal" in the header tabs array (between Strategy Library and Analytics, or as the last tab). Clicking it renders `window.TerminalView`.

Structure:
- Black background card (`#060810`) with glass border, mono font.
- Scrollable output area (`max-height: calc(100vh - 140px); overflow-y: auto`), auto-scrolls to bottom on new output.
- Each output line: monospace 12px, `#8b8fa3` for system lines, `#2ecc71` for success `[ok]`, `#e74c3c` for `ERR`, `#f0a500` for info, `#bef264` for input echo.
- Boot banner (3 lines) printed on first mount: ASCII art or simple `[trading command center] v1.0 | type "help" to begin`.
- Input line: blinking block cursor (`▎` via CSS animation or `setInterval`), mono font, lime text, immediately focused on tab switch.

### Typing micro-interactions

- On command submit: the user's input line is echoed instantly (full color).
- Output text appears progressively at ~8ms per character using `typeOut(callback)` — a utility that appends characters from a buffer to the output div via `requestAnimationFrame`. This creates the "types out" feel from the design doc.
- During `typeOut`, the input line is disabled and shows `█` (blocked).
- A click or second Enter during type-out reveals the full output instantly (skip).
- `prefers-reduced-motion`: output is instant (no type-out).

### Command registry (`window.TerminalCmds`)

Global `Map<string, { description, exec }>`. Files attach commands via:
```js
window.TerminalCmds = window.TerminalCmds || new Map();
window.TerminalCmds.set('status', {
  description: 'Show Delta API health and bridge status',
  exec: async () => {
    const r = await fetch(`${API}/delta/health`);
    const d = await r.json();
    return [
      { text: `status: ${d.running ? 'running' : 'stopped'}`, color: d.running ? COLORS.green : COLORS.red },
      { text: `bridge: 127.0.0.1:8088 · mode: ${d.mode}`, color: COLORS.textSecondary },
      { text: `delta: ${d.connected ? 'connected' : 'offline'}`, color: d.connected ? COLORS.green : COLORS.red },
    ];
  }
});
```

Defined commands (across `terminal.js`, `chrome.js`, `palette.js`):

| Command | Action | Output |
|---------|--------|--------|
| `help` | List all registered commands | Description of each |
| `clear` | Clear terminal output | (blank) |
| `status` | GET `/delta/health` | Bridge status, mode, Delta connection |
| `positions` | GET `/delta/positions` | Position list (open positions table) |
| `tickers [asset]` | GET `/delta/tickers` or `/delta/tickers/{symbol}` | Price and 24h change for one or all |
| `mode [read_only\|trading]` | POST `/delta/mode` | Guarded — prints "requires bridge auth token; use terminal or .env" |
| `calendar` | GET `/calendar/events` | Next high-impact event |
| `journal` | GET `/journal/stats` | Net P&L, win rate, trades summary |
| `trade <sym> <side> <qty> <entry> [exit]` | POST `/journal/trades` | Logged trade confirmation |
| `log <msg...>` | POST `/journal/log` | "logged" confirmation |
| `notify` | POST `/journal/notifications/check` | List triggered notifications |
| `backtest <asset> <strategy>` | POST `/backtest/run` | Backtest metrics (trades, return, drawdown) |
| `echo <msg...>` | — | Prints msg back (pure client-side) |
| `date` | — | Current ISO date/time |
| `version` | — | "trading command center v1.0" |

### Error handling

All `exec` functions are wrapped in try/catch in the REPL dispatcher. On network failure: `ERR <statusCode or 'network'>: <message>`. Output lines pushed to an internal `outputLines` array. REPL never crashes.

---

## S4 — Command Palette (`ui/palette.js`)

### Trigger and overlay

- Global keydown listener: `Cmd+K` (Mac) or `Ctrl+K` (other) toggles palette open/closed. Prevent default.
- Renders an overlay: fixed, full viewport, dark translucent (`rgba(0,0,0,0.6)`), centered box (max-width 560px, glass background, glass border, blur).
- Focus traps the text input inside.
- Click-outside or `Escape` closes.

### Command list

A unified array of `{ id, label, category, exec }` objects, assembled from:
1. **Tab navigation** — all 8 tabs (Dashboard, Options, Strategies, Calendar, Strategy Library, Journal, Analytics, Terminal), each with `exec: () => setTab(id)`.
2. **Bridge info actions** — `Status`, `Positions`, `Next Calendar Event`, `Journal Stats`, `Notification Check`, each with a function hitting the corresponding bridge endpoint.
3. **Terminal passthrough** — if the user types `>` followed by text, it routes the input to the Terminal's REPL dispatcher and opens the Terminal tab.

### UX

- Text input at top of overlay, auto-focused, mono font.
- As the user types, the command list is filtered by simple case-insensitive substring match across `label` and `category`.
- `↑`/`↓` arrows move highlight; `Enter` executes the highlighted command and closes palette; `Tab` accepts first match.
- `Escape` or click outside closes.
- Executing a tab navigation command switches to that tab instantly; info commands print results as a transient toast (using the existing journal toast mechanism) without navigating away.

---

## S5 — Audio Engine (`ui/chrome.js`, `AudioEngine`)

### Web Audio API (fully synthesized)

A singleton `AudioEngine` class attached to `window.Chrome.audio`, constructed once in `App` after boot dismissal (or after first user gesture if boot is skipped).

**Synthesized sounds (no external files):**

| Sound | Implementation | When |
|-------|---------------|------|
| `blip` | 80ms oscillator at 880Hz → 440Hz sweep, gain 0.07, sine wave | Terminal keystrokes (on each key, throttled to 50ms), palette navigation |
| `hum` | Continuous low oscillator at 60Hz, gain 0.02, sine, started/stopped with ramp (50ms attack/release) | Boot sequence running; tilt card hover |
| `ping` | 200ms oscillator at 1200Hz, gain 0.12, sine, with quick decay | Journal notification toast (SSE event) |

**Playback policy:**
- `AudioContext` created lazily on first `resume()`.
- Engine arms only after a user gesture (`click`, `keydown`) — this satisfies Chrome autoplay policy. The boot sequence dismissal is a gesture, so audio is active immediately post-boot.
- A mute toggle button in the header (`🔊` / `🔇` icon) calls `audioEngine.mute()`/`unmute()`. State persisted to `localStorage.setItem('cc_audio_muted', '1'|'0')`.
- Volume slider optional for future; default 0.08 master.
- `prefers-reduced-motion`: audio muted by default, toggle still available.

---

## S6 — Integration and Verification

### `index.html` changes

```html
<!-- Google Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

Script tags (in order, all `type="text/babel"`):
```html
<script type="text/babel" src="theme.js"></script>
<script type="text/babel" src="chrome.js"></script>
<script type="text/babel" src="terminal.js"></script>
<script type="text/babel" src="palette.js"></script>
<script type="text/babel" src="app.jsx"></script>
```

### `app.jsx` changes

- Import/use `Theme.EXTRA` tokens in `Card`, `Metric`, `Section`, `Tab` constructors.
- Add 'Terminal' to the `tabs` array.
- In `App` root element (after boot guard): mount `<Chrome.BootSequence>`, `<Chrome.ScanlineOverlay>`, `<Chrome.GridOverlay>`, `<Chrome.NoiseOverlay>`, `<Chrome.ParticleField>`, `<Chrome.CursorFX>`.
- Mount `<Palette>` (global, non-rendered when closed).
- Add `TerminalView` to the tab render switch.
- Add audio mute toggle button in the sticky header.

### Verification plan

| Test | How |
|------|-----|
| Syntax | `node --input-type=module --check < file` for each of `theme.js`, `chrome.js`, `terminal.js`, `palette.js`, and `ui/app.jsx` |
| Load order | `curl -s http://127.0.0.1:3000/index.html | grep src=` — verify 5 scripts load in correct order |
| Boot | Open browser → boot overlay appears → disappears after ~2s; reload in same session → instant (no boot) |
| Scanlines/grid/noise | Inspect in DevTools: elements present, `pointer-events:none`, low opacity |
| Particles | DevTools → canvas element present, `position:fixed`, `pointer-events:none` |
| CursorFX | On desktop: cursor hidden; crosshair follows mouse; ring scales on button hover; `Shift+X` restores native cursor |
| Tilt | Hover over a Metric card → 3D rotation follows mouse; snaps back on leave |
| Terminal | Click Terminal tab → REPL renders; type `help` → output types out; type `status` → bridge health prints; type `calendar` → next event prints; type `trade BTC buy 0.1 50000` → logged; type `notify` → triggered list |
| Palette | `Cmd+K` → overlay opens; type "journal" → Journal action highlighted; Enter → switches to Journal tab; type `>status` → opens Terminal and runs status |
| Audio | Post-boot: type in terminal → soft blip; hover tilt card → low hum; receive journal notification → ping; mute toggle silences all |
| Endpoints called | `curl` smoke: `/delta/health`, `/delta/positions`, `/delta/tickers`, `/calendar/events`, `/journal/stats`, `/journal/trades` (GET) — all return 200 |
| Contrast | Compute ratio in console: `lime=#bef264, bg=#0a0b0f` → ratio ≥ 13 |
| No regressions | All existing tabs (Dashboard, Options, Strategies, Calendar, Strategy Library, Journal, Analytics) render, data loads, interactions work |
| Reduced motion | Enable `prefers-reduced-motion: reduce` in DevTools → boot skips; overlays hidden; audio muted; type-out instant |

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Audio autoplay blocked | AudioEngine arms only after a real user gesture; boot dismissal counts as one |
| Cursor interferes with normal use | `Shift+X` toggle; disabled on touch; `prefers-reduced-motion` falls back to native |
| Tilt performance on low-end GPU | `will-change: transform` on tilt targets; throttle `mousemove` to 16ms; cap node count |
| Palette type-ahead lag | Simple substring filter, no fuzzy lib needed; command list is ~25 items max |
| Type-out delays user interaction | Click or Enter skips instantly; `prefers-reduced-motion` skips |
| `app.jsx` continues to grow | Terminal/tab/overlay logic lives in separate `.js` files; `app.jsx` only adds the Terminal tab entry and mounts chrome |
