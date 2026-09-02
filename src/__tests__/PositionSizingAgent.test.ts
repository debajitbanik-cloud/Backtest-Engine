import { PositionSizingAgent } from '../agents/PositionSizingAgent';
import { AgentConfig, MarketData, Position, RiskMetrics, TradeSignal } from '../types';

describe('PositionSizingAgent', () => {
  let agent: PositionSizingAgent;
  const config: AgentConfig = {
    id: 'position_sizing_agent',
    name: 'Position Sizing Agent',
    enabled: true,
    priority: 4,
    parameters: {
      riskPerTrade: 0.02,
      maxPortfolioRisk: 0.1,
      maxLeverage: 20,
      minPositionSize: 10,
    },
  };

  beforeEach(() => {
    agent = new PositionSizingAgent(config);
  });

  test('should initialize with correct config', () => {
    expect(agent.getId()).toBe('position_sizing_agent');
    expect(agent.getName()).toBe('Position Sizing Agent');
    expect(agent.isEnabled()).toBe(true);
  });

  test('should calculate position sizing for new signal', async () => {
    const marketData: MarketData[] = Array.from({ length: 50 }, (_, i) => ({
      symbol: 'BTCUSDT',
      timestamp: Date.now() + i * 900000,
      open: 50000 + Math.random() * 1000,
      high: 51000 + Math.random() * 1000,
      low: 49000 + Math.random() * 1000,
      close: 50000 + Math.random() * 1000,
      volume: 1000 + Math.random() * 500,
      timeframe: '15m' as const,
    }));

    const positions: Position[] = [];
    const riskMetrics: RiskMetrics = {
      totalExposure: 0,
      marginUsed: 0,
      marginAvailable: 10000,
      marginRatio: 0,
      maxDrawdown: 0,
      currentDrawdown: 0,
      var95: 0,
      sharpeRatio: 0,
      winRate: 0.55,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };

    const decision = await agent.analyze(marketData, positions, riskMetrics);
    expect(decision).toBeDefined();
    expect(decision.action).toBe('adjust');
    expect(decision.parameters).toBeDefined();
    expect(decision.parameters?.riskPerTrade).toBeDefined();
    expect(decision.parameters?.maxLeverage).toBeDefined();
    expect(decision.parameters?.positionSize).toBeGreaterThan(0);
  });

  test('should reject new positions when portfolio risk is maxed', async () => {
    const marketData: MarketData[] = Array.from({ length: 50 }, (_, i) => ({
      symbol: 'BTCUSDT',
      timestamp: Date.now() + i * 900000,
      open: 50000,
      high: 51000,
      low: 49000,
      close: 50000,
      volume: 1000,
      timeframe: '15m' as const,
    }));

    const positions: Position[] = [
      {
        id: 'pos_1',
        symbol: 'BTCUSDT',
        side: 'long',
        entryPrice: 50000,
        currentPrice: 50000,
        size: 10000, // Large position
        leverage: 10,
        entryTime: Date.now(),
        stopLoss: 49000,
        unrealizedPnl: 0,
        realizedPnl: 0,
        status: 'open',
        mode: 'swing',
      },
    ];

    const riskMetrics: RiskMetrics = {
      totalExposure: 10000000,
      marginUsed: 1000000,
      marginAvailable: 0,
      marginRatio: 1,
      maxDrawdown: 0,
      currentDrawdown: 0,
      var95: 0,
      sharpeRatio: 0,
      winRate: 0.55,
      profitFactor: 1.5,
      openPositions: 1,
      losingPositionsHeld: 0,
    };

    const decision = await agent.analyze(marketData, positions, riskMetrics);
    expect(decision.action).toBe('hold');
    expect(decision.reasoning).toContain('maximum');
  });

  test('should calculate signal sizing', async () => {
    const marketData: MarketData[] = Array.from({ length: 50 }, (_, i) => ({
      symbol: 'BTCUSDT',
      timestamp: Date.now() + i * 900000,
      open: 50000,
      high: 51000,
      low: 49000,
      close: 50000,
      volume: 1000,
      timeframe: '15m' as const,
    }));

    const signal: TradeSignal = {
      symbol: 'BTCUSDT',
      side: 'long',
      entryPrice: 50000,
      stopLoss: 49500,
      takeProfit: 51000,
      size: 0,
      leverage: 10,
      confidence: 0.8,
      mode: 'swing',
      timeframe: '15m',
      reason: 'Test signal',
    };

    const riskMetrics: RiskMetrics = {
      totalExposure: 0,
      marginUsed: 0,
      marginAvailable: 10000,
      marginRatio: 0,
      maxDrawdown: 0,
      currentDrawdown: 0,
      var95: 0,
      sharpeRatio: 0,
      winRate: 0.55,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };

    const sizedSignal = agent.calculateSignalSizing(signal, marketData, riskMetrics, []);
    expect(sizedSignal.size).toBeGreaterThan(0);
    expect(sizedSignal.leverage).toBeGreaterThan(0);
  });
});