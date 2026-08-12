import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, TradingMode, TradeSignal } from '../types';
export declare class StyleManagingAgent extends BaseAgent {
    private currentMode;
    private modeStartTime;
    private scalpingOpportunities;
    constructor(config: AgentConfig);
    analyze(marketData: MarketData[], positions: Position[], riskMetrics: RiskMetrics): Promise<AgentDecision>;
    private shouldSwitchToScalping;
    private shouldSwitchToSwing;
    private detectScalpOpportunities;
    private checkScalpingExits;
    private checkSwingExits;
    private getModeStatusReasoning;
    getCurrentMode(): TradingMode;
    getModeConfig(mode: TradingMode): any;
    createScalpSignal(symbol: string, entryPrice: number, side: 'long' | 'short'): TradeSignal;
    createSwingSignal(symbol: string, entryPrice: number, side: 'long' | 'short'): TradeSignal;
}
//# sourceMappingURL=StyleManagingAgent.d.ts.map