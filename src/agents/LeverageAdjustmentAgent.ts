import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, MarginRequirements, Position, RiskMetrics } from '../types';

const HIGH_MARGIN_THRESHOLD = 0.8;
const CRITICAL_MARGIN_THRESHOLD = 0.9;
const LEVERAGE_REDUCTION_FACTOR = 0.5;
const MIN_LEVERAGE = 1;
const MAX_LEVERAGE = 100;

export class LeverageAdjustmentAgent extends BaseAgent {
  constructor(config: AgentConfig) {
    const params = {
      ...config.parameters,
      highMarginThreshold: config.parameters.highMarginThreshold ?? HIGH_MARGIN_THRESHOLD,
      criticalMarginThreshold: config.parameters.criticalMarginThreshold ?? CRITICAL_MARGIN_THRESHOLD,
      leverageReductionFactor: config.parameters.leverageReductionFactor ?? LEVERAGE_REDUCTION_FACTOR,
      minLeverage: config.parameters.minLeverage ?? MIN_LEVERAGE,
      maxLeverage: config.parameters.maxLeverage ?? MAX_LEVERAGE,
    };
    super({
      ...config,
      id: 'leverage_adjustment_agent',
      name: 'Leverage Adjustment Agent',
      parameters: params,
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    const marginRequirements = this.calculateMarginRequirements(positions, riskMetrics);
    
    if (marginRequirements.isHighMarginPeriod) {
      return this.handleHighMarginPeriod(marginRequirements, positions);
    }

    return this.createDecision('hold', 0.5, 'Margin levels normal, no leverage adjustment needed');
  }

  private calculateMarginRequirements(positions: Position[], riskMetrics: RiskMetrics): MarginRequirements {
    const totalPositionValue = positions.reduce((sum, p) => sum + p.size * p.currentPrice, 0);
    const marginUsed = riskMetrics.marginUsed;
    const marginAvailable = riskMetrics.marginAvailable;
    const marginRatio = marginUsed / (marginUsed + marginAvailable);
    
    const openPositions = positions.filter(p => p.status === 'open');
    const avgLeverage = openPositions.length > 0
      ? openPositions.reduce((sum, p) => sum + p.leverage, 0) / openPositions.length
      : 1;

    return {
      symbol: 'PORTFOLIO',
      maintenanceMargin: marginUsed * 0.5,
      initialMargin: marginUsed,
      currentMarginRatio: marginRatio,
      isHighMarginPeriod: marginRatio >= this.config.parameters.highMarginThreshold,
      leverageLimit: this.calculateLeverageLimit(marginRatio, avgLeverage),
    };
  }

  private calculateLeverageLimit(marginRatio: number, currentAvgLeverage: number): number {
    const { criticalMarginThreshold, leverageReductionFactor, minLeverage, maxLeverage, highMarginThreshold } = this.config.parameters;
    
    if (marginRatio >= criticalMarginThreshold) {
      return Math.max(minLeverage, Math.floor(currentAvgLeverage * leverageReductionFactor));
    }
    
    if (marginRatio >= highMarginThreshold) {
      return Math.max(minLeverage, Math.floor(currentAvgLeverage * (1 - (marginRatio - highMarginThreshold) * 2)));
    }
    
    return maxLeverage;
  }

  private handleHighMarginPeriod(
    marginRequirements: MarginRequirements,
    positions: Position[]
  ): AgentDecision {
    const openPositions = positions.filter(p => p.status === 'open');
    const avgLeverage = openPositions.length > 0
      ? openPositions.reduce((sum, p) => sum + p.leverage, 0) / openPositions.length
      : 1;

    const newLeverageLimit = marginRequirements.leverageLimit;
    const reductionPercent = ((avgLeverage - newLeverageLimit) / avgLeverage) * 100;

    if (marginRequirements.currentMarginRatio >= this.config.parameters.criticalMarginThreshold) {
      return this.createDecision(
        'reduce',
        0.95,
        `CRITICAL: Margin ratio at ${(marginRequirements.currentMarginRatio * 100).toFixed(1)}%. Reducing leverage from ${avgLeverage.toFixed(1)}x to ${newLeverageLimit}x (${reductionPercent.toFixed(1)}% reduction). Immediate position size reduction required.`,
        {
          newLeverageLimit,
          currentMarginRatio: marginRequirements.currentMarginRatio,
          action: 'emergency_deleverage',
          reduceAllPositions: true,
        }
      );
    }

    return this.createDecision(
      'adjust',
      0.85,
      `HIGH MARGIN: Margin ratio at ${(marginRequirements.currentMarginRatio * 100).toFixed(1)}%. Adjusting leverage limit from ${avgLeverage.toFixed(1)}x to ${newLeverageLimit}x (${reductionPercent.toFixed(1)}% reduction).`,
      {
        newLeverageLimit,
        currentMarginRatio: marginRequirements.currentMarginRatio,
        action: 'gradual_deleverage',
        reduceAllPositions: false,
      }
    );
  }

  async onMarginUpdate(marginRequirements: MarginRequirements): Promise<AgentDecision> {
    if (marginRequirements.isHighMarginPeriod) {
      return this.createDecision(
        'adjust',
        0.9,
        `Margin update: Ratio at ${(marginRequirements.currentMarginRatio * 100).toFixed(1)}%. Leverage limit set to ${marginRequirements.leverageLimit}x`,
        { newLeverageLimit: marginRequirements.leverageLimit }
      );
    }
    return this.createDecision('hold', 0.5, 'Margin levels normalized');
  }
}