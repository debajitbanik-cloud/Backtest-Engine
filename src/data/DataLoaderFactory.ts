import { DataLoader } from './DataLoader';
import { BinanceDataLoader } from './BinanceDataLoader';
import { FileDataLoader } from './FileDataLoader';

export type DataLoaderType = 'binance' | 'file' | 'bridge';

export class DataLoaderFactory {
  static create(type: DataLoaderType, options?: { dataDir?: string }): DataLoader {
    switch (type) {
      case 'binance':
        return new BinanceDataLoader();
      case 'file':
        return new FileDataLoader(options?.dataDir);
      default:
        throw new Error(`Unknown data loader type: ${type}`);
    }
  }
}
