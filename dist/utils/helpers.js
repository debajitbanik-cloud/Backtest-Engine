"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EventEmitter = void 0;
exports.generateId = generateId;
exports.formatPrice = formatPrice;
exports.formatPercentage = formatPercentage;
exports.formatCurrency = formatCurrency;
exports.calculatePnl = calculatePnl;
exports.calculatePnlPercentage = calculatePnlPercentage;
exports.calculateLeverage = calculateLeverage;
exports.calculateMargin = calculateMargin;
exports.calculateLiquidationPrice = calculateLiquidationPrice;
exports.timeframeToMs = timeframeToMs;
exports.msToTimeframe = msToTimeframe;
exports.sleep = sleep;
exports.clamp = clamp;
exports.roundTo = roundTo;
exports.calculateSharpeRatio = calculateSharpeRatio;
exports.calculateMaxDrawdown = calculateMaxDrawdown;
exports.calculateWinRate = calculateWinRate;
exports.calculateProfitFactor = calculateProfitFactor;
exports.calculateAvgHoldTime = calculateAvgHoldTime;
exports.debounce = debounce;
exports.throttle = throttle;
function generateId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
function formatPrice(price, decimals = 2) {
    return price.toFixed(decimals);
}
function formatPercentage(value, decimals = 2) {
    return `${(value * 100).toFixed(decimals)}%`;
}
function formatCurrency(value, currency = '$', decimals = 2) {
    return `${currency}${value.toFixed(decimals)}`;
}
function calculatePnl(entryPrice, exitPrice, size, side) {
    if (side === 'long') {
        return (exitPrice - entryPrice) * size;
    }
    else {
        return (entryPrice - exitPrice) * size;
    }
}
function calculatePnlPercentage(entryPrice, exitPrice, side) {
    if (side === 'long') {
        return (exitPrice - entryPrice) / entryPrice;
    }
    else {
        return (entryPrice - exitPrice) / entryPrice;
    }
}
function calculateLeverage(positionValue, margin) {
    return margin > 0 ? positionValue / margin : 1;
}
function calculateMargin(positionValue, leverage) {
    return leverage > 0 ? positionValue / leverage : positionValue;
}
function calculateLiquidationPrice(entryPrice, leverage, side, maintenanceMarginRate = 0.005) {
    if (side === 'long') {
        return entryPrice * (1 - 1 / leverage + maintenanceMarginRate);
    }
    else {
        return entryPrice * (1 + 1 / leverage - maintenanceMarginRate);
    }
}
function timeframeToMs(timeframe) {
    const unit = timeframe.slice(-1);
    const value = parseInt(timeframe.slice(0, -1));
    switch (unit) {
        case 'm': return value * 60 * 1000;
        case 'h': return value * 60 * 60 * 1000;
        case 'd': return value * 24 * 60 * 60 * 1000;
        case 'w': return value * 7 * 24 * 60 * 60 * 1000;
        default: return 60 * 1000;
    }
}
function msToTimeframe(ms) {
    if (ms < 60 * 1000)
        return '1m';
    if (ms < 60 * 60 * 1000)
        return `${Math.round(ms / (60 * 1000))}m`;
    if (ms < 24 * 60 * 60 * 1000)
        return `${Math.round(ms / (60 * 60 * 1000))}h`;
    if (ms < 7 * 24 * 60 * 60 * 1000)
        return `${Math.round(ms / (24 * 60 * 60 * 1000))}d`;
    return `${Math.round(ms / (7 * 24 * 60 * 60 * 1000))}w`;
}
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}
function roundTo(value, precision) {
    const factor = Math.pow(10, precision);
    return Math.round(value * factor) / factor;
}
function calculateSharpeRatio(returns, riskFreeRate = 0) {
    if (returns.length < 2)
        return 0;
    const excessReturns = returns.map(r => r - riskFreeRate / 252);
    const mean = excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length;
    const variance = excessReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (excessReturns.length - 1);
    const stdDev = Math.sqrt(variance);
    return stdDev > 0 ? mean / stdDev * Math.sqrt(252) : 0;
}
function calculateMaxDrawdown(equityCurve) {
    if (equityCurve.length < 2)
        return 0;
    let peak = equityCurve[0];
    let maxDD = 0;
    for (const value of equityCurve) {
        if (value > peak)
            peak = value;
        const dd = (peak - value) / peak;
        if (dd > maxDD)
            maxDD = dd;
    }
    return maxDD;
}
function calculateWinRate(trades) {
    if (trades.length === 0)
        return 0;
    const wins = trades.filter(t => t.pnl > 0).length;
    return wins / trades.length;
}
function calculateProfitFactor(trades) {
    const grossProfit = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
    const grossLoss = Math.abs(trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0));
    return grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;
}
function calculateAvgHoldTime(trades) {
    if (trades.length === 0)
        return 0;
    const totalHours = trades.reduce((sum, t) => sum + (t.exitTime - t.entryTime) / 3600000, 0);
    return totalHours / trades.length;
}
function debounce(fn, delay) {
    let timeoutId = null;
    return (...args) => {
        if (timeoutId)
            clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
}
function throttle(fn, limit) {
    let inThrottle = false;
    return (...args) => {
        if (!inThrottle) {
            fn(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}
class EventEmitter {
    listeners = new Map();
    on(event, listener) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(listener);
        return () => this.off(event, listener);
    }
    off(event, listener) {
        this.listeners.get(event)?.delete(listener);
    }
    emit(event, ...args) {
        this.listeners.get(event)?.forEach(listener => listener(...args));
    }
    once(event, listener) {
        const wrapper = (...args) => {
            listener(...args);
            this.off(event, wrapper);
        };
        return this.on(event, wrapper);
    }
}
exports.EventEmitter = EventEmitter;
//# sourceMappingURL=helpers.js.map