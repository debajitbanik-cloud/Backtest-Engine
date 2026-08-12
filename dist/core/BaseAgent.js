"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BaseAgent = void 0;
class BaseAgent {
    config;
    lastDecision = null;
    decisionHistory = [];
    performance = { correct: 0, total: 0 };
    constructor(config) {
        this.config = config;
    }
    getId() {
        return this.config.id;
    }
    getName() {
        return this.config.name;
    }
    isEnabled() {
        return this.config.enabled;
    }
    getPriority() {
        return this.config.parameters.priority || this.config.priority;
    }
    createDecision(action, confidence, reasoning, parameters) {
        const decision = {
            agentId: this.config.id,
            action,
            confidence,
            reasoning,
            parameters,
            timestamp: Date.now(),
        };
        this.lastDecision = decision;
        this.decisionHistory.push(decision);
        return decision;
    }
    recordOutcome(correct) {
        this.performance.total++;
        if (correct)
            this.performance.correct++;
    }
    getAccuracy() {
        if (this.performance.total === 0)
            return 0;
        return this.performance.correct / this.performance.total;
    }
    getDecisionHistory() {
        return [...this.decisionHistory];
    }
    getLastDecision() {
        return this.lastDecision;
    }
    updateConfig(newConfig) {
        this.config = { ...this.config, ...newConfig };
    }
    reset() {
        this.lastDecision = null;
        this.decisionHistory = [];
        this.performance = { correct: 0, total: 0 };
    }
}
exports.BaseAgent = BaseAgent;
//# sourceMappingURL=BaseAgent.js.map