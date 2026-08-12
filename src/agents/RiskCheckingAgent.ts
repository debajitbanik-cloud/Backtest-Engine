import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics } from '../types';

const MAX_DRAWDOWN = 0.1;
const MAX_POSITION_LOSS = 0.05;
const MAX_HOLD_LOSING_TIME = 4 * 60 * 60 * 1000;
const CORRELATION_LIMIT = 0.7;
const DAILY_LOSS_LIMIT = 0.05;
const MARGIN_CALL_BUFFER = 0.15;

export class RiskCheckingAgent extends BaseAgent {
  private dailyPnl: number = 0;
  private dailyStartEquity: number = 0;
  private lastResetDate: string = new Date().toDateString();

  constructor(config: AgentConfig) {
    const params = {
      ...config.parameters,
      maxDrawdown: config.parameters.maxDrawdown ?? MAX_DRAWDOWN,
      maxPositionLoss: config.parameters.maxPositionLoss ?? MAX_POSITION_LOSS,
      maxHoldLosingTime: config.parameters.maxHoldLosingTime ?? MAX_HOLD_LOSING_TIME,
      correlationLimit: config.parameters.correlationLimit ?? CORRELATION_LIMIT,
      dailyLossLimit: config.parameters.dailyLossLimit ?? DAILY_LOSS_LIMIT,
      marginCallBuffer: config.parameters.marginCallBuffer ?? MARGIN_CALL_BUFFER,
    };
    super({
      ...config,
      id: 'risk_checking_agent',
      name: 'Risk Checking Agent',
      parameters: params,
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    this.checkDailyReset(riskMetrics);
    
    const risks = this.assessAllRisks(positions, riskMetrics, marketData);
    const criticalRisks = risks.filter(r => r.severity === 'critical');
    const highRisks = risks.filter(r => r.severity === 'high');
    
    if (criticalRisks.length > 0) {
      return this.handleCriticalRisks(criticalRisks, positions);
    }
    
    if (highRisks.length > 0) {
      return this.handleHighRisks(highRisks, positions);
    }
    
    return this.createDecision(
      'hold',
      0.7,
      `Risk check passed. ${risks.length} risks monitored. Daily PnL: ${(this.dailyPnl * 100).toFixed(2)}%`,
      { risks, dailyPnl: this.dailyPnl, dailyLimit: this.config.parameters.dailyLossLimit }
    );
  }

  private checkDailyReset(riskMetrics: RiskMetrics): void {
    const today = new Date().toDateString();
    if (today !== this.lastResetDate) {
      this.dailyStartEquity = riskMetrics.marginAvailable + riskMetrics.marginUsed;
      this.dailyPnl = 0;
      this.lastResetDate = today;
    }
  }

  private assessAllRisks(
    positions: Position[],
    riskMetrics: RiskMetrics,
    marketData: MarketData[]
  ): Array<{ type: string; severity: 'low' | 'medium' | 'high' | 'critical'; message: string; action: string; positionId?: string }> {
    const risks: Array<{ type: string; severity: 'low' | 'medium' | 'high' | 'critical'; message: string; action: string; positionId?: string }> = [];
    
    // Portfolio drawdown risk
    if (riskMetrics.currentDrawdown >= this.config.parameters.maxDrawdown) {
      risks.push({
        type: 'portfolio_drawdown',
        severity: 'critical',
        message: `Portfolio drawdown ${(riskMetrics.currentDrawdown * 100).toFixed(2)}% exceeds limit ${(this.config.parameters.maxDrawdown * 100).toFixed(2)}%`,
        action: 'close_all_positions',
      });
    } else if (riskMetrics.currentDrawdown >= this.config.parameters.maxDrawdown * 0.7) {
      risks.push({
        type: 'portfolio_drawdown',
        severity: 'high',
        message: `Portfolio drawdown ${(riskMetrics.currentDrawdown * 100).toFixed(2)}% approaching limit`,
        action: 'reduce_positions',
      });
    }
    
    // Daily loss limit
    const dailyLossPct = this.dailyStartEquity > 0 ? -this.dailyPnl / this.dailyStartEquity : 0;
    if (dailyLossPct >= this.config.parameters.dailyLossLimit) {
      risks.push({
        type: 'daily_loss_limit',
        severity: 'critical',
        message: `Daily loss ${(dailyLossPct * 100).toFixed(2)}% exceeds limit ${(this.config.parameters.dailyLossLimit * 100).toFixed(2)}%`,
        action: 'stop_trading',
      });
    }
    
    // Margin call risk
    const marginRatio = riskMetrics.marginUsed / (riskMetrics.marginUsed + riskMetrics.marginAvailable);
    if (marginRatio >= 1 - this.config.parameters.marginCallBuffer) {
      risks.push({
        type: 'margin_call',
        severity: 'critical',
        message: `Margin ratio ${(marginRatio * 100).toFixed(1)}% critically high`,
        action: 'emergency_deleverage',
      });
    }
    
    // Individual position risks
    const now = Date.now();
    for (const pos of positions.filter(p => p.status === 'open')) {
      const positionLoss = pos.unrealizedPnl / (pos.size * pos.entryPrice);
      const holdTime = now - pos.entryTime;
      
      if (positionLoss <= -this.config.parameters.maxPositionLoss) {
        risks.push({
          type: 'position_loss',
          severity: 'critical',
          message: `Position ${pos.id} loss ${(positionLoss * 100).toFixed(2)}% exceeds limit`,
          action: 'close_position',
          positionId: pos.id,
        });
      } else if (positionLoss <= -this.config.parameters.maxPositionLoss * 0.7) {
        risks.push({
          type: 'position_loss',
          severity: 'high',
          message: `Position ${pos.id} loss ${(positionLoss * 100).toFixed(2)}% approaching limit`,
          action: 'reduce_position',
          positionId: pos.id,
        });
      }
      
      if (positionLoss < 0 && holdTime > this.config.parameters.maxHoldLosingTime) {
        risks.push({
          type: 'held_loser',
          severity: 'high',
          message: `Position ${pos.id} held at loss for ${(holdTime / 3600000).toFixed(1)}h`,
          action: 'review_or_close',
          positionId: pos.id,
        });
      }
    }
    
    // Correlation risk
    const correlationRisk = this.checkCorrelationRisk(positions);
    if (correlationRisk) risks.push(correlationRisk);
    
    // Concentration risk
    const concentrationRisk = this.checkConcentrationRisk(positions, riskMetrics);
    if (concentrationRisk) risks.push(concentrationRisk);
    
    return risks;
  }

  private checkCorrelationRisk(positions: Position[]): { type: string; severity: 'low' | 'medium' | 'high' | 'critical'; message: string; action: string } | null {
    const openPositions = positions.filter(p => p.status === 'open');
    const symbols = [...new Set(openPositions.map(p => p.symbol))];
    
    if (symbols.length < 2) return null;
    
    const baseAssets = symbols.map(s => s.replace(/USDT?|BUSD|BTC|ETH/, ''));
    const uniqueBases = [...new Set(baseAssets)];
    
    if (uniqueBases.length < symbols.length * 0.5) {
      return {
        type: 'correlation',
        severity: 'high',
        message: `High correlation detected: ${symbols.length} positions in ${uniqueBases.length} base assets`,
        action: 'diversify',
      };
    }
    
    return null;
  }

  private checkConcentrationRisk(positions: Position[], riskMetrics: RiskMetrics): { type: string; severity: 'low' | 'medium' | 'high' | 'critical'; message: string; action: string } | null {
    const openPositions = positions.filter(p => p.status === 'open');
    const totalValue = openPositions.reduce((sum, p) => sum + p.size * p.currentPrice, 0);
    
    if (totalValue === 0) return null;
    
    for (const pos of openPositions) {
      const concentration = (pos.size * pos.currentPrice) / totalValue;
      if (concentration > 0.5) {
        return {
          type: 'concentration',
          severity: 'high',
          message: `Position ${pos.symbol} represents ${(concentration * 100).toFixed(1)}% of portfolio`,
          action: 'reduce_position',
        };
      }
    }
    
    return null;
  }

  private handleCriticalRisks(
    criticalRisks: Array<{ type: string; severity: string; message: string; action: string; positionId?: string }>,
    positions: Position[]
  ): AgentDecision {
    const actions = criticalRisks.map(r => r.action);
    const messages = criticalRisks.map(r => r.message);
    
    let primaryAction: AgentDecision['action'] = 'close';
    let reasoning = `CRITICAL RISKS DETECTED: ${messages.join('; ')}`;
    
    if (actions.includes('close_all_positions') || actions.includes('stop_trading')) {
      primaryAction = 'close';
      reasoning += ' - EMERGENCY: Closing all positions and halting trading';
    } else if (actions.includes('emergency_deleverage')) {
      primaryAction = 'reduce';
      reasoning += ' - EMERGENCY: Immediate deleveraging required';
    } else if (actions.includes('close_position')) {
      primaryAction = 'close';
      reasoning += ` - Closing specific positions: ${criticalRisks.filter(r => r.action === 'close_position').map(r => r.positionId).join(', ')}`;
    }
    
    return this.createDecision(primaryAction, 0.99, reasoning, {
      risks: criticalRisks,
      emergency: true,
    });
  }

  private handleHighRisks(
    highRisks: Array<{ type: string; severity: string; message: string; action: string; positionId?: string }>,
    positions: Position[]
  ): AgentDecision {
    const actions = highRisks.map(r => r.action);
    const messages = highRisks.map(r => r.message);
    
    let primaryAction: AgentDecision['action'] = 'reduce';
    let reasoning = `HIGH RISKS DETECTED: ${messages.join('; ')}`;
    
    if (actions.includes('reduce_positions')) {
      primaryAction = 'reduce';
      reasoning += ' - Reducing position sizes across portfolio';
    } else if (actions.includes('reduce_position')) {
      primaryAction = 'reduce';
      reasoning += ` - Reducing specific positions: ${highRisks.filter(r => r.action === 'reduce_position').map(r => r.positionId).join(', ')}`;
    } else if (actions.includes('review_or_close')) {
      primaryAction = 'adjust';
      reasoning += ' - Reviewing held losers for potential closure';
    } else if (actions.includes('diversify')) {
      primaryAction = 'adjust';
      reasoning += ' - Diversifying correlated positions';
    }
    
    return this.createDecision(primaryAction, 0.85, reasoning, {
      risks: highRisks,
      warning: true,
    });
  }

  updateDailyPnl(pnl: number): void {
    this.dailyPnl += pnl;
  }

  getDailyPnl(): number {
    return this.dailyPnl;
  }

  getDailyLossPct(): number {
    return this.dailyStartEquity > 0 ? -this.dailyPnl / this.dailyStartEquity : 0;
  }

  canOpenNewPosition(): boolean {
    const dailyLossPct = this.getDailyLossPct();
    return dailyLossPct < this.config.parameters.dailyLossLimit * 0.8;
  }

  getRiskLimits() {
    return {
      maxDrawdown: this.config.parameters.maxDrawdown,
      maxPositionLoss: this.config.parameters.maxPositionLoss,
      maxHoldLosingTime: this.config.parameters.maxHoldLosingTime,
      dailyLossLimit: this.config.parameters.dailyLossLimit,
      marginCallBuffer: this.config.parameters.marginCallBuffer,
    };
  }
}