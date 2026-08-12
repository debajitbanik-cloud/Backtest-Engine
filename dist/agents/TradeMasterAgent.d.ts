import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, DailyReport, MarketData, Position, RiskMetrics, OptimizationSuggestion, AgentPerformance } from '../types';
interface PositionWithMetadata extends Position {
    metadata?: {
        contributingAgents?: string[];
        fees?: number;
    };
}
export declare class TradeMasterAgent extends BaseAgent {
    private tradeHistory;
    private dailyReports;
    private agentPerformances;
    private insights;
    private lastReportDate;
    private optimizationQueue;
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    recordTrade(position: PositionWithMetadata): void;
    recordAgentDecision(agentId: string, decision: AgentDecision, outcome: 'correct' | 'incorrect' | 'unknown'): void;
    private updateTradeHistory;
    private updateAgentPerformances;
    private generateInsights;
    private shouldGenerateReport;
    private generateDailyReport;
    private generateOptimizations;
    getTradeHistory(): Position[];
    getDailyReports(): DailyReport[];
    getInsights(): string[];
    getAgentPerformances(): AgentPerformance[];
    getPendingOptimizations(): OptimizationSuggestion[];
    applyOptimization(suggestion: OptimizationSuggestion): boolean;
    getPerformanceSummary(): {
        totalTrades: number;
        winRate: number;
        totalPnl: number;
        sharpeRatio: number;
        bestAgent: string;
        worstAgent: string;
    };
}
export {};
//# sourceMappingURL=TradeMasterAgent.d.ts.map