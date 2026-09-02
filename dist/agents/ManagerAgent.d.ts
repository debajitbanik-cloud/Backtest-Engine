import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, DailyReport } from '../types';
import { LeverageAdjustmentAgent } from './LeverageAdjustmentAgent';
import { BiasDeterminingAgent } from './BiasDeterminingAgent';
import { MultiTimeframeConfluenceAgent } from './MultiTimeframeConfluenceAgent';
import { PositionSizingAgent } from './PositionSizingAgent';
import { StyleManagingAgent } from './StyleManagingAgent';
import { RiskCheckingAgent } from './RiskCheckingAgent';
import { TradeMasterAgent } from './TradeMasterAgent';
import { TimeframeRecommendationAgent } from './TimeframeRecommendationAgent';
interface AgentTypeMap {
    leverage_adjustment_agent: LeverageAdjustmentAgent;
    bias_determining_agent: BiasDeterminingAgent;
    multitimeframe_confluence_agent: MultiTimeframeConfluenceAgent;
    position_sizing_agent: PositionSizingAgent;
    style_managing_agent: StyleManagingAgent;
    risk_checking_agent: RiskCheckingAgent;
    trade_master_agent: TradeMasterAgent;
    timeframe_recommendation_agent: TimeframeRecommendationAgent;
}
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
    getSubAgent<K extends keyof AgentTypeMap>(agentId: K): AgentTypeMap[K] | undefined;
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
export {};
//# sourceMappingURL=ManagerAgent.d.ts.map