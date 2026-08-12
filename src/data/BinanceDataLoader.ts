import { MarketData, Timeframe } from '../types';
import { DataLoader, DataLoaderOptions, DataSourceConfig } from './DataLoader';

const BINANCE_CONFIG: DataSourceConfig = {
  name: 'binance',
  baseUrl: 'https://api.binance.com',
  rateLimitMs: 100, // ~10 requests/sec for public endpoints
  supportedTimeframes: ['1m', '5m', '15m', '1h', '4h', '1d'],
};

/**
 * Free data loader using Binance public API.
 * No API key required for market data endpoints.
 */
export class BinanceDataLoader implements DataLoader {
  private lastRequestTime: number = 0;
  private config: DataSourceConfig = BINANCE_CONFIG;

  getConfig(): DataSourceConfig {
    return this.config;
  }

  async fetchOHLCV(options: DataLoaderOptions): Promise<MarketData[]> {
    await this.rateLimit();

    const { symbol, timeframe, limit = 500, startTime, endTime } = options;
    const binanceSymbol = this.normalizeSymbol(symbol);
    const interval = this.normalizeTimeframe(timeframe);

    const params = new URLSearchParams({
      symbol: binanceSymbol,
      interval,
      limit: Math.min(limit, 1000).toString(),
    });

    if (startTime) params.append('startTime', startTime.toString());
    if (endTime) params.append('endTime', endTime.toString());

    const url = `${this.config.baseUrl}/api/v3/klines?${params.toString()}`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Binance API error: ${response.status} ${response.statusText}`);
      }

      const rawData: any[][] = await response.json() as any[][];
      return rawData.map(candle => this.parseCandle(symbol, timeframe, candle));
    } catch (error) {
      console.error(`Failed to fetch OHLCV for ${symbol}:`, error);
      throw error;
    }
  }

  async fetchLatest(symbol: string, timeframe: Timeframe): Promise<MarketData | null> {
    const data = await this.fetchOHLCV({ symbol, timeframe, limit: 1 });
    return data.length > 0 ? data[data.length - 1] : null;
  }

  async isSupported(symbol: string): Promise<boolean> {
    try {
      await this.rateLimit();
      const response = await fetch(`${this.config.baseUrl}/api/v3/exchangeInfo?symbol=${this.normalizeSymbol(symbol)}`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async fetchAvailableSymbols(quoteAsset: string = 'USDT'): Promise<string[]> {
    await this.rateLimit();
    const response = await fetch(`${this.config.baseUrl}/api/v3/exchangeInfo`);
    if (!response.ok) {
      throw new Error(`Failed to fetch exchange info: ${response.status}`);
    }

    const data = await response.json() as any;
    return data.symbols
      .filter((s: any) => s.status === 'TRADING' && s.quoteAsset === quoteAsset)
      .map((s: any) => s.symbol.replace(quoteAsset, '') + quoteAsset);
  }

  private parseCandle(symbol: string, timeframe: Timeframe, candle: any[]): MarketData {
    return {
      symbol,
      timeframe,
      timestamp: candle[0],
      open: parseFloat(candle[1]),
      high: parseFloat(candle[2]),
      low: parseFloat(candle[3]),
      close: parseFloat(candle[4]),
      volume: parseFloat(candle[5]),
    };
  }

  private normalizeSymbol(symbol: string): string {
    // Convert BTCUSDT -> BTCUSDT, BTC/USDT -> BTCUSDT
    return symbol.replace('/', '').toUpperCase();
  }

  private normalizeTimeframe(timeframe: Timeframe): string {
    return timeframe;
  }

  private async rateLimit(): Promise<void> {
    const now = Date.now();
    const elapsed = now - this.lastRequestTime;
    if (elapsed < this.config.rateLimitMs) {
      await this.sleep(this.config.rateLimitMs - elapsed);
    }
    this.lastRequestTime = Date.now();
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
