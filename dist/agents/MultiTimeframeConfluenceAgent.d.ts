import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics } from '../types';
export declare class MultiTimeframeConfluenceAgent extends BaseAgent {
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private groupByTimeframe;
    private analyzeTimeframe;
    private calculateConfluence;
    private calculateRSI;
    private calculateMACD;
    private ema;
    private bollingerBands;
    private calculateATR;
    private sma;
}
//# sourceMappingURL=MultiTimeframeConfluenceAgent.d.ts.map