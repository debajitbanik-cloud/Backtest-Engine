export declare function generateId(): string;
export declare function formatPrice(price: number, decimals?: number): string;
export declare function formatPercentage(value: number, decimals?: number): string;
export declare function formatCurrency(value: number, currency?: string, decimals?: number): string;
export declare function calculatePnl(entryPrice: number, exitPrice: number, size: number, side: 'long' | 'short'): number;
export declare function calculatePnlPercentage(entryPrice: number, exitPrice: number, side: 'long' | 'short'): number;
export declare function calculateLeverage(positionValue: number, margin: number): number;
export declare function calculateMargin(positionValue: number, leverage: number): number;
export declare function calculateLiquidationPrice(entryPrice: number, leverage: number, side: 'long' | 'short', maintenanceMarginRate?: number): number;
export declare function timeframeToMs(timeframe: string): number;
export declare function msToTimeframe(ms: number): string;
export declare function sleep(ms: number): Promise<void>;
export declare function clamp(value: number, min: number, max: number): number;
export declare function roundTo(value: number, precision: number): number;
export declare function calculateSharpeRatio(returns: number[], riskFreeRate?: number): number;
export declare function calculateMaxDrawdown(equityCurve: number[]): number;
export declare function calculateWinRate(trades: Array<{
    pnl: number;
}>): number;
export declare function calculateProfitFactor(trades: Array<{
    pnl: number;
}>): number;
export declare function calculateAvgHoldTime(trades: Array<{
    entryTime: number;
    exitTime: number;
}>): number;
export declare function debounce<T extends (...args: any[]) => any>(fn: T, delay: number): (...args: Parameters<T>) => void;
export declare function throttle<T extends (...args: any[]) => any>(fn: T, limit: number): (...args: Parameters<T>) => void;
export declare class EventEmitter<T extends Record<string, (...args: any[]) => any>> {
    private listeners;
    on(event: string, listener: Function): () => void;
    off(event: string, listener: Function): void;
    emit(event: string, ...args: any[]): void;
    once(event: string, listener: Function): () => void;
}
//# sourceMappingURL=helpers.d.ts.map