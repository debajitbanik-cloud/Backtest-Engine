import { MarketData, Timeframe } from '../types';
import { DataLoader, DataLoaderOptions } from './DataLoader';
/**
 * Loads OHLCV data from local CSV or JSON files.
 * Expected CSV format: timestamp,open,high,low,close,volume
 */
export declare class FileDataLoader implements DataLoader {
    private dataDir;
    constructor(dataDir?: string);
    fetchOHLCV(options: DataLoaderOptions): Promise<MarketData[]>;
    fetchLatest(symbol: string, timeframe: Timeframe): Promise<MarketData | null>;
    isSupported(symbol: string): Promise<boolean>;
    saveOHLCV(data: MarketData[]): Promise<void>;
    private getFilePath;
    private loadFile;
}
//# sourceMappingURL=FileDataLoader.d.ts.map