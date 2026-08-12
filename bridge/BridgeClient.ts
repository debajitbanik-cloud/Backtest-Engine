import { MarketData, Timeframe } from '../src/types';

export interface BridgeStatus {
  running: boolean;
  agents: Record<string, any>;
}

export interface BridgeSignal {
  type: string;
  timestamp: string;
  payload: any;
}

export interface BridgeDataResponse {
  symbol: string;
  timeframe: string;
  count: number;
  data: MarketData[];
}

/**
 * TypeScript client for Python bridge server.
 * Allows TypeScript engine to query Python agent system.
 */
export class BridgeClient {
  private baseUrl: string;

  constructor(host: string = '127.0.0.1', port: number = 8080) {
    this.baseUrl = `http://${host}:${port}`;
  }

  async health(): Promise<{ status: string; timestamp: string; running: boolean }> {
    const response = await fetch(`${this.baseUrl}/health`);
    if (!response.ok) throw new Error(`Bridge health check failed: ${response.status}`);
    return response.json();
  }

  async getStatus(): Promise<BridgeStatus> {
    const response = await fetch(`${this.baseUrl}/status`);
    if (!response.ok) throw new Error(`Failed to get status: ${response.status}`);
    return response.json();
  }

  async getSignals(limit: number = 50): Promise<{ signals: BridgeSignal[]; count: number }> {
    const response = await fetch(`${this.baseUrl}/signals?limit=${limit}`);
    if (!response.ok) throw new Error(`Failed to get signals: ${response.status}`);
    return response.json();
  }

  async getData(symbol: string, timeframe: Timeframe, limit?: number): Promise<BridgeDataResponse> {
    const query = limit ? `?limit=${limit}` : '';
    const response = await fetch(`${this.baseUrl}/data/${symbol}/${timeframe}${query}`);
    if (!response.ok) throw new Error(`Failed to get data: ${response.status}`);
    return response.json();
  }

  async sendCommand(command: string, params: Record<string, any>): Promise<any> {
    const response = await fetch(`${this.baseUrl}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, params }),
    });
    if (!response.ok) throw new Error(`Command failed: ${response.status}`);
    return response.json();
  }

  connectEvents(callback: (event: any) => void): EventSource {
    const eventSource = new EventSource(`${this.baseUrl}/events`);
    eventSource.onmessage = (event) => {
      try {
        callback(JSON.parse(event.data));
      } catch (e) {
        console.error('Failed to parse SSE event:', e);
      }
    };
    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
    };
    return eventSource;
  }
}
