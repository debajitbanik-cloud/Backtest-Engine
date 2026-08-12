import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics } from '../types';
export declare class BiasDeterminingAgent extends BaseAgent {
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private calculateMarketBias;
    private calculateMomentum;
    private calculateTrendStrength;
    private analyzeVolumeProfile;
    private synthesizeBias;
    private identifyKeyLevels;
    private sma;
    private linearRegressionSlope;
}
//# sourceMappingURL=BiasDeterminingAgent.d.ts.map