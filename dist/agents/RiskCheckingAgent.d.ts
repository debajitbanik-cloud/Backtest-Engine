import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics } from '../types';
export declare class RiskCheckingAgent extends BaseAgent {
    private dailyPnl;
    private dailyStartEquity;
    private lastResetDate;
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private checkDailyReset;
    private assessAllRisks;
    private checkCorrelationRisk;
    private checkConcentrationRisk;
    private handleCriticalRisks;
    private handleHighRisks;
    updateDailyPnl(pnl: number): void;
    getDailyPnl(): number;
    getDailyLossPct(): number;
    canOpenNewPosition(): boolean;
    getRiskLimits(): {
        maxDrawdown: any;
        maxPositionLoss: any;
        maxHoldLosingTime: any;
        dailyLossLimit: any;
        marginCallBuffer: any;
    };
}
//# sourceMappingURL=RiskCheckingAgent.d.ts.map