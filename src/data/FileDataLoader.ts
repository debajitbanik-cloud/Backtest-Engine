import * as fs from 'fs';
import * as path from 'path';
import { MarketData, Timeframe } from '../types';
import { DataLoader, DataLoaderOptions } from './DataLoader';

/**
 * Loads OHLCV data from local CSV or JSON files.
 * Expected CSV format: timestamp,open,high,low,close,volume
 */
export class FileDataLoader implements DataLoader {
  private dataDir: string;

  constructor(dataDir: string = './data/shared') {
    this.dataDir = dataDir;
  }

   async fetchOHLCV(options: DataLoaderOptions): Promise<MarketData[]> {
    const { symbol, timeframe, limit, startTime, endTime } = options;
    const filePath = this.getFilePath(symbol, timeframe);

    if (!fs.existsSync(filePath)) {
      throw new Error(`Data file not found: ${filePath}`);
    }

    const data = await this.loadFile(filePath, symbol, timeframe);

    let filtered = data;
    if (startTime) {
      filtered = filtered.filter(d => d.timestamp >= startTime);
    }
    if (endTime) {
      filtered = filtered.filter(d => d.timestamp <= endTime);
    }
    if (limit) {
      filtered = filtered.slice(-limit);
    }

    return filtered;
  }

  async fetchLatest(symbol: string, timeframe: Timeframe): Promise<MarketData | null> {
    const data = await this.fetchOHLCV({ symbol, timeframe, limit: 1 });
    return data.length > 0 ? data[data.length - 1] : null;
  }

  async isSupported(symbol: string): Promise<boolean> {
    for (const tf of ['1m', '5m', '15m', '1h'] as Timeframe[]) {
      if (fs.existsSync(this.getFilePath(symbol, tf))) return true;
    }
    return false;
  }

  async saveOHLCV(data: MarketData[]): Promise<void> {
    if (data.length === 0) return;

    const symbol = data[0].symbol;
    const timeframe = data[0].timeframe;
    const filePath = this.getFilePath(symbol, timeframe);

    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }

    // Save as JSON for simplicity
    fs.writeFileSync(filePath.replace('.csv', '.json'), JSON.stringify(data, null, 2));
  }

  private getFilePath(symbol: string, timeframe: Timeframe): string {
    const normalizedSymbol = symbol.replace('/', '_').toUpperCase();
    const basePath = path.join(this.dataDir, `${normalizedSymbol}_${timeframe}`);
    
    // Try .json first, then .csv
    const jsonPath = `${basePath}.json`;
    if (fs.existsSync(jsonPath)) return jsonPath;
    
    return `${basePath}.csv`;
  }

  private async loadFile(filePath: string, symbol: string, timeframe: Timeframe): Promise<MarketData[]> {
    if (filePath.endsWith('.json')) {
      const content = fs.readFileSync(filePath, 'utf-8');
      const parsed = JSON.parse(content);
      // Convert ISO timestamp strings to Unix ms numbers
      return parsed.map((d: any) => ({
        ...d,
        timestamp: d.timestamp ? (typeof d.timestamp === 'number' 
          ? d.timestamp 
          : Date.parse(d.timestamp)) : Date.now()
      }));
    }

    // CSV
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.trim().split('\n');
    const headers = lines[0].split(',').map((h: string) => h.trim().toLowerCase());

    return lines.slice(1).map((line: string) => {
      const values = line.split(',');
      const row: Record<string, string> = {};
      headers.forEach((h: string, i: number) => (row[h] = values[i]));

      return {
        symbol,
        timeframe,
        timestamp: parseInt(row.timestamp || row.time || row.date),
        open: parseFloat(row.open),
        high: parseFloat(row.high),
        low: parseFloat(row.low),
        close: parseFloat(row.close),
        volume: parseFloat(row.volume || '0'),
      };
    });
  }
}
