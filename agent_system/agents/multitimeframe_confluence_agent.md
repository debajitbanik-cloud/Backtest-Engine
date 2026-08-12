# Multi-Timeframe Confluence Agent

## Purpose
Checks for signal alignment across multiple timeframes and identifies key support/resistance confluence zones before allowing trades to proceed to position sizing.

## Responsibilities
- Collect bias signals from multiple timeframes
- Require minimum alignment (default 3/5 timeframes) for trade signals
- Identify key support/resistance levels on each timeframe
- Detect confluence zones (price at key level + aligned bias)
- Filter and validate trade signals for PositionSizingAgent

## Configuration
```yaml
confluence:
  timeframes: ["5m", "15m", "1h", "4h", "1d"]
  required_alignment: 3           # Minimum timeframes aligned for signal
  strong_alignment: 4             # Timeframes for strong signal
  lookback_candles: 100           # Candle history for level detection
  key_level_lookback: 50          # Lookback for S/R levels
  min_confidence: 0.65            # Minimum confluence confidence
  sr_touch_threshold: 0.002       # 0.2% from level = touch
  volume_confirmation: true       # Require volume confirmation
```

## Confluence Results
| Result | Description | Min Timeframes | Confidence Range |
|--------|-------------|----------------|------------------|
| `strong_bullish` | 4+ timeframes bullish | 4 | 0.85-1.0 |
| `bullish` | 3 timeframes bullish | 3 | 0.65-0.85 |
| `neutral` | No clear alignment | - | 0.5 |
| `bearish` | 3 timeframes bearish | 3 | 0.65-0.85 |
| `strong_bearish` | 4+ timeframes bearish | 4 | 0.85-1.0 |

## Key Level Detection
1. Find swing highs/lows (5-candle pattern)
2. Cluster nearby levels (0.5% threshold)
3. Count touches (price within 0.2% of level)
4. Keep levels with 2+ touches
5. Sort by touch count and proximity to current price

## Event Subscriptions
- `MARKET_CANDLE` - Store candle data for level calculation
- `BIAS_SIGNAL` - Collect bias from BiasDeterminingAgent
- `AGENT_TUNING` - Parameter updates from ManagerAgent

## Event Publications
- `CONFLUENCE_SIGNAL` - Published when enough timeframes collected
  ```json
  {
    "symbol": "BTCUSDT",
    "result": "bullish",
    "confidence": 0.78,
    "alignments": {
      "5m": "bullish",
      "15m": "bullish",
      "1h": "bullish",
      "4h": "neutral",
      "1d": "bullish"
    },
    "key_levels": {
      "15m_level": 44850.0,
      "1h_level": 44900.0
    },
    "reasoning": "3/5 timeframes bullish; 2 key levels confluent; Volume confirms"
  }
  ```
- `AGENT_HEARTBEAT` - Current confluence status per symbol

## Logic Flow
```
BIAS_SIGNAL received
         │
         ▼
Store per timeframe
         │
         ▼
Check if >= required_alignment timeframes collected
         │
         ▼
Count bullish/bearish/neutral
         │
         ▼
Check key level confluence (price near S/R)
         │
         ▼
Check volume confirmation
         │
         ▼
Calculate final confidence
         │
         ▼
If confidence >= min_confidence: Publish CONFLUENCE_SIGNAL
Else: Publish neutral
```

## Integration Points
- **BiasDeterminingAgent**: Primary signal source
- **PositionSizingAgent**: Main consumer - uses confluence for sizing
- **StyleManagingAgent**: Uses confluence result for mode decisions
- **ManagerAgent**: Tunes alignment requirements and confidence thresholds

## Tuning Parameters (from ManagerAgent)
- `required_alignment` - 2-4 (lower = more signals, higher = higher quality)
- `strong_alignment` - 3-5
- `min_confidence` - 0.55-0.80
- `sr_touch_threshold` - 0.001-0.005
- `volume_confirmation` - true/false
- `timeframes` - Which timeframes to include