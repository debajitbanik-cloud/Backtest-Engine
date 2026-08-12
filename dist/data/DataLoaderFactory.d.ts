import { DataLoader } from './DataLoader';
export type DataLoaderType = 'binance' | 'file' | 'bridge';
export declare class DataLoaderFactory {
    static create(type: DataLoaderType, options?: {
        dataDir?: string;
    }): DataLoader;
}
//# sourceMappingURL=DataLoaderFactory.d.ts.map