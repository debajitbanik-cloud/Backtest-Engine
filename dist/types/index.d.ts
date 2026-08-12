export interface MarketData {
    symbol: string;
    timestamp: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    timeframe: Timeframe;
}
export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w';
export interface Position {
    id: string;
    symbol: string;
    side: 'long' | 'short';
    entryPrice: number;
    currentPrice: number;
    size: number;
    leverage: number;
    entryTime: number;
    stopLoss?: number;
    takeProfit?: number;
    unrealizedPnl: number;
    realizedPnl: number;
    status: 'open' | 'closed' | 'liquidated';
    mode: TradingMode;
}
export type TradingMode = 'scalping' | 'swing';
export interface TradeSignal {
    symbol: string;
    side: 'long' | 'short';
    entryPrice: number;
    stopLoss: number;
    takeProfit: number;
    size: number;
    leverage: number;
    confidence: number;
    mode: TradingMode;
    timeframe: Timeframe;
    reason: string;
    metadata?: Record<string, any>;
}
export interface AgentDecision {
    agentId: string;
    action: 'buy' | 'sell' | 'hold' | 'adjust' | 'close' | 'reduce' | 'increase';
    confidence: number;
    reasoning: string;
    parameters?: Record<string, any>;
    timestamp: number;
}
export interface RiskMetrics {
    totalExposure: number;
    marginUsed: number;
    marginAvailable: number;
    marginRatio: number;
    maxDrawdown: number;
    currentDrawdown: number;
    var95: number;
    sharpeRatio: number;
    winRate: number;
    profitFactor: number;
    openPositions: number;
    losingPositionsHeld: number;
}
export interface AgentConfig {
    id: string;
    name: string;
    enabled: boolean;
    parameters: Record<string, any>;
    priority: number;
}
export interface DailyReport {
    date: string;
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    totalPnl: number;
    totalFees: number;
    maxDrawdown: number;
    sharpeRatio: number;
    winRate: number;
    avgHoldTime: number;
    bestTrade: TradeSummary;
    worstTrade: TradeSummary;
    agentPerformance: Record<string, AgentPerformance>;
    optimizations: OptimizationSuggestion[];
}
export interface TradeSummary {
    symbol: string;
    side: 'long' | 'short';
    entryPrice: number;
    exitPrice: number;
    pnl: number;
    holdTime: number;
    mode: TradingMode;
}
export interface AgentPerformance {
    agentId: string;
    decisions: number;
    correctDecisions: number;
    accuracy: number;
    contribution: number;
}
export interface OptimizationSuggestion {
    agentId: string;
    parameter: string;
    currentValue: any;
    suggestedValue: any;
    reason: string;
    expectedImpact: 'high' | 'medium' | 'low';
}
export interface MarginRequirements {
    symbol: string;
    maintenanceMargin: number;
    initialMargin: number;
    currentMarginRatio: number;
    isHighMarginPeriod: boolean;
    leverageLimit: number;
}
export interface ConfluenceSignal {
    timeframe: Timeframe;
    bias: 'bullish' | 'bearish' | 'neutral';
    strength: number;
    indicators: Record<string, number>;
}
export interface StyleConfig {
    scalping: {
        maxHoldTime: number;
        targetProfit: number;
        stopLoss: number;
        maxPositions: number;
        minConfidence: number;
    };
    swing: {
        minHoldTime: number;
        targetProfit: number;
        stopLoss: number;
        maxPositions: number;
        minConfidence: number;
    };
}
//# sourceMappingURL=index.d.ts.map