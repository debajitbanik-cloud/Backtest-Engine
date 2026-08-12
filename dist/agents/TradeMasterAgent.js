"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TradeMasterAgent = void 0;
const BaseAgent_1 = require("../core/BaseAgent");
class TradeMasterAgent extends BaseAgent_1.BaseAgent {
    tradeHistory = [];
    dailyReports = [];
    agentPerformances = new Map();
    insights = [];
    lastReportDate = '';
    optimizationQueue = [];
    constructor(config) {
        const params = {
            ...config.parameters,
            maxHistorySize: config.parameters.maxHistorySize ?? 10000,
            reportTime: config.parameters.reportTime ?? '00:00',
            minTradesForOptimization: config.parameters.minTradesForOptimization ?? 50,
        };
        super({
            ...config,
            id: 'trade_master_agent',
            name: 'Trade Master Agent',
            parameters: params,
        });
    }
    async analyze(marketData, positions, riskMetrics) {
        this.updateTradeHistory(positions);
        this.updateAgentPerformances();
        const today = new Date().toDateString();
        if (today !== this.lastReportDate && this.shouldGenerateReport()) {
            const report = this.generateDailyReport(riskMetrics);
            this.dailyReports.push(report);
            this.lastReportDate = today;
            return this.createDecision('adjust', 0.8, `Daily report generated: ${report.totalTrades} trades, ${(report.winRate * 100).toFixed(1)}% win rate, $${report.totalPnl.toFixed(2)} PnL`, { report, optimizations: this.optimizationQueue });
        }
        const optimizations = this.generateOptimizations();
        this.optimizationQueue = optimizations;
        return this.createDecision('hold', 0.6, `TradeMaster monitoring: ${this.tradeHistory.length} trades in history, ${optimizations.length} pending optimizations`, { optimizations, insights: this.insights.slice(-5) });
    }
    recordTrade(position) {
        if (position.status === 'closed' && position.realizedPnl !== 0) {
            this.tradeHistory.push({ ...position });
            this.generateInsights(position);
            if (this.tradeHistory.length > this.config.parameters.maxHistorySize) {
                this.tradeHistory.shift();
            }
        }
    }
    recordAgentDecision(agentId, decision, outcome) {
        let perf = this.agentPerformances.get(agentId);
        if (!perf) {
            perf = {
                agentId,
                decisions: 0,
                correctDecisions: 0,
                accuracy: 0,
                contribution: 0,
            };
            this.agentPerformances.set(agentId, perf);
        }
        perf.decisions++;
        if (outcome === 'correct')
            perf.correctDecisions++;
        perf.accuracy = perf.correctDecisions / perf.decisions;
    }
    updateTradeHistory(positions) {
        for (const pos of positions) {
            if (pos.status === 'closed' && !this.tradeHistory.find(t => t.id === pos.id)) {
                this.recordTrade(pos);
            }
        }
    }
    updateAgentPerformances() {
        const recentTrades = this.tradeHistory.slice(-100);
        const agentContributions = new Map();
        for (const trade of recentTrades) {
            if (trade.metadata?.contributingAgents) {
                for (const agentId of trade.metadata.contributingAgents) {
                    agentContributions.set(agentId, (agentContributions.get(agentId) || 0) + trade.realizedPnl);
                }
            }
        }
        for (const [agentId, contribution] of agentContributions) {
            const perf = this.agentPerformances.get(agentId);
            if (perf) {
                perf.contribution = contribution;
            }
        }
    }
    generateInsights(position) {
        const holdTimeHours = (position.entryTime - Date.now()) / 3600000;
        const pnlPct = position.realizedPnl / (position.size * position.entryPrice);
        let insight = '';
        if (pnlPct > 0.02) {
            insight = `WIN: ${position.symbol} ${position.side} ${position.mode} +${(pnlPct * 100).toFixed(2)}% in ${Math.abs(holdTimeHours).toFixed(1)}h`;
        }
        else if (pnlPct < -0.01) {
            insight = `LOSS: ${position.symbol} ${position.side} ${position.mode} ${(pnlPct * 100).toFixed(2)}% in ${Math.abs(holdTimeHours).toFixed(1)}h - Review entry criteria`;
        }
        else {
            insight = `FLAT: ${position.symbol} ${position.side} ${position.mode} ${(pnlPct * 100).toFixed(2)}%`;
        }
        this.insights.push(`[${new Date().toISOString()}] ${insight}`);
        if (this.insights.length > 500) {
            this.insights = this.insights.slice(-250);
        }
    }
    shouldGenerateReport() {
        const now = new Date();
        const [hours, minutes] = this.config.parameters.reportTime.split(':').map(Number);
        return now.getHours() === hours && now.getMinutes() >= minutes;
    }
    generateDailyReport(riskMetrics) {
        const today = new Date().toDateString();
        const todayTrades = this.tradeHistory.filter(t => new Date(t.entryTime).toDateString() === today);
        const winningTrades = todayTrades.filter(t => t.realizedPnl > 0);
        const losingTrades = todayTrades.filter(t => t.realizedPnl < 0);
        const totalPnl = todayTrades.reduce((sum, t) => sum + t.realizedPnl, 0);
        const totalFees = todayTrades.reduce((sum, t) => sum + (t.metadata?.fees || 0), 0);
        const holdTimes = todayTrades.map(t => (Date.now() - t.entryTime) / 3600000);
        const avgHoldTime = holdTimes.length > 0
            ? holdTimes.reduce((a, b) => a + b, 0) / holdTimes.length
            : 0;
        const sortedByPnl = [...todayTrades].sort((a, b) => b.realizedPnl - a.realizedPnl);
        const bestTrade = sortedByPnl[0];
        const worstTrade = sortedByPnl[sortedByPnl.length - 1];
        const agentPerformance = {};
        for (const [id, perf] of this.agentPerformances) {
            agentPerformance[id] = { ...perf };
        }
        return {
            date: today,
            totalTrades: todayTrades.length,
            winningTrades: winningTrades.length,
            losingTrades: losingTrades.length,
            totalPnl,
            totalFees,
            maxDrawdown: riskMetrics.maxDrawdown,
            sharpeRatio: riskMetrics.sharpeRatio,
            winRate: todayTrades.length > 0 ? winningTrades.length / todayTrades.length : 0,
            avgHoldTime,
            bestTrade: bestTrade ? {
                symbol: bestTrade.symbol,
                side: bestTrade.side,
                entryPrice: bestTrade.entryPrice,
                exitPrice: bestTrade.currentPrice,
                pnl: bestTrade.realizedPnl,
                holdTime: (Date.now() - bestTrade.entryTime) / 3600000,
                mode: bestTrade.mode,
            } : { symbol: '', side: 'long', entryPrice: 0, exitPrice: 0, pnl: 0, holdTime: 0, mode: 'swing' },
            worstTrade: worstTrade ? {
                symbol: worstTrade.symbol,
                side: worstTrade.side,
                entryPrice: worstTrade.entryPrice,
                exitPrice: worstTrade.currentPrice,
                pnl: worstTrade.realizedPnl,
                holdTime: (Date.now() - worstTrade.entryTime) / 3600000,
                mode: worstTrade.mode,
            } : { symbol: '', side: 'long', entryPrice: 0, exitPrice: 0, pnl: 0, holdTime: 0, mode: 'swing' },
            agentPerformance,
            optimizations: this.optimizationQueue,
        };
    }
    generateOptimizations() {
        const suggestions = [];
        if (this.tradeHistory.length < this.config.parameters.minTradesForOptimization) {
            return suggestions;
        }
        const recentTrades = this.tradeHistory.slice(-200);
        const winRate = recentTrades.filter(t => t.realizedPnl > 0).length / recentTrades.length;
        const avgWin = recentTrades.filter(t => t.realizedPnl > 0).reduce((a, b) => a + b.realizedPnl, 0) / Math.max(1, recentTrades.filter(t => t.realizedPnl > 0).length);
        const avgLoss = recentTrades.filter(t => t.realizedPnl < 0).reduce((a, b) => a + Math.abs(b.realizedPnl), 0) / Math.max(1, recentTrades.filter(t => t.realizedPnl < 0).length);
        // Optimize risk per trade based on Kelly
        if (winRate > 0 && avgWin > 0 && avgLoss > 0) {
            const kellyOptimal = (winRate * avgWin - (1 - winRate) * avgLoss) / avgWin;
            const currentRisk = 0.02; // Would get from PositionSizingAgent
            if (Math.abs(kellyOptimal - currentRisk) > 0.005) {
                suggestions.push({
                    agentId: 'position_sizing_agent',
                    parameter: 'riskPerTrade',
                    currentValue: currentRisk,
                    suggestedValue: Math.max(0.005, Math.min(0.05, kellyOptimal * 0.25)),
                    reason: `Kelly criterion suggests ${(kellyOptimal * 100).toFixed(1)}% optimal risk, current is ${(currentRisk * 100).toFixed(1)}%`,
                    expectedImpact: 'high',
                });
            }
        }
        // Optimize scalping vs swing allocation
        const scalpingTrades = recentTrades.filter(t => t.mode === 'scalping');
        const swingTrades = recentTrades.filter(t => t.mode === 'swing');
        if (scalpingTrades.length > 20 && swingTrades.length > 20) {
            const scalpWinRate = scalpingTrades.filter(t => t.realizedPnl > 0).length / scalpingTrades.length;
            const swingWinRate = swingTrades.filter(t => t.realizedPnl > 0).length / swingTrades.length;
            if (Math.abs(scalpWinRate - swingWinRate) > 0.1) {
                suggestions.push({
                    agentId: 'style_managing_agent',
                    parameter: 'marginThresholdForScalping',
                    currentValue: 0.5,
                    suggestedValue: scalpWinRate > swingWinRate ? 0.6 : 0.4,
                    reason: `Scalping win rate: ${(scalpWinRate * 100).toFixed(1)}%, Swing win rate: ${(swingWinRate * 100).toFixed(1)}%. Adjust threshold to favor better mode.`,
                    expectedImpact: 'medium',
                });
            }
        }
        // Optimize stop loss based on volatility
        const losingTrades = recentTrades.filter(t => t.realizedPnl < 0);
        if (losingTrades.length > 10) {
            const avgLossPct = losingTrades.reduce((sum, t) => sum + Math.abs(t.realizedPnl) / (t.size * t.entryPrice), 0) / losingTrades.length;
            const currentStopLoss = 0.005; // Would get from StyleManagingAgent
            if (avgLossPct > currentStopLoss * 1.5) {
                suggestions.push({
                    agentId: 'style_managing_agent',
                    parameter: 'styleConfig.swing.stopLoss',
                    currentValue: currentStopLoss,
                    suggestedValue: Math.min(0.02, avgLossPct * 1.2),
                    reason: `Average loss ${(avgLossPct * 100).toFixed(2)}% exceeds stop loss ${(currentStopLoss * 100).toFixed(2)}%. Widen stops to avoid premature exits.`,
                    expectedImpact: 'high',
                });
            }
        }
        // Agent performance optimization
        for (const [agentId, perf] of this.agentPerformances) {
            if (perf.decisions > 50 && perf.accuracy < 0.45) {
                suggestions.push({
                    agentId,
                    parameter: 'enabled',
                    currentValue: true,
                    suggestedValue: false,
                    reason: `Agent ${agentId} accuracy only ${(perf.accuracy * 100).toFixed(1)}% over ${perf.decisions} decisions. Consider disabling or retraining.`,
                    expectedImpact: 'high',
                });
            }
        }
        return suggestions;
    }
    getTradeHistory() {
        return [...this.tradeHistory];
    }
    getDailyReports() {
        return [...this.dailyReports];
    }
    getInsights() {
        return [...this.insights];
    }
    getAgentPerformances() {
        return Array.from(this.agentPerformances.values());
    }
    getPendingOptimizations() {
        return [...this.optimizationQueue];
    }
    applyOptimization(suggestion) {
        // In real implementation, this would update the target agent's config
        this.optimizationQueue = this.optimizationQueue.filter(o => o !== suggestion);
        this.insights.push(`[${new Date().toISOString()}] APPLIED: ${suggestion.agentId}.${suggestion.parameter} = ${suggestion.suggestedValue}`);
        return true;
    }
    getPerformanceSummary() {
        const totalTrades = this.tradeHistory.length;
        const winningTrades = this.tradeHistory.filter(t => t.realizedPnl > 0).length;
        const winRate = totalTrades > 0 ? winningTrades / totalTrades : 0;
        const totalPnl = this.tradeHistory.reduce((sum, t) => sum + t.realizedPnl, 0);
        let bestAgent = '';
        let worstAgent = '';
        let bestAcc = 0;
        let worstAcc = 1;
        for (const [id, perf] of this.agentPerformances) {
            if (perf.decisions > 10) {
                if (perf.accuracy > bestAcc) {
                    bestAcc = perf.accuracy;
                    bestAgent = id;
                }
                if (perf.accuracy < worstAcc) {
                    worstAcc = perf.accuracy;
                    worstAgent = id;
                }
            }
        }
        return { totalTrades, winRate, totalPnl, sharpeRatio: 0, bestAgent, worstAgent };
    }
}
exports.TradeMasterAgent = TradeMasterAgent;
//# sourceMappingURL=TradeMasterAgent.js.map