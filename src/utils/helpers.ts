export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function formatPrice(price: number, decimals: number = 2): string {
  return price.toFixed(decimals);
}

export function formatPercentage(value: number, decimals: number = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatCurrency(value: number, currency: string = '$', decimals: number = 2): string {
  return `${currency}${value.toFixed(decimals)}`;
}

export function calculatePnl(entryPrice: number, exitPrice: number, size: number, side: 'long' | 'short'): number {
  if (side === 'long') {
    return (exitPrice - entryPrice) * size;
  } else {
    return (entryPrice - exitPrice) * size;
  }
}

export function calculatePnlPercentage(entryPrice: number, exitPrice: number, side: 'long' | 'short'): number {
  if (side === 'long') {
    return (exitPrice - entryPrice) / entryPrice;
  } else {
    return (entryPrice - exitPrice) / entryPrice;
  }
}

export function calculateLeverage(positionValue: number, margin: number): number {
  return margin > 0 ? positionValue / margin : 1;
}

export function calculateMargin(positionValue: number, leverage: number): number {
  return leverage > 0 ? positionValue / leverage : positionValue;
}

export function calculateLiquidationPrice(
  entryPrice: number,
  leverage: number,
  side: 'long' | 'short',
  maintenanceMarginRate: number = 0.005
): number {
  if (side === 'long') {
    return entryPrice * (1 - 1/leverage + maintenanceMarginRate);
  } else {
    return entryPrice * (1 + 1/leverage - maintenanceMarginRate);
  }
}

export function timeframeToMs(timeframe: string): number {
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

export function msToTimeframe(ms: number): string {
  if (ms < 60 * 1000) return '1m';
  if (ms < 60 * 60 * 1000) return `${Math.round(ms / (60 * 1000))}m`;
  if (ms < 24 * 60 * 60 * 1000) return `${Math.round(ms / (60 * 60 * 1000))}h`;
  if (ms < 7 * 24 * 60 * 60 * 1000) return `${Math.round(ms / (24 * 60 * 60 * 1000))}d`;
  return `${Math.round(ms / (7 * 24 * 60 * 60 * 1000))}w`;
}

export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function roundTo(value: number, precision: number): number {
  const factor = Math.pow(10, precision);
  return Math.round(value * factor) / factor;
}

export function calculateSharpeRatio(returns: number[], riskFreeRate: number = 0): number {
  if (returns.length < 2) return 0;
  
  const excessReturns = returns.map(r => r - riskFreeRate / 252);
  const mean = excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length;
  const variance = excessReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (excessReturns.length - 1);
  const stdDev = Math.sqrt(variance);
  
  return stdDev > 0 ? mean / stdDev * Math.sqrt(252) : 0;
}

export function calculateMaxDrawdown(equityCurve: number[]): number {
  if (equityCurve.length < 2) return 0;
  
  let peak = equityCurve[0];
  let maxDD = 0;
  
  for (const value of equityCurve) {
    if (value > peak) peak = value;
    const dd = (peak - value) / peak;
    if (dd > maxDD) maxDD = dd;
  }
  
  return maxDD;
}

export function calculateWinRate(trades: Array<{ pnl: number }>): number {
  if (trades.length === 0) return 0;
  const wins = trades.filter(t => t.pnl > 0).length;
  return wins / trades.length;
}

export function calculateProfitFactor(trades: Array<{ pnl: number }>): number {
  const grossProfit = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0));
  return grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;
}

export function calculateAvgHoldTime(trades: Array<{ entryTime: number; exitTime: number }>): number {
  if (trades.length === 0) return 0;
  const totalHours = trades.reduce((sum, t) => sum + (t.exitTime - t.entryTime) / 3600000, 0);
  return totalHours / trades.length;
}

export function debounce<T extends (...args: any[]) => any>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

export function throttle<T extends (...args: any[]) => any>(fn: T, limit: number): (...args: Parameters<T>) => void {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

export class EventEmitter<T extends Record<string, (...args: any[]) => any>> {
  private listeners: Map<string, Set<Function>> = new Map();
  
  on(event: string, listener: Function): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener);
    return () => this.off(event, listener);
  }
  
  off(event: string, listener: Function): void {
    this.listeners.get(event)?.delete(listener);
  }
  
  emit(event: string, ...args: any[]): void {
    this.listeners.get(event)?.forEach(listener => listener(...args));
  }
  
  once(event: string, listener: Function): () => void {
    const wrapper = (...args: any[]) => {
      listener(...args);
      this.off(event, wrapper);
    };
    return this.on(event, wrapper);
  }
}