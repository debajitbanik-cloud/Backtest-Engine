export declare const defaultConfig: {
    engine: {
        initialCapital: number;
        maxPositions: number;
        updateInterval: number;
        dataBufferSize: number;
    };
    manager: {
        decisionWeights: {
            leverage_adjustment_agent: number;
            bias_determining_agent: number;
            multitimeframe_confluence_agent: number;
            position_sizing_agent: number;
            style_managing_agent: number;
            risk_checking_agent: number;
        };
        consensusThreshold: number;
        minAgentsForConsensus: number;
    };
    leverageAdjustment: {
        highMarginThreshold: number;
        criticalMarginThreshold: number;
        leverageReductionFactor: number;
        minLeverage: number;
        maxLeverage: number;
    };
    biasDetermining: {
        lookbackPeriods: {
            short: number;
            medium: number;
            long: number;
        };
        trendStrengthThreshold: number;
        momentumThreshold: number;
    };
    multiTimeframeConfluence: {
        timeframes: readonly ["15m", "1h", "4h", "1d"];
        confluenceThreshold: number;
        weights: {
            '15m': number;
            '1h': number;
            '4h': number;
            '1d': number;
        };
    };
    positionSizing: {
        riskPerTrade: number;
        maxPortfolioRisk: number;
        kellyFraction: number;
        minPositionSize: number;
        maxLeverage: number;
    };
    styleManaging: {
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
        marginThresholdForScalping: number;
    };
    riskChecking: {
        maxDrawdown: number;
        maxPositionLoss: number;
        maxHoldLosingTime: number;
        correlationLimit: number;
        dailyLossLimit: number;
        marginCallBuffer: number;
    };
    tradeMaster: {
        maxHistorySize: number;
        reportTime: string;
        minTradesForOptimization: number;
    };
    symbols: string[];
    timeframes: readonly ["1m", "5m", "15m", "1h", "4h", "1d"];
    exchange: {
        name: string;
        testnet: boolean;
        apiKey: string;
        apiSecret: string;
    };
    logging: {
        level: string;
        file: string;
        console: boolean;
    };
};
export type Config = typeof defaultConfig;
//# sourceMappingURL=defaultConfig.d.ts.map