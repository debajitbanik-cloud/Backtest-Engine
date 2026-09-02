const { useState, useEffect, useRef, useMemo } = React;
const API = 'http://127.0.0.1:8088';
const BRIDGE_TOKEN = '8G8VGUXx1sjVEmK7Y2fqs0VF6wcukOXSXwI6dVv24WY';

const COLORS = {
  bgRoot: '#0a0b0f', bgSurface: '#111318', bgElevated: '#161820', bgHover: '#1c1e26',
  border: '#22242c', borderActive: '#333540', text: '#e4e6ef', textSecondary: '#8b8fa3',
  textTertiary: '#5a5e6f', blue: '#4e8cff', green: '#2ecc71', red: '#e74c3c',
  amber: '#f0a500', purple: '#9b59b6', cyan: '#00c8e8',
};

const fmtNum = (n, dec = 2) => (n != null && !isNaN(n)) ? Number(n).toFixed(dec) : '--';
const fmtPct = (n) => (n != null && !isNaN(n)) ? ((Number(n) > 0 ? '+' : '') + Number(n).toFixed(2) + '%') : '--';
const fmtCur = (n) => (n != null && !isNaN(n)) ? '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--';
const ts = () => new Date().toLocaleTimeString();
const toDeltaSymbol = (s) => (s || '').replace(/USDT$/i, 'USD').toUpperCase();

const TV_SYMBOL_MAP = {
  BTC: 'BITSTAMP:BTCUSD', BTCUSD: 'BITSTAMP:BTCUSD', BTCUSDT: 'BINANCE:BTCUSDT',
  ETH: 'BITSTAMP:ETHUSD', ETHUSD: 'BITSTAMP:ETHUSD', ETHUSDT: 'BINANCE:ETHUSDT',
  SOL: 'BINANCE:SOLUSDT', SOLUSD: 'BINANCE:SOLUSDT', SOLUSDT: 'BINANCE:SOLUSDT',
  XRP: 'BINANCE:XRPUSDT', XRPUSD: 'BINANCE:XRPUSDT', XRPUSDT: 'BINANCE:XRPUSDT',
  XAU: 'OANDA:XAUUSD', XAUT: 'OANDA:XAUUSD', GOLD: 'OANDA:XAUUSD',
  DOGE: 'BINANCE:DOGEUSDT', SHIB: 'BINANCE:SHIBUSDT', PEPE: 'BINANCE:PEPEUSDT',
  WIF: 'BINANCE:WIFUSDT', BONK: 'BINANCE:BONKUSDT', FLOKI: 'BINANCE:FLOKIUSDT',
};
const toTradingViewSymbol = (s) => {
  const sym = (s || '').toUpperCase().replace(/USDT$/i, 'USD');
  if (TV_SYMBOL_MAP[sym]) return TV_SYMBOL_MAP[sym];
  if (TV_SYMBOL_MAP[s]) return TV_SYMBOL_MAP[s];
  const base = sym.replace(/USD$/i, '');
  if (TV_SYMBOL_MAP[base]) return TV_SYMBOL_MAP[base];
  return 'BINANCE:' + base + 'USDT';
};
const TV_INTERVAL = { '1m': '1', '5m': '5', '15m': '15', '30m': '30', '1h': '60', '2h': '120', '4h': '240', '1d': 'D', '1w': 'W' };

/* ============================ OPTION STRATEGIES ============================ */
const OPTION_STRATEGIES = [
  { id: 'long_straddle', name: 'Long Straddle', tag: 'Volatile', color: COLORS.purple,
    desc: 'Buy an at-the-money (ATM) call and an ATM put with the same strike and expiry. You profit from a large move in EITHER direction. Maximum loss is limited to the total premium paid. Best when you expect a big move but are unsure of direction (e.g. before major news).' },
  { id: 'long_strangle', name: 'Long Strangle', tag: 'Volatile', color: COLORS.purple,
    desc: 'Buy an out-of-the-money (OTM) call and an OTM put. Cheaper than a straddle, but the underlying must move further before you break even. Profits from large moves either way with lower upfront cost.' },
  { id: 'short_straddle', name: 'Short Straddle', tag: 'Neutral', color: COLORS.amber,
    desc: 'Sell an ATM call and an ATM put. You collect premium and profit when the underlying stays near the strike. Risk is theoretically unlimited if price makes a large move. Only use when volatility is expected to collapse.' },
  { id: 'short_strangle', name: 'Short Strangle', tag: 'Neutral', color: COLORS.amber,
    desc: 'Sell an OTM call and an OTM put. Collect premium and profit inside a wide range. Reward is limited to premium received; risk is large (but less than a straddle) if the price breaks out.' },
  { id: 'bull_call_spread', name: 'Bull Call Spread', tag: 'Bullish', color: COLORS.green,
    desc: 'Buy a lower-strike call and sell a higher-strike call (same expiry). Defined maximum risk (net debit) and capped reward. A cheaper, safer way to express a moderately bullish view than a naked long call.' },
  { id: 'bear_put_spread', name: 'Bear Put Spread', tag: 'Bearish', color: COLORS.red,
    desc: 'Buy a higher-strike put and sell a lower-strike put (same expiry). Defined-risk bearish strategy with capped reward. Expresses a moderately bearish view at lower cost than a naked long put.' },
  { id: 'long_call', name: 'Long Call', tag: 'Bullish', color: COLORS.green,
    desc: 'Buy a single call option. Unlimited upside if the underlying rises, with loss strictly limited to the premium paid. The classic directional bullish play.' },
  { id: 'long_put', name: 'Long Put', tag: 'Bearish', color: COLORS.red,
    desc: 'Buy a single put option. Profits as the underlying falls, with loss limited to premium. Used for bearish bets or as downside hedging.' },
  { id: 'iron_condor', name: 'Iron Condor', tag: 'Neutral', color: COLORS.cyan,
    desc: 'Sell an OTM strangle and buy a further OTM strangle (call side + put side). Fully defined risk and reward. Profits when the underlying stays inside a range until expiry. Popular income strategy in low-vol markets.' },
  { id: 'butterfly', name: 'Butterfly Spread', tag: 'Neutral', color: COLORS.cyan,
    desc: 'Buy 1 ITM strike, sell 2 ATM strikes, buy 1 OTM strike (same side, same expiry). Low-cost, defined-risk strategy that profits when the underlying finishes near the middle strike at expiry.' },
  { id: 'covered_call', name: 'Covered Call', tag: 'Income', color: COLORS.blue,
    desc: 'Hold the underlying spot and sell an OTM call against it. Generates income from premium; upside is capped at the strike. A conservative yield-boosting strategy in sideways markets.' },
  { id: 'protective_put', name: 'Protective Put', tag: 'Hedge', color: COLORS.blue,
    desc: 'Hold the underlying spot and buy a put. Acts as insurance: the put limits downside while you keep upside participation. Cost is the put premium (like an insurance premium).' },
];

/* ============================ TRADING STRATEGIES ============================ */
const TRADING_STRATEGIES = {
  BTC: [
    { id: 'macd_btc', name: 'MACD Momentum', bt: 'macd', desc: 'Appel MACD momentum: long when MACD crosses above its signal line, exits on reverse cross. Captures BTC trend swings.', params: { fast: 12, slow: 26, signal: 9, starting_cash: 10000 } },
    { id: 'rsi_btc', name: 'RSI Mean Reversion', bt: 'rsi', desc: 'Buys when RSI drops below 30 (oversold) and sells when RSI rises above 70 (overbought). Classic counter-trend on BTC.', params: { period: 14, overbought: 70, oversold: 30, starting_cash: 10000 } },
    { id: 'donchian_btc', name: 'Donchian Breakout', bt: 'donchian', desc: 'Turtle-style breakout: long when BTC breaks the 20-period Donchian high, exit on the 10-period low. ATR-aware trend capture.', params: { entry: 20, exit: 10, starting_cash: 10000 } },
  ],
  ETH: [
    { id: 'macd_eth', name: 'MACD Momentum', bt: 'macd', desc: 'Same MACD momentum logic tuned for ETH volatility. Long on MACD/signal bullish cross, exit on bearish cross.', params: { fast: 12, slow: 26, signal: 9, starting_cash: 10000 } },
    { id: 'bb_eth', name: 'Bollinger Reversion', bt: 'bb_reversion', desc: 'Buys when ETH pokes below the lower Bollinger band, exits on reversion to the middle band. Mean-reversion on range-bound ETH.', params: { period: 20, dev: 2, starting_cash: 10000 } },
    { id: 'keltner_eth', name: 'Keltner Breakout', bt: 'keltner', desc: 'ETH breakout: long when price closes above the Keltner upper channel (EMA±ATR), exit when it returns to the middle. ATR-scaled.', params: { period: 20, mult: 2, atr_period: 14, starting_cash: 10000 } },
  ],
  SOL: [
    { id: 'stoch_sol', name: 'Stochastic Reversion', bt: 'stoch', desc: 'High-beta SOL mean-reversion: buys when the fast stochastic crosses back above oversold, exits on overbought cross.', params: { k: 14, d: 3, overbought: 80, oversold: 20, starting_cash: 10000 } },
    { id: 'scalp_sol', name: 'SOL Scalper', bt: 'scalping_meme', desc: 'Short-term momentum scalping on SOL using fast MA crosses. Multiple small entries/exits per day.', params: { period: 20, starting_cash: 10000 } },
    { id: 'psar_sol', name: 'Parabolic SAR', bt: 'parabolic_sar', desc: 'Wilder Parabolic SAR trailing-stop trend follower. Long while SOL holds above the SAR arc, flips when price closes through it.', params: { step: 0.02, max_step: 0.2, starting_cash: 10000 } },
  ],
  XAU: [
    { id: 'ichimoku_xau', name: 'Ichimoku Cloud', bt: 'ichimoku', desc: 'XAUUSD Ichimoku: long when price is above the cloud and Tenkan crosses above Kijun; exits on reverse cross. Multi-TF trend.', params: { tenkan: 9, kijun: 26, senkou_b: 52, starting_cash: 10000 } },
    { id: 'donchian_xau', name: 'Donchian Breakout', bt: 'donchian', desc: 'Gold turtle-style breakout on Donchian channel expansion. Trades XAU trend legs with ATR-scaled risk.', params: { entry: 20, exit: 10, starting_cash: 10000 } },
    { id: 'rsi2_xau', name: 'RSI-2 Reversion', bt: 'rsi2', desc: 'Connors RSI-2 short-term reversion on gold: buys extreme dips (RSI<10), exits at RSI>50. Mean-reversion on XAU.', params: { period: 2, buy_threshold: 10, sell_threshold: 50, starting_cash: 10000 } },
  ],
  XRP: [
    { id: 'macd_xrp', name: 'MACD Momentum', bt: 'macd', desc: 'XRP MACD momentum on bullish/bearish MACD-signal crosses. Trades XRP trend expansion moves.', params: { fast: 12, slow: 26, signal: 9, starting_cash: 10000 } },
    { id: 'bb_xrp', name: 'Bollinger Reversion', bt: 'bb_reversion', desc: 'XRP counter-trend: buys lower-band pokes, sells on reversion to the middle Bollinger band.', params: { period: 20, dev: 2, starting_cash: 10000 } },
    { id: 'stoch_xrp', name: 'Stochastic Reversion', bt: 'stoch', desc: 'XRP stochastic mean-reversion on overbought/oversold crosses. Range-trades XRP.', params: { k: 14, d: 3, overbought: 80, oversold: 20, starting_cash: 10000 } },
  ],
  MEME: [
    { id: 'scalp_meme', name: 'Scalping Meme Coins', bt: 'scalping_meme', desc: 'Short-term momentum scalping on high-beta meme coins (DOGE, SHIB, PEPE, WIF). Enters long when price crosses above its fast MA; exits on the reverse cross. Designed for 15m–1h charts. High turnover, tight risk.', params: { period: 20, starting_cash: 10000 } },
    { id: 'short_meme', name: 'Shorting Meme Coins (Daily)', bt: 'short_meme', desc: 'Contrarian daily-timeframe short bias on overextended meme coins. Enters short when price crosses below its 20-period MA on the daily; covers on reversal. Fades parabolic pumps. High risk — size small.', params: { period: 20, starting_cash: 10000 } },
    { id: 'rsi2_meme', name: 'RSI-2 Meme Scalp', bt: 'rsi2', desc: 'Connors RSI-2 on meme coins: buys sharp dips (RSI<10) and exits on the RSI>50 bounce. Rapid high-probability scalp on volatile memes.', params: { period: 2, buy_threshold: 10, sell_threshold: 50, starting_cash: 10000 } },
  ],
};

const ASSET_TABS = ['BTC', 'ETH', 'SOL', 'XAU', 'XRP', 'MEME'];

/* ============================ SMALL COMPONENTS ============================ */
function StatusDot({ on, color }) {
  return React.createElement('span', { style: { display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: on ? (color || COLORS.green) : COLORS.red, boxShadow: on ? `0 0 6px ${color || COLORS.green}` : 'none', marginRight: 6 } });
}

function Card({ children, style, pad, className }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  return React.createElement('div', {
    className: className || '',
    style: Object.assign({
      background: E.glass || '#111318',
      border: '1px solid ' + (E.glassBorder || '#22242c'),
      borderRadius: 12,
      padding: pad != null ? pad : 16,
      backdropFilter: 'blur(' + (E.glassBlur || '0px') + ')',
      WebkitBackdropFilter: 'blur(' + (E.glassBlur || '0px') + ')',
    }, style || {})
  }, children);
}

function Section({ title, right, children }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  return React.createElement('div', { style: { marginBottom: 18 } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 } },
      React.createElement('h3', { style: {
        margin: 0, fontSize: 14, fontWeight: 800, letterSpacing: 0.3,
        fontFamily: E.fontDisplay || 'inherit',
        color: COLORS.text
      } }, title),
      right || null
    ),
    children
  );
}

function Tab({ active, onClick, children, small }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  return React.createElement('button', {
    onClick: onClick,
    style: {
      padding: small ? '5px 10px' : '8px 14px',
      borderRadius: 8,
      fontSize: small ? 12 : 13,
      fontFamily: E.fontBody || 'inherit',
      fontWeight: 600,
      cursor: 'pointer',
      whiteSpace: 'nowrap',
      background: active ? (E.lime || COLORS.blue) : 'transparent',
      border: '1px solid ' + (active ? (E.lime || COLORS.blue) : COLORS.border),
      color: active ? '#0a0b0f' : COLORS.textSecondary,
      transition: 'background 0.15s, border-color 0.15s, color 0.15s',
    }
  }, children);
}

function Metric({ label, value, sub, color, tilt }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  return React.createElement('div', {
    'data-tilt': tilt !== false ? '' : undefined,
    className: tilt !== false ? 'tilt-card' : undefined,
    style: {
      background: E.glass || COLORS.bgElevated,
      border: '1px solid ' + (E.glassBorder || COLORS.border),
      borderRadius: 10,
      padding: '12px 14px',
      transition: 'transform 0.1s ease-out, box-shadow 0.15s',
      transformStyle: 'preserve-3d',
    }
  },
    React.createElement('div', { style: { fontSize: 11, fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary, marginBottom: 4 } }, label),
    React.createElement('div', { style: { fontSize: 20, fontFamily: E.fontDisplay || 'inherit', fontWeight: 700, color: color || COLORS.text } }, value),
    sub && React.createElement('div', { style: { fontSize: 11, fontFamily: E.fontMono || 'inherit', color: COLORS.textSecondary, marginTop: 2 } }, sub)
  );
}

/* ============================ LIGHTWEIGHT CHART ============================ */
function PriceChart({ symbol, timeframe, height }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [tf, setTf] = useState(timeframe || '1h');
  useEffect(() => {
    if (loaded || !containerRef.current) return;
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js';
    script.onload = () => {
      const LC = window.LightweightCharts;
      const chart = LC.createChart(containerRef.current, {
        width: containerRef.current.clientWidth, height: height || 380,
        layout: { background: { color: '#0a0b0f' }, textColor: '#e4e6ef' },
        grid: { vertLines: { color: '#22242c' }, horzLines: { color: '#22242c' } },
        crosshair: { mode: LC.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#22242c' },
        timeScale: { borderColor: '#22242c', timeVisible: true, secondsVisible: false },
      });
      const series = chart.addCandlestickSeries({ upColor: '#2ecc71', downColor: '#e74c3c', borderUpColor: '#2ecc71', borderDownColor: '#e74c3c', wickUpColor: '#2ecc71', wickDownColor: '#e74c3c' });
      chartRef.current = { chart, series };
      setLoaded(true);
      const now = Math.floor(Date.now() / 1000);
      const tfSec = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };
      const start = now - (tfSec[tf] || 3600) * 250;
      fetch(`${API}/delta/candles?symbol=${toDeltaSymbol(symbol)}&resolution=${tf}&start=${start}&end=${now}&limit=250`)
        .then(r => r.json()).then(d => { if (d.result) { series.setData(d.result.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close }))); chart.timeScale().fitContent(); } });
    };
    document.head.appendChild(script);
    return () => { if (chartRef.current) chartRef.current.chart.remove(); };
  }, [symbol, tf, height]);
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 8 } },
      ['1m', '5m', '15m', '1h', '4h', '1d'].map(t => React.createElement(Tab, { key: t, small: true, active: tf === t, onClick: () => setTf(t) }, t))
    ),
    React.createElement('div', { ref: containerRef, style: { width: '100%', height: height || 380, background: '#0a0b0f', borderRadius: 8 } },
      !loaded && React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: COLORS.textTertiary } }, 'Loading chart...')
    )
  );
}

/* ============================ TRADINGVIEW ADVANCED CHART ============================ */
function TradingViewWidget({ symbol, timeframe, height }) {
  const containerRef = useRef(null);
  const [tf, setTf] = useState(timeframe || '60');
  const iv = TV_INTERVAL[tf] || '60';
  const [tvSymbol, setTvSymbol] = useState(symbol);

  useEffect(() => {
    const mapped = toTradingViewSymbol(symbol);
    setTvSymbol(mapped);
  }, [symbol]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = '';
    const options = {
      "symbol": tvSymbol,
      "interval": iv,
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "allow_symbol_change": true,
      "autosize": true,
      "support_host": "https://www.tradingview.com"
    };
    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.innerHTML = JSON.stringify(options);
    el.appendChild(script);
    return () => { el.innerHTML = ''; };
  }, [tvSymbol, iv]);

  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column' } },
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 8, alignItems: 'center' } },
      ['1m', '5m', '15m', '1h', '4h', '1d'].map(t => React.createElement(Tab, { key: t, small: true, active: tf === t, onClick: () => setTf(t) }, t)),
      React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary, marginLeft: 'auto' } }, tvSymbol)
    ),
    React.createElement('div', { ref: containerRef, style: { width: '100%', height: height || 400, borderRadius: 8, overflow: 'hidden' } })
  );
}

/* ============================ PAYOFF GRAPH ============================ */
function PayoffGraph({ strategy, spot }) {
  const W = 320, H = 160, mid = H / 2;
  const range = spot * 0.4;
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const p = spot - range + (2 * range) * (i / 40);
    let pl = 0;
    switch (strategy.id) {
      case 'long_straddle': case 'long_strangle': case 'long_call': case 'long_put':
        pl = (strategy.id === 'long_put') ? (spot - p) : (p - spot); pl = (strategy.id.indexOf('strangle') >= 0 || strategy.id.indexOf('straddle') >= 0) ? Math.abs(p - spot) - spot * 0.02 : pl - spot * 0.02; break;
      case 'short_straddle': case 'short_strangle': case 'short_call': case 'short_put':
        pl = (strategy.id.indexOf('strangle') >= 0 || strategy.id.indexOf('straddle') >= 0) ? (spot * 0.02 - Math.abs(p - spot)) : ((strategy.id.indexOf('put') >= 0) ? (p - spot) : (spot - p)) + spot * 0.02; break;
      case 'bull_call_spread': pl = Math.min(Math.max(p - spot, 0), spot * 0.1) - spot * 0.03; break;
      case 'bear_put_spread': pl = Math.min(Math.max(spot - p, 0), spot * 0.1) - spot * 0.03; break;
      case 'iron_condor': case 'butterfly': pl = spot * 0.03 - Math.abs(p - spot) * 0.5; break;
      case 'covered_call': pl = (p - spot) + spot * 0.02; break;
      case 'protective_put': pl = (p - spot) - spot * 0.02; break;
      default: pl = p - spot;
    }
    const x = (W * i) / 40;
    const y = mid - (pl / (spot * 0.25)) * (H / 2 - 12);
    pts.push(`${x.toFixed(1)},${Math.max(6, Math.min(H - 6, y)).toFixed(1)}`);
  }
  const line = pts.join(' ');
  return React.createElement('div', null,
    React.createElement('svg', { width: '100%', viewBox: `0 0 ${W} ${H}`, style: { background: COLORS.bgElevated, borderRadius: 8 } },
      React.createElement('line', { x1: 0, y1: mid, x2: W, y2: mid, stroke: COLORS.border, 'strokeWidth': 1 }),
      React.createElement('line', { x1: W / 2, y1: 0, x2: W / 2, y2: H, stroke: COLORS.border, 'strokeDasharray': '3,3' }),
      React.createElement('polyline', { points: line, fill: 'none', stroke: strategy.color || COLORS.blue, 'strokeWidth': 2 })
    ),
    React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, textAlign: 'center', marginTop: 4 } }, `Spot ${fmtCur(spot)}  •  illustrative P/L`)
  );
}

/* ============================ OPTION STRATEGY CARD ============================ */
function OptionStrategyCard({ strategy, spot, running, onToggle, onExplain, onSelect }) {
  return React.createElement(Card, { style: { marginBottom: 10, cursor: 'pointer' }, pad: 12 },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: (strategy.color || COLORS.blue) + '22', color: strategy.color || COLORS.blue } }, strategy.tag),
        React.createElement('span', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text } }, strategy.name)
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
        React.createElement('button', { onClick: (e) => { e.stopPropagation(); onExplain(strategy); }, style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Explain'),
        React.createElement('button', { onClick: (e) => { e.stopPropagation(); onToggle(strategy); }, style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: running ? COLORS.green : 'transparent', border: `1px solid ${running ? COLORS.green : COLORS.border}`, color: running ? '#06281a' : COLORS.textSecondary, cursor: 'pointer', fontWeight: 600 } }, running ? 'ON' : 'OFF')
      )
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6, lineHeight: 1.4 } }, strategy.desc.slice(0, 90) + '…'),
    React.createElement('div', { style: { marginTop: 8 } }, React.createElement(PayoffGraph, { strategy, spot }))
  );
}

/* ============================ TRADING STRATEGY CARD ============================ */
function TradingStrategyCard({ strategy, running, onToggle, onExplain, onBacktest }) {
  return React.createElement(Card, { style: { marginBottom: 10 }, pad: 14 },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
      React.createElement('span', { style: { fontSize: 14, fontWeight: 700, color: COLORS.text } }, strategy.name),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
        React.createElement('button', { onClick: () => onExplain(strategy), style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Explain'),
        React.createElement('button', { onClick: () => onBacktest(strategy), style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Backtest'),
        React.createElement('button', { onClick: () => onToggle(strategy), style: { fontSize: 11, padding: '4px 10px', borderRadius: 6, background: running ? COLORS.green : 'transparent', border: `1px solid ${running ? COLORS.green : COLORS.border}`, color: running ? '#06281a' : COLORS.textSecondary, cursor: 'pointer', fontWeight: 700 } }, running ? 'RUNNING' : 'START')
      )
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6, lineHeight: 1.45 } }, strategy.desc)
  );
}

/* ============================ BACKTEST PANEL ============================ */
function BacktestPanel({ strategy, onClose }) {
  const [asset, setAsset] = useState('BTC');
  const [tf, setTf] = useState('1h');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [params, setParams] = useState(strategy ? strategy.params : {});
  const run = async () => {
    setRunning(true); setResult(null);
    try {
      const r = await fetch(`${API}/backtest/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strategy: strategy.bt, asset, timeframe: tf, limit: 500, params }) });
      const d = await r.json();
      setResult(d.result || d);
    } catch (e) { setResult({ error: String(e) }); }
    setRunning(false);
  };
  const paramDefs = Object.keys(params);
  return React.createElement(Card, { pad: 16, style: { marginBottom: 16 } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 } },
      React.createElement('h3', { style: { margin: 0, fontSize: 15, color: COLORS.text } }, `Backtest: ${strategy.name}`),
      React.createElement('button', { onClick: onClose, style: { fontSize: 12, padding: '4px 10px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Close')
    ),
    React.createElement('div', { style: { display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Asset'),
        React.createElement('div', { style: { display: 'flex', gap: 4 } }, ASSET_TABS.filter(a => a !== 'MEME').map(a => React.createElement(Tab, { key: a, small: true, active: asset === a, onClick: () => setAsset(a) }, a)))
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Timeframe'),
        React.createElement('div', { style: { display: 'flex', gap: 4 } }, ['15m', '1h', '4h', '1d'].map(t => React.createElement(Tab, { key: t, small: true, active: tf === t, onClick: () => setTf(t) }, t)))
      )
    ),
    React.createElement('div', { style: { marginBottom: 12 } },
      React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Parameters'),
      React.createElement('div', { style: { display: 'flex', gap: 12, flexWrap: 'wrap' } },
        paramDefs.map(k => React.createElement('label', { key: k, style: { fontSize: 11, color: COLORS.textSecondary, display: 'flex', flexDirection: 'column', gap: 2 } },
          k,
          React.createElement('input', { type: 'number', value: params[k], onChange: (e) => setParams(Object.assign({}, params, { [k]: parseFloat(e.target.value) || 0 })), style: { width: 90, padding: '4px 8px', borderRadius: 6, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } })
        ))
      )
    ),
    React.createElement('button', { onClick: run, disabled: running, style: { padding: '8px 18px', borderRadius: 8, background: COLORS.blue, border: 'none', color: '#fff', fontWeight: 700, fontSize: 13, cursor: running ? 'wait' : 'pointer' } }, running ? 'Running…' : 'Run Backtest'),
    result && React.createElement('div', { style: { marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 } },
      React.createElement(Metric, { label: 'Total Return', value: fmtPct(result.total_return_pct), color: (result.total_return_pct || 0) >= 0 ? COLORS.green : COLORS.red }),
      React.createElement(Metric, { label: 'Max Drawdown', value: fmtPct(-(result.max_drawdown_pct || 0)), color: COLORS.red }),
      React.createElement(Metric, { label: 'Trades', value: result.trades || 0 }),
      React.createElement(Metric, { label: 'Win Rate', value: fmtPct(result.win_rate).replace('%', '') + '%' }),
      React.createElement(Metric, { label: 'Final Equity', value: fmtCur(result.final_equity) }),
      React.createElement(Metric, { label: 'Sharpe', value: fmtNum(result.sharpe) })
    )
  );
}

/* ============================ OPTIONS VIEW ============================ */
function OptionsView() {
  const [underlying, setUnderlying] = useState('BTC');
  const [options, setOptions] = useState([]);
  const [spot, setSpot] = useState(0);
  const [running, setRunning] = useState({});
  const [explain, setExplain] = useState(null);
  const [positions, setPositions] = useState(null);
  const [selStrategy, setSelStrategy] = useState(OPTION_STRATEGIES[0]);
  useEffect(() => {
    fetch(`${API}/delta/options?underlying=${underlying}`).then(r => r.json()).then(d => { setOptions(d.options || []); if ((d.options || []).length) setSpot(d.options[0].spot); });
    fetch(`${API}/delta/positions`).then(r => r.json()).then(d => setPositions(d.positions || []));
  }, [underlying]);
  const toggle = (s) => setRunning(Object.assign({}, running, { [s.id]: !running[s.id] }));
  return React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 340px', gap: 18, alignItems: 'start' } },
    React.createElement('div', null,
      React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' } },
        React.createElement('span', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Underlying:'),
        ['BTC', 'ETH', 'XAU'].map(u => React.createElement(Tab, { key: u, active: underlying === u, onClick: () => setUnderlying(u) }, u + ' Options'))
      ),
      React.createElement(Section, { title: `Option Strategies — ${underlying} (${options.length} contracts)` },
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 } },
          OPTION_STRATEGIES.map(s => React.createElement(OptionStrategyCard, { key: s.id, strategy: s, spot, running: !!running[s.id], onToggle: toggle, onExplain: setExplain, onSelect: setSelStrategy }))
        )
      )
    ),
    React.createElement('div', null,
      React.createElement(Section, { title: 'Selected Strategy' },
        React.createElement(Card, { pad: 14 },
          React.createElement('div', { style: { fontSize: 13, fontWeight: 700, color: selStrategy.color || COLORS.blue, marginBottom: 6 } }, selStrategy.name),
          React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.5 } }, selStrategy.desc),
          React.createElement('div', { style: { marginTop: 10 } }, React.createElement(PayoffGraph, { strategy: selStrategy, spot }))
        )
      ),
      React.createElement(Section, { title: 'Your Positions' },
        positions && positions.length
          ? React.createElement('div', null, positions.map(p => React.createElement(Card, { key: p.symbol || Math.random(), pad: 10, style: { marginBottom: 8 } },
            React.createElement('div', { style: { fontSize: 12, color: COLORS.text } }, (p.symbol || 'Position')),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, `Size: ${fmtNum(p.size)}  PnL: ${fmtCur(p.unrealized_pnl)}`)
          )))
          : React.createElement(Card, { pad: 12 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No open option positions.'))
      )
    ),
    explain && React.createElement(Modal, { title: explain.name, onClose: () => setExplain(null) },
      React.createElement('div', { style: { fontSize: 13, color: COLORS.textSecondary, lineHeight: 1.6 } }, explain.desc)
    )
  );
}

/* ============================ STRATEGIES VIEW ============================ */
function StrategiesView() {
  const [asset, setAsset] = useState('BTC');
  const [running, setRunning] = useState({});
  const [explain, setExplain] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const list = TRADING_STRATEGIES[asset] || [];
  const toggle = (s) => setRunning(Object.assign({}, running, { [s.id]: !running[s.id] }));
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' } },
      ASSET_TABS.map(a => React.createElement(Tab, { key: a, active: asset === a, onClick: () => setAsset(a) }, a + (a === 'MEME' ? ' Coins' : ' Strategies')))
    ),
    backtest
      ? React.createElement(BacktestPanel, { strategy: backtest, onClose: () => setBacktest(null) })
      : React.createElement(Section, { title: `${asset} Trading Strategies` },
        list.map(s => React.createElement(TradingStrategyCard, { key: s.id, strategy: s, running: !!running[s.id], onToggle: toggle, onExplain: setExplain, onBacktest: setBacktest }))
      ),
    explain && React.createElement(Modal, { title: explain.name, onClose: () => setExplain(null) },
      React.createElement('div', { style: { fontSize: 13, color: COLORS.textSecondary, lineHeight: 1.6 } }, explain.desc)
    )
  );
}

/* ============================ MODAL ============================ */
function Modal({ title, onClose, children }) {
  return React.createElement('div', { style: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 } },
    React.createElement('div', { style: { background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`, borderRadius: 12, width: '90%', maxWidth: 520, padding: 20, maxHeight: '85%', overflow: 'auto' } },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 } },
        React.createElement('h3', { style: { margin: 0, fontSize: 16, color: COLORS.text } }, title),
        React.createElement('button', { onClick: onClose, style: { fontSize: 12, padding: '4px 10px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Close')
      ),
      children
    )
  );
}

/* ============================ ANALYTICS VIEW ============================ */
function AnalyticsView() {
  return React.createElement('div', null,
    React.createElement(Section, { title: 'Market Heatmap — Crypto Bubbles' },
      React.createElement('iframe', {
        src: 'https://cryptobubbles.net/', title: 'Crypto Bubbles',
        style: { width: '100%', height: '80vh', border: `1px solid ${COLORS.border}`, borderRadius: 12, background: '#000' },
        sandbox: 'allow-scripts allow-same-origin allow-forms'
      })
    )
  );
}

/* ============================ DASHBOARD VIEW ============================ */
function DashboardView({ gainers, losers, health, search, setSearch, chartSymbol, setChartSymbol, onModeToggle, modeBusy }) {
  const E = window.Theme && window.Theme.EXTRA || {};
  const [chartSource, setChartSource] = useState('delta');
  const [chartTf, setChartTf] = useState('1h');
  const topGainer = gainers && gainers.length ? gainers[0] : null;
  const topLoser = losers && losers.length ? losers.slice().sort((a, b) => (a.change_24h || 0) - (b.change_24h || 0))[0] : null;
  const connected = health && health.connected;
  const trading = health && health.mode === 'trading';
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 18 } },
      topGainer && React.createElement(Card, { pad: 14, style: { borderColor: COLORS.green } },
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Top Gainer 24h'),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.green, marginTop: 4 } }, topGainer.symbol),
        React.createElement('div', { style: { fontSize: 14, color: COLORS.green } }, fmtPct(topGainer.change_24h)),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, `Vol ${fmtCur(topGainer.volume_24h)}`)
      ),
      topLoser && React.createElement(Card, { pad: 14, style: { borderColor: COLORS.red } },
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Top Loser 24h'),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.red, marginTop: 4 } }, topLoser.symbol),
        React.createElement('div', { style: { fontSize: 14, color: COLORS.red } }, fmtPct(topLoser.change_24h)),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, `Vol ${fmtCur(topLoser.volume_24h)}`)
      ),
      React.createElement(Card, { pad: 14, style: { display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderColor: connected ? (trading ? COLORS.green : COLORS.amber) : COLORS.red } },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
          React.createElement('span', { style: { fontSize: 11, fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary } }, 'TRADING CONNECTED'),
          React.createElement('span', { style: {
            width: 34, height: 19, borderRadius: 11, cursor: modeBusy ? 'wait' : 'pointer',
            background: trading ? COLORS.green : COLORS.bgElevated,
            border: '1px solid ' + (trading ? COLORS.green : COLORS.border),
            position: 'relative', transition: 'background 0.2s',
            opacity: modeBusy ? 0.6 : 1,
          }, onClick: () => { if (!modeBusy && onModeToggle) onModeToggle(trading ? 'read_only' : 'trading'); } },
            React.createElement('span', { style: {
              position: 'absolute', top: 2, width: 13, height: 13, borderRadius: '50%',
              left: trading ? 17 : 2, background: trading ? '#0a0b0f' : COLORS.textSecondary,
              transition: 'left 0.2s',
            } })
          )
        ),
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 } },
          React.createElement('span', { style: { width: 8, height: 8, borderRadius: '50%', background: connected ? COLORS.green : COLORS.red, boxShadow: connected ? '0 0 8px ' + COLORS.green : 'none' } }),
          React.createElement('span', { style: { fontSize: 18, fontFamily: E.fontDisplay || 'inherit', fontWeight: 700, color: connected ? COLORS.green : COLORS.red } }, connected ? 'Connected' : 'Offline'),
          React.createElement('span', { style: { marginLeft: 'auto', fontSize: 10, fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary } }, (health && health.environment || 'production'))
        ),
        React.createElement('div', { style: { marginTop: 4, fontSize: 11, fontFamily: E.fontMono || 'inherit', color: trading ? COLORS.green : COLORS.amber, fontWeight: 700 } }, trading ? '▲ TRADING MODE' : '● READ ONLY'),
        (!health.has_auth && (React.createElement('div', { style: { marginTop: 4, fontSize: 10, color: COLORS.red, fontFamily: E.fontMono || 'inherit' } }, 'No API keys — trading disabled' )))
      )
    ),
    React.createElement(Section, { title: 'Trending Perpetuals', right: React.createElement('span', { style: { fontSize: 11, fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary } }, 'sorted by 24h change') },
      React.createElement(TrendingPairs, { limit: 12 })
    ),
    React.createElement(Section, { title: 'Asset Chart', right: React.createElement('div', { style: { display: 'flex', gap: 4 } },
        React.createElement(Tab, { small: true, active: chartSource === 'delta', onClick: () => setChartSource('delta') }, 'Delta'),
        React.createElement(Tab, { small: true, active: chartSource === 'tradingview', onClick: () => setChartSource('tradingview') }, 'TradingView')
      ) },
      React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' } },
        React.createElement('input', {
          value: search, placeholder: 'Search any asset (e.g. BTC, ETH, SOL, XAU, DOGE)…',
          onChange: (e) => setSearch(e.target.value),
          onKeyDown: (e) => { if (e.key === 'Enter' && search.trim()) setChartSymbol(search.trim().toUpperCase()); },
          style: { flex: 1, padding: '8px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13 }
        }),
        React.createElement('button', { onClick: () => search.trim() && setChartSymbol(search.trim().toUpperCase()), style: { padding: '8px 16px', borderRadius: 8, background: COLORS.blue, border: 'none', color: '#fff', fontWeight: 600, cursor: 'pointer' } }, 'Load')
      ),
      React.createElement(Card, { pad: 12 },
        React.createElement('div', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
          React.createElement('span', null, chartSource === 'tradingview' ? toTradingViewSymbol(chartSymbol) : chartSymbol + 'USDT'),
          React.createElement('span', { style: { fontSize: 10, fontWeight: 400, color: COLORS.textTertiary } }, chartSource === 'tradingview' ? 'powered by TradingView' : 'live data via Delta')
        ),
        chartSource === 'tradingview'
          ? React.createElement(TradingViewWidget, { symbol: chartSymbol, timeframe: chartTf, height: 430 })
          : React.createElement(PriceChart, { symbol: chartSymbol, timeframe: chartTf, height: 430 })
      )
    )
  );
}

/* ============================ TRENDING PERPETUALS ============================ */
function TrendingPairs({ limit }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const load = async () => {
    try {
      const r = await fetch(`${API}/delta/tickers`);
      if (!r.ok) throw new Error('tickers ' + r.status);
      const d = await r.json();
      const perps = (d.tickers || []).filter(t => t && t.contract_type === 'perpetual_futures' && t.symbol && !/^[CP]-/.test(t.symbol));
      const sorted = perps
        .map(t => ({
          symbol: t.symbol,
          price: Number(t.mark_price || t.close || 0),
          chg: Number(t.mark_change_24h != null ? t.mark_change_24h : t.ltp_change_24h || 0),
          vol: Number(t.turnover_usd || 0),
        }))
        .filter(x => x.chg !== 0 || true)
        .sort((a, b) => b.chg - a.chg)
        .slice(0, limit || 12);
      setRows(sorted);
      setErr(null);
    } catch (e) { setErr(String(e.message || e)); }
  };
  useEffect(() => { load(); const iv = setInterval(load, 30000); return () => clearInterval(iv); }, [limit]);
  return React.createElement(Card, { pad: 14 },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
      React.createElement('div', { style: { fontSize: 11, fontFamily: E.fontMono || 'inherit', fontWeight: 700, color: COLORS.text, letterSpacing: 0.4 } }, 'TRENDING PERPETUAL PAIRS'),
      React.createElement('span', { style: { fontSize: 10, fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary } }, '24h')
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 340, overflowY: 'auto' } },
      !rows && !err && ['…', '…', '…', '…'].map((_, i) => React.createElement('div', { key: i, style: { height: 14, background: COLORS.bgElevated, borderRadius: 4 } })),
      err && React.createElement('div', { style: { fontSize: 11, color: COLORS.red, fontFamily: E.fontMono || 'inherit' } }, 'tickers unavailable — ' + err),
      (rows || []).map((x, i) => {
        const up = x.chg >= 0;
        const c = up ? COLORS.green : COLORS.red;
        return React.createElement('div', { key: x.symbol + i, style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 } },
          React.createElement('span', { style: { width: 18, textAlign: 'right', fontFamily: E.fontMono || 'inherit', fontSize: 10, color: COLORS.textTertiary } }, i + 1),
          React.createElement('span', { style: { flex: 1, fontWeight: 700, color: COLORS.text, fontFamily: E.fontDisplay || 'inherit' } }, x.symbol.replace(/USD$/, '')),
          React.createElement('span', { style: { fontFamily: E.fontMono || 'inherit', color: COLORS.textSecondary } }, '$' + Number(x.price).toLocaleString(undefined, { maximumFractionDigits: 4 })),
          React.createElement('span', { style: { fontFamily: E.fontMono || 'inherit', fontWeight: 700, color: c, width: 70, textAlign: 'right' } }, fmtPct(x.chg)),
          React.createElement('span', { style: { fontFamily: E.fontMono || 'inherit', color: COLORS.textTertiary, width: 84, textAlign: 'right', fontSize: 10 } }, 'V ' + (x.vol >= 1e9 ? (x.vol / 1e9).toFixed(1) + 'B' : x.vol >= 1e6 ? (x.vol / 1e6).toFixed(1) + 'M' : (x.vol / 1e3).toFixed(0) + 'K'))
        );
      })
    )
  );
}

/* ============================ ECONOMIC CALENDAR ============================ */
function AssetTags({ assets }) {
  if (!assets || !assets.length) return null;
  const color = { BTC: '#f7931a', ETH: '#627eea', SOL: '#9945ff', XRP: '#00aae4', XAU: '#f0a500', DOGE: '#c2a633' };
  return React.createElement('div', { style: { display: 'flex', gap: 4, flexWrap: 'wrap' } },
    assets.map(a => React.createElement('span', { key: a, style: { fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: (color[a] || COLORS.blue) + '22', color: color[a] || COLORS.blue, border: `1px solid ${(color[a] || COLORS.blue)}44` } }, a))
  );
}

function timeUntil(min) {
  if (min < 0) return 'released';
  const h = Math.floor(min / 60), m = min % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  if (h >= 1) return `${h}h ${m}m`;
  return `${m}m`;
}

function CalendarView() {
  const [data, setData] = useState(null);
  const [includeMedium, setIncludeMedium] = useState(false);
  const [filterAsset, setFilterAsset] = useState('ALL');
  const [alerts, setAlerts] = useState([]);
  const load = async () => {
    try {
      const r = await fetch(`${API}/calendar/events?include_medium=${includeMedium}`);
      const d = await r.json();
      setData(d);
      if (d.next_event) {
        const label = `${d.next_event.title} (${d.next_event.currency}) at ${new Date(d.next_event.timestamp * 1000).toLocaleString()}`;
        setAlerts(prev => prev[0] !== label ? [label].concat(prev).slice(0, 20) : prev);
      }
    } catch (e) {}
  };
  useEffect(() => { load(); const iv = setInterval(load, 3600000); return () => clearInterval(iv); }, [includeMedium]);
  const allAssets = React.useMemo(() => {
    const s = new Set(); (data ? data.upcoming : []).forEach(u => (u.assets || []).forEach(a => s.add(a)));
    return ['ALL'].concat(Array.from(s));
  }, [data]);
  const focus = (data ? data.next_event : null);
  const ups = (data ? data.upcoming : []).filter(u => filterAsset === 'ALL' || (u.assets || []).includes(filterAsset));
  return React.createElement('div', null,
    React.createElement(Section, { title: 'High-Impact Economic Calendar', right: React.createElement('div', { style: { display: 'flex', gap: 8, alignItems: 'center' } },
        React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Auto-updates every 24h from Forex Factory'),
        React.createElement(Tab, { small: true, active: includeMedium, onClick: () => setIncludeMedium(!includeMedium) }, 'Include Medium')
      ) },
      focus && React.createElement(Card, { pad: 16, style: { borderColor: COLORS.red, marginBottom: 14, background: 'linear-gradient(135deg,#1a0d0d,#111318)' } },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 } },
          React.createElement('span', { style: { fontSize: 11, fontWeight: 800, padding: '3px 9px', borderRadius: 5, background: COLORS.red, color: '#fff' } }, 'NEXT HIGH-IMPACT'),
          React.createElement('span', { style: { fontSize: 16, fontWeight: 800, color: COLORS.text } }, `${focus.title} · ${focus.currency}`),
          React.createElement('span', { style: { fontSize: 14, fontWeight: 700, color: COLORS.amber, marginLeft: 'auto' } }, focus.time_until_min >= 0 ? `in ${timeUntil(focus.time_until_min)}` : 'now')
        ),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, marginBottom: 8 } },
          `${new Date(focus.timestamp * 1000).toLocaleString()}  ·  Forecast ${focus.forecast || '—'}  ·  Previous ${focus.previous || '—'}`
        ),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginBottom: 8 } }, focus.note),
        React.createElement(AssetTags, { assets: focus.assets })
      ),
      React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' } },
        allAssets.map(a => React.createElement(Tab, { key: a, small: true, active: filterAsset === a, onClick: () => setFilterAsset(a) }, a))
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
        ups.length === 0 && React.createElement(Card, { pad: 14 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No upcoming high-impact events in the next 72h.')),
        ups.map((u, i) => React.createElement(Card, { key: i, pad: 12 },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4, background: u.impact === 'High' ? COLORS.red : COLORS.amber, color: '#fff' } }, u.impact),
            React.createElement('div', { style: { flex: 1 } },
              React.createElement('div', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text } }, `${u.title} · ${u.currency}`),
              React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, `${new Date(u.timestamp * 1000).toLocaleString()}  ·  Forecast ${u.forecast || '—'} · Previous ${u.previous || '—'}`)
            ),
            React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: u.time_until_min <= 360 ? COLORS.red : COLORS.textSecondary, whiteSpace: 'nowrap' } }, timeUntil(u.time_until_min))
          ),
          React.createElement('div', { style: { marginTop: 6 } }, React.createElement(AssetTags, { assets: u.assets }))
        ))
      )
    ),
    alerts.length > 1 && React.createElement(Section, { title: 'Recent Alerts' },
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
        alerts.slice(1).map((a, i) => React.createElement(Card, { key: i, pad: 10 }, React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, '⚠ ' + a)))
      )
    )
  );
}

/* ============================ STRATEGY LIBRARY ============================ */
const CLASS_LABEL = { trend: 'Trend', mean_reversion: 'Mean Reversion', momentum: 'Momentum', breakout: 'Breakout' };
const CLASS_COLOR = { trend: COLORS.blue, mean_reversion: COLORS.green, momentum: COLORS.amber, breakout: COLORS.purple };
const RISK_COLOR = { Low: COLORS.green, Medium: COLORS.amber, High: COLORS.red };

function LibraryView() {
  const [data, setData] = useState(null);
  const [classFilter, setClassFilter] = useState('ALL');
  const [assetFilter, setAssetFilter] = useState('ALL');
  const [expanded, setExpanded] = useState(null);
  const [desc, setDesc] = useState('');
  const [generating, setGenerating] = useState(false);
  const [spec, setSpec] = useState(null);
  const [specError, setSpecError] = useState(null);
  const [btResult, setBtResult] = useState(null);
  const [btRunning, setBtRunning] = useState(false);
  useEffect(() => {
    fetch(`${API}/strategies/library`).then(r => r.json()).then(d => setData(d)).catch(() => {});
  }, []);
  const generate = async () => {
    if (!desc.trim()) return;
    setGenerating(true); setSpec(null); setBtResult(null); setSpecError(null);
    try {
      const r = await fetch(`${API}/strategies/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ description: desc }) });
      const d = await r.json();
      if (!r.ok) setSpecError(d.error || 'Could not parse the description');
      else setSpec(d);
    } catch (e) { setSpecError(String(e)); }
    setGenerating(false);
  };
  const runBacktest = async () => {
    if (!spec) return;
    setBtRunning(true); setBtResult(null);
    try {
      const r = await fetch(`${API}/backtest/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(spec.backtest_request) });
      const d = await r.json();
      setBtResult(d.result || d);
    } catch (e) { setBtResult({ error: String(e) }); }
    setBtRunning(false);
  };
  if (!data) return React.createElement(Card, { pad: 16 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'Loading strategy library…'));
  let list = data.strategies;
  if (classFilter !== 'ALL') list = list.filter(s => s.class === classFilter);
  if (assetFilter !== 'ALL') list = list.filter(s => (s.assets || []).includes(assetFilter));
  return React.createElement('div', null,
    React.createElement(Section, { title: `Strategy Library — ${data.count} strategies onboarded`, right: React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'sourced from the quantitative trading literature + in-house') },
      React.createElement('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 } },
        React.createElement(Tab, { small: true, active: classFilter === 'ALL', onClick: () => setClassFilter('ALL') }, 'All'),
        data.classes.map(c => React.createElement(Tab, { key: c, small: true, active: classFilter === c, onClick: () => setClassFilter(c) }, CLASS_LABEL[c] || c)),
        React.createElement('span', { style: { width: 12 } }),
        ['ALL'].concat(data.assets).map(a => React.createElement(Tab, { key: a, small: true, active: assetFilter === a, onClick: () => setAssetFilter(a) }, a))
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
        list.map(s => React.createElement('div', { key: s.id, style: { background: COLORS.bgSurface, border: `1px solid ${expanded === s.id ? (CLASS_COLOR[s.class] || COLORS.blue) : COLORS.border}`, borderRadius: 12, padding: 14 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }, onClick: () => setExpanded(expanded === s.id ? null : s.id) },
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 5, background: (CLASS_COLOR[s.class] || COLORS.blue) + '22', color: CLASS_COLOR[s.class] || COLORS.blue, border: `1px solid ${(CLASS_COLOR[s.class] || COLORS.blue)}44` } }, CLASS_LABEL[s.class] || s.class),
            React.createElement('span', { style: { flex: 1, fontSize: 14, fontWeight: 700, color: COLORS.text } }, s.name),
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, color: RISK_COLOR[s.risk] || COLORS.amber, border: `1px solid ${(RISK_COLOR[s.risk] || COLORS.amber)}66`, padding: '2px 7px', borderRadius: 5 } }, s.risk + ' risk'),
            React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, expanded === s.id ? '▲' : '▼')
          ),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6 } }, s.id + (s.source ? ' · ' + s.source : '')),
          expanded === s.id && React.createElement('div', { style: { marginTop: 10, fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.55 } },
            React.createElement('div', { style: { marginBottom: 8 } }, s.description),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Assets: ' + (s.assets || []).join(', ') + '  ·  Params: ' + Object.keys(s.params || {}).join(', ')),
            React.createElement('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } }, (s.assets || []).map(a => React.createElement(Tab, { key: a, small: true, active: false, onClick: () => {} }, a)))
          )
        ))
      )
    ),
    React.createElement(Section, { title: 'Describe a Strategy in Plain English', right: React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'the engine converts it into a full parameter spec you can backtest') },
      React.createElement(Card, { pad: 16 },
        React.createElement('textarea', {
          value: desc, placeholder: 'e.g. "Buy BTC when RSI 2 drops below 10 and sell at 50, on the 1h chart with 5000 capital"  or  "Turtle breakout on SOL, enter on 20 period high, exit at 10 low"',
          onChange: (e) => setDesc(e.target.value),
          onKeyDown: (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) generate(); },
          rows: 3, style: { width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13, resize: 'vertical', fontFamily: 'inherit' }
        }),
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 } },
          React.createElement('button', { onClick: generate, disabled: generating || !desc.trim(), style: { padding: '8px 18px', borderRadius: 8, background: COLORS.blue, border: 'none', color: '#fff', fontWeight: 700, fontSize: 13, cursor: (generating || !desc.trim()) ? 'wait' : 'pointer' } }, generating ? 'Generating…' : 'Generate Strategy Spec'),
          React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Ctrl/⌘ + Enter to generate')
        )
      ),
      specError && React.createElement(Card, { pad: 14, style: { borderColor: COLORS.red, marginTop: 10 } }, React.createElement('div', { style: { fontSize: 12, color: COLORS.red } }, '⚠ ' + specError)),
      spec && React.createElement('div', { style: { marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 } },
        React.createElement(Card, { pad: 14, style: { borderColor: (CLASS_COLOR[spec.class] || COLORS.blue) } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' } },
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 5, background: (CLASS_COLOR[spec.class] || COLORS.blue) + '22', color: CLASS_COLOR[spec.class] || COLORS.blue, border: `1px solid ${(CLASS_COLOR[spec.class] || COLORS.blue)}44` } }, CLASS_LABEL[spec.class] || spec.class),
            React.createElement('span', { style: { fontSize: 15, fontWeight: 800, color: COLORS.text } }, spec.name),
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, color: RISK_COLOR[spec.risk] || COLORS.amber, border: `1px solid ${(RISK_COLOR[spec.risk] || COLORS.amber)}66`, padding: '2px 7px', borderRadius: 5 } }, spec.risk + ' risk'),
            React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'matched "' + spec.strategy_id + '" · source: ' + spec.source),
            React.createElement('span', { style: { marginLeft: 'auto', fontSize: 11, color: spec.matched ? COLORS.green : COLORS.amber, fontWeight: 700 } }, spec.matched === false ? 'loose match — defaults applied' : 'matched')
          ),
          React.createElement('div', { style: { marginTop: 8, fontSize: 11, color: COLORS.textTertiary } }, 'Recommended: ' + spec.asset + ' · ' + spec.timeframe),
          React.createElement('div', { style: { marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' } },
            (spec.notes || []).map((n, i) => React.createElement('span', { key: i, style: { fontSize: 10, padding: '2px 7px', borderRadius: 5, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary } }, n))
          )
        ),
        React.createElement(Card, { pad: 16, style: { borderColor: COLORS.blue } },
          React.createElement('div', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text, marginBottom: 10 } }, 'Parameter Specification (engine-ready)'),
          React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
            spec.param_specs.map(p => React.createElement('div', { key: p.name, style: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, background: p.changed ? (COLORS.blue + '14') : COLORS.bgElevated, border: `1px solid ${p.changed ? (COLORS.blue + '66') : COLORS.border}` } },
              React.createElement('code', { style: { fontSize: 12, fontWeight: 700, color: p.changed ? COLORS.blue : COLORS.text, minWidth: 120 } }, p.name),
              React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary, width: 40 } }, p.type),
              React.createElement('div', { style: { flex: 1, fontSize: 11, color: COLORS.textSecondary, lineHeight: 1.35 } }, p.description),
              React.createElement('div', { style: { textAlign: 'right', fontSize: 11 } },
                React.createElement('div', { style: { color: COLORS.textTertiary } }, p.changed ? 'default ' + String(p.default) : 'default ' + String(p.default)),
                React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 10 } }, 'range [' + p.min + ',' + p.max + ']'),
                React.createElement('div', { style: { color: COLORS.blue, fontWeight: 800, fontSize: 13 } }, '→ ' + String(p.value))
              )
            ))
          )
        ),
        React.createElement(Card, { pad: 16 },
          React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
            React.createElement('div', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text } }, 'Backtest Engine Request'),
            React.createElement('button', { onClick: runBacktest, disabled: btRunning, style: { padding: '7px 14px', borderRadius: 8, background: COLORS.green, border: 'none', color: '#06281a', fontWeight: 700, fontSize: 12, cursor: btRunning ? 'wait' : 'pointer' } }, btRunning ? 'Running…' : '▶ Run in Backtest Engine')
          ),
          React.createElement('pre', { style: { background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12, fontSize: 11, color: COLORS.textSecondary, overflow: 'auto', margin: 0 } }, 'POST /backtest/run\n' + JSON.stringify(spec.backtest_request, null, 2)),
          btResult && !btResult.error && React.createElement('div', { style: { marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 } },
            React.createElement(Metric, { label: 'Total Return', value: fmtPct(btResult.total_return_pct), color: (btResult.total_return_pct || 0) >= 0 ? COLORS.green : COLORS.red }),
            React.createElement(Metric, { label: 'Max Drawdown', value: fmtPct(-(btResult.max_drawdown_pct || 0)), color: COLORS.red }),
            React.createElement(Metric, { label: 'Trades', value: btResult.trades || 0 }),
            React.createElement(Metric, { label: 'Win Rate', value: (btResult.win_rate != null ? fmtPct(btResult.win_rate).replace('%', '') : '--') + '%' }),
            React.createElement(Metric, { label: 'Final Equity', value: fmtCur(btResult.final_equity) }),
            React.createElement(Metric, { label: 'Sharpe', value: fmtNum(btResult.sharpe) })
          ),
          btResult && btResult.error && React.createElement('div', { style: { marginTop: 10, fontSize: 12, color: COLORS.red } }, '⚠ ' + btResult.error)
        )
      )
    )
  );
}

/* ============================ TRADE JOURNAL ============================ */
const fmtDT = (ts) => ts ? new Date(ts * 1000).toLocaleString() : '—';
const reportEvent = (message, category, level, detail) => {
  try {
    fetch(`${API}/journal/log`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, category: category || 'info', level: level || 'INFO', detail: detail || {} }) }).catch(() => {});
  } catch (e) {}
};

const PRIORITY_COLOR = { urgent: COLORS.red, high: COLORS.amber, normal: COLORS.blue, low: COLORS.textTertiary };

function EquityCurve({ points, height }) {
  if (!points || points.length < 2) return React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Not enough closed trades to build an equity curve.');
  const vals = points.map(p => (p.value != null ? p.value : p.pnl)).map(Number);
  const vmin = Math.min.apply(null, vals), vmax = Math.max.apply(null, vals);
  const range = (vmax - vmin) || 1;
  const w = 860, h = height || 150;
  const step = w / (points.length - 1);
  const pts = points.map((p, i) => `${(i * step).toFixed(1)},${(h - 12 - ((p.value - vmin) / range) * (h - 24)).toFixed(1)}`).join(' ');
  const up = vals[vals.length - 1] >= vals[0];
  return React.createElement('div', null,
    React.createElement('svg', { width: '100%', viewBox: `0 0 ${w} ${h}`, style: { display: 'block' } },
      React.createElement('polygon', { points: pts + ` ${w},${h} 0,${h}`, fill: (up ? COLORS.green : COLORS.red) + '18' }),
      React.createElement('polyline', { points: pts, fill: 'none', stroke: up ? COLORS.green : COLORS.red, strokeWidth: 2 })
    ),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 10, color: COLORS.textTertiary } },
      React.createElement('span', null, fmtCur(vmin)), React.createElement('span', null, 'equity curve · ' + fmtCur(vals[vals.length - 1])), React.createElement('span', null, fmtCur(vmax))
    )
  );
}

function BreakdownBars({ rows, colorFn }) {
  const max = rows.length ? Math.max.apply(null, rows.map(r => Math.abs(r.net_pnl != null ? r.net_pnl : (r.value || 0)))) : 0;
  if (!rows.length) return React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'No data yet.');
  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
    rows.map(r => { const v = r.net_pnl != null ? r.net_pnl : (r.value || 0); return React.createElement('div', { key: String(r.group || r.key || r.id), style: { display: 'flex', alignItems: 'center', gap: 8 } },
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700, color: COLORS.text, width: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, String(r.group || r.key)),
      React.createElement('div', { style: { flex: 1, height: 14, background: COLORS.bgElevated, borderRadius: 4, overflow: 'hidden' } },
        React.createElement('div', { style: { width: max ? (Math.abs(v) / max) * 100 + '%' : 0, height: '100%', background: colorFn ? colorFn(v) : COLORS.blue, borderRadius: 4 } })
      ),
      React.createElement('span', { style: { fontSize: 11, width: 90, textAlign: 'right', color: v >= 0 ? COLORS.green : COLORS.red } }, `${r.trades || 0} · ${fmtCur(v)}`)
    ); })
  );
}

function TradeRow({ t, onClose, onDelete }) {
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' } },
      React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary, width: 110 } }, fmtDT(t.opened_at)),
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800, color: COLORS.text, minWidth: 70 } }, t.symbol),
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: (t.side === 'buy' ? COLORS.green : COLORS.red) + '22', color: t.side === 'buy' ? COLORS.green : COLORS.red } }, (t.side || '').toUpperCase()),
      React.createElement('span', { style: { fontSize: 11, color: COLORS.textSecondary } }, `qty ${t.qty} · entry ${fmtNum(t.entry_price, 4)}` + (t.exit_price ? ` → exit ${fmtNum(t.exit_price, 4)}` : '')),
      t.pnl_usd != null && React.createElement('span', { style: { fontSize: 13, fontWeight: 800, color: t.pnl_usd >= 0 ? COLORS.green : COLORS.red, marginLeft: 'auto' } }, fmtCur(t.pnl_usd) + (t.pnl_pct != null ? ' (' + fmtPct(t.pnl_pct) + ')' : '')),
      React.createElement('span', { style: { fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, border: `1px solid ${t.status === 'closed' ? COLORS.green + '66' : COLORS.amber + '66'}`, color: t.status === 'closed' ? COLORS.green : COLORS.amber } }, (t.status || '').toUpperCase()),
      t.strategy && React.createElement('span', { style: { fontSize: 10, color: COLORS.purple, border: `1px solid ${COLORS.purple}44`, padding: '2px 7px', borderRadius: 4 } }, t.strategy),
      React.createElement('div', { style: { display: 'flex', gap: 6 } },
        t.status === 'open' && React.createElement('button', { onClick: () => onClose(t), style: { padding: '4px 10px', borderRadius: 6, background: COLORS.blue, border: 'none', color: '#fff', fontSize: 11, fontWeight: 700, cursor: 'pointer' } }, 'Close'),
        React.createElement('button', { onClick: () => onDelete(t), style: { padding: '4px 10px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.red}66`, color: COLORS.red, fontSize: 11, fontWeight: 700, cursor: 'pointer' } }, 'Delete')
      )
    ),
    t.notes && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6 } }, t.notes)
  );
}

function JournalView() {
  const [sub, setSub] = useState('overview');
  const [days, setDays] = useState(null);
  const [stats, setStats] = useState(null);
  const [trades, setTrades] = useState([]);
  const [tradeCount, setTradeCount] = useState(0);
  const [sessions, setSessions] = useState([]);
  const [log, setLog] = useState([]);
  const [logCat, setLogCat] = useState('ALL');
  const [logLevel, setLogLevel] = useState('ALL');
  const [rules, setRules] = useState([]);
  const [notifLog, setNotifLog] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [checking, setChecking] = useState(false);
  const [syncInterval, setSyncInterval] = useState(null);
  const [customLogMsg, setCustomLogMsg] = useState('');
  const [closedId, setClosedId] = useState(null);

  const loadStats = async (d) => {
    try {
      const q = d ? `?days=${d}` : '';
      const r = await fetch(`${API}/journal/stats${q}`);
      const j = await r.json();
      if (!j.error) setStats(j);
    } catch (e) {}
  };
  const loadTrades = async () => {
    try {
      const r = await fetch(`${API}/journal/trades?limit=500`);
      const j = await r.json();
      if (j.trades) { setTrades(j.trades); setTradeCount(j.count); }
    } catch (e) {}
  };
  const loadSessions = async () => {
    try { const r = await fetch(`${API}/journal/sessions?limit=50`); const j = await r.json(); if (j.sessions) setSessions(j.sessions); } catch (e) {}
  };
  const loadLog = async () => {
    try {
      const r = await fetch(`${API}/journal/log?category=${logCat}&level=${logLevel}&limit=300`);
      const j = await r.json();
      if (j.entries) setLog(j.entries);
    } catch (e) {}
  };
  const loadNotifications = async () => {
    try { const r = await fetch(`${API}/journal/notifications`); const j = await r.json(); if (j.rules) setRules(j.rules); } catch (e) {}
    try { const r = await fetch(`${API}/journal/notification-log?limit=30`); const j = await r.json(); if (j.entries) setNotifLog(j.entries); } catch (e) {}
  };

  const refresh = () => { loadStats(days); loadTrades(); loadSessions(); loadNotifications(); };

  useEffect(() => {
    reportEvent('Journal opened', 'ui', 'INFO');
    refresh();
    const iv = setInterval(() => { loadLog(); loadNotifications(); }, 10000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => { loadLog(); }, [logCat, logLevel]);
  useEffect(() => { loadStats(days); }, [days]);

  useEffect(() => {
    const es = new EventSource(`${API}/events`);
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const p = d.payload || {};
        if (p.journal_notification) {
          const t = { title: p.title, message: p.message, priority: p.priority || 'normal', ts: Date.now() };
          setToasts(prev => [t].concat(prev).slice(0, 5));
          setTimeout(() => setToasts(prev => prev.filter(x => x.ts !== t.ts)), 8000);
        }
        if (d.type === 'trade_log' || d.type === 'risk_alert' || d.type === 'mode_switch') reportEvent(p.type || d.type, d.type === 'risk_alert' ? 'risk' : d.type === 'trade_log' ? 'trade' : 'system', d.type === 'risk_alert' ? 'WARNING' : 'INFO');
      } catch (e) {}
    };
    es.onerror = () => {};
    return () => es.close();
  }, []);

  const addTrade = async (t) => {
    try {
      const r = await fetch(`${API}/journal/trades`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(t) });
      const j = await r.json();
      if (!j.error) { loadTrades(); loadStats(days); reportEvent(`Manual trade logged — ${t.symbol} ${(t.side || 'buy').toUpperCase()}`, 'trade', 'INFO'); }
    } catch (e) {}
  };
  const closeTrade = async (trade, exitPrice) => {
    try {
      const r = await fetch(`${API}/journal/trades/close`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trade_id: trade.id, exit_price: exitPrice }) });
      const j = await r.json();
      if (!j.error) { loadTrades(); loadStats(days); reportEvent(`Trade closed — ${trade.symbol} @ ${exitPrice}`, 'trade', 'INFO'); }
    } catch (e) {}
  };
  const deleteTrade = async (trade) => {
    try {
      await fetch(`${API}/journal/trades?id=${trade.id}`, { method: 'DELETE' });
      loadTrades(); loadStats(days); reportEvent(`Trade deleted — ${trade.symbol}`, 'trade', 'WARNING');
    } catch (e) {}
  };
  const startSession = async () => {
    await fetch(`${API}/journal/sessions/start?source=ui`, { method: 'POST' });
    reportEvent('Session started from UI', 'system', 'INFO');
    loadSessions();
  };
  const endSession = async (sid) => {
    await fetch(`${API}/journal/sessions/end`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sid }) });
    reportEvent('Session ended from UI', 'system', 'INFO');
    loadSessions();
  };
  const saveRule = async (r) => {
    try {
      await fetch(`${API}/journal/notifications`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(r) });
      loadNotifications(); reportEvent(`Notification rule saved — ${r.title}`, 'ui', 'INFO');
    } catch (e) {}
  };
  const deleteRule = async (r) => {
    try {
      await fetch(`${API}/journal/notifications?id=${r.id}`, { method: 'DELETE' });
      loadNotifications(); reportEvent(`Notification rule removed — ${r.title}`, 'ui', 'INFO');
    } catch (e) {}
  };
  const checkNow = async () => {
    setChecking(true);
    try {
      const r = await fetch(`${API}/journal/notifications/check`, { method: 'POST' });
      const j = await r.json();
      (j.triggered || []).forEach(t => {
        const tt = { title: t.title, message: t.message, priority: t.priority || 'normal', ts: Date.now() };
        setToasts(prev => [tt].concat(prev).slice(0, 5));
        setTimeout(() => setToasts(prev => prev.filter(x => x.ts !== tt.ts)), 8000);
      });
      setTimeout(() => loadNotifications(), 600);
    } catch (e) {}
    setChecking(false);
  };

  const t = stats ? stats.total : null;
  const subTabs = [
    { id: 'overview', label: 'Overview' }, { id: 'trades', label: 'Trades' },
    { id: 'sessions', label: 'Sessions' }, { id: 'log', label: 'Session Log' },
    { id: 'notify', label: 'Notifications' }
  ];

  return React.createElement('div', null,
    React.createElement('div', { style: { position: 'fixed', top: 64, right: 18, zIndex: 100, display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 340 } },
      toasts.map(to => React.createElement(Card, { key: to.ts, pad: 12, style: { borderColor: PRIORITY_COLOR[to.priority] || COLORS.blue, boxShadow: '0 6px 20px rgba(0,0,0,.5)' } },
        React.createElement('div', { style: { fontSize: 11, fontWeight: 800, color: PRIORITY_COLOR[to.priority] || COLORS.blue, marginBottom: 4 } }, to.title),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, to.message)
      ))
    ),
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 } },
      React.createElement('div', { style: { display: 'flex', gap: 6 } },
        subTabs.map(s => React.createElement(Tab, { key: s.id, small: true, active: sub === s.id, onClick: () => setSub(s.id) }, s.label))
      ),
      React.createElement('button', { onClick: checkNow, disabled: checking, style: { padding: '7px 16px', borderRadius: 8, background: COLORS.purple, border: 'none', color: '#fff', fontWeight: 700, fontSize: 12, cursor: checking ? 'wait' : 'pointer' } }, checking ? 'Checking…' : '🔔 Check notifications now')
    ),

    sub === 'overview' && React.createElement('div', null,
      React.createElement(Section, { title: 'Performance Overview', right: React.createElement('div', { style: { display: 'flex', gap: 6 } },
          React.createElement(Tab, { small: true, active: days === null, onClick: () => setDays(null) }, 'All'),
          React.createElement(Tab, { small: true, active: days === 7, onClick: () => setDays(7) }, '7D'),
          React.createElement(Tab, { small: true, active: days === 30, onClick: () => setDays(30) }, '30D'),
          React.createElement(Tab, { small: true, active: days === 90, onClick: () => setDays(90) }, '90D')
        ) },
        stats && React.createElement('div', null,
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 } },
            React.createElement(Metric, { label: 'Net P&L', value: fmtCur(t.net_pnl), color: (t.net_pnl || 0) >= 0 ? COLORS.green : COLORS.red, sub: (stats.state && stats.state.open_positions || 0) + ' open positions' }),
            React.createElement(Metric, { label: 'Win Rate', value: (t.win_rate != null ? t.win_rate.toFixed(1) : '--') + '%', color: (t.win_rate || 0) >= 50 ? COLORS.green : COLORS.amber, sub: t.trades + ' closed trades' }),
            React.createElement(Metric, { label: 'Profit Factor', value: fmtNum(t.profit_factor), color: (t.profit_factor || 0) >= 1 ? COLORS.green : COLORS.red }),
            React.createElement(Metric, { label: 'Expectancy', value: fmtCur(t.expectancy), color: (t.expectancy || 0) >= 0 ? COLORS.green : COLORS.red, sub: 'per trade' }),
            React.createElement(Metric, { label: 'Avg Win', value: fmtCur(t.avg_win), color: COLORS.green }),
            React.createElement(Metric, { label: 'Avg Loss', value: fmtCur(t.avg_loss), color: COLORS.red }),
            React.createElement(Metric, { label: 'Streaks', value: t.streaks ? `${t.streaks.wins}W / ${t.streaks.losses}L` : '—', sub: 'current' }),
            React.createElement(Metric, { label: 'Max Drawdown', value: t.max_drawdown_usd != null ? fmtCur(-t.max_drawdown_usd) : '—', color: COLORS.red })
          ),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 14 } },
            React.createElement(Metric, { label: 'Best Trade', value: t.best_trade != null ? fmtCur(typeof t.best_trade === 'object' ? t.best_trade.pnl_usd : t.best_trade) : '—', color: COLORS.green, sub: typeof t.best_trade === 'object' && t.best_trade ? t.best_trade.symbol || '' : '' }),
            React.createElement(Metric, { label: 'Worst Trade', value: t.worst_trade != null ? fmtCur(typeof t.worst_trade === 'object' ? t.worst_trade.pnl_usd : t.worst_trade) : '—', color: COLORS.red, sub: typeof t.worst_trade === 'object' && t.worst_trade ? t.worst_trade.symbol || '' : '' }),
            React.createElement(Metric, { label: 'Avg Hold', value: t.avg_hold_min ? Math.round(t.avg_hold_min) + ' min' : '—', sub: 'closed positions' })
          ),
          React.createElement(Card, { pad: 14, style: { marginBottom: 14 } },
            React.createElement(EquityCurve, { points: t.equity_curve })
          ),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 } },
            React.createElement(Card, { pad: 14 },
              React.createElement('div', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text, marginBottom: 8 } }, 'By Symbol'),
              React.createElement(BreakdownBars, { rows: stats.by_symbol, colorFn: v => v >= 0 ? COLORS.green : COLORS.red })
            ),
            React.createElement(Card, { pad: 14 },
              React.createElement('div', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text, marginBottom: 8 } }, 'By Strategy'),
              React.createElement(BreakdownBars, { rows: stats.by_strategy, colorFn: v => v >= 0 ? COLORS.blue : COLORS.red })
            )
          )
        )
      )
    ),

    sub === 'trades' && React.createElement('div', null,
      React.createElement(Section, { title: `Trade Log — ${tradeCount} trades`, right: React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'trades auto-capture live fills + session events') },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
          trades.length === 0 && React.createElement(Card, { pad: 14 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No trades recorded yet. They appear automatically from the live engine, or log one below.')),
          trades.map(tr => React.createElement(TradeRow, { key: tr.id, t: tr, onClose: (x) => {
            const p = window.prompt('Exit price for ' + x.symbol + ':', x.entry_price != null ? String(x.entry_price) : '');
            if (p != null && !isNaN(Number(p))) closeTrade(x, Number(p));
          }, onDelete: (x) => { if (window.confirm('Delete this trade?')) deleteTrade(x); } }))
        )
      ),
      React.createElement(Section, { title: 'Manual Trade Entry' },
        React.createElement(AddTradeForm, { onAdd: addTrade })
      )
    ),

    sub === 'sessions' && React.createElement(Section, { title: 'Sessions', right: React.createElement('button', { onClick: startSession, style: { padding: '6px 14px', borderRadius: 8, background: COLORS.green, border: 'none', color: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' } }, '+ Start session') },
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
        sessions.length === 0 && React.createElement(Card, { pad: 14 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No sessions yet.')),
        sessions.map(s => React.createElement(Card, { key: s.id, pad: 12 },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' } },
            React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: COLORS.blue + '22', color: COLORS.blue, border: `1px solid ${COLORS.blue}44` } }, s.source),
            React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, fmtDT(s.started_at) + (s.ended_at ? ' → ' + fmtDT(s.ended_at) : ' (active)')),
            React.createElement('span', { style: { fontSize: 11, color: COLORS.textSecondary } }, s.duration_min != null ? Math.round(s.duration_min) + ' min' : '—'),
            React.createElement('span', { style: { marginLeft: 'auto', fontSize: 11, color: COLORS.textSecondary } }, s.events_count + ' events'),
            !s.ended_at && React.createElement('button', { onClick: () => endSession(s.id), style: { padding: '4px 10px', borderRadius: 6, background: COLORS.amber, border: 'none', color: '#fff', fontSize: 11, fontWeight: 700, cursor: 'pointer' } }, 'End session')
          ),
          s.summary && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6 } }, s.summary)
        ))
      )
    ),

    sub === 'log' && React.createElement(Section, { title: 'Session Log — automatic capture', right: React.createElement('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
        React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'auto-refreshes every 10s'),
        React.createElement(Tab, { small: true, active: logCat === 'ALL', onClick: () => setLogCat('ALL') }, 'All'),
        ['trade', 'system', 'risk', 'ui', 'calendar', 'strategy', 'error', 'info'].map(c => React.createElement(Tab, { key: c, small: true, active: logCat === c, onClick: () => setLogCat(c) }, c))
      ) },
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4 } },
        log.length === 0 && React.createElement(Card, { pad: 14 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No log entries yet.')),
        log.map(e => React.createElement('div', { key: e.ts + '_' + e.session_id + '_' + e.message, style: { display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px', borderRadius: 7, background: COLORS.bgSurface, border: `1px solid ${COLORS.border}` } },
          React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, fmtDT(e.ts)),
          React.createElement('span', { style: { fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: (e.level === 'WARNING' ? COLORS.amber : e.level === 'ERROR' ? COLORS.red : COLORS.blue) + '22', color: e.level === 'WARNING' ? COLORS.amber : e.level === 'ERROR' ? COLORS.red : COLORS.blue } }, e.level),
          React.createElement('span', { style: { fontSize: 10, fontWeight: 700, color: COLORS.textTertiary, width: 64 } }, e.category),
          React.createElement('span', { style: { fontSize: 12, color: COLORS.text, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, e.message)
        ))
      ),
      React.createElement('div', { style: { marginTop: 10, display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement('input', { value: customLogMsg, placeholder: 'Log a manual note (e.g. "Increased position after breakout")…', onChange: (e) => setCustomLogMsg(e.target.value), onKeyDown: (e) => { if (e.key === 'Enter' && customLogMsg.trim()) { reportEvent(customLogMsg.trim(), 'ui', 'INFO'); setCustomLogMsg(''); setTimeout(loadLog, 300); } }, style: { flex: 1, padding: '8px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } }),
        React.createElement('button', { onClick: () => { if (customLogMsg.trim()) { reportEvent(customLogMsg.trim(), 'ui', 'INFO'); setCustomLogMsg(''); setTimeout(loadLog, 300); } }, style: { padding: '8px 14px', borderRadius: 8, background: COLORS.blue, border: 'none', color: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' } }, 'Log note')
      )
    ),

    sub === 'notify' && React.createElement('div', null,
      React.createElement(Section, { title: 'Custom Notification Set', right: React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'rules are evaluated against the live engine + economic calendar') },
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 } },
          rules.map(r => React.createElement(NotificationRuleCard, { key: r.id, r: r, onSave: saveRule, onDelete: deleteRule }))
        )
      ),
      React.createElement(Section, { title: 'Notification History' },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4 } },
          notifLog.length === 0 && React.createElement(Card, { pad: 14 }, React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } }, 'No notifications pushed yet.')),
          notifLog.map(n => React.createElement(Card, { key: n.ts + '_' + n.rule_id, pad: 10 },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
              React.createElement('span', { style: { fontSize: 11, fontWeight: 800, color: PRIORITY_COLOR[n.priority] || COLORS.blue } }, n.title),
              React.createElement('span', { style: { fontSize: 11, color: COLORS.textSecondary, flex: 1 } }, n.message),
              React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, fmtDT(n.ts))
            )
          ))
        )
      )
    )
  );
}

function AddTradeForm({ onAdd }) {
  const [form, setForm] = useState({ symbol: 'BTC', side: 'buy', qty: '', size_usd: '', entry_price: '', exit_price: '', strategy: 'rsi', notes: '' });
  const set = (k) => (e) => setForm(Object.assign({}, form, { [k]: e.target.value }));
  const submit = () => {
    if (!form.symbol || !form.qty || !form.entry_price) return;
    onAdd(form);
    setForm(Object.assign({}, form, { qty: '', size_usd: '', entry_price: '', exit_price: '', notes: '' }));
  };
  const field = (label, key, ph, w) => React.createElement('div', { key: key, style: { display: 'flex', flexDirection: 'column', gap: 4, width: w || 110 } },
    React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, label),
    React.createElement('input', { value: form[key], placeholder: ph, onChange: set(key), style: { padding: '7px 9px', borderRadius: 6, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } }));
  return React.createElement(Card, { pad: 14 },
    React.createElement('div', { style: { display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' } },
      field('Symbol', 'symbol', 'BTC', 90),
      React.createElement('div', { key: 'side', style: { display: 'flex', flexDirection: 'column', gap: 4 } },
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Side'),
        React.createElement('div', { style: { display: 'flex', gap: 4 } },
          React.createElement(Tab, { small: true, active: form.side === 'buy', onClick: () => setForm(Object.assign({}, form, { side: 'buy' })) }, 'BUY'),
          React.createElement(Tab, { small: true, active: form.side === 'sell', onClick: () => setForm(Object.assign({}, form, { side: 'sell' })) }, 'SELL')
        )
      ),
      field('Qty', 'qty', '0.1'),
      field('Size USD', 'size_usd', '500'),
      field('Entry', 'entry_price', '50000', 110),
      field('Exit (opt)', 'exit_price', '51000', 110),
      field('Strategy', 'strategy', 'rsi', 130),
      React.createElement('button', { onClick: submit, style: { padding: '8px 16px', borderRadius: 8, background: COLORS.green, border: 'none', color: '#06281a', fontWeight: 700, fontSize: 12, cursor: 'pointer' } }, '+ Log trade')
    ),
    React.createElement('input', { value: form.notes, placeholder: 'Notes for this trade…', onChange: set('notes'), style: { marginTop: 8, width: '100%', boxSizing: 'border-box', padding: '7px 9px', borderRadius: 6, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } })
  );
}

function NotificationRuleCard({ r, onSave, onDelete }) {
  const [rule, setRule] = useState(r);
  useEffect(() => setRule(r), [r]);
  const set = (k, v) => setRule(Object.assign({}, rule, { [k]: v }));
  const save = () => onSave(Object.assign({}, rule, { threshold: isNaN(Number(rule.threshold)) ? 0 : Number(rule.threshold), cooldown_sec: isNaN(Number(rule.cooldown_sec)) ? 60 : Number(rule.cooldown_sec) }));
  return React.createElement(Card, { pad: 14, style: { borderColor: rule.enabled ? (PRIORITY_COLOR[rule.priority] || COLORS.blue) + '88' : COLORS.border } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: (PRIORITY_COLOR[rule.priority] || COLORS.blue) + '22', color: PRIORITY_COLOR[rule.priority] || COLORS.blue, border: `1px solid ${(PRIORITY_COLOR[rule.priority] || COLORS.blue)}44` } }, rule.priority),
      React.createElement('div', { style: { flex: 1 } },
        React.createElement('input', { value: rule.title, onChange: (e) => set('title', e.target.value), style: { width: '100%', boxSizing: 'border-box', background: 'transparent', border: 'none', color: COLORS.text, fontSize: 13, fontWeight: 800 } }),
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, rule.id),
        React.createElement('input', { value: rule.message, onChange: (e) => set('message', e.target.value), style: { width: '100%', boxSizing: 'border-box', background: 'transparent', border: 'none', color: COLORS.textSecondary, fontSize: 11, marginTop: 2 } })
      ),
      React.createElement('label', { style: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: COLORS.textSecondary, cursor: 'pointer' } },
        React.createElement('input', { type: 'checkbox', checked: !!rule.enabled, onChange: (e) => set('enabled', e.target.checked) }), rule.enabled ? 'ON' : 'OFF')
    ),
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Threshold'),
        React.createElement('input', { value: rule.threshold, onChange: (e) => set('threshold', e.target.value), style: { width: 80, padding: '5px 8px', borderRadius: 6, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } })
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Units'),
        React.createElement('span', { style: { fontSize: 11, color: COLORS.textSecondary, paddingBottom: 5 } }, rule.threshold_units)
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Cooldown (s)'),
        React.createElement('input', { value: rule.cooldown_sec, onChange: (e) => set('cooldown_sec', e.target.value), style: { width: 70, padding: '5px 8px', borderRadius: 6, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 12 } })
      ),
      React.createElement('span', { style: { marginLeft: 'auto', display: 'flex', gap: 6 } },
        React.createElement('button', { onClick: save, style: { padding: '6px 12px', borderRadius: 6, background: COLORS.blue, border: 'none', color: '#fff', fontSize: 11, fontWeight: 700, cursor: 'pointer' } }, 'Save'),
        React.createElement('button', { onClick: () => onDelete(rule), style: { padding: '6px 12px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.red}66`, color: COLORS.red, fontSize: 11, fontWeight: 700, cursor: 'pointer' } }, 'Reset')
      )
    )
  );
}

/* ============================ MAIN APP ============================ */
function App() {
  const E = window.Theme && window.Theme.EXTRA || {};
  const [tab, setTab] = useState('dashboard');
  const [connected, setConnected] = useState(false);
  const [health, setHealth] = useState(null);
  const [gainers, setGainers] = useState([]);
  const [losers, setLosers] = useState([]);
  const [search, setSearch] = useState('');
  const [chartSymbol, setChartSymbol] = useState('BTC');
  const [modeBusy, setModeBusy] = useState(false);
  const pendingTermRef = useRef(null);
  const setTerminalCommand = (cmd) => { pendingTermRef.current = cmd; setTab('terminal'); };
  const onModeToggle = async (mode) => {
    if (modeBusy) return;
    setModeBusy(true);
    try {
      const r = await fetch(`${API}/delta/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + BRIDGE_TOKEN },
        body: JSON.stringify({ mode }),
      });
      const d = await r.json();
      if (r.ok && d && d.status === 'ok') {
        setHealth(Object.assign({}, health || {}, { mode: d.mode }));
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.ping();
      } else {
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.blip();
        alert(d && d.error ? d.error : 'Mode switch failed');
      }
    } catch (e) {
      if (window.Chrome && window.Chrome.audio) window.Chrome.audio.blip();
      alert('Mode switch failed: ' + e.message);
    } finally { setModeBusy(false); }
  };

  useEffect(() => {
    const poll = async () => {
      try {
        const [h, g] = await Promise.all([
          fetch(`${API}/delta/health`).then(r => r.ok ? r.json() : null),
          fetch(`${API}/delta/top-gainers?limit=50`).then(r => r.ok ? r.json() : null),
        ]);
        if (h) setHealth(h);
        if (g && g.gainers) {
          const spot = g.gainers.filter(x => !/-[0-9]{6}$/.test(x.symbol || '') && !/^[CP]-/.test(x.symbol || ''));
          setGainers(spot.length ? spot : g.gainers);
          setLosers(spot.length ? spot : g.gainers);
        }
      } catch (e) {}
    };
    poll();
    const iv = setInterval(poll, 15000);
    const es = new EventSource(`${API}/events`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    return () => { clearInterval(iv); es.close(); };
  }, []);

  useEffect(() => {
    if (window.__chromeMounted) return;
    window.__chromeMounted = true;
    try {
      if (window.Chrome && window.Chrome.runBoot) window.Chrome.runBoot();
      if (window.Chrome && window.Chrome.createScanline && !document.querySelector('.cc-scanline')) document.body.appendChild(window.Chrome.createScanline());
      if (window.Chrome && window.Chrome.createGrid && !document.querySelector('.cc-grid')) document.body.appendChild(window.Chrome.createGrid());
      if (window.Chrome && window.Chrome.createNoise && !document.querySelector('.cc-noise')) document.body.appendChild(window.Chrome.createNoise());
      if (window.Chrome && window.Chrome.createParticleField && !document.querySelector('.cc-particles')) document.body.appendChild(window.Chrome.createParticleField());
      if (window.Chrome && window.Chrome.createDataStream && !document.querySelector('.cc-datastream')) document.body.appendChild(window.Chrome.createDataStream());
      if (window.Chrome && window.Chrome.initCursor) window.Chrome.initCursor();
      if (window.Chrome && window.Chrome.initTilt) window.Chrome.initTilt();
    } catch (e) {}
    document.addEventListener('click', function arm() {
      try { if (window.Chrome && window.Chrome.audio) window.Chrome.audio.arm(); } catch (e) {}
      document.removeEventListener('click', arm);
    });
  }, []);

  useEffect(() => {
    if (window.__paletteMounted) return;
    window.__paletteMounted = true;
    try {
      if (window.Palette) {
        var pal = document.getElementById('command-palette-root');
        if (!pal) {
          pal = document.createElement('div');
          pal.id = 'command-palette-root';
          document.body.appendChild(pal);
        }
        window.Palette.mount(pal, { onNavigate: (k) => setTab(k) });
        if (window.Palette.setTerminalRunner) window.Palette.setTerminalRunner(setTerminalCommand);
      }
    } catch (e) {}
  }, []);

  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'options', label: 'Options' },
    { id: 'strategies', label: 'Strategies' },
    { id: 'calendar', label: 'Calendar' },
    { id: 'library', label: 'Strategy Library' },
    { id: 'journal', label: 'Journal' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'terminal', label: 'TERM' },
  ];

  return React.createElement('div', { style: { minHeight: '100vh', background: COLORS.bgRoot, color: COLORS.text } },
    React.createElement('header', { style: { position: 'sticky', top: 0, zIndex: 50, background: 'rgba(10,11,15,0.95)', borderBottom: `1px solid ${COLORS.border}`, padding: '10px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backdropFilter: 'blur(8px)' } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
        React.createElement('div', { style: { width: 26, height: 26, borderRadius: 7, background: 'linear-gradient(135deg,#4e8cff,#9b59b6)' } }),
        React.createElement('span', { style: { fontSize: 15, fontFamily: E.fontDisplay || 'inherit', fontWeight: 800, letterSpacing: 0.4 } }, 'Trading Command Center')
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 14 } },
        React.createElement('div', { style: { display: 'flex', gap: 6, background: COLORS.bgElevated, padding: 4, borderRadius: 10, border: `1px solid ${COLORS.border}` } },
          tabs.map(t => React.createElement(Tab, { key: t.id, small: true, active: tab === t.id, onClick: () => setTab(t.id) }, t.label))
        ),
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', fontSize: 12, color: COLORS.textSecondary } },
          React.createElement(StatusDot, { on: connected }), connected ? 'Live' : 'Offline'
        ),
        React.createElement('button', {
          onClick: (e) => { const ap = window.Chrome && window.Chrome.audio; if (ap) {
            ap.arm();
            const m = ap.toggle();
            if (m) ap.mute(); else ap.unmute();
            e.target.textContent = ap.isMuted() ? 'SOUND OFF' : 'SOUND ON';
          } },
          style: { padding: '5px 10px', borderRadius: 6, border: `1px solid ${COLORS.border}`, background: 'transparent', color: COLORS.textSecondary, fontSize: 11, fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer' }
        }, 'SOUND ON')
      )
    ),
    React.createElement('main', { style: { padding: 18, maxWidth: 1400, margin: '0 auto' } },
      tab === 'dashboard' && React.createElement(DashboardView, { gainers, losers, health, search, setSearch, chartSymbol, setChartSymbol, onModeToggle, modeBusy }),
      tab === 'options' && React.createElement(OptionsView, null),
      tab === 'strategies' && React.createElement(StrategiesView, null),
      tab === 'calendar' && React.createElement(CalendarView, null),
      tab === 'library' && React.createElement(LibraryView, null),
      tab === 'journal' && React.createElement(JournalView, null),
      tab === 'analytics' && React.createElement(AnalyticsView, null),
      tab === 'terminal' && React.createElement(window.TerminalView, { pendingCmd: pendingTermRef.current }),
    )
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
