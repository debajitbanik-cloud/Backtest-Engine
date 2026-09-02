import { ManagerAgent } from '../agents/ManagerAgent';
import { MarketData, Position, RiskMetrics, TradeSignal, AgentConfig, AgentDecision, ConfluenceSignal, StyleConfig, TradingMode } from '../types';
import { StyleManagingAgent } from '../agents/StyleManagingAgent';
import { TradeMasterAgent } from '../agents/TradeMasterAgent';
import { PositionSizingAgent } from '../agents/PositionSizingAgent';

export class TradingEngine {
  private manager: ManagerAgent;
  private marketDataBuffer: MarketData[] = [];
  private positions: Position[] = [];
  private riskMetrics: RiskMetrics;
  private isRunning: boolean = false;
  private updateInterval: ReturnType<typeof setInterval> | null = null;
  private equityCurve: number[] = []; // Track equity over time
  private closedTrades: Position[] = []; // Track closed trades for metrics
  private startingCapital: number = 10000;
  private callbacks: {
    onSignal?: (signal: TradeSignal) => void;
    onPositionUpdate?: (positions: Position[]) => void;
    onRiskAlert?: (alert: AgentDecision) => void;
    onDailyReport?: (report: any) => void;
  } = {};

  constructor(managerConfig?: Partial<AgentConfig>) {
    this.manager = new ManagerAgent({
      id: 'manager_agent',
      name: 'Manager Agent',
      enabled: true,
      priority: 0,
      parameters: managerConfig?.parameters || {},
    });
    
    this.riskMetrics = this.initializeRiskMetrics();
  }

  private initializeRiskMetrics(): RiskMetrics {
    return {
      totalExposure: 0,
      marginUsed: 0,
      marginAvailable: this.startingCapital,
      marginRatio: 0,
      maxDrawdown: 0,
      currentDrawdown: 0,
      var95: 0,
      sharpeRatio: 0,
      winRate: 0.5,
      profitFactor: 1.5,
      openPositions: 0,
      losingPositionsHeld: 0,
    };
  }

  setCallbacks(callbacks: {
    onSignal?: (signal: TradeSignal) => void;
    onPositionUpdate?: (positions: Position[]) => void;
    onRiskAlert?: (alert: AgentDecision) => void;
    onDailyReport?: (report: any) => void;
  }): void {
    this.callbacks = callbacks;
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    this.isRunning = true;
    console.log('Trading Engine started');
  }

  async stop(): Promise<void> {
    this.isRunning = false;
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
    console.log('Trading Engine stopped');
  }

  async processMarketData(data: MarketData): Promise<AgentDecision | null> {
    if (!this.isRunning) return null;
    
    this.marketDataBuffer.push(data);
    if (this.marketDataBuffer.length > 5000) {
      this.marketDataBuffer.shift();
    }
    
    this.updateRiskMetrics();
    
    const decision = await this.manager.analyze(this.marketDataBuffer, this.positions, this.riskMetrics);
    
    await this.handleDecision(decision);
    
    return decision;
  }

  private updateRiskMetrics(): void {
    const openPositions = this.positions.filter(p => p.status === 'open');
    this.riskMetrics.openPositions = openPositions.length;
    this.riskMetrics.totalExposure = openPositions.reduce((sum, p) => sum + p.size * p.currentPrice, 0);
    this.riskMetrics.marginUsed = openPositions.reduce((sum, p) => sum + (p.size * p.currentPrice) / p.leverage, 0);
    this.riskMetrics.marginRatio = this.riskMetrics.marginUsed / (this.riskMetrics.marginUsed + this.riskMetrics.marginAvailable);
    
    // Update equity curve with current portfolio value
    const currentEquity = this.riskMetrics.marginAvailable + this.riskMetrics.marginUsed + 
      this.positions.reduce((sum, p) => sum + p.realizedPnl + p.unrealizedPnl, 0);
    this.equityCurve.push(currentEquity);
    
    // Calculate drawdown
    const peakEquity = Math.max(...this.equityCurve);
    this.riskMetrics.currentDrawdown = peakEquity > 0 ? (peakEquity - currentEquity) / peakEquity : 0;
    this.riskMetrics.maxDrawdown = Math.max(this.riskMetrics.maxDrawdown, this.riskMetrics.currentDrawdown);
    
    // Calculate VaR 95% (using historical returns)
    this.riskMetrics.var95 = this.calculateVaR95();
    
    // Calculate Sharpe ratio
    this.riskMetrics.sharpeRatio = this.calculateSharpeRatio();
    
    // Calculate win rate and profit factor from closed trades
    this.updateTradeMetrics();
    
    this.riskMetrics.losingPositionsHeld = openPositions.filter(p => p.unrealizedPnl < 0).length;
  }
  
  private calculateVaR95(): number {
    if (this.equityCurve.length < 20) return 0;
    
    const returns: number[] = [];
    for (let i = 1; i < this.equityCurve.length; i++) {
      const ret = (this.equityCurve[i] - this.equityCurve[i - 1]) / this.equityCurve[i - 1];
      returns.push(ret);
    }
    
    if (returns.length < 20) return 0;
    
    // Use last 100 returns or all available
    const recentReturns = returns.slice(-100);
    recentReturns.sort((a, b) => a - b);
    
    // 5th percentile for 95% VaR
    const index = Math.floor(recentReturns.length * 0.05);
    return Math.abs(recentReturns[index]) * this.equityCurve[this.equityCurve.length - 1];
  }
  
  private calculateSharpeRatio(): number {
    if (this.equityCurve.length < 20) return 0;
    
    const returns: number[] = [];
    for (let i = 1; i < this.equityCurve.length; i++) {
      const ret = (this.equityCurve[i] - this.equityCurve[i - 1]) / this.equityCurve[i - 1];
      returns.push(ret);
    }
    
    if (returns.length < 2) return 0;
    
    const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
    const stdDev = Math.sqrt(variance);
    
    if (stdDev === 0) return 0;
    
    // Annualize assuming 15m candles (96 periods per day, 252 trading days)
    const annualizationFactor = Math.sqrt(96 * 252);
    return (meanReturn / stdDev) * annualizationFactor;
  }
  
  private updateTradeMetrics(): void {
    if (this.closedTrades.length === 0) {
      this.riskMetrics.winRate = 0.5;
      this.riskMetrics.profitFactor = 1.5;
      return;
    }
    
    const winningTrades = this.closedTrades.filter(t => t.realizedPnl > 0);
    const losingTrades = this.closedTrades.filter(t => t.realizedPnl < 0);
    
    this.riskMetrics.winRate = winningTrades.length / this.closedTrades.length;
    
    const grossProfit = winningTrades.reduce((sum, t) => sum + t.realizedPnl, 0);
    const grossLoss = Math.abs(losingTrades.reduce((sum, t) => sum + t.realizedPnl, 0));
    
    this.riskMetrics.profitFactor = grossLoss > 0 ? grossProfit / grossLoss : 1.5;
  }

  private async handleDecision(decision: AgentDecision): Promise<void> {
    if (decision.parameters?.emergency || decision.parameters?.halted) {
      this.callbacks.onRiskAlert?.(decision);
      return;
    }
    
    if (decision.parameters?.riskOverride) {
      this.callbacks.onRiskAlert?.(decision);
    }
    
    if (decision.action === 'buy' || decision.action === 'sell') {
      const signal = this.createSignalFromDecision(decision);
      if (signal) {
        this.callbacks.onSignal?.(signal);
      }
    } else if (decision.action === 'close' || decision.action === 'reduce') {
      this.handlePositionReduction(decision);
    }
    
    if (decision.parameters?.report) {
      this.callbacks.onDailyReport?.(decision.parameters.report);
      await this.manager.onDailyReport(decision.parameters.report);
    }
  }

  private createSignalFromDecision(decision: AgentDecision): TradeSignal | null {
    const styleAgent = this.manager.getSubAgent('style_managing_agent');
    const currentMode = styleAgent?.getCurrentMode() || 'swing';
    const sizingDecision = decision.parameters?.subDecisions?.find((d: { agentId: string }) => d.agentId === 'position_sizing_agent');
    
    const latestData = this.marketDataBuffer[this.marketDataBuffer.length - 1];
    if (!latestData) return null;
    
    const biasDecision = decision.parameters?.subDecisions?.find((d: any) => d.agentId === 'bias_determining_agent');
    const side = biasDecision?.parameters?.bias === 'bullish' ? 'long' : 'short';
    
    let leverage = 5;
    let stopLoss = 0.005;
    let takeProfit = 0.01;
    
    if (currentMode === 'scalping') {
      leverage = 10;
      stopLoss = 0.0005;
      takeProfit = 0.001;
    }
    
    if (sizingDecision?.parameters) {
      leverage = sizingDecision.parameters.maxLeverage || leverage;
    }
    
    const entryPrice = latestData.close;
    const stopLossPrice = side === 'long' 
      ? entryPrice * (1 - stopLoss)
      : entryPrice * (1 + stopLoss);
    const takeProfitPrice = side === 'long'
      ? entryPrice * (1 + takeProfit)
      : entryPrice * (1 - takeProfit);
    
    const baseSignal: TradeSignal = {
      symbol: latestData.symbol,
      side,
      entryPrice,
      stopLoss: stopLossPrice,
      takeProfit: takeProfitPrice,
      size: 0,
      leverage,
      confidence: decision.confidence,
      mode: currentMode,
      timeframe: currentMode === 'scalping' ? '15m' : '4h',
      reason: `Manager consensus: ${decision.reasoning}`,
      metadata: { managerDecision: decision },
    };
    
    // Use PositionSizingAgent to calculate proper position size
    const sizingAgent = this.manager.getSubAgent('position_sizing_agent');
    if (sizingAgent) {
      const sizedSignal = sizingAgent.calculateSignalSizing(
        baseSignal,
        this.marketDataBuffer,
        this.riskMetrics,
        this.positions.filter(p => p.status === 'open')
      );
      return sizedSignal;
    }
    
    return baseSignal;
  }

  private handlePositionReduction(decision: AgentDecision): void {
    const openPositions = this.positions.filter(p => p.status === 'open');
    
    if (decision.parameters?.reduceAllPositions) {
      for (const pos of openPositions) {
        pos.size *= 0.5;
        console.log(`Reduced position ${pos.id} by 50%`);
      }
    } else {
      const targetIds = decision.parameters?.positionIds || [];
      for (const pos of openPositions) {
        if (targetIds.includes(pos.id)) {
          pos.size *= 0.5;
          console.log(`Reduced position ${pos.id} by 50%`);
        }
      }
    }
    
    this.callbacks.onPositionUpdate?.(this.positions);
  }

  addPosition(position: Position): void {
    this.positions.push(position);
    this.callbacks.onPositionUpdate?.(this.positions);
  }

  updatePosition(positionId: string, updates: Partial<Position>): void {
    const index = this.positions.findIndex(p => p.id === positionId);
    if (index !== -1) {
      this.positions[index] = { ...this.positions[index], ...updates };
      this.callbacks.onPositionUpdate?.(this.positions);
    }
  }

  closePosition(positionId: string, exitPrice: number): void {
    const index = this.positions.findIndex(p => p.id === positionId);
    if (index !== -1) {
      const pos = this.positions[index];
      pos.status = 'closed';
      pos.currentPrice = exitPrice;
      pos.realizedPnl = pos.side === 'long'
        ? (exitPrice - pos.entryPrice) * pos.size
        : (pos.entryPrice - exitPrice) * pos.size;
      pos.unrealizedPnl = 0;
      
      // Track closed trade for metrics
      this.closedTrades.push({ ...pos });
      
      const tradeMaster = this.manager.getSubAgent('trade_master_agent');
      tradeMaster?.recordTrade(pos);
      
      this.callbacks.onPositionUpdate?.(this.positions);
    }
  }

  getPositions(): Position[] {
    return [...this.positions];
  }

  getOpenPositions(): Position[] {
    return this.positions.filter(p => p.status === 'open');
  }

  getRiskMetrics(): RiskMetrics {
    return { ...this.riskMetrics };
  }

  getMarketDataBuffer(): MarketData[] {
    return [...this.marketDataBuffer];
  }

  getManager(): ManagerAgent {
    return this.manager;
  }

  getSystemStatus() {
    return this.manager.getSystemStatus();
  }

  isEngineRunning(): boolean {
    return this.isRunning;
  }
}