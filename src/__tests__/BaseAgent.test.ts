import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics } from '../types';

class TestAgent extends BaseAgent {
  async analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision> {
    return this.createDecision('buy', 0.8, 'Test decision');
  }
}

describe('BaseAgent', () => {
  let agent: TestAgent;
  const config: AgentConfig = {
    id: 'test_agent',
    name: 'Test Agent',
    enabled: true,
    priority: 1,
    parameters: {},
  };

  beforeEach(() => {
    agent = new TestAgent(config);
  });

  test('should initialize with correct config', () => {
    expect(agent.getId()).toBe('test_agent');
    expect(agent.getName()).toBe('Test Agent');
    expect(agent.isEnabled()).toBe(true);
    expect(agent.getPriority()).toBe(1);
  });

  test('should create decisions correctly', async () => {
    const marketData: MarketData[] = [];
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
      winRate: 0.5,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };

    const decision = await agent.analyze(marketData, positions, riskMetrics);
    expect(decision.agentId).toBe('test_agent');
    expect(decision.action).toBe('buy');
    expect(decision.confidence).toBe(0.8);
    expect(decision.reasoning).toBe('Test decision');
  });

  test('should track decision history', async () => {
    const marketData: MarketData[] = [];
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
      winRate: 0.5,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };

    await agent.analyze(marketData, positions, riskMetrics);
    await agent.analyze(marketData, positions, riskMetrics);

    const history = agent.getDecisionHistory();
    expect(history.length).toBe(2);
  });

  test('should record outcomes and calculate accuracy', () => {
    agent.recordOutcome(true);
    agent.recordOutcome(false);
    agent.recordOutcome(true);

    expect(agent.getAccuracy()).toBeCloseTo(2/3);
  });

  test('should update config', () => {
    agent.updateConfig({ enabled: false });
    expect(agent.isEnabled()).toBe(false);
  });

  test('should reset state', async () => {
    const marketData: MarketData[] = [];
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
      winRate: 0.5,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };

    await agent.analyze(marketData, positions, riskMetrics);
    agent.recordOutcome(true);

    agent.reset();

    expect(agent.getDecisionHistory().length).toBe(0);
    expect(agent.getAccuracy()).toBe(0);
    expect(agent.getLastDecision()).toBeNull();
  });
});