import { AgentDecision, AgentConfig, MarketData, Position, RiskMetrics } from '../types';

export abstract class BaseAgent {
  protected config: AgentConfig;
  protected lastDecision: AgentDecision | null = null;
  protected decisionHistory: AgentDecision[] = [];
  protected performance: { correct: number; total: number } = { correct: 0, total: 0 };

  constructor(config: AgentConfig) {
    this.config = config;
  }

  getId(): string {
    return this.config.id;
  }

  getName(): string {
    return this.config.name;
  }

  isEnabled(): boolean {
    return this.config.enabled;
  }

  getPriority(): number {
    return this.config.parameters.priority || this.config.priority;
  }

  abstract analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;

  protected createDecision(
    action: AgentDecision['action'],
    confidence: number,
    reasoning: string,
    parameters?: Record<string, any>
  ): AgentDecision {
    const decision: AgentDecision = {
      agentId: this.config.id,
      action,
      confidence,
      reasoning,
      parameters,
      timestamp: Date.now(),
    };
    this.lastDecision = decision;
    this.decisionHistory.push(decision);
    return decision;
  }

  recordOutcome(correct: boolean): void {
    this.performance.total++;
    if (correct) this.performance.correct++;
  }

  getAccuracy(): number {
    if (this.performance.total === 0) return 0;
    return this.performance.correct / this.performance.total;
  }

  getDecisionHistory(): AgentDecision[] {
    return [...this.decisionHistory];
  }

  getLastDecision(): AgentDecision | null {
    return this.lastDecision;
  }

  updateConfig(newConfig: Partial<AgentConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  reset(): void {
    this.lastDecision = null;
    this.decisionHistory = [];
    this.performance = { correct: 0, total: 0 };
  }
}