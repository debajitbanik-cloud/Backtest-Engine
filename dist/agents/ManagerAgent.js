"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ManagerAgent = void 0;
const BaseAgent_1 = require("../core/BaseAgent");
const LeverageAdjustmentAgent_1 = require("./LeverageAdjustmentAgent");
const BiasDeterminingAgent_1 = require("./BiasDeterminingAgent");
const MultiTimeframeConfluenceAgent_1 = require("./MultiTimeframeConfluenceAgent");
const PositionSizingAgent_1 = require("./PositionSizingAgent");
const StyleManagingAgent_1 = require("./StyleManagingAgent");
const RiskCheckingAgent_1 = require("./RiskCheckingAgent");
const TradeMasterAgent_1 = require("./TradeMasterAgent");
const TimeframeRecommendationAgent_1 = require("./TimeframeRecommendationAgent");
class ManagerAgent extends BaseAgent_1.BaseAgent {
    agents = new Map();
    agentOrder = [];
    lastDecisions = new Map();
    pendingOptimizations = [];
    lastDailyReport = null;
    isTradingHalted = false;
    haltReason = '';
    constructor(config) {
        const params = {
            ...config.parameters,
            decisionWeights: config.parameters.decisionWeights ?? {
                leverage_adjustment_agent: 0.12,
                bias_determining_agent: 0.15,
                multitimeframe_confluence_agent: 0.2,
                position_sizing_agent: 0.08,
                style_managing_agent: 0.12,
                risk_checking_agent: 0.2,
                timeframe_recommendation_agent: 0.13,
            },
            consensusThreshold: config.parameters.consensusThreshold ?? 0.6,
            minAgentsForConsensus: config.parameters.minAgentsForConsensus ?? 3,
        };
        super({
            ...config,
            id: 'manager_agent',
            name: 'Manager Agent',
            parameters: params,
        });
        this.initializeSubAgents();
    }
    initializeSubAgents() {
        const agentConfigs = [
            {
                id: 'leverage_adjustment_agent',
                name: 'Leverage Adjustment Agent',
                enabled: true,
                priority: 1,
                parameters: { highMarginThreshold: 0.8, criticalMarginThreshold: 0.9 },
            },
            {
                id: 'bias_determining_agent',
                name: 'Bias Determining Agent',
                enabled: true,
                priority: 2,
                parameters: { lookbackPeriods: { short: 20, medium: 50, long: 200 } },
            },
            {
                id: 'multitimeframe_confluence_agent',
                name: 'Multi-Timeframe Confluence Agent',
                enabled: true,
                priority: 3,
                parameters: { confluenceThreshold: 0.7 },
            },
            {
                id: 'position_sizing_agent',
                name: 'Position Sizing Agent',
                enabled: true,
                priority: 4,
                parameters: { riskPerTrade: 0.02, maxPortfolioRisk: 0.1 },
            },
            {
                id: 'style_managing_agent',
                name: 'Style Managing Agent',
                enabled: true,
                priority: 5,
                parameters: { marginThresholdForScalping: 0.5 },
            },
            {
                id: 'risk_checking_agent',
                name: 'Risk Checking Agent',
                enabled: true,
                priority: 6,
                parameters: { maxDrawdown: 0.1, dailyLossLimit: 0.05 },
            },
            {
                id: 'trade_master_agent',
                name: 'Trade Master Agent',
                enabled: true,
                priority: 7,
                parameters: { reportTime: '00:00' },
            },
            {
                id: 'timeframe_recommendation_agent',
                name: 'Timeframe Recommendation Agent',
                enabled: true,
                priority: 8,
                parameters: {
                    availableTimeframes: ['1m', '5m', '15m', '1h', '4h'],
                    preferredTimeframes: ['15m', '1h'],
                    minConfidence: 0.55,
                    confluenceWeight: 0.35,
                    biasWeight: 0.30,
                    riskWeight: 0.20,
                    modeWeight: 0.15,
                    maxHistory: 100,
                },
            },
        ];
        for (const agentConfig of agentConfigs) {
            let agent;
            switch (agentConfig.id) {
                case 'leverage_adjustment_agent':
                    agent = new LeverageAdjustmentAgent_1.LeverageAdjustmentAgent(agentConfig);
                    break;
                case 'bias_determining_agent':
                    agent = new BiasDeterminingAgent_1.BiasDeterminingAgent(agentConfig);
                    break;
                case 'multitimeframe_confluence_agent':
                    agent = new MultiTimeframeConfluenceAgent_1.MultiTimeframeConfluenceAgent(agentConfig);
                    break;
                case 'position_sizing_agent':
                    agent = new PositionSizingAgent_1.PositionSizingAgent(agentConfig);
                    break;
                case 'style_managing_agent':
                    agent = new StyleManagingAgent_1.StyleManagingAgent(agentConfig);
                    break;
                case 'risk_checking_agent':
                    agent = new RiskCheckingAgent_1.RiskCheckingAgent(agentConfig);
                    break;
                case 'trade_master_agent':
                    agent = new TradeMasterAgent_1.TradeMasterAgent(agentConfig);
                    break;
                case 'timeframe_recommendation_agent':
                    agent = new TimeframeRecommendationAgent_1.TimeframeRecommendationAgent(agentConfig);
                    break;
                default:
                    continue;
            }
            this.agents.set(agentConfig.id, agent);
            this.agentOrder.push(agentConfig.id);
        }
        this.agentOrder.sort((a, b) => {
            const agentA = this.agents.get(a);
            const agentB = this.agents.get(b);
            return (agentA?.getPriority() || 0) - (agentB?.getPriority() || 0);
        });
    }
    async analyze(marketData, positions, riskMetrics) {
        if (this.isTradingHalted) {
            return this.createDecision('hold', 1.0, `TRADING HALTED: ${this.haltReason}`, { halted: true });
        }
        const decisions = await this.collectAgentDecisions(marketData, positions, riskMetrics);
        this.lastDecisions = new Map(decisions.map(d => [d.agentId, d]));
        const riskDecision = decisions.find(d => d.agentId === 'risk_checking_agent');
        if (riskDecision && (riskDecision.action === 'close' || riskDecision.action === 'reduce')) {
            return this.executeRiskDecision(riskDecision, decisions);
        }
        const consensus = this.buildConsensus(decisions);
        const finalDecision = this.makeFinalDecision(consensus, decisions, positions, riskMetrics);
        this.applyOptimizations();
        return finalDecision;
    }
    async collectAgentDecisions(marketData, positions, riskMetrics) {
        const decisions = [];
        for (const agentId of this.agentOrder) {
            const agent = this.agents.get(agentId);
            if (!agent || !agent.isEnabled())
                continue;
            try {
                const decision = await agent.analyze(marketData, positions, riskMetrics);
                decisions.push(decision);
            }
            catch (error) {
                console.error(`Error in agent ${agentId}:`, error);
                decisions.push(this.createDecision('hold', 0, `Agent error: ${error}`, { agentId, error: true }));
            }
        }
        return decisions;
    }
    buildConsensus(decisions) {
        const weights = this.config.parameters.decisionWeights;
        let buyScore = 0;
        let sellScore = 0;
        let holdScore = 0;
        let reduceScore = 0;
        let closeScore = 0;
        let totalWeight = 0;
        for (const decision of decisions) {
            const weight = weights[decision.agentId] || 0.1;
            totalWeight += weight;
            const weightedConfidence = decision.confidence * weight;
            switch (decision.action) {
                case 'buy':
                    buyScore += weightedConfidence;
                    break;
                case 'sell':
                    sellScore += weightedConfidence;
                    break;
                case 'hold':
                    holdScore += weightedConfidence;
                    break;
                case 'reduce':
                    reduceScore += weightedConfidence;
                    break;
                case 'close':
                    closeScore += weightedConfidence;
                    break;
                case 'adjust':
                    holdScore += weightedConfidence * 0.5;
                    break;
            }
        }
        const scores = { buy: buyScore, sell: sellScore, hold: holdScore, reduce: reduceScore, close: closeScore };
        const maxAction = Object.entries(scores).reduce((a, b) => scores[a[0]] > scores[b[0]] ? a : b);
        const confidence = maxAction[1] / totalWeight;
        const participatingAgents = decisions.filter(d => d.confidence > 0.3).length;
        let reasoning = `Consensus: ${maxAction[0].toUpperCase()} (${(confidence * 100).toFixed(1)}% confidence). `;
        reasoning += `${participatingAgents}/${decisions.length} agents participated. `;
        reasoning += `Scores: Buy:${buyScore.toFixed(2)} Sell:${sellScore.toFixed(2)} Hold:${holdScore.toFixed(2)} Reduce:${reduceScore.toFixed(2)} Close:${closeScore.toFixed(2)}`;
        return { action: maxAction[0], confidence, reasoning };
    }
    makeFinalDecision(consensus, decisions, positions, riskMetrics) {
        const styleAgent = this.getSubAgent('style_managing_agent');
        const currentMode = styleAgent?.getCurrentMode() || 'swing';
        let finalAction = consensus.action;
        let finalConfidence = consensus.confidence;
        let finalReasoning = consensus.reasoning;
        if (consensus.confidence < this.config.parameters.consensusThreshold) {
            finalAction = 'hold';
            finalConfidence = 0.5;
            finalReasoning = `Consensus below threshold (${this.config.parameters.consensusThreshold}). Defaulting to HOLD. ${consensus.reasoning}`;
        }
        if (finalAction === 'buy' || finalAction === 'sell') {
            const sizingAgent = this.getSubAgent('position_sizing_agent');
            const sizingDecision = decisions.find(d => d.agentId === 'position_sizing_agent');
            if (sizingDecision && sizingDecision.parameters) {
                finalReasoning += ` | Position sizing: ${sizingDecision.reasoning}`;
            }
        }
        if (finalAction === 'buy' || finalAction === 'sell') {
            const biasDecision = decisions.find(d => d.agentId === 'bias_determining_agent');
            const confluenceDecision = decisions.find(d => d.agentId === 'multitimeframe_confluence_agent');
            if (biasDecision && confluenceDecision) {
                const biasAligns = (finalAction === 'buy' && biasDecision.parameters?.bias === 'bullish') ||
                    (finalAction === 'sell' && biasDecision.parameters?.bias === 'bearish');
                const confluenceAligns = (finalAction === 'buy' && confluenceDecision.parameters?.confluenceScore > 0.6) ||
                    (finalAction === 'sell' && confluenceDecision.parameters?.confluenceScore > 0.6);
                if (!biasAligns || !confluenceAligns) {
                    finalConfidence *= 0.7;
                    finalReasoning += ` | Warning: Bias/Confluence misalignment detected`;
                }
            }
        }
        return this.createDecision(finalAction, finalConfidence, finalReasoning, {
            consensus,
            subDecisions: decisions.map(d => ({ agentId: d.agentId, action: d.action, confidence: d.confidence })),
            currentMode,
            riskMetrics: {
                marginRatio: riskMetrics.marginUsed / (riskMetrics.marginUsed + riskMetrics.marginAvailable),
                drawdown: riskMetrics.currentDrawdown,
                dailyPnl: riskMetrics.marginAvailable > 0 ? 0 : 0,
            },
        });
    }
    executeRiskDecision(riskDecision, allDecisions) {
        if (riskDecision.parameters?.emergency) {
            this.haltTrading(riskDecision.reasoning);
            return this.createDecision('close', 1.0, `EMERGENCY: ${riskDecision.reasoning}`, { emergency: true, halted: true });
        }
        return this.createDecision(riskDecision.action, riskDecision.confidence, `RISK OVERRIDE: ${riskDecision.reasoning}`, {
            riskOverride: true,
            originalConsensus: this.buildConsensus(allDecisions.filter(d => d.agentId !== 'risk_checking_agent')),
        });
    }
    applyOptimizations() {
        const tradeMaster = this.getSubAgent('trade_master_agent');
        if (tradeMaster) {
            const optimizations = tradeMaster.getPendingOptimizations();
            for (const opt of optimizations) {
                if (opt.expectedImpact === 'high') {
                    const targetAgent = this.agents.get(opt.agentId);
                    if (targetAgent) {
                        targetAgent.updateConfig({ parameters: { [opt.parameter]: opt.suggestedValue } });
                        this.pendingOptimizations = this.pendingOptimizations.filter(o => o !== opt);
                        console.log(`Applied optimization: ${opt.agentId}.${opt.parameter} = ${opt.suggestedValue}`);
                    }
                }
            }
        }
    }
    haltTrading(reason) {
        this.isTradingHalted = true;
        this.haltReason = reason;
        console.log(`TRADING HALTED: ${reason}`);
    }
    resumeTrading() {
        this.isTradingHalted = false;
        this.haltReason = '';
        console.log('Trading resumed');
    }
    isHalted() {
        return this.isTradingHalted;
    }
    getHaltReason() {
        return this.haltReason;
    }
    getSubAgent(agentId) {
        return this.agents.get(agentId);
    }
    getAllSubAgents() {
        return Array.from(this.agents.values());
    }
    getLastDecisions() {
        return new Map(this.lastDecisions);
    }
    enableAgent(agentId) {
        const agent = this.agents.get(agentId);
        if (agent) {
            agent.updateConfig({ enabled: true });
            return true;
        }
        return false;
    }
    disableAgent(agentId) {
        const agent = this.agents.get(agentId);
        if (agent) {
            agent.updateConfig({ enabled: false });
            return true;
        }
        return false;
    }
    updateAgentConfig(agentId, config) {
        const agent = this.agents.get(agentId);
        if (agent) {
            agent.updateConfig(config);
            return true;
        }
        return false;
    }
    getSystemStatus() {
        const styleAgent = this.getSubAgent('style_managing_agent');
        return {
            isHalted: this.isTradingHalted,
            haltReason: this.haltReason,
            activeAgents: Array.from(this.agents.values()).filter(a => a.isEnabled()).length,
            totalAgents: this.agents.size,
            currentMode: styleAgent?.getCurrentMode() || 'unknown',
            lastConsensus: this.lastDecisions.get('manager_agent')?.parameters?.consensus,
        };
    }
    async onDailyReport(report) {
        this.lastDailyReport = report;
        this.pendingOptimizations = report.optimizations;
        console.log(`Daily Report Received: ${report.date}`);
        console.log(`  Trades: ${report.totalTrades} (W: ${report.winningTrades}, L: ${report.losingTrades})`);
        console.log(`  PnL: $${report.totalPnl.toFixed(2)} | Win Rate: ${(report.winRate * 100).toFixed(1)}%`);
        console.log(`  Optimizations: ${report.optimizations.length}`);
        for (const opt of report.optimizations) {
            console.log(`  - ${opt.agentId}.${opt.parameter}: ${opt.currentValue} -> ${opt.suggestedValue} (${opt.expectedImpact})`);
        }
    }
}
exports.ManagerAgent = ManagerAgent;
//# sourceMappingURL=ManagerAgent.js.map