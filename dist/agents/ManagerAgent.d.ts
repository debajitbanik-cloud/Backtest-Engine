import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, DailyReport } from '../types';
export declare class ManagerAgent extends BaseAgent {
    private agents;
    private agentOrder;
    private lastDecisions;
    private pendingOptimizations;
    private lastDailyReport;
    private isTradingHalted;
    private haltReason;
    constructor(config: AgentConfig);
    private initializeSubAgents;
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private collectAgentDecisions;
    private buildConsensus;
    private makeFinalDecision;
    private executeRiskDecision;
    private applyOptimizations;
    haltTrading(reason: string): void;
    resumeTrading(): void;
    isHalted(): boolean;
    getHaltReason(): string;
    getSubAgent(agentId: string): BaseAgent | undefined;
    getAllSubAgents(): BaseAgent[];
    getLastDecisions(): Map<string, AgentDecision>;
    enableAgent(agentId: string): boolean;
    disableAgent(agentId: string): boolean;
    updateAgentConfig(agentId: string, config: Partial<AgentConfig>): boolean;
    getSystemStatus(): {
        isHalted: boolean;
        haltReason: string;
        activeAgents: number;
        totalAgents: number;
        currentMode: string;
        lastConsensus: any;
    };
    onDailyReport(report: DailyReport): Promise<void>;
}
//# sourceMappingURL=ManagerAgent.d.ts.map