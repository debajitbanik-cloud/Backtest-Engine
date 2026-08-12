import { MarketData, Timeframe } from '../types';
import { DataLoader, DataLoaderOptions, DataSourceConfig } from './DataLoader';
/**
 * Free data loader using Binance public API.
 * No API key required for market data endpoints.
 */
export declare class BinanceDataLoader implements DataLoader {
    private lastRequestTime;
    private config;
    getConfig(): DataSourceConfig;
    fetchOHLCV(options: DataLoaderOptions): Promise<MarketData[]>;
    fetchLatest(symbol: string, timeframe: Timeframe): Promise<MarketData | null>;
    isSupported(symbol: string): Promise<boolean>;
    fetchAvailableSymbols(quoteAsset?: string): Promise<string[]>;
    private parseCandle;
    private normalizeSymbol;
    private normalizeTimeframe;
    private rateLimit;
    private sleep;
}
//# sourceMappingURL=BinanceDataLoader.d.ts.map