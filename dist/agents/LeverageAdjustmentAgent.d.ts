import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, MarginRequirements, Position, RiskMetrics } from '../types';
export declare class LeverageAdjustmentAgent extends BaseAgent {
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private calculateMarginRequirements;
    private calculateLeverageLimit;
    private handleHighMarginPeriod;
    onMarginUpdate(marginRequirements: MarginRequirements): Promise<AgentDecision>;
}
//# sourceMappingURL=LeverageAdjustmentAgent.d.ts.map