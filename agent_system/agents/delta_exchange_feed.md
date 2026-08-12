# Delta Exchange Data Feed Agent

## Purpose
Provides real-time market data from Delta Exchange via WebSocket and REST API, publishing standardized events to the agent system's event bus.

## Responsibilities
- Maintain WebSocket connection to Delta Exchange
- Subscribe to ticker, candle, orderbook, trade channels
- Handle authentication for private endpoints
- Automatic reconnection with exponential backoff
- Publish market data events to event bus
- Provide REST API for historical data

## Configuration
```yaml
delta_exchange:
  api_key: ""                       # Set via environment variable
  api_secret: ""                    # Set via environment variable
  environment: "production"         # production or testnet
  ws_url: "wss://socket.delta.exchange"
  rest_url: "https://api.delta.exchange"
  reconnect_interval: 5             # Base reconnect delay (seconds)
  max_reconnect_attempts: 10
  ping_interval: 20                 # WebSocket ping interval
  symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
  timeframes: ["1m", "5m", "15m", "1h", "4h"]
```

## WebSocket Channels
| Channel | Format | Description |
|---------|--------|-------------|
| Ticker | `ticker.{symbol}` | Real-time price, volume, 24h stats |
| Candle | `candle.{timeframe}.{symbol}` | OHLCV candles |
| Orderbook | `orderbook.{depth}.{symbol}` | Orderbook depth (default 20) |
| Trades | `trade.{symbol}` | Individual trade prints |

## Authentication
HMAC-SHA256 signature for WebSocket auth:
```
timestamp = current_unix_timestamp
method = "GET"
path = "/v2/ws/auth"
payload = ""
signature = HMAC_SHA256(api_secret, timestamp + method + path + payload)
```

## Event Publications

### MARKET_TICK (on ticker update)
```json
{
  "symbol": "BTCUSDT",
  "price": 45123.45,
  "volume": 1234.56,
  "bid": 45120.00,
  "ask": 45125.00,
  "timestamp": "2024-01-15T10:30:00.123Z"
}
```

### MARKET_CANDLE (on candle close)
```json
{
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "candle": {
    "open": 45000.0,
    "high": 45200.0,
    "low": 44950.0,
    "close": 45123.45,
    "volume": 123.45,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

## REST API Methods
```python
# Historical candles
candles = await feed.get_historical_candles(
    symbol="BTCUSDT",
    resolution="15m",
    start=1705312800,  # Unix timestamp
    end=1705399200
)

# Current ticker
ticker = await feed.get_ticker("BTCUSDT")

# All products
products = await feed.get_products()
```

## Connection Lifecycle
```
START
  │
  ▼
Connect WebSocket
  │
  ▼
Authenticate (if credentials)
  │
  ▼
Subscribe to channels
  │
  ▼
Message Loop ──► Process Messages ──► Publish Events
  │                    │
  │                    ▼
  │              Connection Lost
  │                    │
  ▼                    ▼
Reconnect ◄──── Exponential Backoff
  │
  ▼
Resubscribe to channels
  │
  ▼
Continue Message Loop
```

## Reconnection Logic
- Base interval: 5 seconds
- Exponential backoff: 5s, 10s, 20s, 40s, 80s, 160s, 320s, 640s, 1280s, 2560s
- Max attempts: 10
- On success: Reset attempt counter, resubscribe to all channels

## Health Monitoring
- Ping/pong every 20 seconds
- Heartbeat published to event bus
- Stale connection detection (no messages > 60s)

## Integration Points
- **BiasDeterminingAgent**: Consumes MARKET_TICK and MARKET_CANDLE
- **MultiTimeframeConfluenceAgent**: Consumes MARKET_CANDLE
- **StyleManagingAgent**: Consumes MARKET_TICK for volatility/volume
- **LeverageAdjustmentAgent**: Consumes MARKET_TICK for margin recalc
- **PositionSizingAgent**: Consumes MARKET_TICK for notional calc
- **RiskCheckingAgent**: Consumes MARKET_TICK for P&L updates

## Usage
```python
from data.delta_exchange_feed import DeltaDataFeedAgent, DeltaConfig, DeltaEnvironment
from core.event_bus import event_bus

config = DeltaConfig(
    api_key=os.getenv("DELTA_API_KEY"),
    api_secret=os.getenv("DELTA_API_SECRET"),
    environment=DeltaEnvironment.PRODUCTION
)

feed = DeltaDataFeedAgent(config, event_bus)
await feed.start(["BTCUSDT", "ETHUSDT", "SOLUSDT"])

# Run until shutdown
await asyncio.Event().wait()

await feed.stop()
```

## Environment Variables
```bash
export DELTA_API_KEY="your_api_key"
export DELTA_API_SECRET="your_api_secret"
export DELTA_ENVIRONMENT="production"  # or "testnet"
```

## Error Handling
- WebSocket errors: Automatic reconnection
- Authentication failure: Log error, continue unauthenticated
- Message parse errors: Log and continue
- Callback errors: Isolated per callback, don't break message loop
- REST API errors: Retry with backoff, return empty on failure

## Rate Limits
- WebSocket: No explicit limit (Delta Exchange)
- REST API: 100 requests/second (Delta Exchange)
- Implements internal rate limiting for REST calls