"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TradingEngine = void 0;
const ManagerAgent_1 = require("../agents/ManagerAgent");
class TradingEngine {
    manager;
    marketDataBuffer = [];
    positions = [];
    riskMetrics;
    isRunning = false;
    updateInterval = null;
    callbacks = {};
    constructor(managerConfig) {
        this.manager = new ManagerAgent_1.ManagerAgent({
            id: 'manager_agent',
            name: 'Manager Agent',
            enabled: true,
            priority: 0,
            parameters: managerConfig?.parameters || {},
        });
        this.riskMetrics = this.initializeRiskMetrics();
    }
    initializeRiskMetrics() {
        return {
            totalExposure: 0,
            marginUsed: 0,
            marginAvailable: 10000, // Starting capital
            marginRatio: 0,
            maxDrawdown: 0,
            currentDrawdown: 0,
            var95: 0,
            sharpeRatio: 0,
            winRate: 0.5,
            profitFactor: 1.5,
            openPositions: 0,
            losingPositionsHeld: 0,
        };
    }
    setCallbacks(callbacks) {
        this.callbacks = callbacks;
    }
    async start() {
        if (this.isRunning)
            return;
        this.isRunning = true;
        console.log('Trading Engine started');
    }
    async stop() {
        this.isRunning = false;
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        console.log('Trading Engine stopped');
    }
    async processMarketData(data) {
        if (!this.isRunning)
            return null;
        this.marketDataBuffer.push(data);
        if (this.marketDataBuffer.length > 5000) {
            this.marketDataBuffer.shift();
        }
        this.updateRiskMetrics();
        const decision = await this.manager.analyze(this.marketDataBuffer, this.positions, this.riskMetrics);
        await this.handleDecision(decision);
        return decision;
    }
    updateRiskMetrics() {
        const openPositions = this.positions.filter(p => p.status === 'open');
        this.riskMetrics.openPositions = openPositions.length;
        this.riskMetrics.totalExposure = openPositions.reduce((sum, p) => sum + p.size * p.currentPrice, 0);
        this.riskMetrics.marginUsed = openPositions.reduce((sum, p) => sum + (p.size * p.currentPrice) / p.leverage, 0);
        this.riskMetrics.marginRatio = this.riskMetrics.marginUsed / (this.riskMetrics.marginUsed + this.riskMetrics.marginAvailable);
        const totalPnl = this.positions.reduce((sum, p) => sum + p.realizedPnl + p.unrealizedPnl, 0);
        const peakEquity = this.riskMetrics.marginAvailable + this.riskMetrics.marginUsed + Math.max(0, totalPnl);
        this.riskMetrics.currentDrawdown = peakEquity > 0 ? -totalPnl / peakEquity : 0;
        this.riskMetrics.maxDrawdown = Math.max(this.riskMetrics.maxDrawdown, this.riskMetrics.currentDrawdown);
        this.riskMetrics.losingPositionsHeld = openPositions.filter(p => p.unrealizedPnl < 0).length;
    }
    async handleDecision(decision) {
        if (decision.parameters?.emergency || decision.parameters?.halted) {
            this.callbacks.onRiskAlert?.(decision);
            return;
        }
        if (decision.parameters?.riskOverride) {
            this.callbacks.onRiskAlert?.(decision);
        }
        if (decision.action === 'buy' || decision.action === 'sell') {
            const signal = this.createSignalFromDecision(decision);
            if (signal) {
                this.callbacks.onSignal?.(signal);
            }
        }
        else if (decision.action === 'close' || decision.action === 'reduce') {
            this.handlePositionReduction(decision);
        }
        if (decision.parameters?.report) {
            this.callbacks.onDailyReport?.(decision.parameters.report);
            await this.manager.onDailyReport(decision.parameters.report);
        }
    }
    createSignalFromDecision(decision) {
        const styleAgent = this.manager.getSubAgent('style_managing_agent');
        const currentMode = styleAgent?.getCurrentMode() || 'swing';
        const sizingDecision = decision.parameters?.subDecisions?.find((d) => d.agentId === 'position_sizing_agent');
        const latestData = this.marketDataBuffer[this.marketDataBuffer.length - 1];
        if (!latestData)
            return null;
        const biasDecision = decision.parameters?.subDecisions?.find((d) => d.agentId === 'bias_determining_agent');
        const side = biasDecision?.parameters?.bias === 'bullish' ? 'long' : 'short';
        let leverage = 5;
        let stopLoss = 0.005;
        let takeProfit = 0.01;
        if (currentMode === 'scalping') {
            leverage = 10;
            stopLoss = 0.0005;
            takeProfit = 0.001;
        }
        if (sizingDecision?.parameters) {
            leverage = sizingDecision.parameters.maxLeverage || leverage;
        }
        const entryPrice = latestData.close;
        const stopLossPrice = side === 'long'
            ? entryPrice * (1 - stopLoss)
            : entryPrice * (1 + stopLoss);
        const takeProfitPrice = side === 'long'
            ? entryPrice * (1 + takeProfit)
            : entryPrice * (1 - takeProfit);
        return {
            symbol: latestData.symbol,
            side,
            entryPrice,
            stopLoss: stopLossPrice,
            takeProfit: takeProfitPrice,
            size: 0, // Will be calculated by PositionSizingAgent
            leverage,
            confidence: decision.confidence,
            mode: currentMode,
            timeframe: currentMode === 'scalping' ? '15m' : '4h',
            reason: `Manager consensus: ${decision.reasoning}`,
            metadata: { managerDecision: decision },
        };
    }
    handlePositionReduction(decision) {
        const openPositions = this.positions.filter(p => p.status === 'open');
        if (decision.parameters?.reduceAllPositions) {
            for (const pos of openPositions) {
                pos.size *= 0.5;
                console.log(`Reduced position ${pos.id} by 50%`);
            }
        }
        else {
            const targetIds = decision.parameters?.positionIds || [];
            for (const pos of openPositions) {
                if (targetIds.includes(pos.id)) {
                    pos.size *= 0.5;
                    console.log(`Reduced position ${pos.id} by 50%`);
                }
            }
        }
        this.callbacks.onPositionUpdate?.(this.positions);
    }
    addPosition(position) {
        this.positions.push(position);
        this.callbacks.onPositionUpdate?.(this.positions);
    }
    updatePosition(positionId, updates) {
        const index = this.positions.findIndex(p => p.id === positionId);
        if (index !== -1) {
            this.positions[index] = { ...this.positions[index], ...updates };
            this.callbacks.onPositionUpdate?.(this.positions);
        }
    }
    closePosition(positionId, exitPrice) {
        const index = this.positions.findIndex(p => p.id === positionId);
        if (index !== -1) {
            const pos = this.positions[index];
            pos.status = 'closed';
            pos.currentPrice = exitPrice;
            pos.realizedPnl = pos.side === 'long'
                ? (exitPrice - pos.entryPrice) * pos.size
                : (pos.entryPrice - exitPrice) * pos.size;
            pos.unrealizedPnl = 0;
            const tradeMaster = this.manager.getSubAgent('trade_master_agent');
            tradeMaster?.recordTrade(pos);
            this.callbacks.onPositionUpdate?.(this.positions);
        }
    }
    getPositions() {
        return [...this.positions];
    }
    getOpenPositions() {
        return this.positions.filter(p => p.status === 'open');
    }
    getRiskMetrics() {
        return { ...this.riskMetrics };
    }
    getMarketDataBuffer() {
        return [...this.marketDataBuffer];
    }
    getManager() {
        return this.manager;
    }
    getSystemStatus() {
        return this.manager.getSystemStatus();
    }
    isEngineRunning() {
        return this.isRunning;
    }
}
exports.TradingEngine = TradingEngine;
//# sourceMappingURL=TradingEngine.js.map