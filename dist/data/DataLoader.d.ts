import { MarketData, Timeframe } from '../types';
export interface DataLoaderOptions {
    symbol: string;
    timeframe: Timeframe;
    limit?: number;
    startTime?: number;
    endTime?: number;
}
export interface DataLoader {
    fetchOHLCV(options: DataLoaderOptions): Promise<MarketData[]>;
    fetchLatest(symbol: string, timeframe: Timeframe): Promise<MarketData | null>;
    isSupported(symbol: string): Promise<boolean>;
}
export interface DataSourceConfig {
    name: string;
    baseUrl: string;
    rateLimitMs: number;
    supportedTimeframes: Timeframe[];
}
//# sourceMappingURL=DataLoader.d.ts.map