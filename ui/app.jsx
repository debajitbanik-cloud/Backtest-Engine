const { useState, useEffect, useRef, useMemo } = React;
const API = 'http://127.0.0.1:8088';
const BRIDGE_TOKEN = '8G8VGUXx1sjVEmK7Y2fqs0VF6wcukOXSXwI6dVv24WY';

const COLORS = {
  bgRoot: '#020617', bgSurface: '#0E1223', bgElevated: '#1A1E2F', bgHover: '#232842',
  border: '#334155', borderActive: '#475569', text: '#F8FAFC', textSecondary: '#94A3B8',
  textTertiary: '#64748B', blue: '#4e8cff', green: '#22C55E', red: '#EF4444',
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

/* ============================ BOT LIBRARY ============================ */
const BOT_CATEGORIES = [
  { id: 'btc', label: 'BTC Bots', icon: '₿', color: COLORS.amber },
  { id: 'xau_arb', label: 'XAU Arbitrage', icon: '🥇', color: COLORS.gold || '#ffd700' },
  { id: 'sol_scalp', label: 'SOL Scalping', icon: '◎', color: COLORS.green },
  { id: 'xau_swing', label: 'XAU Swing', icon: '📈', color: COLORS.blue },
  { id: 'options', label: 'Option Bots', icon: '⚡', color: COLORS.purple },
  { id: 'basket', label: 'Basket Bots', icon: '🧺', color: COLORS.cyan },
  { id: 'trade_logic', label: 'Trade Logic', icon: '🧠', color: COLORS.magenta || '#ff00ff' },
];

const BOTS = {
  btc: [
    { id: 'btc_ma_trend', name: 'BTC MA Trend Follower', class: 'trend', risk: 'Medium',
      desc: 'Multi-timeframe MA crossover (EMA 50/200 daily + EMA 12/26 4h) with ATR trailing stop. Enters on golden cross confirmation, exits on death cross or ATR breach.',
      params: { fast: 12, slow: 26, atr_mult: 2.5, tf: '4h', starting_cash: 10000 },
      logic: 'trend_follow', assets: ['BTCUSD'], status: 'ready' },
    { id: 'btc_rsi_div', name: 'BTC RSI Divergence Reversal', class: 'mean_reversion', risk: 'Medium',
      desc: 'Trades RSI divergence on 4h chart: bullish divergence (price lower low, RSI higher long) triggers long; bearish divergence triggers short. Confirmed by volume spike.',
      params: { period: 14, div_lookback: 20, tf: '4h', starting_cash: 10000 },
      logic: 'reversion', assets: ['BTCUSD'], status: 'ready' },
    { id: 'btc_breakout_vol', name: 'BTC Volume Breakout', class: 'breakout', risk: 'High',
      desc: 'Donchian 20-channel breakout with volume confirmation (>2x 20-period avg volume). ATR-based position sizing, partial TP at 1R/2R/3R.',
      params: { entry: 20, vol_mult: 2.0, atr_mult: 1.5, tf: '1h', starting_cash: 10000 },
      logic: 'breakout', assets: ['BTCUSD'], status: 'ready' },
    { id: 'btc_macd_momentum', name: 'BTC MACD Momentum', class: 'momentum', risk: 'Medium',
      desc: 'MACD (12,26,9) histogram flip with signal line cross confirmation. Trades momentum bursts in trending BTC phases.',
      params: { fast: 12, slow: 26, signal: 9, tf: '1h', starting_cash: 10000 },
      logic: 'momentum', assets: ['BTCUSD'], status: 'ready' },
    { id: 'btc_grid', name: 'BTC Grid Trader', class: 'grid', risk: 'High',
      desc: 'Infinite grid around VWAP: places buy/sell orders every 0.5% ATR. Accumulates in range, reduces avg cost. Best for sideways BTC.',
      params: { grid_step_pct: 0.5, atr_mult: 1.0, max_levels: 20, tf: '15m', starting_cash: 10000 },
      logic: 'grid', assets: ['BTCUSD'], status: 'ready' },
  ],
  xau_arb: [
    { id: 'xau_spot_fut_arb', name: 'XAU Spot-Futures Arb', class: 'arbitrage', risk: 'Low',
      desc: 'Cash-and-carry arb: long XAU spot (XAUT) + short XAU perp when basis > funding cost + slippage buffer. Delta-neutral, harvests positive carry.',
      params: { min_basis_bps: 15, max_pos_usd: 50000, tf: '1h', starting_cash: 10000 },
      logic: 'arb_carry', assets: ['XAUTUSD'], status: 'ready' },
    { id: 'xau_funding_arb', name: 'XAU Funding Rate Arb', class: 'arbitrage', risk: 'Low',
      desc: 'Long perp when funding << spot carry, short when funding >> spot carry. Dynamically hedges with spot. Captures funding premium.',
      params: { funding_thresh: 0.0001, hedge_ratio: 1.0, tf: '1h', starting_cash: 10000 },
      logic: 'arb_funding', assets: ['XAUTUSD'], status: 'ready' },
    { id: 'xau_cross_venue', name: 'XAU Cross-Venue Arb', class: 'arbitrage', risk: 'Medium',
      desc: 'Monitors XAU price across Delta, Binance, Bybit perps. Executes when spread > 2x taker fee + latency buffer. Triangular with USDT.',
      params: { min_spread_bps: 8, venues: ['delta','binance','bybit'], tf: '5m', starting_cash: 10000 },
      logic: 'arb_cross_venue', assets: ['XAUTUSD'], status: 'dev' },
    { id: 'xau_calendar_spread', name: 'XAU Calendar Spread', class: 'spread', risk: 'Low',
      desc: 'Long near-term XAU option, short far-term same strike. Theta positive, benefits from term structure flattening in gold.',
      params: { dte_near: 7, dte_far: 30, strike_atm: true, tf: '1d', starting_cash: 10000 },
      logic: 'spread_calendar', assets: ['XAUTUSD'], status: 'dev' },
  ],
  sol_scalp: [
    { id: 'sol_ma_scalp', name: 'SOL Fast MA Scalper', class: 'scalping', risk: 'High',
      desc: 'EMA 9/21 cross on 5m chart with RSI filter (only long if RSI<60, short if RSI>40). Tight 0.5% SL, 1:1.5 TP. High frequency.',
      params: { fast: 9, slow: 21, rsi_period: 14, tf: '5m', starting_cash: 10000 },
      logic: 'scalp_ma', assets: ['SOLUSD'], status: 'ready' },
    { id: 'sol_obv_flow', name: 'SOL OBV Order Flow', class: 'scalping', risk: 'High',
      desc: 'Tracks OBV slope + CVD (cumulative volume delta). Enters when OBV breaks trendline with CVD confirmation. 30s-5m holds.',
      params: { obv_lookback: 50, cvd_thresh: 1000, tf: '1m', starting_cash: 10000 },
      logic: 'scalp_flow', assets: ['SOLUSD'], status: 'dev' },
    { id: 'sol_vwap_reclaim', name: 'SOL VWAP Reclaim', class: 'scalping', risk: 'Medium',
      desc: 'Buys when SOL reclaims VWAP after deviation >1.5% with volume surge. Exits at VWAP + 1 SD band. Classic intraday mean-revert.',
      params: { vwap_dev: 1.5, vol_surge: 1.5, tf: '5m', starting_cash: 10000 },
      logic: 'scalp_vwap', assets: ['SOLUSD'], status: 'ready' },
    { id: 'sol_funding_scalp', name: 'SOL Funding Scalp', class: 'scalping', risk: 'Medium',
      desc: 'Scalps funding rate discontinuities: shorts before funding when rate > 0.01%, covers after. 8h cycle aligned.',
      params: { funding_thresh: 0.0001, tf: '1h', starting_cash: 10000 },
      logic: 'scalp_funding', assets: ['SOLUSD'], status: 'ready' },
  ],
  xau_swing: [
    { id: 'xau_ichimoku_swing', name: 'XAU Ichimoku Swing', class: 'swing', risk: 'Medium',
      desc: 'Daily Ichimoku: long when price > cloud & Tenkan > Kijun & Chikou > price 26 bars ago. Holds weeks. Trail by Kijun.',
      params: { tenkan: 9, kijun: 26, senkou_b: 52, tf: '1d', starting_cash: 10000 },
      logic: 'swing_ichimoku', assets: ['XAUTUSD'], status: 'ready' },
    { id: 'xau_seasonal', name: 'XAU Seasonal Swing', class: 'seasonal', risk: 'Medium',
      desc: 'Gold seasonal patterns: long Jan-Feb (CNY demand), Aug-Sep (India wedding), Dec (central bank buying). Exits at historical resistance.',
      params: { entry_months: [1,2,8,9,12], tf: '1d', starting_cash: 10000 },
      logic: 'seasonal', assets: ['XAUTUSD'], status: 'ready' },
    { id: 'xau_dxy_inverse', name: 'XAU DXY Inverse Swing', class: 'macro', risk: 'Medium',
      desc: 'Trades XAU inverse correlation with DXY. Long XAU when DXY breaks below 200 DMA & RSI<30; short when DXY > 200 DMA & RSI>70.',
      params: { dxy_ma: 200, rsi_period: 14, tf: '4h', starting_cash: 10000 },
      logic: 'macro_dxy', assets: ['XAUTUSD'], status: 'ready' },
    { id: 'xau_real_yield', name: 'XAU Real Yield Model', class: 'macro', risk: 'Medium',
      desc: 'Fair value model: XAU = f(US 10Y real yield, DXY, oil). Long when XAU > model + 1 SD, short when < -1 SD. Weekly rebalance.',
      params: { lookback: 252, z_entry: 1.0, tf: '1d', starting_cash: 10000 },
      logic: 'macro_real_yield', assets: ['XAUTUSD'], status: 'dev' },
  ],
  options: [
    { id: 'opt_iron_condor', name: 'Delta Iron Condor', class: 'income', risk: 'Low',
      desc: 'Sells 16-delta put/call spreads on BTC/ETH/XAU weekly expiries. Manages at 21 DTE, rolls untested side. High prob, defined risk.',
      params: { delta: 16, dte: 21, width: 10, tf: '1d', starting_cash: 10000 },
      logic: 'opt_iron_condor', assets: ['BTCUSD','ETHUSD','XAUTUSD'], status: 'ready' },
    { id: 'opt_diagonal', name: 'Diagonal Call Spread', class: 'directional', risk: 'Medium',
      desc: 'Long 45-delta 60-day call, short 30-delta 30-day call. Positive theta, long vega. Bullish with time decay tailwind.',
      params: { long_delta: 45, short_delta: 30, dte_long: 60, dte_short: 30, tf: '1d', starting_cash: 10000 },
      logic: 'opt_diagonal', assets: ['BTCUSD','ETHUSD'], status: 'ready' },
    { id: 'opt_straddle_gamma', name: 'Long Straddle Gamma Scalp', class: 'volatility', risk: 'High',
      desc: 'Buys ATM straddle before major events (CPI, FOMC, earnings). Gamma scalps intraday to offset theta. Exits post-event IV crush.',
      params: { dte: 7, event_calendar: true, tf: '1h', starting_cash: 10000 },
      logic: 'opt_gamma_scalp', assets: ['BTCUSD','ETHUSD'], status: 'ready' },
    { id: 'opt_covered_call', name: 'Covered Call Wheel', class: 'income', risk: 'Low',
      desc: 'Wheel strategy: sell CSP → if assigned, sell covered call → if called, repeat. Runs on BTC/ETH/XAU. Compounds premium.',
      params: { csp_delta: 20, cc_delta: 30, dte: 30, tf: '1d', starting_cash: 20000 },
      logic: 'opt_wheel', assets: ['BTCUSD','ETHUSD','XAUTUSD'], status: 'ready' },
  ],
  basket: [
    { id: 'meme_pump_5', name: 'Meme Pump 5-Coin Long', class: 'basket', risk: 'Very High',
      desc: 'Longs top 5 memecoins by 24h volume (DOGE, SHIB, PEPE, WIF, BONK) when ALL show: RSI<45, volume >2x avg, funding <0.01%. Equal weight, 2% risk each.',
      params: { min_vol_mult: 2.0, max_rsi: 45, max_funding: 0.0001, coins: 5, tf: '1h', starting_cash: 10000 },
      logic: 'basket_meme_pump', assets: ['DOGEUSD','SHIBUSD','PEPEUSD','WIFUSD','BONKUSD'], status: 'ready' },
    { id: 'meme_dump_5', name: 'Meme Dump 5-Coin Short', class: 'basket', risk: 'Very High',
      desc: 'Shorts top 5 memecoins by 24h volume when ALL show: RSI>75, price >2SD above VWAP, funding >0.05%. Equal weight, 2% risk each.',
      params: { min_rsi: 75, vwap_dev: 2.0, min_funding: 0.0005, coins: 5, tf: '4h', starting_cash: 10000 },
      logic: 'basket_meme_dump', assets: ['DOGEUSD','SHIBUSD','PEPEUSD','WIFUSD','BONKUSD'], status: 'ready' },
    { id: 'crypto_top10', name: 'Top 10 Crypto Momentum', class: 'basket', risk: 'Medium',
      desc: 'Long top 10 perps by 24h turnover with positive 24h change & funding <0.02%. Monthly rebalance. Captures broad crypto beta.',
      params: { top_n: 10, min_chg: 0, max_funding: 0.0002, tf: '1d', starting_cash: 10000 },
      logic: 'basket_momentum', assets: ['BTCUSD','ETHUSD','SOLUSD','XRPUSD','DOGEUSD','SHIBUSD','PEPEUSD','WIFUSD','BONKUSD','ADAUSD'], status: 'ready' },
    { id: 'defi_bluechip', name: 'DeFi Blue-Chip Basket', class: 'basket', risk: 'Medium',
      desc: 'Long UNI, AAVE, LDO, CRV, MKR, SNX when sector momentum >0 & BTC trend up. Equal weight, 15% per asset max.',
      params: { assets: ['UNIUSD','AAVEUSD','LDOUSD','CRVUSD','MKRUSD','SNXUSD'], tf: '4h', starting_cash: 10000 },
      logic: 'basket_sector', assets: ['UNIUSD','AAVEUSD','LDOUSD','CRVUSD','MKRUSD','SNXUSD'], status: 'dev' },
    { id: 'rwa_real_world', name: 'RWA (Real World Assets) Basket', class: 'basket', risk: 'Medium',
      desc: 'Long tokenized T-bills (ONDO), real estate (REAL), private credit (CFG), gold (XAUT). Rebalances monthly. Low correlation to crypto.',
      params: { assets: ['ONDOUSD','REALUSD','CFGUSD','XAUTUSD'], tf: '1d', starting_cash: 10000 },
      logic: 'basket_rwa', assets: ['ONDOUSD','REALUSD','CFGUSD','XAUTUSD'], status: 'dev' },
  ],
  trade_logic: [
    { category: 'Hedged Ideas', items: [
      { name: 'Delta-Neutral Basis Trade', desc: 'Long spot + short perp when basis > funding. Harvests carry with zero directional risk.', logic: 'arb_carry' },
      { name: 'Options Collar', desc: 'Long asset + long put (floor) + short call (cap). Defined risk/reward, sleeps well at night.', logic: 'opt_collar' },
      { name: 'Calendar Spread', desc: 'Long near-term option + short far-term same strike. Theta positive, benefits from IV term structure.', logic: 'spread_calendar' },
      { name: 'Pairs Trading (BTC/ETH)', desc: 'Long BTC / short ETH when ratio at 2SD extreme. Mean-reverts on ratio. Market-neutral.', logic: 'pairs_stat_arb' },
      { name: 'Funding Rate Arb', desc: 'Long perp when funding negative, short when funding > spot carry. Delta-hedged with spot.', logic: 'arb_funding' },
    ]},
    { category: 'Scalping Ideas', items: [
      { name: 'VWAP Reclaim Scalp', desc: 'Price deviates >1.5% from VWAP → reclaim with volume surge → scalp back to VWAP + 1SD.', logic: 'scalp_vwap' },
      { name: 'OBV/CVD Flow Scalp', desc: 'OBV trendline break + CVD confirmation. 30s-5m holds. Pure order flow.', logic: 'scalp_flow' },
      { name: 'Funding Rate Scalp', desc: 'Short before 8h funding when rate > 0.01%, cover after. Risk-free if hedged.', logic: 'scalp_funding' },
      { name: 'Order Book Imbalance', desc: 'Bid/ask volume imbalance >3:1 at key level → scalp 2-5 ticks. Microstructure edge.', logic: 'scalp_obi' },
      { name: 'MA Cross Scalp (5m)', desc: 'EMA 9/21 cross on 5m with RSI filter. Tight SL (0.5%), 1:1.5 TP. High win-rate.', logic: 'scalp_ma' },
    ]},
    { category: 'Perpetuals Multi-Indicator Confluence', items: [
      { name: 'Trend + Momentum + Volume', desc: 'EMA 50>200 (trend) + MACD hist >0 (momentum) + vol >1.5x avg (conviction). All 3 align = high prob.', logic: 'confluence_trend_mom_vol' },
      { name: 'Breakout + Funding + OI', desc: 'Donchian break + funding <0.01% (no crowded long) + OI rising (new money). Strong trend confirmation.', logic: 'confluence_breakout_funding_oi' },
      { name: 'SMC + Order Block + FVG', desc: 'Price taps order block + fair value gap fill + CHoCH on lower TF. Institutional entry model.', logic: 'smc_ob_fvg' },
      { name: 'Wyckoff Spring + Volume', desc: 'Spring below support with low volume → immediate reclaim with high volume. Accumulation schematic.', logic: 'wyckoff_spring' },
      { name: 'Harmonic + RSI Div', desc: 'Gartley/bat pattern completion + RSI divergence. Precision entry with defined risk.', logic: 'harmonic_div' },
    ]},
    { category: 'Smart Money Concept (SMC)', items: [
      { name: 'Order Block Entry', desc: 'Identify last up-candle before down-move (bearish OB) or last down-candle before up-move (bullish OB). Enter on retest.', logic: 'smc_order_block' },
      { name: 'Fair Value Gap (FVG)', desc: '3-candle gap where candle 1 high < candle 3 low (bullish FVG) or candle 1 low > candle 3 high (bearish). Price fills 50%+ often.', logic: 'smc_fvg' },
      { name: 'Break of Structure (BOS)', desc: 'Higher high + higher low sequence broken → trend change. Enter on retest of broken structure.', logic: 'smc_bos' },
      { name: 'Change of Character (CHoCH)', desc: 'Lower high + lower low in uptrend (or vice versa). First sign of trend reversal. Early entry.', logic: 'smc_choch' },
      { name: 'Liquidity Sweep', desc: 'Price sweeps equal highs/lows (stop hunt) then reverses. Enter on rejection candle after sweep.', logic: 'smc_liquidity' },
    ]},
    { category: 'Real-World Token (RWA) Ideas', items: [
      { name: 'Tokenized T-Bill Carry', desc: 'Long ONDO/BUIDL (tokenized Treasuries) earning ~5% risk-free. Hedge with short BTC if crypto beta unwanted.', logic: 'rwa_tbill_carry' },
      { name: 'Real Estate Yield', desc: 'Long REAL/PROPC (tokenized real estate) for 8-12% yield. Low correlation to crypto. Monthly rebalance.', logic: 'rwa_real_estate' },
      { name: 'Private Credit Yield', desc: 'Long CFG/MAKER (tokenized private credit) for 10-15% yield. Senior tranche, low default risk.', logic: 'rwa_credit' },
      { name: 'Gold Token Carry', desc: 'Long XAUT (Tether Gold) vs short GC futures. Arb storage cost vs funding. Pure gold carry.', logic: 'rwa_gold_carry' },
      { name: 'Commodity Index Basket', desc: 'Long DBC/USOI/GLD tokenized equivalents. Broad commodity beta, inflation hedge.', logic: 'rwa_commodity_basket' },
    ]},
  ],
};

/* ============================ SMALL COMPONENTS ============================ */
function StatusDot({ on, color }) {
  return React.createElement('span', { style: { display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: on ? (color || COLORS.green) : COLORS.red, boxShadow: on ? `0 0 6px ${color || COLORS.green}` : 'none', marginRight: 6 } });
}

function Card({ children, style, pad, className, onClick }) {
  var E = window.Theme && window.Theme.EXTRA || {};
  return React.createElement('div', {
    className: className || '',
    onClick: onClick,
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

/* ============================ CHART COMPONENT ============================ */
function Chart({ type, data, width, height, color, background }) {
  const canvasRef = React.useRef(null);
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = width || canvas.width;
    const h = height || canvas.height;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    if (background) {
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, w, h);
    }

    const strokeColor = color || COLORS.blue;

    if (type === 'sparkline') {
      if (!data || data.length < 2) return;
      const min = Math.min(...data);
      const max = Math.max(...data);
      const range = max - min || 1;
      ctx.beginPath();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      data.forEach((v, i) => {
        const x = (i / (data.length - 1)) * w;
        const y = h - ((v - min) / range) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      // Gradient fill
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, strokeColor + '33');
      grad.addColorStop(1, strokeColor + '00');
      ctx.fillStyle = grad;
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      ctx.fill();
    } else if (type === 'bar') {
      if (!data || data.length === 0) return;
      const max = Math.max(...data.map(d => d[1]));
      const barW = w / (data.length * 1.5);
      data.forEach((d, i) => {
        const h_ = (d[1] / max) * (h - 10);
        const x = i * (w / data.length) + (w / data.length - barW) / 2;
        const y = h - h_ - 5;
        ctx.fillStyle = strokeColor;
        ctx.fillRect(x, y, barW, h_);
        // Label
        ctx.fillStyle = COLORS.textTertiary;
        ctx.font = '10px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText(d[0], x + barW / 2, h - 2);
      });
    } else if (type === 'distribution') {
      if (!data || data.length === 0) return;
      const max = Math.max(...data.map(d => d[1]));
      const barW = w / data.length;
      data.forEach((d, i) => {
        const h_ = (d[1] / max) * (h - 20);
        const x = i * barW + barW / 2;
        const y = h - h_ - 10;
        ctx.beginPath();
        ctx.moveTo(x - barW / 2, h - 10);
        ctx.lineTo(x - barW / 2, y);
        ctx.lineTo(x + barW / 2, y);
        ctx.lineTo(x + barW / 2, h - 10);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, h, 0, y);
        grad.addColorStop(0, strokeColor + '88');
        grad.addColorStop(1, strokeColor + '22');
        ctx.fillStyle = grad;
        ctx.fill();
        // Label
        ctx.fillStyle = COLORS.textTertiary;
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText(d[0], x, h - 2);
      });
    }
  }, [type, data, width, height, color, background]);

  return React.createElement('canvas', {
    ref: canvasRef,
    width: width || 300,
    height: height || 120,
    style: { width: width || 300, height: height || 120 }
  });
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
        layout: { background: { color: '#020617' }, textColor: '#F8FAFC' },
        grid: { vertLines: { color: '#334155' }, horzLines: { color: '#334155' } },
        crosshair: { mode: LC.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#334155' },
        timeScale: { borderColor: '#334155', timeVisible: true, secondsVisible: false },
      });
      const series = chart.addCandlestickSeries({ upColor: '#22C55E', downColor: '#EF4444', borderUpColor: '#22C55E', borderDownColor: '#EF4444', wickUpColor: '#22C55E', wickDownColor: '#EF4444' });
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
    React.createElement('div', { ref: containerRef, style: { width: '100%', height: height || 380, background: '#020617', borderRadius: 8 } },
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
function OptionStrategyCard({ strategy, spot, onExplain, onSelect }) {
  return React.createElement(Card, { style: { marginBottom: 10, cursor: 'pointer' }, pad: 12, onClick: () => onSelect && onSelect(strategy) },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: (strategy.color || COLORS.blue) + '22', color: strategy.color || COLORS.blue } }, strategy.tag),
        React.createElement('span', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text } }, strategy.name)
      ),
React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
          React.createElement('button', { onClick: (e) => { e.stopPropagation(); onExplain(strategy); }, style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Explain'),
          React.createElement('button', { disabled: true, title: 'Strategy execution not yet implemented', style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textTertiary, cursor: 'not-allowed', fontWeight: 600, opacity: 0.6 } }, 'NOT IMPLEMENTED')
        )
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 6, lineHeight: 1.4 } }, strategy.desc.slice(0, 90) + '…'),
    React.createElement('div', { style: { marginTop: 8 } }, React.createElement(PayoffGraph, { strategy, spot }))
  );
}

/* ============================ TRADING STRATEGY CARD ============================ */
function TradingStrategyCard({ strategy, onExplain, onBacktest }) {
  return React.createElement(Card, { style: { marginBottom: 10 }, pad: 14 },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
      React.createElement('span', { style: { fontSize: 14, fontWeight: 700, color: COLORS.text } }, strategy.name),
React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
          React.createElement('button', { onClick: () => onExplain(strategy), style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Explain'),
          React.createElement('button', { onClick: () => onBacktest(strategy), style: { fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textSecondary, cursor: 'pointer' } }, 'Backtest'),
          React.createElement('button', { disabled: true, title: 'Strategy execution not yet implemented', style: { fontSize: 11, padding: '4px 10px', borderRadius: 6, background: 'transparent', border: `1px solid ${COLORS.border}`, color: COLORS.textTertiary, cursor: 'not-allowed', fontWeight: 700, opacity: 0.6 } }, 'NOT IMPLEMENTED')
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
        React.createElement('div', { style: { display: 'flex', gap: 4 } }, ASSET_TABS.map(a => React.createElement(Tab, { key: a, small: true, active: asset === a, onClick: () => setAsset(a) }, a)))
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
  const [explain, setExplain] = useState(null);
  const [positions, setPositions] = useState(null);
  const [selStrategy, setSelStrategy] = useState(OPTION_STRATEGIES[0]);
  useEffect(() => {
    fetch(`${API}/delta/options?underlying=${underlying}`).then(r => r.json()).then(d => { setOptions(d.options || []); if ((d.options || []).length) setSpot(d.options[0].spot); });
    fetch(`${API}/delta/positions`).then(r => r.json()).then(d => setPositions(d.positions || []));
  }, [underlying]);
  return React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 340px', gap: 18, alignItems: 'start' } },
    React.createElement('div', null,
      React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' } },
        React.createElement('span', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Underlying:'),
        ['BTC', 'ETH', 'XAU'].map(u => React.createElement(Tab, { key: u, active: underlying === u, onClick: () => setUnderlying(u) }, u + ' Options'))
      ),
      React.createElement(Section, { title: `Option Strategies — ${underlying} (${options.length} contracts)` },
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 } },
          OPTION_STRATEGIES.map(s => React.createElement(OptionStrategyCard, { key: s.id, strategy: s, spot, onExplain: setExplain, onSelect: setSelStrategy }))
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
  const [explain, setExplain] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const list = TRADING_STRATEGIES[asset] || [];
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' } },
      ASSET_TABS.map(a => React.createElement(Tab, { key: a, active: asset === a, onClick: () => setAsset(a) }, a + (a === 'MEME' ? ' Coins' : ' Strategies')))
    ),
    backtest
      ? React.createElement(BacktestPanel, { strategy: backtest, onClose: () => setBacktest(null) })
      : React.createElement(Section, { title: `${asset} Trading Strategies` },
        list.map(s => React.createElement(TradingStrategyCard, { key: s.id, strategy: s, onExplain: setExplain, onBacktest: setBacktest }))
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
  const E = window.Theme && window.Theme.EXTRA || {};
  const [asset, setAsset] = useState('BTC');
  const [tf, setTf] = useState('1h');
  const [sub, setSub] = useState('features');
  const ASSETS = ['BTC', 'ETH', 'XAU', 'SOL', 'XRP', 'DOGE'];
  const TFS = ['15m', '1h', '4h', '1d'];
  const subTabs = [
    { id: 'features', label: 'Features' },
    { id: 'micro', label: 'Micro-Features' },
    { id: 'regime', label: 'Regime' },
    { id: 'alpha', label: 'Alpha Zoo' },
    { id: 'leakage', label: 'Leakage' },
    { id: 'registry', label: 'Registry' },
  ];
  return React.createElement('div', null,
    React.createElement(Section, { title: 'Feature Engineering Console', right: React.createElement('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
        ASSETS.map(a => React.createElement(Tab, { key: a, small: true, active: asset === a, onClick: () => setAsset(a) }, a)),
        React.createElement('span', { style: { color: COLORS.border, fontFamily: E.fontMono || 'inherit' } }, '·'),
        sub !== 'micro' && TFS.map(t => React.createElement(Tab, { key: t, small: true, active: tf === t, onClick: () => setTf(t) }, t))
      ) },
      React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' } },
        subTabs.map(s => React.createElement(Tab, { key: s.id, small: true, active: sub === s.id, onClick: () => setSub(s.id) }, s.label))
      ),
      React.createElement(AnalyticsInsightCards, { asset, tf }),
      sub === 'features' && React.createElement(FeaturesView, { asset, tf }),
      sub === 'micro' && React.createElement(MicroFeaturesView, { asset }),
      sub === 'regime' && React.createElement(RegimeView, { asset, tf }),
      sub === 'alpha' && React.createElement(AlphaZooView, { asset, tf }),
      sub === 'leakage' && React.createElement(LeakageView, { asset, tf }),
      sub === 'registry' && React.createElement(RegistryView, null)
    )
  );
}

function AnalyticsInsightCards({ asset, tf }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const [f, r, a] = await Promise.all([
          fetch(`${API}/analytics/features?asset=${asset}&timeframe=${tf}&limit=300`).then(r => r.json()),
          fetch(`${API}/analytics/regime?asset=${asset}&timeframe=${tf}`).then(r => r.json()),
          fetch(`${API}/analytics/alpha-zoo?asset=${asset}&timeframe=${tf}&limit=300`).then(r => r.json()),
        ]);
        setData({ features: f, regime: r, alpha: a });
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [asset, tf]);

  if (!data) return React.createElement('div', { style: { height: 80 } });

  const f = data.features || {};
  const r = data.regime || {};
  const a = data.alpha || {};

  // Feature distribution by category
  const catDist = (f.features || []).reduce((acc, feat) => {
    acc[feat.category] = (acc[feat.category] || 0) + 1;
    return acc;
  }, {});

  // Top features by absolute value
  const topFeats = (f.features || [])
    .filter(feat => feat.value != null)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 8);

  return React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginBottom: 16 } },
    // Regime Card
    React.createElement(Card, { pad: 14 },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
        React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text } }, 'MARKET REGIME'),
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, tf)
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 } },
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.bgElevated, borderRadius: 8 } },
          React.createElement('div', { style: { fontSize: 24, fontWeight: 800, color: r.trend_direction === 'up' ? COLORS.green : r.trend_direction === 'down' ? COLORS.red : COLORS.amber, fontFamily: 'JetBrains Mono, monospace' } }, String(r.trend_direction || '-').toUpperCase()),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'TREND')
        ),
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.bgElevated, borderRadius: 8 } },
          React.createElement('div', { style: { fontSize: 24, fontWeight: 800, color: r.volatility_regime === 'high' ? COLORS.red : COLORS.green, fontFamily: 'JetBrains Mono, monospace' } }, String(r.volatility_regime || '-').toUpperCase()),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'VOLATILITY')
        ),
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.bgElevated, borderRadius: 8 } },
          React.createElement('div', { style: { fontSize: 24, fontWeight: 800, color: r.momentum_score > 0 ? COLORS.green : COLORS.red, fontFamily: 'JetBrains Mono, monospace' } }, (r.momentum_score || 0).toFixed(2)),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'MOMENTUM')
        )
      )
    ),
    // Feature Category Distribution
    React.createElement(Card, { pad: 14 },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
        React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text } }, 'FEATURE CATEGORIES'),
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, Object.values(catDist).reduce((a,b)=>a+b,0) + ' features')
      ),
      React.createElement(Chart, {
        type: 'bar',
        data: Object.entries(catDist).map(([k,v]) => [k, v]),
        width: '100%',
        height: 100,
        color: COLORS.blue
      })
    ),
    // Top Features by Magnitude
    React.createElement(Card, { pad: 14 },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
        React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text } }, 'TOP FEATURES (|VALUE|)'),
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Latest snapshot')
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
        topFeats.map(feat => React.createElement('div', { key: feat.name, style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 10px', background: COLORS.bgElevated, borderRadius: 6 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
            React.createElement('span', { style: { width: 10, height: 10, borderRadius: 2, background: CAT_COLOR[feat.category] || COLORS.blue } }),
            React.createElement('span', { style: { fontSize: 11, fontWeight: 600, color: COLORS.text, fontFamily: 'JetBrains Mono, monospace' } }, feat.name),
            React.createElement('span', { style: { fontSize: 10, color: CAT_COLOR[feat.category] || COLORS.blue } }, feat.category)
          ),
          React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: feat.value >= 0 ? COLORS.green : COLORS.red, fontFamily: 'JetBrains Mono, monospace' } }, feat.value.toFixed(4))
        ))
      )
    ),
    // Alpha Zoo Summary
    React.createElement(Card, { pad: 14 },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
        React.createElement('span', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text } }, 'ALPHA ZOO'),
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, (a.factors || []).length + ' factors')
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 } },
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.green + '22', borderRadius: 8, border: `1px solid ${COLORS.green}44` } },
          React.createElement('div', { style: { fontSize: 20, fontWeight: 800, color: COLORS.green, fontFamily: 'JetBrains Mono, monospace' } }, (a.factors || []).filter(f => f.accepted).length),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'ACCEPTED')
        ),
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.red + '22', borderRadius: 8, border: `1px solid ${COLORS.red}44` } },
          React.createElement('div', { style: { fontSize: 20, fontWeight: 800, color: COLORS.red, fontFamily: 'JetBrains Mono, monospace' } }, (a.factors || []).filter(f => !f.accepted).length),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'REJECTED')
        ),
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.amber + '22', borderRadius: 8, border: `1px solid ${COLORS.amber}44` } },
          React.createElement('div', { style: { fontSize: 20, fontWeight: 800, color: COLORS.amber, fontFamily: 'JetBrains Mono, monospace' } }, (a.factors || []).reduce((sum,f)=>sum+(f.ic||0),0) / Math.max((a.factors||[]).length,1) || 0).toFixed(3),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'AVG IC')
        ),
        React.createElement('div', { style: { textAlign: 'center', padding: '8px', background: COLORS.cyan + '22', borderRadius: 8, border: `1px solid ${COLORS.cyan}44` } },
          React.createElement('div', { style: { fontSize: 20, fontWeight: 800, color: COLORS.cyan, fontFamily: 'JetBrains Mono, monospace' } }, (a.factors || []).reduce((sum,f)=>sum+(f.ir||0),0) / Math.max((a.factors||[]).length,1) || 0).toFixed(3),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'AVG IR')
        )
      )
    )
  );
}

function AnalyticsHeader({ data }) {
  return React.createElement('div', { style: { display: 'flex', gap: 14, alignItems: 'center', marginBottom: 12, fontSize: 12, color: COLORS.textSecondary, fontFamily: 'JetBrains Mono, monospace' } },
    data && data.asset && React.createElement('span', null, 'ASSET ' + data.asset),
    data && data.timeframe && React.createElement('span', null, 'TF ' + data.timeframe),
    data && data.bars != null && React.createElement('span', null, 'BARS ' + data.bars),
    data && data.count != null && React.createElement('span', null, 'COUNT ' + data.count)
  );
}

function FeaturesView({ asset, tf }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [catFilter, setCatFilter] = useState('ALL');
  const load = () => {
    fetch(`${API}/analytics/features?asset=${asset}&timeframe=${tf}&limit=300`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) { setData(d); setErr(null); } })
      .catch(() => setErr('failed to load features'));
  };
  useEffect(() => { setData(null); load(); }, [asset, tf]);
  const cats = data ? (data.categories || []) : [];
  const feats = data ? (data.features || []).filter(f => catFilter === 'ALL' || f.category === catFilter) : [];
  return React.createElement('div', null,
    React.createElement(AnalyticsHeader, { data }),
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' } },
      React.createElement(Tab, { small: true, active: catFilter === 'ALL', onClick: () => setCatFilter('ALL') }, 'ALL'),
      cats.map(c => React.createElement(Tab, { key: c, small: true, active: catFilter === c, onClick: () => setCatFilter(c) }, c))
    ),
    err && React.createElement('div', { style: { color: COLORS.red, fontSize: 12 } }, err),
    React.createElement(Card, { pad: 12 },
      React.createElement('div', { style: { maxHeight: 520, overflowY: 'auto' } },
        React.createElement('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } },
          React.createElement('thead', null, React.createElement('tr', null,
            ['Feature', 'Category', 'Value', 'Lookback', 'Norm'].map(h => React.createElement('th', { key: h, style: { textAlign: 'left', padding: '6px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontFamily: 'JetBrains Mono, monospace', fontSize: 10, letterSpacing: 0.4 } }, h))
          )),
          React.createElement('tbody', null,
            feats.map(f => React.createElement('tr', { key: f.name },
              React.createElement('td', { style: { padding: '5px 8px', fontFamily: 'JetBrains Mono, monospace', color: COLORS.text, fontWeight: 600, borderBottom: '1px solid ' + COLORS.border } }, f.name),
              React.createElement('td', { style: { padding: '5px 8px', color: CAT_COLOR[f.category] || COLORS.blue, borderBottom: '1px solid ' + COLORS.border, fontSize: 11 } }, f.category),
              React.createElement('td', { style: { padding: '5px 8px', fontFamily: 'JetBrains Mono, monospace', color: f.value == null ? COLORS.textTertiary : COLORS.textSecondary, borderBottom: '1px solid ' + COLORS.border, textAlign: 'right' } }, f.value == null ? '—' : (Math.abs(f.value) >= 1000 ? f.value.toExponential(2) : Number(f.value).toFixed(4))),
              React.createElement('td', { style: { padding: '5px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border } }, f.lookback),
              React.createElement('td', { style: { padding: '5px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontSize: 10 } }, f.normalization)
            )),
            feats.length === 0 && React.createElement('tr', null, React.createElement('td', { colSpan: 5, style: { padding: 12, color: COLORS.textTertiary, textAlign: 'center' } }, 'No features'))
          )
        )
      )
    )
  );
}

function MicroFeaturesView({ asset }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => {
    fetch(`${API}/analytics/microfeatures?underlying=${asset}&symbol=${asset}USD`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && !d.error) { setData(d); setErr(null); } else setErr((d && d.error) || 'failed'); })
      .catch(() => setErr('failed to load micro-features'));
  };
  useEffect(() => { setData(null); load(); }, [asset]);
  const render = (fam) => {
    const f = (data && data[fam] && data[fam].features) || null;
    if (!f || !Object.keys(f).length) return null;
    return React.createElement(Card, { pad: 12, style: { background: (window.Theme && window.Theme.EXTRA && window.Theme.EXTRA.glass) } },
      React.createElement('div', { style: { fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: COLORS.text, letterSpacing: 0.5, marginBottom: 8 } }, String(fam).toUpperCase().replace('_', ' ')),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 14px' } },
        Object.keys(f).filter(k => typeof f[k] !== 'object').map(k => React.createElement('div', { key: k, style: { display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 } }, k),
          React.createElement('span', { style: { color: COLORS.textSecondary, fontFamily: 'JetBrains Mono, monospace', textAlign: 'right' } }, (typeof f[k] === 'number' ? (Math.abs(f[k]) >= 1000 ? Number(f[k]).toFixed(0) : Number(f[k]).toFixed(4)) : String(f[k])))
        ))
      )
    );
  };
  return React.createElement('div', null,
    (err || data === null) && React.createElement('div', { style: { color: COLORS.red, fontSize: 12, marginBottom: 10 } }, err || 'loading…'),
    data && React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 } },
      render('derivatives_symbol'),
      render('cross_asset'),
      render('options_iv'),
      render('journal'),
      render('event')
    ),
    data && data.cross_asset && data.cross_asset.sector_breakdown && React.createElement(Card, { pad: 12, style: { marginTop: 12 } },
      React.createElement('div', { style: { fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: COLORS.text, letterSpacing: 0.5, marginBottom: 8 } }, 'SECTOR MOMENTUM (24H %)'),
      React.createElement('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
        Object.entries(data.cross_asset.sector_breakdown).map(([k, v]) => React.createElement('span', { key: k, style: { padding: '4px 10px', borderRadius: 6, fontSize: 12, fontFamily: 'JetBrains Mono, monospace', background: COLORS.bgElevated, border: '1px solid ' + COLORS.border, color: v >= 0 ? COLORS.green : COLORS.red } }, k + ' ' + (v >= 0 ? '+' : '') + v + '%'))
      )
    )
  );
}

function RegimeView({ asset, tf }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setD(null);
    fetch(`${API}/analytics/regime?asset=${asset}&timeframe=${tf}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data && !data.error) setD(data); else setErr((data && data.error) || 'failed'); })
      .catch(() => setErr('failed'));
  }, [asset, tf]);
  const rows = d ? [
    ['Trend', d.trend, d.trend_strength, d.trend === 'up' ? COLORS.green : d.trend === 'down' ? COLORS.red : COLORS.amber],
    ['Volatility', d.volatility, d.vol_percentile, d.volatility === 'high' ? COLORS.red : COLORS.textSecondary],
    ['Liquidity', d.liquidity, null, COLORS.textSecondary],
    ['Momentum', Number(d.momentum).toFixed(2), null, Number(d.momentum) >= 0 ? COLORS.green : COLORS.red],
    ['Session', d.session, null, COLORS.textSecondary],
    ['Stress', d.stress, d.confidence, d.stress === 'elevated' ? COLORS.amber : COLORS.textSecondary],
  ] : [];
  return React.createElement('div', null,
    React.createElement(AnalyticsHeader, { data: d }),
    err && React.createElement('div', { style: { color: COLORS.red, fontSize: 12 } }, err),
    d && React.createElement('div', null,
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 14 } },
        React.createElement(Card, { pad: 18, style: { borderColor: d.trend === 'up' ? COLORS.green : d.trend === 'down' ? COLORS.red : COLORS.amber } },
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace' } }, 'DOMINANT REGIME'),
          React.createElement('div', { style: { fontSize: 26, fontWeight: 800, color: d.trend === 'up' ? COLORS.green : d.trend === 'down' ? COLORS.red : COLORS.amber, fontFamily: (window.Theme && window.Theme.EXTRA && window.Theme.EXTRA.fontDisplay) } }, String(d.dominant || '-').toUpperCase()),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'confidence ' + Number(d.confidence || 0).toFixed(2))
        ),
        React.createElement(Card, { pad: 18 },
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace' } }, 'TREND STRENGTH'),
          React.createElement('div', { style: { fontSize: 26, fontWeight: 800, color: COLORS.text, fontFamily: 'JetBrains Mono, monospace' } }, Number(d.trend_strength || 0).toFixed(2)),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, '0 = weak · 1 = strong')
        ),
        React.createElement(Card, { pad: 18 },
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace' } }, 'VOL PERCENTILE'),
          React.createElement('div', { style: { fontSize: 26, fontWeight: 800, color: COLORS.text, fontFamily: 'JetBrains Mono, monospace' } }, Number(d.vol_percentile || 0).toFixed(2)),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, '0 = low vol · 1 = high vol')
        )
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 } },
        rows.map(r => React.createElement(Card, { key: r[0], pad: 12 },
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace' } }, r[0].toUpperCase()),
          React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: r[3], marginTop: 3, fontFamily: 'JetBrains Mono, monospace' } }, String(r[1])),
          r[2] != null && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, Number(r[2]).toFixed(3))
        ))
      )
    )
  );
}

function AlphaZooView({ asset, tf }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setD(null);
    fetch(`${API}/analytics/alpha-zoo?asset=${asset}&timeframe=${tf}&limit=300`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data && !data.error) setD(data); else setErr((data && data.error) || 'failed'); })
      .catch(() => setErr('failed'));
  }, [asset, tf]);
  const results = (d && d.results) || [];
  return React.createElement('div', null,
    React.createElement(AnalyticsHeader, { data: d }),
    err && React.createElement('div', { style: { color: COLORS.red, fontSize: 12 } }, err),
    React.createElement(Card, { pad: 12 },
      React.createElement('div', { style: { maxHeight: 520, overflowY: 'auto' } },
        React.createElement('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } },
          React.createElement('thead', null, React.createElement('tr', null,
            ['Factor', 'Status', 'IC mean', 'IR', 'Stability', 'Turnover'].map(h => React.createElement('th', { key: h, style: { textAlign: 'left', padding: '6px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontFamily: 'JetBrains Mono, monospace', fontSize: 10 } }, h))
          )),
          React.createElement('tbody', null,
            results.map(r => React.createElement('tr', { key: r.name },
              React.createElement('td', { style: { padding: '5px 8px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, color: COLORS.text, borderBottom: '1px solid ' + COLORS.border } }, r.name),
              React.createElement('td', { style: { padding: '5px 8px', borderBottom: '1px solid ' + COLORS.border } },
                React.createElement('span', { style: { padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700, background: r.accepted ? COLORS.green + '22' : COLORS.bgElevated, color: r.accepted ? COLORS.green : COLORS.textTertiary, border: '1px solid ' + (r.accepted ? COLORS.green : COLORS.border) } }, r.accepted ? 'ACCEPTED' : 'REJECTED')
              ),
              React.createElement('td', { style: { padding: '5px 8px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', color: r.ic_mean >= 0 ? COLORS.green : COLORS.red, borderBottom: '1px solid ' + COLORS.border } }, Number(r.ic_mean).toFixed(4)),
              React.createElement('td', { style: { padding: '5px 8px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', color: COLORS.textSecondary, borderBottom: '1px solid ' + COLORS.border } }, Number(r.ic_sharpe).toFixed(2)),
              React.createElement('td', { style: { padding: '5px 8px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', color: COLORS.textSecondary, borderBottom: '1px solid ' + COLORS.border } }, Number(r.stability).toFixed(2)),
              React.createElement('td', { style: { padding: '5px 8px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', color: COLORS.textSecondary, borderBottom: '1px solid ' + COLORS.border } }, Number(r.turnover).toFixed(2))
            )),
            results.length === 0 && React.createElement('tr', null, React.createElement('td', { colSpan: 6, style: { padding: 12, color: COLORS.textTertiary, textAlign: 'center' } }, 'No factors evaluated'))
          )
        )
      ),
      results.length > 0 && React.createElement('div', { style: { marginTop: 8, fontSize: 11, color: COLORS.textTertiary, fontFamily: 'JetBrains Mono, monospace' } },
        'Gates: IC ≥ 0.01 · IR ≥ 0.5 · turnover < 0.5 · stability > 0.3 · IC std < 0.5'
      )
    )
  );
}

function LeakageView({ asset, tf }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setD(null);
    fetch(`${API}/analytics/leakage?asset=${asset}&timeframe=${tf}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data && !data.error) setD(data); else setErr((data && data.error) || 'failed'); })
      .catch(() => setErr('failed'));
  }, [asset, tf]);
  const details = (d && d.details) || [];
  const sevColor = { critical: COLORS.red, warning: COLORS.amber, info: COLORS.blue };
  return React.createElement('div', null,
    React.createElement(AnalyticsHeader, { data: d }),
    err && React.createElement('div', { style: { color: COLORS.red, fontSize: 12 } }, err),
    d && React.createElement('div', { style: { display: 'flex', gap: 12, marginBottom: 12 } },
      React.createElement(Card, { pad: 12 }, React.createElement('div', { style: { fontSize: 22, fontWeight: 800, color: COLORS.text } }, d.total_checks), React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Total checks')),
      React.createElement(Card, { pad: 12, style: { borderColor: COLORS.green } }, React.createElement('div', { style: { fontSize: 22, fontWeight: 800, color: COLORS.green } }, d.passed), React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Passed')),
      React.createElement(Card, { pad: 12, style: { borderColor: COLORS.red } }, React.createElement('div', { style: { fontSize: 22, fontWeight: 800, color: COLORS.red } }, d.failed), React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Failed'))
    ),
    React.createElement(Card, { pad: 12 },
      React.createElement('div', { style: { maxHeight: 420, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 } },
        details.map((c, i) => React.createElement('div', { key: i, style: { display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, padding: '8px 10px', borderRadius: 8, background: COLORS.bgElevated, border: '1px solid ' + COLORS.border } },
          React.createElement('span', { style: { padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700, background: (sevColor[c.severity] || COLORS.blue) + '22', color: sevColor[c.severity] || COLORS.blue } }, c.type),
          React.createElement('span', { style: { fontWeight: 600, color: COLORS.text, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, width: 150 } }, c.check),
          React.createElement('span', { style: { flex: 1, color: COLORS.textTertiary, fontSize: 11 } }, c.message || ''),
          React.createElement('span', { style: { fontWeight: 800, color: c.passed ? COLORS.green : COLORS.red } }, c.passed ? 'PASS' : 'FAIL')
        )),
        details.length === 0 && React.createElement('div', { style: { color: COLORS.textTertiary, textAlign: 'center' } }, 'No checks')
      )
    )
  );
}

function RegistryView() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [cat, setCat] = useState('ALL');
  useEffect(() => { fetch(`${API}/analytics/registry`).then(r => r.ok ? r.json() : null).then(x => { if (x && !x.error) setD(x); else setErr((x && x.error) || 'failed'); }).catch(() => setErr('failed')); }, []);
  const features = (d && Array.isArray(d.features)) ? d.features : [];
  const cats = [...new Set(features.map(f => f.category))];
  const feats = features.filter(f => cat === 'ALL' || f.category === cat);
  return React.createElement('div', null,
    err && React.createElement('div', { style: { color: COLORS.red, fontSize: 12 } }, err),
    d && React.createElement('div', null,
      React.createElement(AnalyticsHeader, { data: { asset: 'REGISTRY', count: d.count } }),
      React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' } },
        React.createElement(Tab, { small: true, active: cat === 'ALL', onClick: () => setCat('ALL') }, 'ALL'),
        cats.map(c => React.createElement(Tab, { key: c, small: true, active: cat === c, onClick: () => setCat(c) }, c))
      ),
      React.createElement(Card, { pad: 12 },
        React.createElement('div', { style: { maxHeight: 520, overflowY: 'auto' } },
          React.createElement('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } },
            React.createElement('thead', null, React.createElement('tr', null,
              ['Feature', 'Category', 'Lookback', 'Norm', 'Formula'].map(h => React.createElement('th', { key: h, style: { textAlign: 'left', padding: '6px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontFamily: 'JetBrains Mono, monospace', fontSize: 10 } }, h))
            )),
            React.createElement('tbody', null,
              feats.map(f => React.createElement('tr', { key: f.name },
                React.createElement('td', { style: { padding: '5px 8px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, color: COLORS.text, borderBottom: '1px solid ' + COLORS.border } }, f.name),
                React.createElement('td', { style: { padding: '5px 8px', color: CAT_COLOR[f.category] || COLORS.blue, borderBottom: '1px solid ' + COLORS.border, fontSize: 11 } }, f.category),
                React.createElement('td', { style: { padding: '5px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border } }, f.lookback),
                React.createElement('td', { style: { padding: '5px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontSize: 10 } }, f.normalization),
                React.createElement('td', { style: { padding: '5px 8px', color: COLORS.textTertiary, borderBottom: '1px solid ' + COLORS.border, fontSize: 10 } }, f.formula)
              )),
              feats.length === 0 && React.createElement('tr', null, React.createElement('td', { colSpan: 5, style: { padding: 12, color: COLORS.textTertiary, textAlign: 'center' } }, 'No features'))
            )
          )
        )
      )
    )
  );
}

function BotsView() {
  const [cat, setCat] = useState('btc');
  const [selBot, setSelBot] = useState(null);
  const [running, setRunning] = useState({});
  const [logs, setLogs] = useState({});

  const bots = BOTS[cat] || [];
  const categories = BOT_CATEGORIES;

  const toggleBot = async (bot) => {
    const id = bot.id;
    const next = !running[id];
    setRunning(prev => ({ ...prev, [id]: next }));
    if (next) {
      try {
        const r = await fetch(`${API}/bot/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + BRIDGE_TOKEN },
          body: JSON.stringify({ bot_id: id, category: cat, params: bot.params })
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'Failed to start');
        addLog(id, `[${new Date().toLocaleTimeString()}] Started: ${bot.name}`);
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.ping();
      } catch (e) {
        setRunning(prev => ({ ...prev, [id]: false }));
        addLog(id, `[${new Date().toLocaleTimeString()}] Error: ${e.message}`);
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.blip();
      }
    } else {
      try {
        await fetch(`${API}/bot/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + BRIDGE_TOKEN },
          body: JSON.stringify({ bot_id: id })
        });
        addLog(id, `[${new Date().toLocaleTimeString()}] Stopped: ${bot.name}`);
      } catch (e) {
        addLog(id, `[${new Date().toLocaleTimeString()}] Stop error: ${e.message}`);
      }
    }
  };

  const addLog = (id, msg) => {
    setLogs(prev => ({ ...prev, [id]: [...(prev[id] || []), msg].slice(-50) }));
  };

  const botLogs = selBot ? (logs[selBot.id] || []) : [];

  return React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '300px 1fr', gap: 18, height: 'calc(100vh - 120px)' } },
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
      React.createElement(Card, { pad: 14 },
        React.createElement('div', { style: { fontSize: 14, fontWeight: 800, marginBottom: 12, color: COLORS.text } }, 'BOT CATEGORIES'),
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
          categories.map(c => React.createElement('button', {
            key: c.id,
            onClick: () => { setCat(c.id); setSelBot(null); },
            style: {
              padding: '10px 12px', borderRadius: 8, textAlign: 'left', border: 'none',
              background: cat === c.id ? c.color + '22' : 'transparent',
              borderLeft: cat === c.id ? `3px solid ${c.color}` : '3px solid transparent',
              color: cat === c.id ? c.color : COLORS.textSecondary,
              fontSize: 13, fontWeight: cat === c.id ? 700 : 500, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8
            }
          }, c.icon, ' ', c.label))
        )
      ),
      bots.length && React.createElement(Card, { pad: 14, style: { flex: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 300px)' } },
        React.createElement('div', { style: { fontSize: 14, fontWeight: 800, marginBottom: 12, color: COLORS.text } }, 'AVAILABLE BOTS'),
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
          bots.map(b => React.createElement('div', {
            key: b.id,
            onClick: () => setSelBot(b),
            style: {
              padding: '12px', borderRadius: 8, cursor: 'pointer',
              background: selBot?.id === b.id ? COLORS.blue + '11' : COLORS.bgElevated,
              border: selBot?.id === b.id ? `1px solid ${COLORS.blue}` : `1px solid ${COLORS.border}`,
              transition: 'all 0.15s'
            }
          },
            React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 } },
              React.createElement('div', null,
                React.createElement('div', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text } }, b.name),
                React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.5 } }, b.class)
              ),
              React.createElement('span', { style: { fontSize: 10, padding: '2px 6px', borderRadius: 4, background: b.status === 'ready' ? COLORS.green + '22' : COLORS.amber + '22', color: b.status === 'ready' ? COLORS.green : COLORS.amber, fontWeight: 700 } }, b.status.toUpperCase())
            ),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, lineHeight: 1.4, marginBottom: 8 } }, b.desc.slice(0, 100) + '…'),
            React.createElement('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' } },
              React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Risk: ' + b.risk),
              React.createElement('span', { style: { color: COLORS.textTertiary } }, b.assets.join(', ')),
              running[b.id] && React.createElement('span', { style: { color: COLORS.green, fontWeight: 700 } }, '● RUNNING')
            )
          ))
        )
      )
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
      selBot ? React.createElement(Card, { pad: 16, style: { flex: 1, display: 'flex', flexDirection: 'column' } },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 } },
          React.createElement('div', null,
            React.createElement('div', { style: { fontSize: 16, fontWeight: 800, color: COLORS.text } }, selBot.name),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 2 } }, selBot.class.toUpperCase() + ' • ' + selBot.logic.replace('_', ' ').toUpperCase())
          ),
          React.createElement('button', {
            onClick: () => toggleBot(selBot),
            disabled: running[selBot.id],
            style: {
              padding: '10px 20px', borderRadius: 8, border: 'none', fontWeight: 700, fontSize: 13,
              background: running[selBot.id] ? COLORS.red : COLORS.green,
              color: '#000', cursor: 'pointer',
            }
          }, running[selBot.id] ? 'STOP BOT' : 'START BOT')
        ),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.6, marginBottom: 16, paddingBottom: 16, borderBottom: `1px solid ${COLORS.border}` } }, selBot.desc),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 16 } },
          Object.entries(selBot.params).map(([k, v]) => React.createElement(Card, { pad: 10, key: k },
            React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 } }, k),
            React.createElement('div', { style: { fontSize: 14, fontWeight: 700, color: COLORS.text, fontFamily: 'JetBrains Mono, monospace' } }, String(v))
          ))
        ),
        React.createElement('div', { style: { fontSize: 11, fontWeight: 700, color: COLORS.textTertiary, marginBottom: 8, letterSpacing: 0.5 } }, 'BOT LOG'),
        React.createElement('div', { style: { flex: 1, background: '#08090c', borderRadius: 8, padding: 10, overflowY: 'auto', fontSize: 11, fontFamily: 'JetBrains Mono, monospace', color: COLORS.green, minHeight: 180 } },
          botLogs.length === 0 ? React.createElement('div', { style: { color: COLORS.textTertiary, textAlign: 'center', padding: 20 } }, 'No logs yet. Start the bot to see activity.') :
          botLogs.map((l, i) => React.createElement('div', { key: i, style: { padding: '2px 0', borderBottom: `1px solid ${COLORS.border}22` } }, l))
        )
      ) :
      cat === 'trade_logic' ? React.createElement(Card, { pad: 16, style: { flex: 1 } },
        React.createElement('div', { style: { fontSize: 16, fontWeight: 800, color: COLORS.text, marginBottom: 16 } }, 'TRADE LOGIC CLASSIFICATION'),
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 16 } },
          BOTS.trade_logic.map(group => React.createElement(Card, { pad: 14, key: group.category },
            React.createElement('div', { style: { fontSize: 13, fontWeight: 800, color: COLORS.magenta || '#ff00ff', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 } }, '🧠', group.category),
            React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
              group.items.map(item => React.createElement('div', {
                style: { padding: '10px 12px', background: COLORS.bgElevated, borderRadius: 8, border: `1px solid ${COLORS.border}`, cursor: 'pointer' }
              },
                React.createElement('div', { style: { fontSize: 12, fontWeight: 700, color: COLORS.text, marginBottom: 4 } }, item.name),
                React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, lineHeight: 1.5 } }, item.desc),
                React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginTop: 4, fontFamily: 'JetBrains Mono, monospace' } }, 'Logic: ' + item.logic)
              ))
            )
          ))
        )
      ) :
      React.createElement(Card, { pad: 16, style: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' } },
        React.createElement('div', { style: { textAlign: 'center', color: COLORS.textTertiary } },
          React.createElement('div', { style: { fontSize: 14, fontWeight: 700, marginBottom: 8 } }, 'Select a bot to view details'),
          React.createElement('div', { style: { fontSize: 12 } }, 'Or click "TRADE LOGIC" to explore strategy classifications')
        )
      )
    )
  );
}

const CAT_COLOR = {
  price: '#4e8cff', momentum: '#22C55E', volatility: '#f0a500', volume: '#00c8e8',
  microstructure: '#9b59b6', derivatives: '#EF4444', cross_asset: '#e91e63', time: '#8b8fa3',
  regime: '#ff9800',
};


/* ============================ MT5 FLOW TERMINAL ============================ */
const FLOW_RAIL = [
  { id: 'dashboard', label: 'DASHBOARD', icon: 'layout-dashboard' },
  { id: 'bots', label: 'BOTS', icon: 'bot' },
  { id: 'options', label: 'OPTIONS', icon: 'candlestick-chart' },
  { id: 'strategies', label: 'STRATEGIES', icon: 'layers' },
  { id: 'calendar', label: 'CALENDAR', icon: 'calendar' },
  { id: 'library', label: 'LIBRARY', icon: 'library' },
  { id: 'journal', label: 'JOURNAL', icon: 'notebook-pen' },
  { id: 'analytics', label: 'ANALYTICS', icon: 'bar-chart-3' },
  { id: 'terminal', label: 'TERM', icon: 'terminal' },
  { id: 'settings', label: 'SETTINGS', icon: 'settings' },
];

function FlowRail({ active, onNav }) {
  useEffect(() => { try { if (window.lucide && window.lucide.createIcons) window.lucide.createIcons(); } catch (e) {} });
  return React.createElement('nav', { 'aria-label': 'Terminal sections', style: { display: 'flex', flexDirection: 'column', gap: 2, background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '10px 6px', alignSelf: 'start', position: 'sticky', top: 96 } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 6 } },
      React.createElement('div', { style: { width: 0, height: 0, borderLeft: '9px solid transparent', borderRight: '9px solid transparent', borderBottom: '14px solid ' + COLORS.blue } })
    ),
    FLOW_RAIL.map(t => React.createElement('button', { key: t.id, onClick: () => onNav && onNav(t.id), title: t.label,
      style: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: '9px 2px', borderRadius: 8, border: 'none', cursor: 'pointer',
        background: active === t.id ? COLORS.blue + '22' : 'transparent',
        boxShadow: active === t.id ? `inset 2px 0 0 ${COLORS.blue}` : 'none',
        color: active === t.id ? COLORS.text : COLORS.textTertiary } },
      React.createElement('i', { 'data-lucide': t.icon, style: { width: 18, height: 18 } }),
      React.createElement('span', { style: { fontSize: 8, fontWeight: 700, letterSpacing: 0.4 } }, t.label)))
  );
}

function FlowTopbar({ health, search, setSearch, onSearch, onModeToggle, modeBusy }) {
  const [bal, setBal] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/balance`);
        const d = await r.json();
        if (d && !d.error) setBal(d);
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, []);
  const pick = (o, ks) => { if (!o) return null; for (let i = 0; i < ks.length; i++) { if (o[ks[i]] != null && !isNaN(Number(o[ks[i]]))) return Number(o[ks[i]]); } return null; };
  const balance = pick(bal, ['balance', 'wallet_balance', 'total', 'available']) ;
  const equity = pick(bal, ['equity', 'total_equity']) ?? balance;
  const upnl = pick(bal, ['unrealized_pnl', 'unrealizedPnl', 'upnl', 'pnl']);
  return React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12, background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '10px 14px', flexWrap: 'wrap' } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
      React.createElement('div', { style: { width: 0, height: 0, borderLeft: '10px solid transparent', borderRight: '10px solid transparent', borderBottom: '16px solid ' + COLORS.blue } }),
      React.createElement('span', { style: { fontSize: 15, fontWeight: 800, letterSpacing: 0.4 } }, 'MT5 FLOW')
    ),
    React.createElement('span', { style: { fontSize: 11, fontWeight: 700, padding: '5px 12px', borderRadius: 7, background: COLORS.purple + '22', color: COLORS.purple, border: `1px solid ${COLORS.purple}55` } }, 'Scalping Mode'),
    (() => {
      const trading = health && health.mode === 'trading';
      const noAuth = !!(health && !health.has_auth);
      return React.createElement('button', { onClick: () => { if (!modeBusy && !noAuth && onModeToggle) onModeToggle(trading ? 'read_only' : 'trading'); }, disabled: modeBusy || noAuth, title: noAuth ? 'Add API keys in Settings to enable trading mode' : 'Toggle trading mode',
        style: { fontSize: 10, fontWeight: 800, letterSpacing: 0.4, padding: '5px 12px', borderRadius: 7, border: `1px solid ${trading ? COLORS.green : COLORS.amber}`, background: trading ? COLORS.green + '1c' : 'transparent', color: trading ? COLORS.green : COLORS.amber, cursor: (modeBusy || noAuth) ? 'not-allowed' : 'pointer', opacity: (modeBusy || noAuth) ? 0.55 : 1 } },
        trading ? '▲ TRADING' : '● READ ONLY');
    })(),
    React.createElement('input', {
      value: search, placeholder: 'Search markets, pairs, bots…',
      onChange: (e) => setSearch(e.target.value),
      onKeyDown: (e) => { if (e.key === 'Enter' && search.trim() && onSearch) onSearch(search.trim().toUpperCase()); },
      style: { flex: 1, minWidth: 180, padding: '8px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13 }
    }),
    React.createElement('div', { style: { display: 'flex', gap: 18, alignItems: 'center', marginLeft: 'auto' } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Balance'),
        React.createElement('div', { style: { fontSize: 13, fontWeight: 700, fontFamily: "'Fira Code', monospace" } }, balance != null ? fmtCur(balance) : '--')
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Equity'),
        React.createElement('div', { style: { fontSize: 13, fontWeight: 700, fontFamily: "'Fira Code', monospace" } }, equity != null ? fmtCur(equity) : '--')
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Unrealized PnL'),
        React.createElement('div', { style: { fontSize: 13, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: upnl == null ? COLORS.text : (upnl >= 0 ? COLORS.green : COLORS.red) } }, upnl != null ? fmtCur(upnl) : '--')
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}` } },
        React.createElement('div', { style: { width: 26, height: 26, borderRadius: '50%', background: 'linear-gradient(135deg,#4e8cff,#9b59b6)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 800 } }, 'P'),
        React.createElement('div', null,
          React.createElement('div', { style: { fontSize: 12, fontWeight: 700 } }, 'Pro Trader'),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.amber } }, 'VIP 2')
        )
      )
    )
  );
}

function flowFindTicker(tickers, sym) {
  const s = (sym || 'BTC').toUpperCase();
  const cands = [s + 'USD', s + 'USDT', s];
  if (s === 'XAU' || s === 'GOLD') cands.unshift('XAUTUSD');
  if (s === 'XAUT') cands.unshift('XAUTUSD');
  for (let i = 0; i < cands.length; i++) {
    const t = (tickers || []).find(x => x && x.symbol === cands[i]);
    if (t) return t;
  }
  return null;
}

function FlowSymbolHeader({ symbol }) {
  const [tick, setTick] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/tickers`);
        const d = await r.json();
        setTick(flowFindTicker(d.tickers, symbol));
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [symbol]);
  const p = tick ? Number(tick.mark_price || tick.close || 0) : 0;
  const chg = tick ? Number(tick.mark_change_24h != null ? tick.mark_change_24h : (tick.ltp_change_24h || 0)) : 0;
  const up = chg >= 0;
  const stat = (l, v, c) => React.createElement('div', { style: { minWidth: 86 } },
    React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, l),
    React.createElement('div', { style: { fontSize: 12, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: c || COLORS.text } }, v));
  return React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 16, background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '10px 16px', flexWrap: 'wrap' } },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
      React.createElement('div', { style: { width: 30, height: 30, borderRadius: '50%', background: '#f7931a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 800, color: '#fff' } }, (symbol || 'B')[0].toUpperCase()),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 14, fontWeight: 800 } }, (symbol || 'BTC').toUpperCase() + 'USDT'),
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Perpetual')
      )
    ),
    React.createElement('div', { style: { fontSize: 22, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: up ? COLORS.green : COLORS.red } }, p ? p.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--'),
    stat('Mark Price', p ? p.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--'),
    stat('24h Change', (up ? '+' : '') + (tick ? Number(chg).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--'), up ? COLORS.green : COLORS.red),
    stat('24h High', tick && tick.high ? Number(tick.high).toLocaleString() : '--'),
    stat('24h Low', tick && tick.low ? Number(tick.low).toLocaleString() : '--'),
    stat('24h Volume', tick && tick.turnover_usd ? (Number(tick.turnover_usd) >= 1e9 ? (Number(tick.turnover_usd) / 1e9).toFixed(2) + 'B' : (Number(tick.turnover_usd) / 1e6).toFixed(1) + 'M') + ' USDT' : '--'),
    stat('Funding / 8h', tick && tick.funding_rate != null ? (Number(tick.funding_rate) * 100).toFixed(4) + '%' : '--', COLORS.amber)
  );
}

function FlowTicket({ symbol, health }) {
  const [lev, setLev] = useState(100);
  const [otype, setOtype] = useState('market');
  const [size, setSize] = useState(0.01);
  const [limitPx, setLimitPx] = useState(0);
  const [tick, setTick] = useState(null);
  const [avail, setAvail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const noAuth = !!(health && !health.has_auth);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/tickers`);
        const d = await r.json();
        setTick(flowFindTicker(d.tickers, symbol));
      } catch (e) {}
      try {
        const r = await fetch(`${API}/delta/balance`);
        const d = await r.json();
        if (d && !d.error) {
          const v = d.balance ?? d.wallet_balance ?? d.available ?? d.total;
          if (v != null && !isNaN(Number(v))) setAvail(Number(v));
        }
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [symbol]);
  const px = tick ? Number(tick.mark_price || tick.close || 0) : 0;
  const place = async (side) => {
    if (busy || noAuth) return;
    setBusy(true);
    setMsg(null);
    try {
      const body = { symbol: toDeltaSymbol(symbol), side, size: String(size), order_type: otype, leverage: String(lev) };
      if (otype === 'limit') body.limit_price = String(limitPx || px);
      const r = await fetch(`${API}/delta/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + BRIDGE_TOKEN }, body: JSON.stringify(body) });
      const d = await r.json();
      if (r.ok && (d.id || d.order_id || d.status === 'ok')) {
        setMsg({ ok: true, text: `${side === 'buy' ? 'Long' : 'Short'} ${size} @ ${otype === 'market' ? 'market' : (limitPx || px)} placed` });
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.ping();
      } else {
        setMsg({ ok: false, text: (d && d.error) || 'Order rejected' });
        if (window.Chrome && window.Chrome.audio) window.Chrome.audio.blip();
      }
    } catch (e) {
      setMsg({ ok: false, text: String(e.message || e) });
    }
    setBusy(false);
  };
  const closeAll = async () => {
    if (busy) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API}/journal/trades?status=open&limit=100`);
      const d = await r.json();
      const open = (d.trades || []).filter(t => t && t.status !== 'closed');
      let n = 0;
      for (let i = 0; i < open.length; i++) {
        const rr = await fetch(`${API}/journal/trades/close`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trade_id: open[i].id }) });
        if (rr.ok) n++;
      }
      setMsg({ ok: true, text: open.length ? `Closed ${n}/${open.length} journal-tracked trades` : 'No open journal-tracked trades' });
    } catch (e) { setMsg({ ok: false, text: String(e.message || e) }); }
    setBusy(false);
  };
  const notional = size * px;
  const liqLong = px ? px * (1 - 1 / lev) : 0;
  const pctBtn = (f) => { if (avail != null && px) setSize(Number(((avail * f) / px).toFixed(4))); };
  const execBtn = (side) => {
    const isBuy = side === 'buy';
    return React.createElement('button', { onClick: () => place(isBuy ? 'buy' : 'sell'), disabled: busy || noAuth,
      style: { padding: '12px 6px', borderRadius: 8, border: 'none', cursor: (busy || noAuth) ? 'not-allowed' : 'pointer', opacity: (busy || noAuth) ? 0.55 : 1,
        background: isBuy ? COLORS.green : COLORS.red, color: '#fff', transition: 'filter 150ms',
        boxShadow: isBuy ? '0 0 14px rgba(34,197,94,0.35)' : '0 0 14px rgba(239,68,68,0.35)' } },
      React.createElement('div', { style: { fontSize: 13, fontWeight: 800 } }, isBuy ? 'Buy / Long' : 'Sell / Short'),
      React.createElement('div', { style: { fontSize: 11, fontWeight: 700, fontFamily: "'Fira Code', monospace", marginTop: 2 } }, px ? px.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--')
    );
  };
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 } },
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, 'Scalping Mode'),
      React.createElement('span', { style: { width: 30, height: 17, borderRadius: 10, background: COLORS.green, position: 'relative' } },
        React.createElement('span', { style: { position: 'absolute', top: 2, right: 2, width: 13, height: 13, borderRadius: '50%', background: '#fff' } }))
    ),
    React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'High Leverage'),
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 6 } },
      [25, 50, 75, 100, 125].map(l => React.createElement('button', { key: l, onClick: () => setLev(l),
        style: { flex: 1, padding: '4px 0', fontSize: 10, fontWeight: 700, fontFamily: "'Fira Code', monospace", borderRadius: 5, border: 'none', cursor: 'pointer', background: lev === l ? COLORS.blue : 'transparent', color: lev === l ? '#fff' : COLORS.textTertiary } }, l + 'x'))
    ),
    React.createElement('input', { type: 'range', min: 1, max: 125, value: lev, onChange: (e) => setLev(Number(e.target.value)), style: { width: '100%', accentColor: COLORS.blue, marginBottom: 4 } }),
    React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 10 } }, 'Max Leverage: 125x'),
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 10 } },
      ['market', 'limit'].map(t => React.createElement('button', { key: t, onClick: () => setOtype(t),
        style: { flex: 1, padding: '7px 0', fontSize: 11, fontWeight: 700, borderRadius: 6, border: 'none', cursor: 'pointer', background: otype === t ? COLORS.bgHover : 'transparent', color: otype === t ? COLORS.text : COLORS.textTertiary } }, t[0].toUpperCase() + t.slice(1)))
    ),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } },
      React.createElement('span', null, 'Available'),
      React.createElement('span', { style: { fontFamily: "'Fira Code', monospace", color: COLORS.text } }, avail != null ? avail.toLocaleString(undefined, { maximumFractionDigits: 2 }) + ' USDT' : '--')
    ),
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 8 } },
      React.createElement('input', { type: 'number', step: '0.0001', min: '0', value: size, onChange: (e) => setSize(Number(e.target.value)),
        style: { flex: 1, padding: '8px 10px', borderRadius: 7, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13, fontFamily: "'Fira Code', monospace" } }),
      React.createElement('span', { style: { alignSelf: 'center', fontSize: 11, color: COLORS.textTertiary } }, 'USDT')
    ),
    otype === 'limit' && React.createElement('input', { type: 'number', step: '0.1', min: '0', value: limitPx || '', placeholder: 'Limit price', onChange: (e) => setLimitPx(Number(e.target.value)),
      style: { width: '100%', padding: '8px 10px', borderRadius: 7, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13, fontFamily: "'Fira Code', monospace", marginBottom: 8 } }),
    React.createElement('div', { style: { display: 'flex', gap: 6, marginBottom: 8 } },
      [0.25, 0.5, 0.75, 1].map(f => React.createElement('button', { key: f, onClick: () => pctBtn(f),
        style: { flex: 1, padding: '5px 0', fontSize: 10, fontFamily: "'Fira Code', monospace", borderRadius: 5, border: `1px solid ${COLORS.border}`, background: 'transparent', color: COLORS.textTertiary, cursor: 'pointer' } }, (f * 100) + '%'))
    ),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 10, color: COLORS.textTertiary, marginBottom: 8 } },
      React.createElement('span', null, 'Est. Liq. Price (long)'),
      React.createElement('span', { style: { fontFamily: "'Fira Code', monospace", color: COLORS.text } }, liqLong ? liqLong.toLocaleString(undefined, { maximumFractionDigits: 1 }) + ' USDT' : '--')
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 } }, execBtn('buy'), execBtn('sell')),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 10, color: COLORS.textTertiary, marginBottom: 2 } },
      React.createElement('span', null, 'Cost ' + (notional ? notional.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '--') + ' USDT'),
      React.createElement('span', null, 'Max ' + (avail != null ? (avail * lev).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '--') + ' USDT')
    ),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 10, color: COLORS.textTertiary, marginBottom: 8 } },
      React.createElement('span', null, 'Fee (0.02%) ' + (notional ? (notional * 0.0002).toFixed(2) : '--') + ' USDT'),
      React.createElement('span', null, 'Fee (0.02%) ' + (notional ? (notional * 0.0002).toFixed(2) : '--') + ' USDT')
    ),
    noAuth && React.createElement('div', { style: { fontSize: 10, color: COLORS.red, marginBottom: 8 } }, 'No API keys — connect in Settings to trade.'),
    msg && React.createElement('div', { style: { fontSize: 11, padding: '7px 10px', borderRadius: 6, marginBottom: 8, background: msg.ok ? COLORS.green + '1c' : COLORS.red + '1c', border: `1px solid ${msg.ok ? COLORS.green : COLORS.red}`, color: msg.ok ? COLORS.green : COLORS.red } }, msg.text),
    React.createElement('button', { onClick: closeAll, disabled: busy,
      style: { width: '100%', padding: '10px 0', borderRadius: 8, border: `1px solid ${COLORS.red}66`, background: 'transparent', color: COLORS.red, fontSize: 12, fontWeight: 700, cursor: busy ? 'not-allowed' : 'pointer' } }, 'Close All Positions'),
    React.createElement('div', { style: { fontSize: 9, color: COLORS.textTertiary, marginTop: 4, textAlign: 'center' } }, 'closes journal-tracked trades')
  );
}

function FlowBook({ symbol }) {
  const [tab, setTab] = useState('book');
  const [tick, setTick] = useState(null);
  const [trades, setTrades] = useState([]);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/tickers`);
        const d = await r.json();
        setTick(flowFindTicker(d.tickers, symbol));
      } catch (e) {}
      try {
        const r = await fetch(`${API}/journal/trades?limit=8`);
        const d = await r.json();
        if (d.trades) setTrades(d.trades.slice(0, 8));
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [symbol]);
  const px = tick ? Number(tick.mark_price || tick.close || 0) : 0;
  const step = px ? px * 0.0002 : 0;
  const baseVol = tick && tick.turnover_usd && px ? Number(tick.turnover_usd) / px / 40 : 100;
  const mkRow = (p, q, i, isAsk) => React.createElement('div', { key: (isAsk ? 'a' : 'b') + i, style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', fontSize: 11, fontFamily: "'Fira Code', monospace", padding: '3px 0', position: 'relative' } },
    React.createElement('div', { style: { position: 'absolute', top: 0, bottom: 0, right: 0, width: Math.min(100, (q / (baseVol * 1.6)) * 100) + '%', background: isAsk ? COLORS.red + '14' : COLORS.green + '14' } }),
    React.createElement('span', { style: { color: isAsk ? COLORS.red : COLORS.green, zIndex: 1 } }, p.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })),
    React.createElement('span', { style: { color: COLORS.textSecondary, textAlign: 'right', zIndex: 1 } }, q.toFixed(2)),
    React.createElement('span', { style: { color: COLORS.textTertiary, textAlign: 'right', zIndex: 1 } }, (p * q / 1e6).toFixed(2) + 'M')
  );
  const asks = [], bids = [];
  for (let i = 7; i >= 1; i--) asks.push(mkRow(px + step * i, baseVol * (1 + (7 - i) * 0.18), i, true));
  for (let i = 1; i <= 7; i++) bids.push(mkRow(px - step * i, baseVol * (1 + (i - 1) * 0.15), i, false));
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', gap: 12, marginBottom: 8 } },
      ['book', 'trades'].map(t => React.createElement('button', { key: t, onClick: () => setTab(t),
        style: { fontSize: 11, fontWeight: 700, padding: '4px 2px', border: 'none', borderBottom: tab === t ? `2px solid ${COLORS.blue}` : '2px solid transparent', background: 'transparent', color: tab === t ? COLORS.text : COLORS.textTertiary, cursor: 'pointer' } }, t === 'book' ? 'Order Book' : 'Trades'))
    ),
    tab === 'book' ? React.createElement('div', null,
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', fontSize: 10, color: COLORS.textTertiary, paddingBottom: 4 } },
        React.createElement('span', null, 'Price (USDT)'), React.createElement('span', { style: { textAlign: 'right' } }, 'Size'), React.createElement('span', { style: { textAlign: 'right' } }, 'Sum')
      ),
      asks,
      React.createElement('div', { style: { display: 'flex', alignItems: 'baseline', gap: 8, padding: '8px 0', borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}`, margin: '4px 0' } },
        React.createElement('span', { style: { fontSize: 18, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: COLORS.green } }, px ? px.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '--'),
        React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary, fontFamily: "'Fira Code', monospace" } }, '≈ mark')
      ),
      bids
    ) : React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
      trades.length === 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, textAlign: 'center', padding: 16 } }, 'No recent trades'),
      trades.map(t => React.createElement('div', { key: t.id, style: { display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: "'Fira Code', monospace" } },
        React.createElement('span', { style: { color: (t.side || '').toLowerCase() === 'sell' ? COLORS.red : COLORS.green } }, (t.side || '--').toUpperCase()),
        React.createElement('span', { style: { color: COLORS.text } }, t.symbol || '--'),
        React.createElement('span', { style: { color: COLORS.textSecondary } }, t.entry_price != null ? Number(t.entry_price).toLocaleString() : '--')
      ))
    )
  );
}

function FlowPositions({ onNav }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/positions`);
        const d = await r.json();
        if (d.positions && d.positions.length) { setRows({ src: 'exchange', list: d.positions }); return; }
      } catch (e) {}
      try {
        const r = await fetch(`${API}/journal/trades?status=open&limit=20`);
        const d = await r.json();
        setRows({ src: 'journal', list: (d.trades || []).filter(t => t && t.status !== 'closed') });
      } catch (e) { setRows({ src: 'none', list: [] }); }
    };
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, []);
  const list = (rows && rows.list) || [];
  let total = 0;
  list.forEach(p => { const v = Number(p.unrealized_pnl ?? p.pnl ?? p.pnl_usd ?? 0); if (!isNaN(v)) total += v; });
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, `Positions (${list.length})`),
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: total >= 0 ? COLORS.green : COLORS.red } }, 'Total PnL ' + fmtCur(total))
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1.2fr 0.7fr 1fr 1fr 1fr', fontSize: 10, color: COLORS.textTertiary, paddingBottom: 4 } },
      React.createElement('span', null, 'Symbol'), React.createElement('span', null, 'Size'), React.createElement('span', null, 'Entry'), React.createElement('span', null, 'Mark'), React.createElement('span', { style: { textAlign: 'right' } }, 'PnL')
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 150, overflowY: 'auto' } },
      list.length === 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, textAlign: 'center', padding: 12 } }, 'Flat — no open positions'),
      list.slice(0, 6).map((p, i) => {
        const pnl = Number(p.unrealized_pnl ?? p.pnl ?? p.pnl_usd ?? 0);
        const sym = p.symbol || p.product_symbol || '--';
        return React.createElement('div', { key: i, style: { display: 'grid', gridTemplateColumns: '1.2fr 0.7fr 1fr 1fr 1fr', fontSize: 11, fontFamily: "'Fira Code', monospace" } },
          React.createElement('span', { style: { color: COLORS.text, fontFamily: "'Fira Sans', sans-serif", fontWeight: 700 } }, sym),
          React.createElement('span', { style: { color: COLORS.textSecondary } }, p.size ?? p.qty ?? '--'),
          React.createElement('span', { style: { color: COLORS.textSecondary } }, p.entry_price ?? p.avg_entry ?? p.entry ?? '--'),
          React.createElement('span', { style: { color: COLORS.textSecondary } }, p.mark_price ?? p.mark ?? '--'),
          React.createElement('span', { style: { textAlign: 'right', color: pnl >= 0 ? COLORS.green : COLORS.red } }, fmtCur(pnl))
        );
      })
    ),
    React.createElement('button', { onClick: () => onNav && onNav('journal'), style: { width: '100%', marginTop: 8, padding: '7px 0', fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: 'transparent', color: COLORS.textSecondary, cursor: 'pointer' } }, 'View All Positions')
  );
}

function FlowSuggestions({ onNav }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/trading/suggestions`);
        const d = await r.json();
        let arr = [];
        if (Array.isArray(d)) arr = d;
        else if (Array.isArray(d.suggestions)) arr = d.suggestions;
        else if (d.suggestions && typeof d.suggestions === 'object') arr = Object.entries(d.suggestions).map(([k, v]) => Object.assign({ symbol: k }, v));
        else if (d.recommendations && typeof d.recommendations === 'object') arr = Object.entries(d.recommendations).map(([k, v]) => Object.assign({ symbol: k }, v));
        setItems(arr.slice(0, 3));
      } catch (e) { setItems([]); }
    };
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, []);
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, 'Trade Suggestions'),
      React.createElement('span', { style: { fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: COLORS.blue + '22', color: COLORS.blue } }, 'AI')
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
      items === null && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, textAlign: 'center', padding: 12 } }, 'Scanning…'),
      items && items.length === 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, textAlign: 'center', padding: 12 } }, 'No suggestions right now'),
      (items || []).map((s, i) => {
        const sym = s.symbol || s.pair || '--';
        const dir = (s.direction || s.side || s.action || '').toString();
        const conf = s.confidence != null ? Math.round(Number(s.confidence) * (Number(s.confidence) <= 1 ? 100 : 1)) : null;
        const long = /long|buy/i.test(dir);
        return React.createElement('div', { key: i, style: { padding: '8px 10px', background: COLORS.bgElevated, borderRadius: 8, border: `1px solid ${COLORS.border}` } },
          React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 } },
            React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, sym + ' ', React.createElement('span', { style: { color: long ? COLORS.green : COLORS.red } }, dir || '')),
            conf != null && React.createElement('span', { style: { fontSize: 10, color: COLORS.textTertiary } }, 'Confidence ' + conf + '%')
          ),
          React.createElement('div', { style: { fontSize: 10, color: COLORS.textSecondary, fontFamily: "'Fira Code', monospace" } },
            'TP1 ' + (s.tp1 ?? s.take_profit_1 ?? s.tp ?? '--') + '  TP2 ' + (s.tp2 ?? s.take_profit_2 ?? '--') + '  SL ' + (s.sl ?? s.stop_loss ?? s.stop ?? '--'))
        );
      })
    ),
    React.createElement('button', { onClick: () => onNav && onNav('strategies'), style: { width: '100%', marginTop: 8, padding: '7px 0', fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: 'transparent', color: COLORS.textSecondary, cursor: 'pointer' } }, 'View All Suggestions')
  );
}

function FlowMarket({ gainers, losers, onSelect, onNav }) {
  const [heat, setHeat] = useState([]);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/tickers`);
        const d = await r.json();
        const perps = (d.tickers || []).filter(t => t && t.contract_type === 'perpetual_futures' && t.funding_rate != null);
        perps.sort((a, b) => Math.abs(Number(b.funding_rate)) - Math.abs(Number(a.funding_rate)));
        setHeat(perps.slice(0, 12));
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, []);
  const top = (gainers || []).slice(0, 2);
  const flop = (losers || []).slice(-1);
  const spark = (v) => React.createElement('svg', { width: 72, height: 22 },
    React.createElement('polyline', { points: `0,${v >= 0 ? 16 : 6} 24,${v >= 0 ? 12 : 10} 48,${v >= 0 ? 8 : 14} 72,${v >= 0 ? 4 : 18}`, fill: 'none', stroke: v >= 0 ? COLORS.green : COLORS.red, strokeWidth: 1.5 })
  );
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { fontSize: 12, fontWeight: 800, marginBottom: 8 } }, 'Market Overview'),
    top.concat(flop).slice(0, 3).map((t, i) => React.createElement('div', { key: i, onClick: () => onSelect && onSelect((t.symbol || '').replace(/USD$/, '')), style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', cursor: 'pointer' } },
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700 } }, t.symbol),
      spark(Number(t.change_24h || 0)),
      React.createElement('span', { style: { fontSize: 11, fontWeight: 700, fontFamily: "'Fira Code', monospace", color: Number(t.change_24h || 0) >= 0 ? COLORS.green : COLORS.red } }, fmtPct(t.change_24h))
    )),
    React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, margin: '8px 0 5px' } }, 'Funding Heatmap'),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 4 } },
      heat.map((t, i) => {
        const f = Number(t.funding_rate);
        return React.createElement('div', { key: i, title: `${t.symbol} ${(f * 100).toFixed(4)}%`, style: { height: 16, borderRadius: 3, background: f >= 0 ? COLORS.green : COLORS.red, opacity: Math.min(1, 0.25 + Math.abs(f) * 400) } });
      })
    ),
    React.createElement('button', { onClick: () => onNav && onNav('analytics'), style: { width: '100%', marginTop: 8, padding: '7px 0', fontSize: 11, borderRadius: 6, border: `1px solid ${COLORS.border}`, background: 'transparent', color: COLORS.textSecondary, cursor: 'pointer' } }, 'View Market Dashboard')
  );
}


function FlowNews({ onNav }) {
  const [evts, setEvts] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/calendar/events`);
        const d = await r.json();
        setEvts(((d.upcoming && d.upcoming.length ? d.upcoming : (d.recent || [])).slice(0, 4)));
      } catch (e) { setEvts([]); }
    };
    load();
    const iv = setInterval(load, 300000);
    return () => clearInterval(iv);
  }, []);
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, 'News Feed'),
      React.createElement('button', { onClick: () => onNav && onNav('calendar'), style: { background: 'none', border: 'none', color: COLORS.textTertiary, fontSize: 12, cursor: 'pointer' } }, '×')
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
      evts === null && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Loading calendar…'),
      evts && evts.length === 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'No upcoming high-impact events'),
      (evts || []).map((e, i) => React.createElement('div', { key: i, style: { display: 'flex', gap: 8, fontSize: 11 } },
        React.createElement('span', { style: { color: COLORS.textTertiary, fontFamily: "'Fira Code', monospace", whiteSpace: 'nowrap' } }, String(e.time || e.datetime || e.date || '').slice(0, 16)),
        React.createElement('span', { style: { color: COLORS.textSecondary } }, e.title || e.event || JSON.stringify(e).slice(0, 80))
      ))
    )
  );
}

function FlowBots({ onNav }) {
  const [bots, setBots] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/bot/status`);
        const d = await r.json();
        const obj = d.bots || d || {};
        setBots(Object.entries(obj).slice(0, 5));
      } catch (e) { setBots([]); }
    };
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, []);
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 12, fontWeight: 800 } }, 'Bot Status'),
      React.createElement('button', { onClick: () => onNav && onNav('bots'), style: { background: 'none', border: 'none', color: COLORS.textTertiary, fontSize: 11, cursor: 'pointer' } }, 'Manage Bots')
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 7 } },
      bots === null && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Loading bots…'),
      bots && bots.length === 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'No bots registered'),
      (bots || []).map(([id, b], i) => {
        const running = b && (b.running === true || b.status === 'running');
        return React.createElement('div', { key: id + i, style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 } },
          React.createElement('span', { style: { width: 7, height: 7, borderRadius: '50%', background: running ? COLORS.green : COLORS.textTertiary, boxShadow: running ? `0 0 6px ${COLORS.green}` : 'none' } }),
          React.createElement('span', { style: { flex: 1, fontWeight: 600, color: COLORS.text } }, id),
          React.createElement('span', { style: { color: running ? COLORS.green : COLORS.textTertiary } }, running ? 'Running' : 'Stopped'),
          React.createElement('span', { style: { color: COLORS.textTertiary, fontFamily: "'Fira Code', monospace" } }, (b && b.category) || '')
        );
      })
    )
  );
}

function FlowRisk() {
  const [d, setD] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const [j, x] = await Promise.all([
          fetch(`${API}/journal/stats`).then(r => r.ok ? r.json() : null),
          fetch(`${API}/metrics/exposure`).then(r => r.ok ? r.json() : null),
        ]);
        setD({ jstat: j, expo: x });
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, []);
  const js = ((d && d.jstat && d.jstat.total) || {});
  const ex = (d && d.expo) || {};
  const nTrades = Number(js.trades || 0);
  const winRate = js.win_rate != null ? Number(js.win_rate) : null;
  const score = winRate != null ? Math.max(0, Math.min(100, Math.round(winRate))) : null;
  const R = 44, C = Math.PI * R;
  const col = score == null ? COLORS.textTertiary : (score >= 60 ? COLORS.green : (score >= 40 ? COLORS.amber : COLORS.red));
  return React.createElement(Card, { pad: 12 },
    React.createElement('div', { style: { fontSize: 12, fontWeight: 800, marginBottom: 8 } }, 'Account Risk Summary'),
    React.createElement('div', { style: { display: 'flex', gap: 14, alignItems: 'center' } },
      React.createElement('svg', { width: 110, height: 68, viewBox: '0 0 110 68' },
        React.createElement('path', { d: `M 8 60 A ${R} ${R} 0 0 1 102 60`, fill: 'none', stroke: COLORS.border, strokeWidth: 9, strokeLinecap: 'round' }),
        React.createElement('path', { d: `M 8 60 A ${R} ${R} 0 0 1 102 60`, fill: 'none', stroke: col, strokeWidth: 9, strokeLinecap: 'round', strokeDasharray: `${C}`, strokeDashoffset: `${C * (1 - score / 100)}` }),
        React.createElement('text', { x: 55, y: 48, textAnchor: 'middle', fill: COLORS.text, fontSize: 17, fontWeight: 800, fontFamily: "'Fira Code', monospace" }, score != null ? score : '--'),
        React.createElement('text', { x: 55, y: 60, textAnchor: 'middle', fill: COLORS.textTertiary, fontSize: 8 }, nTrades ? 'WIN RATE' : 'NO TRADES YET')
      ),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11 } },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Gross Exposure'), React.createElement('span', { style: { fontFamily: "'Fira Code', monospace" } }, ex.gross_exposure != null ? fmtCur(ex.gross_exposure) : '--')),
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Leverage'), React.createElement('span', { style: { fontFamily: "'Fira Code', monospace" } }, ex.leverage_ratio != null ? Number(ex.leverage_ratio).toFixed(1) + 'x' : '--')),
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Net Exposure'), React.createElement('span', { style: { fontFamily: "'Fira Code', monospace" } }, ex.net_exposure != null ? fmtCur(ex.net_exposure) : '--')),
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Total PnL'), React.createElement('span', { style: { fontFamily: "'Fira Code', monospace", color: Number(js.net_pnl || 0) >= 0 ? COLORS.green : COLORS.red } }, js.net_pnl != null ? fmtCur(js.net_pnl) : '--')),
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 12 } },
          React.createElement('span', { style: { color: COLORS.textTertiary } }, 'Max DD'), React.createElement('span', { style: { fontFamily: "'Fira Code', monospace", color: COLORS.red } }, js.max_drawdown_usd != null ? fmtCur(js.max_drawdown_usd) : '--')
        )
      )
    ),
    React.createElement('div', { style: { fontSize: 9, color: COLORS.textTertiary, marginTop: 6 } }, nTrades ? `${nTrades} closed trades · gauge = journal win rate` : 'Gauge activates after first closed trades')
  );
}

function FlowTape({ connected }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/delta/tickers`);
        const d = await r.json();
        const perps = (d.tickers || []).filter(t => t && t.contract_type === 'perpetual_futures' && t.symbol && !/^[CP]-/.test(t.symbol));
        perps.sort((a, b) => Number(b.turnover_usd || 0) - Number(a.turnover_usd || 0));
        setRows(perps.slice(0, 8));
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, []);
  return React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 18, background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '7px 14px', overflowX: 'auto', whiteSpace: 'nowrap' } },
    rows.map((t, i) => {
      const chg = Number(t.mark_change_24h != null ? t.mark_change_24h : (t.ltp_change_24h || 0));
      return React.createElement('span', { key: i, style: { fontSize: 11, fontFamily: "'Fira Code', monospace", color: COLORS.textSecondary } },
        React.createElement('span', { style: { color: COLORS.text, fontWeight: 700 } }, t.symbol),
        ' ',
        React.createElement('span', { style: { color: chg >= 0 ? COLORS.green : COLORS.red } }, fmtPct(chg)),
        ' ',
        Number(t.mark_price || t.close || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })
      );
    }),
    React.createElement('span', { style: { marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: COLORS.textSecondary } },
      React.createElement('span', { style: { width: 7, height: 7, borderRadius: '50%', background: connected ? COLORS.green : COLORS.red } }),
      connected ? 'System Status: All Systems Operational' : 'System Status: Degraded'
    )
  );
}

/* ============================ DASHBOARD VIEW — MT5 FLOW TERMINAL ============================ */
function DashboardView({ gainers, losers, health, search, setSearch, chartSymbol, setChartSymbol, onModeToggle, modeBusy, setTab }) {
  const nav = (t) => { if (setTab) setTab(t); };
  const pickSymbol = (s) => { if (s) setChartSymbol(String(s).toUpperCase()); };
  return React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '72px minmax(0,1fr)', gap: 12, alignItems: 'start' } },
    React.createElement(FlowRail, { active: 'dashboard', onNav: nav }),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 } },
      React.createElement(FlowTopbar, { health, search, setSearch, onSearch: pickSymbol, onModeToggle, modeBusy }),
      React.createElement(FlowSymbolHeader, { symbol: chartSymbol }),
      React.createElement('div', { style: { overflowX: 'auto' } },
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 300px 280px', gap: 12, alignItems: 'start', minWidth: 1180 } },
          React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 } },
            React.createElement(Card, { pad: 12 },
              React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 8, fontFamily: "'Fira Code', monospace" } }, toTradingViewSymbol(chartSymbol) + ' · powered by TradingView'),
              React.createElement(TradingViewWidget, { symbol: chartSymbol, height: 470 })
            ),
            React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12 } },
              React.createElement(FlowPositions, { onNav: nav }),
              React.createElement(FlowSuggestions, { onNav: nav }),
              React.createElement(FlowMarket, { gainers, losers, onSelect: pickSymbol, onNav: nav })
            )
          ),
          React.createElement(FlowTicket, { symbol: chartSymbol, health }),
          React.createElement(FlowBook, { symbol: chartSymbol })
        )
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12 } },
        React.createElement(FlowNews, { onNav: nav }),
        React.createElement(FlowBots, { onNav: nav }),
        React.createElement(FlowRisk, null)
      ),
      React.createElement(FlowTape, { connected: health && health.connected })
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
  const [err, setErr] = useState(null);
  useEffect(() => {
    fetch(`${API}/strategies/library`).then(r => r.ok ? r.json() : null).then(d => { if (d && d.strategies) setData(d); else setErr('Strategy library unavailable'); }).catch(() => setErr('Failed to load strategy library'));
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
  if (!data) return React.createElement(Card, { pad: 16 }, React.createElement('div', { style: { fontSize: 12, color: err ? COLORS.red : COLORS.textTertiary } }, err || 'Loading strategy library…'));
  let list = data.strategies || [];
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
  const loadLog = async (cat, level) => {
    try {
      const c = cat != null ? cat : logCat;
      const l = level != null ? level : logLevel;
      const r = await fetch(`${API}/journal/log?category=${c}&level=${l}&limit=300`);
      const j = await r.json();
      if (j.entries) setLog(j.entries);
    } catch (e) {}
  };
  const loadNotifications = async () => {
    try { const r = await fetch(`${API}/journal/notifications`); const j = await r.json(); if (j.rules) setRules(j.rules); } catch (e) {}
    try { const r = await fetch(`${API}/journal/notification-log?limit=30`); const j = await r.json(); if (j.entries) setNotifLog(j.entries); } catch (e) {}
  };

  const refresh = () => { loadStats(days); loadTrades(); loadSessions(); loadNotifications(); };

  const logFilterRef = React.useRef({ cat: 'ALL', level: 'ALL' });

  useEffect(() => {
    reportEvent('Journal opened', 'ui', 'INFO');
    refresh();
    const iv = setInterval(() => {
      loadLog(logFilterRef.current.cat, logFilterRef.current.level);
      loadNotifications();
    }, 10000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => { logFilterRef.current = { cat: logCat, level: logLevel }; loadLog(); }, [logCat, logLevel]);
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

/* ============================ SETTINGS VIEW ============================ */
function SettingsView({ health }) {
  const [deltaKey, setDeltaKey] = useState('');
  const [deltaSecret, setDeltaSecret] = useState('');
  const [testnet, setTestnet] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    try {
      const k = localStorage.getItem('delta_api_key');
      const s = localStorage.getItem('delta_api_secret');
      const t = localStorage.getItem('delta_testnet');
      if (k) setDeltaKey(k);
      if (s) setDeltaSecret(s);
      if (t) setTestnet(t === 'true');
    } catch (e) {}
  }, []);

  const saveKeys = () => {
    try {
      localStorage.setItem('delta_api_key', deltaKey);
      localStorage.setItem('delta_api_secret', deltaSecret);
      localStorage.setItem('delta_testnet', testnet.toString());
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {}
  };

  const clearKeys = () => {
    setDeltaKey('');
    setDeltaSecret('');
    setTestnet(false);
    try {
      localStorage.removeItem('delta_api_key');
      localStorage.removeItem('delta_api_secret');
      localStorage.removeItem('delta_testnet');
    } catch (e) {}
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await fetch(`${API}/delta/health`, {
        headers: {
          'Authorization': 'Bearer ' + BRIDGE_TOKEN,
          'X-Delta-Key': deltaKey,
          'X-Delta-Secret': deltaSecret,
          'X-Delta-Testnet': testnet.toString()
        }
      });
      const d = await r.json();
      if (r.ok && d.connected) {
        setTestResult({ type: 'success', text: 'Connection successful! ' + (d.has_auth ? 'API keys valid.' : 'Connected (read-only).') });
      } else {
        setTestResult({ type: 'error', text: d.error || 'Connection failed' });
      }
    } catch (e) {
      setTestResult({ type: 'error', text: e.message });
    }
    setTesting(false);
  };

  const hasAuth = health?.has_auth;
  const apiConfigured = !!deltaKey && !!deltaSecret;

  return React.createElement('div', { style: { maxWidth: 800, margin: '0 auto' } },
    React.createElement(Section, { title: 'API Configuration' },
      React.createElement(Card, { pad: 16 },
        React.createElement('div', { style: { display: 'grid', gap: 16, maxWidth: 500 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10, padding: 12, borderRadius: 8, background: hasAuth ? COLORS.green + '15' : COLORS.amber + '15', border: `1px solid ${hasAuth ? COLORS.green : COLORS.amber}` } },
            React.createElement('span', { style: { width: 10, height: 10, borderRadius: '50%', background: hasAuth ? COLORS.green : COLORS.amber } }),
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 700, color: COLORS.text } }, hasAuth ? 'Delta API Connected' : 'Delta API Not Connected'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, hasAuth ? 'Trading enabled with stored credentials' : 'Add API keys to enable trading')
            )
          ),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginBottom: 8 } }, 'Enter your Delta Exchange API credentials. Keys are stored locally in your browser and sent with each trading request.'),
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 12 } }, 'Get keys at: https://www.delta.exchange/app/api-management'),
          React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
            React.createElement('div', null,
              React.createElement('label', { style: { display: 'block', fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'API Key'),
              React.createElement('input', { type: 'password', value: deltaKey, onChange: (e) => setDeltaKey(e.target.value), placeholder: 'Enter API Key', style: { width: '100%', padding: '10px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13, fontFamily: 'JetBrains Mono, monospace' } })
            ),
            React.createElement('div', null,
              React.createElement('label', { style: { display: 'block', fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'API Secret'),
              React.createElement('input', { type: 'password', value: deltaSecret, onChange: (e) => setDeltaSecret(e.target.value), placeholder: 'Enter API Secret', style: { width: '100%', padding: '10px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text, fontSize: 13, fontFamily: 'JetBrains Mono, monospace' } })
            ),
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
              React.createElement('input', { type: 'checkbox', checked: testnet, onChange: (e) => setTestnet(e.target.checked), style: { width: 18, height: 18, accentColor: COLORS.blue } }),
              React.createElement('label', { style: { fontSize: 12, color: COLORS.text } }, 'Testnet (Delta Testnet)')
            )
          ),
          React.createElement('div', { style: { display: 'flex', gap: 8, marginTop: 8 } },
            React.createElement('button', { onClick: saveKeys, style: { padding: '10px 16px', borderRadius: 8, background: COLORS.blue, border: 'none', color: '#fff', fontWeight: 700, cursor: 'pointer' } }, saved ? 'Saved!' : 'Save Keys'),
            React.createElement('button', { onClick: clearKeys, style: { padding: '10px 16px', borderRadius: 8, background: 'transparent', border: `1px solid ${COLORS.red}`, color: COLORS.red, fontWeight: 700, cursor: 'pointer' } }, 'Clear Keys'),
            React.createElement('button', { onClick: testConnection, disabled: testing || !deltaKey || !deltaSecret, style: { padding: '10px 16px', borderRadius: 8, background: testing ? 'transparent' : COLORS.green, border: `1px solid ${testing ? COLORS.border : COLORS.green}`, color: testing ? COLORS.textSecondary : '#000', fontWeight: 700, cursor: testing ? 'not-allowed' : 'pointer' } }, testing ? 'Testing...' : 'Test Connection')
          ),
          testResult && React.createElement('div', { style: { marginTop: 12, padding: '10px 12px', borderRadius: 6, background: testResult.type === 'success' ? COLORS.green + '22' : COLORS.red + '22', border: `1px solid ${testResult.type === 'success' ? COLORS.green : COLORS.red}`, color: testResult.type === 'success' ? COLORS.green : COLORS.red, fontSize: 12 } }, testResult.text)
        )
      )
    ),
    React.createElement(Section, { title: 'Trading Preferences' },
      React.createElement(Card, { pad: 16 },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Default Leverage'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Leverage applied when opening quick trades')
            ),
            React.createElement('select', { defaultValue: '10', style: { width: 120, padding: '8px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text } },
              [1, 2, 5, 10, 20, 50].map(l => React.createElement('option', { key: l, value: l }, l + 'x'))
            )
          ),
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Default Order Type'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Market or Limit for quick trade panel')
            ),
            React.createElement('select', { defaultValue: 'market', style: { width: 120, padding: '8px 12px', borderRadius: 8, background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`, color: COLORS.text } },
              React.createElement('option', { value: 'market' }, 'Market'),
              React.createElement('option', { value: 'limit' }, 'Limit')
            )
          ),
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Confirm Before Trade'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Show confirmation dialog before placing orders')
            ),
            React.createElement('input', { type: 'checkbox', defaultChecked: true, style: { width: 18, height: 18, accentColor: COLORS.blue } })
          )
        )
      )
    ),
    React.createElement(Section, { title: 'UI Preferences' },
      React.createElement(Card, { pad: 16 },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Sound Effects'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Audio feedback for trades, alerts, bot actions')
            ),
            React.createElement('input', { type: 'checkbox', defaultChecked: true, onChange: (e) => { if (window.Chrome && window.Chrome.audio) window.Chrome.audio.setMuted(!e.target.checked); }, style: { width: 18, height: 18, accentColor: COLORS.blue } })
          ),
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Scanline Effect'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'CRT scanline overlay on the UI')
            ),
            React.createElement('input', { type: 'checkbox', defaultChecked: true, style: { width: 18, height: 18, accentColor: COLORS.blue } })
          ),
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Particle Field'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Animated background particles')
            ),
            React.createElement('input', { type: 'checkbox', defaultChecked: true, style: { width: 18, height: 18, accentColor: COLORS.blue } })
          ),
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } },
            React.createElement('div', null,
              React.createElement('div', { style: { fontWeight: 600, color: COLORS.text } }, 'Tilt Effect'),
              React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } }, 'Subtle 3D tilt on cards on mouse move')
            ),
            React.createElement('input', { type: 'checkbox', defaultChecked: true, style: { width: 18, height: 18, accentColor: COLORS.blue } })
          )
        )
      )
    ),
    React.createElement(Section, { title: 'Data & Cache' },
      React.createElement(Card, { pad: 16 },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
          React.createElement('button', { onClick: () => { try { localStorage.clear(); setDeltaKey(''); setDeltaSecret(''); setTestnet(false); setSaved(true); setTimeout(() => setSaved(false), 2000); } catch (e) {} }, style: { padding: '10px 16px', borderRadius: 8, background: COLORS.red + '22', border: `1px solid ${COLORS.red}`, color: COLORS.red, fontWeight: 700, cursor: 'pointer', width: 'fit-content' } }, 'Clear All Local Storage')
        )
      )
    )
  );
}

/* ============================ MAIN APP ============================ */
function SlimBanner({ onSelect }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${API}/market/banner?slim=true`);
        const d = await r.json();
        if (d && d.banner) setData(d.banner);
      } catch (e) {}
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, []);
  if (!data) return React.createElement('div', { style: { height: 24 } });
  return React.createElement('div', {
    style: {
      position: 'absolute', top: 0, left: 0, right: 0, height: 24,
      background: 'linear-gradient(90deg, #0a0b0f 0%, #111318 50%, #0a0b0f 100%)',
      borderBottom: `1px solid ${COLORS.border}`,
      overflow: 'hidden', whiteSpace: 'nowrap', zIndex: 100
    }
  },
    React.createElement('div', {
      style: {
        display: 'inline-flex', gap: 40, paddingLeft: '100%',
        animation: 'marquee 30s linear infinite',
        fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600
      }
    },
      data.map((a, i) => React.createElement('span', {
        key: a.symbol,
        onClick: () => onSelect && onSelect(a.symbol),
        style: {
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0 20px',
          color: a.change_pct >= 0 ? COLORS.green : COLORS.red,
          cursor: onSelect ? 'pointer' : 'default'
        }
      },
        React.createElement('span', { style: { fontSize: 14 } }, a.emoji),
        React.createElement('span', null, a.symbol),
        React.createElement('span', { style: { fontWeight: 700 } }, a.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })),
        React.createElement('span', null, (a.change_pct >= 0 ? '▲ ' : '▼ ') + Math.abs(a.change_pct).toFixed(2) + '%')
      ))
    ),
    React.createElement('style', null, `
      @keyframes marquee {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
      }
    `)
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
    { id: 'bots', label: 'Bots' },
    { id: 'options', label: 'Options' },
    { id: 'strategies', label: 'Strategies' },
    { id: 'calendar', label: 'Calendar' },
    { id: 'library', label: 'Strategy Library' },
    { id: 'journal', label: 'Journal' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'terminal', label: 'TERM' },
    { id: 'settings', label: 'Settings' },
  ];

  return React.createElement('div', { style: { minHeight: '100vh', background: COLORS.bgRoot, color: COLORS.text } },
    React.createElement(SlimBanner, { onSelect: (sym) => { setChartSymbol(sym); setChartSource('tradingview'); setTab('dashboard'); } }),
    React.createElement('header', { style: { position: 'sticky', top: 24, zIndex: 50, background: 'rgba(10,11,15,0.95)', borderBottom: `1px solid ${COLORS.border}`, padding: '10px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backdropFilter: 'blur(8px)' } },
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
      tab === 'dashboard' && React.createElement(DashboardView, { gainers, losers, health, search, setSearch, chartSymbol, setChartSymbol, onModeToggle, modeBusy, setTab }),
      tab === 'bots' && React.createElement(BotsView, null),
      tab === 'options' && React.createElement(OptionsView, null),
      tab === 'strategies' && React.createElement(StrategiesView, null),
      tab === 'calendar' && React.createElement(CalendarView, null),
      tab === 'library' && React.createElement(LibraryView, null),
      tab === 'journal' && React.createElement(JournalView, null),
      tab === 'analytics' && React.createElement(AnalyticsView, null),
      tab === 'terminal' && React.createElement(window.TerminalView, { pendingCmd: pendingTermRef.current }),
      tab === 'settings' && React.createElement(SettingsView, { health }),
    )
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
