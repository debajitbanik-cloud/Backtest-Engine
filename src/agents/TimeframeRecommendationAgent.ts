import { BaseAgent } from '../core/BaseAgent';
import { AgentConfig, AgentDecision, MarketData, Position, RiskMetrics, Timeframe, TimeframeRecommendation, TimeframeRecommendationConfig } from '../types';

const DEFAULT_CONFIG: TimeframeRecommendationConfig = {
  availableTimeframes: ['1m', '5m', '15m', '1h', '4h'],
  preferredTimeframes: ['15m', '1h'],
  minConfidence: 0.55,
  confluenceWeight: 0.35,
  biasWeight: 0.30,
  riskWeight: 0.20,
  modeWeight: 0.15,
  maxHistory: 100,
};

export class TimeframeRecommendationAgent extends BaseAgent {
  private biasSignals: Map<string, { direction: string; confidence: number; timeframe: Timeframe }> = new Map();
  private confluenceSignals: Map<string, { result: string; confidence: number; alignments: Record<string, string> }> = new Map();
  private modeSignals: Map<string, { mode: string; reasoning: string }> = new Map();
  private riskSignals: Map<string, { riskLevel: string; action: string }> = new Map();
  private recommendations: Map<string, TimeframeRecommendation> = new Map();
  private history: Map<string, TimeframeRecommendation[]> = new Map();

  private get recConfig(): TimeframeRecommendationConfig {
    const params = this.config.parameters;
    return {
      availableTimeframes: params.availableTimeframes ?? DEFAULT_CONFIG.availableTimeframes,
      preferredTimeframes: params.preferredTimeframes ?? DEFAULT_CONFIG.preferredTimeframes,
      minConfidence: params.minConfidence ?? DEFAULT_CONFIG.minConfidence,
      confluenceWeight: params.confluenceWeight ?? DEFAULT_CONFIG.confluenceWeight,
      biasWeight: params.biasWeight ?? DEFAULT_CONFIG.biasWeight,
      riskWeight: params.riskWeight ?? DEFAULT_CONFIG.riskWeight,
      modeWeight: params.modeWeight ?? DEFAULT_CONFIG.modeWeight,
      maxHistory: params.maxHistory ?? DEFAULT_CONFIG.maxHistory,
    };
  }

  constructor(config: AgentConfig) {
    super({
      ...config,
      id: 'timeframe_recommendation_agent',
      name: 'Timeframe Recommendation Agent',
      parameters: {
        ...DEFAULT_CONFIG,
        ...config.parameters,
      },
    });
  }

  async analyze(
    marketData: MarketData[],
    positions: Position[],
    riskMetrics: RiskMetrics
  ): Promise<AgentDecision> {
    const symbols = [...new Set(marketData.map(d => d.symbol))];
    let recommendationsGenerated = 0;

    for (const symbol of symbols) {
      if (this.shouldGenerateRecommendation(symbol)) {
        const rec = this.generateRecommendation(symbol);
        this.recommendations.set(symbol, rec);
        this.addToHistory(symbol, rec);
        recommendationsGenerated++;
      }
    }

    return this.createDecision(
      'adjust',
      0.7,
      `Timeframe recommendations updated for ${recommendationsGenerated} symbols`,
      { recommendations: Array.from(this.recommendations.values()) }
    );
  }

  private shouldGenerateRecommendation(symbol: string): boolean {
    return this.biasSignals.has(symbol);
  }

  private generateRecommendation(symbol: string): TimeframeRecommendation {
    const bias = this.biasSignals.get(symbol)!;
    const confluence = this.confluenceSignals.get(symbol);
    const mode = this.modeSignals.get(symbol);
    const risk = this.riskSignals.get(symbol);

    const reasoning: string[] = [];
    const alignment: Record<string, string> = {};

    // 1. Bias score
    const biasDirection = bias.direction;
    const biasConf = bias.confidence;
    const biasScore = biasConf > 0.3 && biasDirection !== 'neutral' ? biasConf : 0.3;

    // 2. Confluence score
    let confluenceScore = 0.3;
    let confluenceDir: 'long' | 'short' | 'flat' = 'flat';
    let confluenceResult = 'unavailable';

    if (confluence) {
      confluenceResult = confluence.result;
      const confluenceConf = confluence.confidence;

      if (confluenceResult === 'strong_bullish' || confluenceResult === 'bullish') {
        confluenceScore = confluenceConf * (confluenceResult === 'strong_bullish' ? 1 : 0.8);
        confluenceDir = 'long';
      } else if (confluenceResult === 'strong_bearish' || confluenceResult === 'bearish') {
        confluenceScore = confluenceConf * (confluenceResult === 'strong_bearish' ? 1 : 0.8);
        confluenceDir = 'short';
      } else {
        confluenceScore = 0.3;
        confluenceDir = 'flat';
      }
    } else {
      // No confluence signal: derive from bias
      confluenceScore = biasScore * 0.7;
      confluenceDir = biasDirection === 'bullish' ? 'long' : biasDirection === 'bearish' ? 'short' : 'flat';
    }

    // 3. Mode score
    let modeScore = 0.5;
    let modeTimeframe: Timeframe = '15m';

    if (mode) {
      const modeName = mode.mode;
      if (modeName === 'scalping') {
        modeScore = 0.7;
        modeTimeframe = '5m';
      } else if (modeName === 'swing') {
        modeScore = 0.8;
        modeTimeframe = '1h';
      } else {
        modeScore = 0.6;
        modeTimeframe = '15m';
      }
    }

    // 4. Risk score
    const riskLevel = risk?.riskLevel || 'low';
    let riskScore = 0.9;
    if (riskLevel === 'medium') riskScore = 0.6;
    else if (riskLevel === 'high') riskScore = 0.4;
    else if (riskLevel === 'critical') riskScore = 0.2;

    // 5. Determine direction
    let direction: 'long' | 'short' | 'flat' = 'flat';

    if (confluenceDir === 'long' && biasDirection === 'bullish') {
      direction = 'long';
    } else if (confluenceDir === 'short' && biasDirection === 'bearish') {
      direction = 'short';
    } else if (confluenceDir === 'flat' || biasDirection === 'neutral') {
      direction = 'flat';
    } else {
      // Conflicting signals
      if (confluenceScore > biasScore) {
        direction = confluenceDir;
      } else if (biasScore > confluenceScore) {
        direction = biasDirection === 'bullish' ? 'long' : 'short';
      }
    }

    // 6. Select recommended timeframe
    const tfScores: Record<Timeframe, number> = {
      '1m': 0, '5m': 0, '15m': 0, '1h': 0, '4h': 0, '1d': 0, '1w': 0
    };

    for (const tf of this.recConfig.availableTimeframes) {
      let score = 0;
      if (tf === modeTimeframe) score += 0.4;
      if (this.recConfig.preferredTimeframes.includes(tf)) score += 0.3;
      if (tf === '15m') score += 0.15;
      if (confluence?.alignments[tf]) score += 0.15;
      tfScores[tf] = score;
    }

    const recommendedTimeframe = (Object.entries(tfScores)
      .sort((a, b) => b[1] - a[1])[0][0]) as Timeframe;

    // 7. Combined confidence
    let confidence = (
      this.recConfig.biasWeight * biasScore +
      this.recConfig.confluenceWeight * confluenceScore +
      this.recConfig.modeWeight * modeScore +
      this.recConfig.riskWeight * riskScore
    );

    if (confidence < this.recConfig.minConfidence && direction !== 'flat') {
      direction = 'flat';
    }

    // Build reasoning
    reasoning.push(`Bias: ${biasDirection} (${biasConf.toFixed(2)})`);
    if (confluence) {
      reasoning.push(`Confluence: ${confluenceResult} (${confluence.confidence.toFixed(2)})`);
    } else {
      reasoning.push('Confluence: not yet available');
    }
    if (mode) {
      reasoning.push(`Mode: ${mode.mode}`);
    }
    reasoning.push(`Risk: ${riskLevel}`);
    reasoning.push(`Recommended timeframe: ${recommendedTimeframe}`);

    // Alignment matrix
    alignment.bias_agent = biasDirection;
    alignment.confluence_agent = confluenceResult;
    alignment.style_agent = mode?.mode || 'unknown';
    alignment.risk_agent = riskLevel;

    return {
      symbol,
      recommendedTimeframe,
      direction,
      confidence: Math.min(confidence, 1.0),
      confluenceScore,
      biasScore,
      riskScore,
      alignment,
      reasoning,
      timestamp: Date.now(),
    };
  }

  private addToHistory(symbol: string, rec: TimeframeRecommendation): void {
    if (!this.history.has(symbol)) {
      this.history.set(symbol, []);
    }
    const hist = this.history.get(symbol)!;
    hist.push(rec);
    if (hist.length > this.recConfig.maxHistory) {
      hist.shift();
    }
  }

  updateBiasSignal(symbol: string, direction: 'bullish' | 'bearish' | 'neutral', confidence: number, timeframe: Timeframe): void {
    this.biasSignals.set(symbol, { direction, confidence, timeframe });
  }

  updateConfluenceSignal(symbol: string, result: string, confidence: number, alignments: Record<string, string>): void {
    this.confluenceSignals.set(symbol, { result, confidence, alignments });
  }

  updateModeSignal(symbol: string, mode: string, reasoning: string): void {
    this.modeSignals.set(symbol, { mode, reasoning });
  }

  updateRiskSignal(symbol: string, riskLevel: string, action: string): void {
    this.riskSignals.set(symbol, { riskLevel, action });
  }

  getRecommendation(symbol: string): TimeframeRecommendation | undefined {
    return this.recommendations.get(symbol);
  }

  getAllRecommendations(): Map<string, TimeframeRecommendation> {
    return new Map(this.recommendations);
  }
}