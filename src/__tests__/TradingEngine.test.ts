import { TradingEngine } from '../core/TradingEngine';
import { MarketData, TradeSignal, Position, RiskMetrics } from '../types';

describe('TradingEngine', () => {
  let engine: TradingEngine;

  beforeEach(() => {
    engine = new TradingEngine();
  });

  test('should initialize with default config', () => {
    expect(engine.isEngineRunning()).toBe(false);
    expect(engine.getPositions().length).toBe(0);
    expect(engine.getOpenPositions().length).toBe(0);
  });

  test('should start and stop correctly', async () => {
    await engine.start();
    expect(engine.isEngineRunning()).toBe(true);

    await engine.stop();
    expect(engine.isEngineRunning()).toBe(false);
  });

  test('should process market data', async () => {
    await engine.start();

    const marketData: MarketData = {
      symbol: 'BTCUSDT',
      timestamp: Date.now(),
      open: 50000,
      high: 51000,
      low: 49000,
      close: 50500,
      volume: 1000,
      timeframe: '15m',
    };

    const decision = await engine.processMarketData(marketData);
    expect(decision).toBeDefined();
    expect(decision?.agentId).toBe('manager_agent');

    await engine.stop();
  });

  test('should update risk metrics', async () => {
    await engine.start();

    const marketData: MarketData = {
      symbol: 'BTCUSDT',
      timestamp: Date.now(),
      open: 50000,
      high: 51000,
      low: 49000,
      close: 50500,
      volume: 1000,
      timeframe: '15m',
    };

    await engine.processMarketData(marketData);

    const riskMetrics = engine.getRiskMetrics();
    expect(riskMetrics).toBeDefined();
    expect(riskMetrics.marginAvailable).toBeGreaterThan(0);

    await engine.stop();
  });

  test('should add and update positions', async () => {
    await engine.start();

    const position: Position = {
      id: 'test_pos_1',
      symbol: 'BTCUSDT',
      side: 'long',
      entryPrice: 50000,
      currentPrice: 51000,
      size: 0.1,
      leverage: 10,
      entryTime: Date.now(),
      stopLoss: 49000,
      takeProfit: 52000,
      unrealizedPnl: 100,
      realizedPnl: 0,
      status: 'open',
      mode: 'swing',
    };

    engine.addPosition(position);
    const positions = engine.getPositions();
    expect(positions.length).toBe(1);
    expect(positions[0].id).toBe('test_pos_1');

    engine.updatePosition('test_pos_1', { currentPrice: 52000, unrealizedPnl: 200 });
    const updated = engine.getPositions();
    expect(updated[0].currentPrice).toBe(52000);
    expect(updated[0].unrealizedPnl).toBe(200);

    await engine.stop();
  });

  test('should close positions and calculate PnL', async () => {
    await engine.start();

    const position: Position = {
      id: 'test_pos_1',
      symbol: 'BTCUSDT',
      side: 'long',
      entryPrice: 50000,
      currentPrice: 51000,
      size: 0.1,
      leverage: 10,
      entryTime: Date.now(),
      stopLoss: 49000,
      takeProfit: 52000,
      unrealizedPnl: 100,
      realizedPnl: 0,
      status: 'open',
      mode: 'swing',
    };

    engine.addPosition(position);
    engine.closePosition('test_pos_1', 52000);

    const positions = engine.getPositions();
    expect(positions[0].status).toBe('closed');
    expect(positions[0].realizedPnl).toBe(200); // (52000 - 50000) * 0.1

    await engine.stop();
  });
});