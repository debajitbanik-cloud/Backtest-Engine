import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, StyleConfig, TradingMode, TradeSignal } from '../types';

const SCALPING_MAX_HOLD = 15 * 60 * 1000;
const SWING_TARGET_PROFIT = 0.01;
const MARGIN_THRESHOLD_FOR_SCALPING = 0.5;

const DEFAULT_STYLE_CONFIG: StyleConfig = {
  scalping: {
    maxHoldTime: 15 * 60 * 1000,
    targetProfit: 0.001,
    stopLoss: 0.0005,
    maxPositions: 5,
    minConfidence: 0.7,
  },
  swing: {
    minHoldTime: 60 * 60 * 1000,
    targetProfit: 0.01,
    stopLoss: 0.005,
    maxPositions: 3,
    minConfidence: 0.6,
  },
};

export class StyleManagingAgent extends BaseAgent {
  private currentMode: TradingMode = 'swing';
  private modeStartTime: number = Date.now();
  private scalpingOpportunities: number = 0;

  constructor(config: AgentConfig) {
    const params = {
      ...config.parameters,
      styleConfig: config.parameters.styleConfig ?? DEFAULT_STYLE_CONFIG,
      scalpingMaxHold: config.parameters.scalpingMaxHold ?? SCALPING_MAX_HOLD,
      swingTargetProfit: config.parameters.swingTargetProfit ?? SWING_TARGET_PROFIT,
      marginThresholdForScalping: config.parameters.marginThresholdForScalping ?? MARGIN_THRESHOLD_FOR_SCALPING,
    };
    super({
      ...config,
      id: 'style_managing_agent',
      name: 'Style Managing Agent',
      parameters: params,
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    const marginRatio = riskMetrics.marginUsed / (riskMetrics.marginUsed + riskMetrics.marginAvailable);
    const openPositions = positions.filter(p => p.status === 'open');
    const scalpingPositions = openPositions.filter(p => p.mode === 'scalping');
    const swingPositions = openPositions.filter(p => p.mode === 'swing');
    
    const shouldScalp = this.shouldSwitchToScalping(marginRatio, riskMetrics, marketData);
    const shouldSwing = this.shouldSwitchToSwing(marginRatio, openPositions);
    
    let newMode = this.currentMode;
    let action: AgentDecision['action'] = 'hold';
    let reasoning = '';
    let confidence = 0.5;
    
    if (shouldScalp && this.currentMode !== 'scalping') {
      newMode = 'scalping';
      action = 'adjust';
      reasoning = `Switching to SCALPING mode: Margin ratio ${(marginRatio * 100).toFixed(1)}% allows frequent trades. Scalp opportunities detected: ${this.scalpingOpportunities}`;
      confidence = 0.85;
      this.modeStartTime = Date.now();
    } else if (shouldSwing && this.currentMode !== 'swing') {
      newMode = 'swing';
      action = 'adjust';
      reasoning = `Switching to SWING mode: Margin ratio ${(marginRatio * 100).toFixed(1)}% or insufficient scalp opportunities. Targeting 1%+ moves.`;
      confidence = 0.85;
      this.modeStartTime = Date.now();
    } else {
      reasoning = this.getModeStatusReasoning(marginRatio, scalpingPositions.length, swingPositions.length);
      confidence = 0.6;
    }
    
    this.currentMode = newMode;
    
    this.checkScalpingExits(positions);
    this.checkSwingExits(positions, marketData);
    
    return this.createDecision(action, confidence, reasoning, {
      currentMode: this.currentMode,
      modeDuration: Date.now() - this.modeStartTime,
      scalpingPositions: scalpingPositions.length,
      swingPositions: swingPositions.length,
      marginRatio,
      scalpOpportunities: this.scalpingOpportunities,
      config: this.config.parameters.styleConfig,
    });
  }

  private shouldSwitchToScalping(
    marginRatio: number,
    riskMetrics: RiskMetrics,
    marketData: MarketData[]
  ): boolean {
    if (marginRatio > this.config.parameters.marginThresholdForScalping) return false;
    
    this.scalpingOpportunities = this.detectScalpOpportunities(marketData);
    
    if (this.scalpingOpportunities >= 2) return true;
    
    if (riskMetrics.currentDrawdown < 0.02 && riskMetrics.winRate > 0.55) {
      return true;
    }
    
    return false;
  }

  private shouldSwitchToSwing(marginRatio: number, openPositions: Position[]): boolean {
    if (marginRatio > 0.7) return true;
    
    if (this.scalpingOpportunities < 1) return true;
    
    const scalpingPositions = openPositions.filter(p => p.mode === 'scalping');
    if (scalpingPositions.length >= this.config.parameters.styleConfig.scalping.maxPositions) {
      return true;
    }
    
    return false;
  }

  private detectScalpOpportunities(marketData: MarketData[]): number {
    if (marketData.length < 20) return 0;
    
    const recentData = marketData.slice(-20);
    let opportunities = 0;
    
    for (let i = 1; i < recentData.length; i++) {
      const prev = recentData[i - 1];
      const curr = recentData[i];
      
      const bodySize = Math.abs(curr.close - curr.open) / curr.open;
      const range = (curr.high - curr.low) / curr.open;
      const volumeSpike = curr.volume > prev.volume * 1.5;
      
      if (bodySize > 0.0005 && bodySize < 0.003 && range < 0.01 && volumeSpike) {
        opportunities++;
      }
    }
    
    return opportunities;
  }

  private checkScalpingExits(positions: Position[]): void {
    const now = Date.now();
    for (const pos of positions) {
      if (pos.mode === 'scalping' && pos.status === 'open') {
        const holdTime = now - pos.entryTime;
        if (holdTime > this.config.parameters.scalpingMaxHold) {
          // Would trigger exit in real implementation
        }
      }
    }
  }

  private checkSwingExits(positions: Position[], marketData: MarketData[]): void {
    if (marketData.length === 0) return;
    
    const currentPrice = marketData[marketData.length - 1].close;
    
    for (const pos of positions) {
      if (pos.mode === 'swing' && pos.status === 'open') {
        const pnlPct = pos.side === 'long' 
          ? (currentPrice - pos.entryPrice) / pos.entryPrice
          : (pos.entryPrice - currentPrice) / pos.entryPrice;
        
        if (pnlPct >= this.config.parameters.swingTargetProfit) {
          // Would trigger take profit
        }
      }
    }
  }

  private getModeStatusReasoning(
    marginRatio: number,
    scalpingCount: number,
    swingCount: number
  ): string {
    const modeConfig = this.config.parameters.styleConfig[this.currentMode];
    const holdTime = Date.now() - this.modeStartTime;
    
    return `Current mode: ${this.currentMode.toUpperCase()} (${(holdTime / 60000).toFixed(1)}min). ` +
           `Margin: ${(marginRatio * 100).toFixed(1)}%. ` +
           `Positions - Scalping: ${scalpingCount}/${modeConfig.maxPositions}, Swing: ${swingCount}/${this.config.parameters.styleConfig.swing.maxPositions}. ` +
           `Scalp opportunities: ${this.scalpingOpportunities}`;
  }

  getCurrentMode(): TradingMode {
    return this.currentMode;
  }

  getModeConfig(mode: TradingMode) {
    return this.config.parameters.styleConfig[mode];
  }

  createScalpSignal(symbol: string, entryPrice: number, side: 'long' | 'short'): TradeSignal {
    const config = this.config.parameters.styleConfig.scalping;
    return {
      symbol,
      side,
      entryPrice,
      stopLoss: side === 'long' 
        ? entryPrice * (1 - config.stopLoss)
        : entryPrice * (1 + config.stopLoss),
      takeProfit: side === 'long'
        ? entryPrice * (1 + config.targetProfit)
        : entryPrice * (1 - config.targetProfit),
      size: 0, // Will be set by PositionSizingAgent
      leverage: 10, // Higher leverage for scalping
      confidence: config.minConfidence,
      mode: 'scalping',
      timeframe: '15m',
      reason: 'Scalping signal from StyleManagingAgent',
    };
  }

  createSwingSignal(symbol: string, entryPrice: number, side: 'long' | 'short'): TradeSignal {
    const config = this.config.parameters.styleConfig.swing;
    return {
      symbol,
      side,
      entryPrice,
      stopLoss: side === 'long'
        ? entryPrice * (1 - config.stopLoss)
        : entryPrice * (1 + config.stopLoss),
      takeProfit: side === 'long'
        ? entryPrice * (1 + config.targetProfit)
        : entryPrice * (1 - config.targetProfit),
      size: 0,
      leverage: 5, // Lower leverage for swing
      confidence: config.minConfidence,
      mode: 'swing',
      timeframe: '4h',
      reason: 'Swing signal from StyleManagingAgent',
    };
  }
}