import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, ConfluenceSignal, MarketData, Position, RiskMetrics, Timeframe } from '../types';

const TIMEFRAMES: Timeframe[] = ['15m', '1h', '4h', '1d'];
const CONFLUENCE_THRESHOLD = 0.7;
const WEIGHTS = {
  '15m': 0.15,
  '1h': 0.25,
  '4h': 0.35,
  '1d': 0.25,
};

export class MultiTimeframeConfluenceAgent extends BaseAgent {
  constructor(config: AgentConfig) {
    const params = {
      ...config.parameters,
      timeframes: config.parameters.timeframes ?? TIMEFRAMES,
      confluenceThreshold: config.parameters.confluenceThreshold ?? CONFLUENCE_THRESHOLD,
      weights: config.parameters.weights ?? WEIGHTS,
    };
    super({
      ...config,
      id: 'multitimeframe_confluence_agent',
      name: 'Multi-Timeframe Confluence Agent',
      parameters: params,
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    const timeframeData = this.groupByTimeframe(marketData);
    const signals: ConfluenceSignal[] = [];
    
    for (const tf of this.config.parameters.timeframes) {
      const tfData = timeframeData[tf as Timeframe];
      if (tfData && tfData.length >= 50) {
        const signal = this.analyzeTimeframe(tfData, tf);
        signals.push(signal);
      }
    }
    
    if (signals.length < 2) {
      return this.createDecision('hold', 0.3, 'Insufficient timeframe data for confluence analysis');
    }
    
    const confluence = this.calculateConfluence(signals);
    
    return this.createDecision(
      confluence.action,
      confluence.confidence,
      confluence.reasoning,
      {
        signals,
        confluenceScore: confluence.score,
        alignedTimeframes: confluence.alignedCount,
        totalTimeframes: signals.length,
      }
    );
  }

  private groupByTimeframe(data: MarketData[]): Record<Timeframe, MarketData[]> {
    const grouped: Record<Timeframe, MarketData[]> = {
      '1m': [], '5m': [], '15m': [], '1h': [], '4h': [], '1d': [], '1w': []
    } as Record<Timeframe, MarketData[]>;
    
    for (const d of data) {
      const tf = d.timeframe;
      if (grouped[tf]) {
        grouped[tf].push(d);
      }
    }
    
    return grouped;
  }

  private analyzeTimeframe(data: MarketData[], timeframe: Timeframe): ConfluenceSignal {
    const closes = data.map(d => d.close);
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const volumes = data.map(d => d.volume);
    
    const indicators = {
      rsi: this.calculateRSI(closes, 14),
      macd: this.calculateMACD(closes),
      ema20: this.ema(closes, 20),
      ema50: this.ema(closes, 50),
      ema200: this.ema(closes, 200),
      bbUpper: this.bollingerBands(closes, 20, 2).upper,
      bbLower: this.bollingerBands(closes, 20, 2).lower,
      bbMiddle: this.bollingerBands(closes, 20, 2).middle,
      atr: this.calculateATR(highs, lows, closes, 14),
      volumeSMA: this.sma(volumes, 20),
      currentVolume: volumes[volumes.length - 1],
    };
    
    let bullishScore = 0;
    let bearishScore = 0;
    
    const currentPrice = closes[closes.length - 1];
    
    if (indicators.rsi < 30) bullishScore += 1;
    else if (indicators.rsi > 70) bearishScore += 1;
    else if (indicators.rsi > 50) bullishScore += 0.5;
    else bearishScore += 0.5;
    
    if (indicators.macd.histogram > 0) bullishScore += 1;
    else bearishScore += 1;
    
    if (currentPrice > indicators.ema20) bullishScore += 1;
    else bearishScore += 1;
    
    if (currentPrice > indicators.ema50) bullishScore += 1;
    else bearishScore += 1;
    
    if (currentPrice > indicators.ema200) bullishScore += 1.5;
    else bearishScore += 1.5;
    
    if (currentPrice < indicators.bbLower) bullishScore += 1;
    else if (currentPrice > indicators.bbUpper) bearishScore += 1;
    
    if (indicators.currentVolume > indicators.volumeSMA * 1.5) {
      if (currentPrice > data[data.length - 1].open) bullishScore += 0.5;
      else bearishScore += 0.5;
    }
    
    const total = bullishScore + bearishScore;
    const strength = Math.abs(bullishScore - bearishScore) / total;
    const bias = bullishScore > bearishScore ? 'bullish' : bearishScore > bullishScore ? 'bearish' : 'neutral';
    
    return {
      timeframe,
      bias,
      strength,
      indicators: {
        rsi: indicators.rsi,
        macd: indicators.macd.histogram,
        ema20: indicators.ema20,
        ema50: indicators.ema50,
        ema200: indicators.ema200,
        bbPosition: (currentPrice - indicators.bbLower) / (indicators.bbUpper - indicators.bbLower),
        volumeRatio: indicators.currentVolume / indicators.volumeSMA,
      },
    };
  }

  private calculateConfluence(signals: ConfluenceSignal[]): { action: AgentDecision['action']; confidence: number; reasoning: string; score: number; alignedCount: number } {
    let weightedBullish = 0;
    let weightedBearish = 0;
    let totalWeight = 0;
    
    for (const signal of signals) {
      const weight = this.config.parameters.weights[signal.timeframe] || 0;
      totalWeight += weight;
      
      if (signal.bias === 'bullish') {
        weightedBullish += weight * signal.strength;
      } else if (signal.bias === 'bearish') {
        weightedBearish += weight * signal.strength;
      }
    }
    
    const bullishPct = weightedBullish / totalWeight;
    const bearishPct = weightedBearish / totalWeight;
    const score = Math.max(bullishPct, bearishPct);
    
    const alignedCount = signals.filter(s => 
      (bullishPct > bearishPct && s.bias === 'bullish') ||
      (bearishPct > bullishPct && s.bias === 'bearish')
    ).length;
    
    const isConfluence = score >= this.config.parameters.confluenceThreshold;
    
    let action: AgentDecision['action'] = 'hold';
    let confidence = score;
    let reasoning = '';
    
    if (isConfluence) {
      if (bullishPct > bearishPct) {
        action = 'buy';
        reasoning = `Strong BULLISH confluence (${(score * 100).toFixed(0)}%) across ${alignedCount}/${signals.length} timeframes`;
      } else {
        action = 'sell';
        reasoning = `Strong BEARISH confluence (${(score * 100).toFixed(0)}%) across ${alignedCount}/${signals.length} timeframes`;
      }
    } else {
      reasoning = `Weak confluence (${(score * 100).toFixed(0)}%) - timeframes not aligned. Bullish: ${(bullishPct * 100).toFixed(0)}%, Bearish: ${(bearishPct * 100).toFixed(0)}%`;
      confidence = 0.4;
    }
    
    return { action, confidence, reasoning, score, alignedCount };
  }

  private calculateRSI(closes: number[], period: number): number {
    if (closes.length < period + 1) return 50;
    
    let gains = 0;
    let losses = 0;
    
    for (let i = closes.length - period; i < closes.length; i++) {
      const change = closes[i] - closes[i - 1];
      if (change > 0) gains += change;
      else losses -= change;
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    
    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  private calculateMACD(closes: number[]): { macd: number; signal: number; histogram: number } {
    const ema12 = this.ema(closes, 12);
    const ema26 = this.ema(closes, 26);
    const macd = ema12 - ema26;
    const signal = this.ema([macd], 9);
    return { macd, signal, histogram: macd - signal };
  }

  private ema(values: number[], period: number): number {
    if (values.length === 0) return 0;
    if (values.length < period) return values[values.length - 1];
    
    const k = 2 / (period + 1);
    let ema = values[values.length - period];
    
    for (let i = values.length - period + 1; i < values.length; i++) {
      ema = values[i] * k + ema * (1 - k);
    }
    
    return ema;
  }

  private bollingerBands(closes: number[], period: number, stdDev: number): { upper: number; middle: number; lower: number } {
    const slice = closes.slice(-period);
    const middle = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((sum, v) => sum + Math.pow(v - middle, 2), 0) / period;
    const std = Math.sqrt(variance);
    
    return {
      upper: middle + stdDev * std,
      middle,
      lower: middle - stdDev * std,
    };
  }

  private calculateATR(highs: number[], lows: number[], closes: number[], period: number): number {
    if (highs.length < period + 1) return 0;
    
    const trueRanges: number[] = [];
    for (let i = 1; i < highs.length; i++) {
      const tr = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      trueRanges.push(tr);
    }
    
    const slice = trueRanges.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / period;
  }

  private sma(values: number[], period: number): number {
    if (values.length < period) return values[values.length - 1] || 0;
    const slice = values.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / period;
  }
}