# Bias Determining Agent

## Purpose
Determines market bias (bullish/bearish/neutral) using multiple technical indicators across multiple timeframes, providing confidence-scored signals for downstream agents.

## Responsibilities
- Analyze price action across 5 timeframes (1m, 5m, 15m, 1h, 4h)
- Combine trend, momentum, volume, and volatility signals
- Output bias direction with confidence score (0.0-1.0)
- Publish bias signals for Confluence Agent and Style Managing Agent

## Configuration
```yaml
bias:
  timeframes: ["1m", "5m", "15m", "1h", "4h"]
  primary_timeframe: "15m"          # Timeframe for signal publication
  lookback_periods: 100             # Candle history for indicators
  min_confidence: 0.60              # Minimum confidence to publish signal
  trend_weight: 0.40                # Weight for trend indicators
  momentum_weight: 0.30             # Weight for momentum indicators
  volume_weight: 0.20               # Weight for volume confirmation
  volatility_weight: 0.10           # Weight for volatility adjustment
  ema_periods: [9, 21, 50, 200]     # EMA periods for trend analysis
  rsi_period: 14                    # RSI period
  macd_fast: 12                     # MACD fast period
  macd_slow: 26                     # MACD slow period
  macd_signal: 9                    # MACD signal period
```

## Indicators Calculated
### Trend (40% weight)
- EMA alignment (9 > 21 > 50 > 200 = strong uptrend)
- Price vs key EMAs (21, 50, 200)
- EMA slopes

### Momentum (30% weight)
- RSI (14): >60 bullish, >70 overbought caution, <40 bearish, <30 oversold caution
- MACD histogram: positive = bullish, negative = bearish

### Volume (20% weight)
- Volume ratio vs 20-period SMA
- High volume (>1.5x) confirms direction

### Volatility (10% weight)
- ATR % of price
- High volatility (>5%) reduces confidence in both directions

## Event Subscriptions
- `MARKET_TICK` - Real-time price updates for primary timeframe
- `MARKET_CANDLE` - Completed candles for indicator calculation
- `AGENT_TUNING` - Parameter updates from ManagerAgent

## Event Publications
- `BIAS_SIGNAL` - Published when confidence >= min_confidence
  ```json
  {
    "symbol": "BTCUSDT",
    "direction": "bullish",
    "confidence": 0.78,
    "indicators": {
      "15m_ema_9": 45123.45,
      "15m_ema_21": 44987.12,
      "15m_rsi": 62.3,
      "15m_macd_histogram": 45.2,
      "15m_price_vs_ema_21": 0.003,
      "15m_volume_ratio": 1.8
    },
    "timeframe": "15m",
    "reasoning": "Strong uptrend (EMA alignment); RSI bullish; MACD positive; Volume confirms"
  }
  ```
- `AGENT_HEARTBEAT` - Current biases for all symbols

## Multi-Timeframe Combination
Higher timeframes weighted more heavily:
- 1m: 5%, 5m: 10%, 15m: 20%, 1h: 30%, 4h: 35%

Final confidence = weighted average of timeframe confidences

## Integration Points
- **MultiTimeframeConfluenceAgent**: Primary consumer of bias signals
- **StyleManagingAgent**: Uses bias confidence for trend strength assessment
- **PositionSizingAgent**: Receives bias for confluence weighting
- **ManagerAgent**: Tunes weights and thresholds based on performance

## Tuning Parameters (from ManagerAgent)
- `min_confidence` - Signal publication threshold
- `trend_weight`, `momentum_weight`, `volume_weight`, `volatility_weight`
- `ema_periods` - Trend sensitivity
- `rsi_period`, `macd_*` - Momentum sensitivity
- `primary_timeframe` - Signal frequency