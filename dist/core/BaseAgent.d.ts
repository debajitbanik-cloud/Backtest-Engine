import { AgentDecision, AgentConfig, MarketData, Position, RiskMetrics } from '../types';
export declare abstract class BaseAgent {
    protected config: AgentConfig;
    protected lastDecision: AgentDecision | null;
    protected decisionHistory: AgentDecision[];
    protected performance: {
        correct: number;
        total: number;
    };
    constructor(config: AgentConfig);
    getId(): string;
    getName(): string;
    isEnabled(): boolean;
    getPriority(): number;
    abstract analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    protected createDecision(action: AgentDecision['action'], confidence: number, reasoning: string, parameters?: Record<string, any>): AgentDecision;
    recordOutcome(correct: boolean): void;
    getAccuracy(): number;
    getDecisionHistory(): AgentDecision[];
    getLastDecision(): AgentDecision | null;
    updateConfig(newConfig: Partial<AgentConfig>): void;
    reset(): void;
}
//# sourceMappingURL=BaseAgent.d.ts.map