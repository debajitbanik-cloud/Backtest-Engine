import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, TradeSignal } from '../types';
export declare class PositionSizingAgent extends BaseAgent {
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    calculateSignalSizing(signal: TradeSignal, marketData: MarketData[], riskMetrics: RiskMetrics, openPositions?: Position[]): TradeSignal;
    private calculateCurrentRisk;
    private calculateOptimalSizing;
    private calculateVolatility;
    adjustForCorrelation(positions: Position[], newSignal: TradeSignal): TradeSignal;
    private areCorrelated;
}
//# sourceMappingURL=PositionSizingAgent.d.ts.map