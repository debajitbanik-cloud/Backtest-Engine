import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, TradeSignal } from '../types';

const DEFAULT_RISK_PER_TRADE = 0.02;
const MAX_PORTFOLIO_RISK = 0.1;
const KELLY_FRACTION = 0.25;
const MIN_POSITION_SIZE = 10;
const MAX_LEVERAGE = 20;

export class PositionSizingAgent extends BaseAgent {
  constructor(config: AgentConfig) {
    const params = {
      ...config.parameters,
      riskPerTrade: config.parameters.riskPerTrade ?? DEFAULT_RISK_PER_TRADE,
      maxPortfolioRisk: config.parameters.maxPortfolioRisk ?? MAX_PORTFOLIO_RISK,
      kellyFraction: config.parameters.kellyFraction ?? KELLY_FRACTION,
      minPositionSize: config.parameters.minPositionSize ?? MIN_POSITION_SIZE,
      maxLeverage: config.parameters.maxLeverage ?? MAX_LEVERAGE,
    };
    super({
      ...config,
      id: 'position_sizing_agent',
      name: 'Position Sizing Agent',
      parameters: params,
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    const openPositions = positions.filter(p => p.status === 'open');
    const currentRisk = this.calculateCurrentRisk(openPositions, riskMetrics);
    const availableRisk = this.config.parameters.maxPortfolioRisk - currentRisk;
    
    if (availableRisk <= 0) {
      return this.createDecision(
        'hold',
        0.9,
        `Portfolio risk at maximum (${(currentRisk * 100).toFixed(1)}%). No new positions allowed.`,
        { currentRisk, maxRisk: this.config.parameters.maxPortfolioRisk, availableRisk: 0 }
      );
    }

    const sizingParams = this.calculateOptimalSizing(marketData, riskMetrics, availableRisk);
    
    return this.createDecision(
      'adjust',
      0.85,
      `Position sizing calculated: Risk per trade ${(sizingParams.riskPerTrade * 100).toFixed(2)}%, Max leverage ${sizingParams.maxLeverage}x, Position size $${sizingParams.positionSize.toFixed(2)}`,
      sizingParams
    );
  }

  calculateSignalSizing(signal: TradeSignal, marketData: MarketData[], riskMetrics: RiskMetrics, openPositions: Position[] = []): TradeSignal {
    const currentRisk = this.calculateCurrentRisk(openPositions, riskMetrics);
    const availableRisk = this.config.parameters.maxPortfolioRisk - currentRisk;
    
    if (availableRisk <= 0) {
      return { ...signal, size: 0 };
    }

    const stopDistance = Math.abs(signal.entryPrice - signal.stopLoss) / signal.entryPrice;
    const riskAmount = riskMetrics.marginAvailable * Math.min(availableRisk, this.config.parameters.riskPerTrade);
    const positionValue = riskAmount / stopDistance;
    
    const maxPositionValue = riskMetrics.marginAvailable * this.config.parameters.maxPortfolioRisk;
    const finalPositionValue = Math.min(positionValue, maxPositionValue);
    
    const leverage = Math.min(
      this.config.parameters.maxLeverage,
      Math.max(1, finalPositionValue / riskAmount)
    );
    
    const size = finalPositionValue / signal.entryPrice;
    
    return {
      ...signal,
      size: Math.max(size, this.config.parameters.minPositionSize / signal.entryPrice),
      leverage,
    };
  }

  private calculateCurrentRisk(positions: Position[], riskMetrics: RiskMetrics): number {
    if (riskMetrics.marginAvailable + riskMetrics.marginUsed === 0) return 0;
    
    let totalRisk = 0;
    for (const pos of positions) {
      if (pos.stopLoss) {
        const riskPerUnit = Math.abs(pos.entryPrice - pos.stopLoss) / pos.entryPrice;
        const positionRisk = (pos.size * pos.entryPrice * riskPerUnit) / (riskMetrics.marginAvailable + riskMetrics.marginUsed);
        totalRisk += positionRisk;
      }
    }
    
    return totalRisk;
  }

  private calculateOptimalSizing(
    marketData: MarketData[],
    riskMetrics: RiskMetrics,
    availableRisk: number
  ): {
    riskPerTrade: number;
    maxLeverage: number;
    positionSize: number;
    kellySize: number;
    volatilityAdjustedSize: number;
  } {
    const volatility = this.calculateVolatility(marketData);
    const winRate = riskMetrics.winRate || 0.5;
    const avgWin = riskMetrics.profitFactor > 0 ? riskMetrics.profitFactor : 1.5;
    const avgLoss = 1;
    
    const kellyPct = (winRate * avgWin - (1 - winRate) * avgLoss) / avgWin;
    const kellySize = Math.max(0, kellyPct * this.config.parameters.kellyFraction);
    
    const riskPerTrade = Math.min(
      this.config.parameters.riskPerTrade,
      availableRisk,
      kellySize
    );
    
    const maxLeverage = Math.min(
      this.config.parameters.maxLeverage,
      1 / (riskPerTrade * 2)
    );
    
    const accountEquity = riskMetrics.marginAvailable + riskMetrics.marginUsed;
    const positionSize = accountEquity * riskPerTrade / (volatility * 2);
    
    const volatilityAdjustedSize = positionSize / (1 + volatility * 10);
    
    return {
      riskPerTrade,
      maxLeverage: Math.max(1, Math.floor(maxLeverage)),
      positionSize: Math.max(this.config.parameters.minPositionSize, volatilityAdjustedSize),
      kellySize: kellySize * accountEquity,
      volatilityAdjustedSize,
    };
  }

  private calculateVolatility(marketData: MarketData[]): number {
    if (marketData.length < 20) return 0.02;
    
    const closes = marketData.map(d => d.close);
    const returns: number[] = [];
    
    for (let i = 1; i < closes.length; i++) {
      returns.push((closes[i] - closes[i - 1]) / closes[i - 1]);
    }
    
    const recentReturns = returns.slice(-20);
    const mean = recentReturns.reduce((a, b) => a + b, 0) / recentReturns.length;
    const variance = recentReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / recentReturns.length;
    
    return Math.sqrt(variance);
  }

  adjustForCorrelation(positions: Position[], newSignal: TradeSignal): TradeSignal {
    const correlatedPositions = positions.filter(p => 
      p.symbol === newSignal.symbol || this.areCorrelated(p.symbol, newSignal.symbol)
    );
    
    if (correlatedPositions.length === 0) return newSignal;
    
    const totalCorrelatedSize = correlatedPositions.reduce((sum, p) => sum + p.size * p.currentPrice, 0);
    const accountEquity = totalCorrelatedSize * 10; // Rough estimate
    
    const reductionFactor = Math.max(0.3, 1 - (totalCorrelatedSize / accountEquity));
    
    return {
      ...newSignal,
      size: newSignal.size * reductionFactor,
    };
  }

  private areCorrelated(symbol1: string, symbol2: string): boolean {
    const base1 = symbol1.replace(/USDT?|BUSD|BTC|ETH/, '');
    const base2 = symbol2.replace(/USDT?|BUSD|BTC|ETH/, '');
    return base1 === base2;
  }
}