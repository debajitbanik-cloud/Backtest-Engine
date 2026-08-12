"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.defaultConfig = void 0;
exports.defaultConfig = {
    engine: {
        initialCapital: 10000,
        maxPositions: 10,
        updateInterval: 1000, // ms
        dataBufferSize: 5000,
    },
    manager: {
        decisionWeights: {
            leverage_adjustment_agent: 0.15,
            bias_determining_agent: 0.15,
            multitimeframe_confluence_agent: 0.2,
            position_sizing_agent: 0.1,
            style_managing_agent: 0.15,
            risk_checking_agent: 0.25,
        },
        consensusThreshold: 0.6,
        minAgentsForConsensus: 3,
    },
    leverageAdjustment: {
        highMarginThreshold: 0.8,
        criticalMarginThreshold: 0.9,
        leverageReductionFactor: 0.5,
        minLeverage: 1,
        maxLeverage: 100,
    },
    biasDetermining: {
        lookbackPeriods: { short: 20, medium: 50, long: 200 },
        trendStrengthThreshold: 0.6,
        momentumThreshold: 0.02,
    },
    multiTimeframeConfluence: {
        timeframes: ['15m', '1h', '4h', '1d'],
        confluenceThreshold: 0.7,
        weights: { '15m': 0.15, '1h': 0.25, '4h': 0.35, '1d': 0.25 },
    },
    positionSizing: {
        riskPerTrade: 0.02,
        maxPortfolioRisk: 0.1,
        kellyFraction: 0.25,
        minPositionSize: 10,
        maxLeverage: 20,
    },
    styleManaging: {
        scalping: {
            maxHoldTime: 15 * 60 * 1000,
            targetProfit: 0.001,
            stopLoss: 0.0005,
            maxPositions: 5,
            minConfidence: 0.7,
        },
        swing: {
            minHoldTime: 60 * 60 * 1000,
            targetProfit: 0.01,
            stopLoss: 0.005,
            maxPositions: 3,
            minConfidence: 0.6,
        },
        marginThresholdForScalping: 0.5,
    },
    riskChecking: {
        maxDrawdown: 0.1,
        maxPositionLoss: 0.05,
        maxHoldLosingTime: 4 * 60 * 60 * 1000,
        correlationLimit: 0.7,
        dailyLossLimit: 0.05,
        marginCallBuffer: 0.15,
    },
    tradeMaster: {
        maxHistorySize: 10000,
        reportTime: '00:00',
        minTradesForOptimization: 50,
    },
    symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'],
    timeframes: ['1m', '5m', '15m', '1h', '4h', '1d'],
    exchange: {
        name: 'binance',
        testnet: true,
        apiKey: '',
        apiSecret: '',
    },
    logging: {
        level: 'info',
        file: 'trading-engine.log',
        console: true,
    },
};
//# sourceMappingURL=defaultConfig.js.map