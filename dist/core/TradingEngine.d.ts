import { ManagerAgent } from '../agents/ManagerAgent';
import { MarketData, Position, RiskMetrics, TradeSignal, AgentConfig, AgentDecision } from '../types';
export declare class TradingEngine {
    private manager;
    private marketDataBuffer;
    private positions;
    private riskMetrics;
    private isRunning;
    private updateInterval;
    private callbacks;
    constructor(managerConfig?: Partial<AgentConfig>);
    private initializeRiskMetrics;
    setCallbacks(callbacks: {
        onSignal?: (signal: TradeSignal) => void;
        onPositionUpdate?: (positions: Position[]) => void;
        onRiskAlert?: (alert: AgentDecision) => void;
        onDailyReport?: (report: any) => void;
    }): void;
    start(): Promise<void>;
    stop(): Promise<void>;
    processMarketData(data: MarketData): Promise<AgentDecision | null>;
    private updateRiskMetrics;
    private handleDecision;
    private createSignalFromDecision;
    private handlePositionReduction;
    addPosition(position: Position): void;
    updatePosition(positionId: string, updates: Partial<Position>): void;
    closePosition(positionId: string, exitPrice: number): void;
    getPositions(): Position[];
    getOpenPositions(): Position[];
    getRiskMetrics(): RiskMetrics;
    getMarketDataBuffer(): MarketData[];
    getManager(): ManagerAgent;
    getSystemStatus(): {
        isHalted: boolean;
        haltReason: string;
        activeAgents: number;
        totalAgents: number;
        currentMode: string;
        lastConsensus: any;
    };
    isEngineRunning(): boolean;
}
//# sourceMappingURL=TradingEngine.d.ts.map