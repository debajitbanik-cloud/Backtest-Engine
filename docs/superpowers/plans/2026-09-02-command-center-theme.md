# Command Center Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Backtest Engine trading dashboard to a cohesive "Cyber-Minimalism / Command Center" aesthetic with interactive terminal, Cmd+K palette, ambient overlays, tilt cards, cursor FX, and Web Audio.

**Architecture:** Four new `.js` files loaded in global-scope order by Babel-standalone before the existing `app.jsx`: `theme.js` (tokens), `chrome.js` (boot/overlays/particles/cursor/audio), `terminal.js` (REPL), `palette.js` (Cmd+K). `app.jsx` consumes the new tokens in its shared components, mounts the chrome, adds the Terminal tab, and wires the audio toggle. No build step; hard-refresh workflow preserved.

**Tech Stack:** React 18 via Babel-standalone, vanilla CSS inline styles, Google Fonts (Space Grotesk + JetBrains Mono), Web Audio API, Canvas API, SVG stroke-dashoffset animation, `sessionStorage`/`localStorage` for state persistence.

**Spec:** `docs/superpowers/specs/2026-09-02-command-center-theme-design.md`

## Global Constraints

- No build step (no Vite, no webpack); all `.js` files are `<script type="text/babel">` loaded in global scope.
- No ES modules (`import`/`export`); all symbols are `window`-attached or global.
- Every component uses `React.createElement` (no JSX).
- Shared components (`Card`, `Metric`, `Section`, `Tab`) live in `app.jsx` — `theme.js` supplies tokens only; `app.jsx` consumes them.
- `COLORS` object stays unchanged; new tokens live in `window.Theme.EXTRA`.
- `prefers-reduced-motion: reduce` respected everywhere (no animations, instant output, native cursor, muted audio).
- API base: `http://127.0.0.1:8088` (existing bridge).
- Lime accent: `#bef264` (WCAG AAA on `#0a0b0f`, ratio >= 13).
- Audio muted by default on first load; toggled by header button; persisted in `localStorage`.

## Tasks

### Task 1: Create ui/theme.js + add fonts to index.html
- Create `ui/theme.js` with `window.Theme.EXTRA` tokens
- Add Google Fonts link to `ui/index.html`
- Syntax check both files

### Task 2: Re-tokenize shared components in app.jsx
- Update Card to use glass tokens
- Update Section title font
- Update Tab to use lime accent for active state
- Update Metric with font families and tilt attribute
- Syntax check app.jsx

### Task 3-7: Create ui/chrome.js (all components)
- BootSequence (bios-style overlay, sessionStorage skip, prefers-reduced-motion)
- ScanlineOverlay, GridOverlay, NoiseOverlay
- ParticleField (canvas, 40 nodes, 30fps, proximity lines)
- DataStream (SVG animated border lines)
- CursorFX (crosshair, tilt cards, Shift+X toggle)
- AudioEngine (Web Audio, blip/hum/ping, gesture-gated, mute toggle)

### Task 8: Create ui/terminal.js
- TerminalView component (REPL, type-out, history, tab-complete)
- TerminalCmds registry (help, clear, status, positions, tickers, calendar, journal, log, trade, notify, backtest, echo, date, version)

### Task 9: Create ui/palette.js
- Palette component (Cmd+K overlay, filter, nav, bridge actions, terminal passthrough)
- Global keydown listener

### Task 10: Modify index.html load order
- Add 4 script tags before app.jsx

### Task 11: Modify app.jsx integration
- Mount all chrome in App root
- Add Terminal tab
- Wire palette + audio toggle
- Arm audio on first gesture

### Task 12: Full verification
- Syntax check all files
- Verify load order, bridge endpoints, contrast ratios
- Exercise terminal commands, palette, audio
- Check no regressions in existing tabs
