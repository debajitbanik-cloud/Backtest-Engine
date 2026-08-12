"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BiasDeterminingAgent = void 0;
const BaseAgent_1 = require("../core/BaseAgent");
const LOOKBACK_PERIODS = { short: 20, medium: 50, long: 200 };
const TREND_STRENGTH_THRESHOLD = 0.6;
const MOMENTUM_THRESHOLD = 0.02;
class BiasDeterminingAgent extends BaseAgent_1.BaseAgent {
    constructor(config) {
        const params = {
            ...config.parameters,
            lookbackPeriods: config.parameters.lookbackPeriods ?? LOOKBACK_PERIODS,
            trendStrengthThreshold: config.parameters.trendStrengthThreshold ?? TREND_STRENGTH_THRESHOLD,
            momentumThreshold: config.parameters.momentumThreshold ?? MOMENTUM_THRESHOLD,
        };
        super({
            ...config,
            id: 'bias_determining_agent',
            name: 'Bias Determining Agent',
            parameters: params,
        });
    }
    async analyze(marketData, positions, riskMetrics) {
        if (marketData.length < this.config.parameters.lookbackPeriods.long) {
            return this.createDecision('hold', 0.3, 'Insufficient data for bias determination');
        }
        const bias = this.calculateMarketBias(marketData);
        const momentum = this.calculateMomentum(marketData);
        const trendStrength = this.calculateTrendStrength(marketData);
        const volumeProfile = this.analyzeVolumeProfile(marketData);
        const overallBias = this.synthesizeBias(bias, momentum, trendStrength, volumeProfile);
        return this.createDecision(overallBias.action, overallBias.confidence, overallBias.reasoning, {
            bias: overallBias.direction,
            trendStrength,
            momentum,
            volumeProfile,
            keyLevels: this.identifyKeyLevels(marketData),
        });
    }
    calculateMarketBias(data) {
        const { short, medium, long } = this.config.parameters.lookbackPeriods;
        const closes = data.map(d => d.close);
        const smaShort = this.sma(closes, short);
        const smaMedium = this.sma(closes, medium);
        const smaLong = this.sma(closes, long);
        const currentPrice = closes[closes.length - 1];
        let bullishSignals = 0;
        let bearishSignals = 0;
        if (currentPrice > smaShort)
            bullishSignals++;
        else
            bearishSignals++;
        if (currentPrice > smaMedium)
            bullishSignals++;
        else
            bearishSignals++;
        if (currentPrice > smaLong)
            bullishSignals++;
        else
            bearishSignals++;
        if (smaShort > smaMedium)
            bullishSignals++;
        else
            bearishSignals++;
        if (smaMedium > smaLong)
            bullishSignals++;
        else
            bearishSignals++;
        const total = bullishSignals + bearishSignals;
        const strength = Math.abs(bullishSignals - bearishSignals) / total;
        if (bullishSignals > bearishSignals)
            return { direction: 'bullish', strength };
        if (bearishSignals > bullishSignals)
            return { direction: 'bearish', strength };
        return { direction: 'neutral', strength: 0 };
    }
    calculateMomentum(data) {
        const closes = data.map(d => d.close);
        const period = 14;
        if (closes.length < period + 1)
            return 0;
        const currentClose = closes[closes.length - 1];
        const pastClose = closes[closes.length - 1 - period];
        return (currentClose - pastClose) / pastClose;
    }
    calculateTrendStrength(data) {
        const closes = data.map(d => d.close);
        const period = 20;
        if (closes.length < period)
            return 0;
        const recentCloses = closes.slice(-period);
        const slope = this.linearRegressionSlope(recentCloses);
        const avgPrice = recentCloses.reduce((a, b) => a + b, 0) / recentCloses.length;
        return Math.abs(slope) / avgPrice * 100;
    }
    analyzeVolumeProfile(data) {
        const volumes = data.map(d => d.volume);
        const period = 20;
        if (volumes.length < period)
            return { trend: 'stable', strength: 0 };
        const recentVolumes = volumes.slice(-period);
        const firstHalf = recentVolumes.slice(0, period / 2).reduce((a, b) => a + b, 0) / (period / 2);
        const secondHalf = recentVolumes.slice(period / 2).reduce((a, b) => a + b, 0) / (period / 2);
        const change = (secondHalf - firstHalf) / firstHalf;
        if (change > 0.1)
            return { trend: 'increasing', strength: Math.min(change, 1) };
        if (change < -0.1)
            return { trend: 'decreasing', strength: Math.min(Math.abs(change), 1) };
        return { trend: 'stable', strength: 0 };
    }
    synthesizeBias(bias, momentum, trendStrength, volumeProfile) {
        let score = 0;
        let reasoningParts = [];
        if (bias.direction === 'bullish') {
            score += bias.strength * 0.4;
            reasoningParts.push(`MA alignment bullish (${(bias.strength * 100).toFixed(0)}%)`);
        }
        else if (bias.direction === 'bearish') {
            score -= bias.strength * 0.4;
            reasoningParts.push(`MA alignment bearish (${(bias.strength * 100).toFixed(0)}%)`);
        }
        if (momentum > this.config.parameters.momentumThreshold) {
            score += 0.3;
            reasoningParts.push(`Positive momentum (${(momentum * 100).toFixed(2)}%)`);
        }
        else if (momentum < -this.config.parameters.momentumThreshold) {
            score -= 0.3;
            reasoningParts.push(`Negative momentum (${(momentum * 100).toFixed(2)}%)`);
        }
        if (trendStrength > this.config.parameters.trendStrengthThreshold) {
            score += 0.2 * (bias.direction === 'bullish' ? 1 : -1);
            reasoningParts.push(`Strong trend (${trendStrength.toFixed(2)}%)`);
        }
        if (volumeProfile.trend === 'increasing' && volumeProfile.strength > 0.2) {
            score += 0.1 * (bias.direction === 'bullish' ? 1 : -1);
            reasoningParts.push(`Volume increasing (${(volumeProfile.strength * 100).toFixed(0)}%)`);
        }
        const confidence = Math.min(Math.abs(score), 1);
        let direction = 'neutral';
        let action = 'hold';
        if (score > 0.3) {
            direction = 'bullish';
            action = 'buy';
        }
        else if (score < -0.3) {
            direction = 'bearish';
            action = 'sell';
        }
        return {
            action,
            confidence,
            reasoning: `Bias: ${direction.toUpperCase()}. ${reasoningParts.join('; ')}`,
            direction,
        };
    }
    identifyKeyLevels(data) {
        const highs = data.map(d => d.high);
        const lows = data.map(d => d.low);
        const period = 20;
        const support = [];
        const resistance = [];
        for (let i = period; i < lows.length - period; i++) {
            const isSupport = lows.slice(i - period, i).every(l => l >= lows[i]) &&
                lows.slice(i + 1, i + 1 + period).every(l => l >= lows[i]);
            if (isSupport)
                support.push(lows[i]);
        }
        for (let i = period; i < highs.length - period; i++) {
            const isResistance = highs.slice(i - period, i).every(h => h <= highs[i]) &&
                highs.slice(i + 1, i + 1 + period).every(h => h <= highs[i]);
            if (isResistance)
                resistance.push(highs[i]);
        }
        return {
            support: [...new Set(support)].sort((a, b) => a - b).slice(-5),
            resistance: [...new Set(resistance)].sort((a, b) => a - b).slice(-5),
        };
    }
    sma(values, period) {
        if (values.length < period)
            return values[values.length - 1];
        const slice = values.slice(-period);
        return slice.reduce((a, b) => a + b, 0) / period;
    }
    linearRegressionSlope(values) {
        const n = values.length;
        const x = Array.from({ length: n }, (_, i) => i);
        const y = values;
        const sumX = x.reduce((a, b) => a + b, 0);
        const sumY = y.reduce((a, b) => a + b, 0);
        const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
        const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);
        return (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    }
}
exports.BiasDeterminingAgent = BiasDeterminingAgent;
//# sourceMappingURL=BiasDeterminingAgent.js.map