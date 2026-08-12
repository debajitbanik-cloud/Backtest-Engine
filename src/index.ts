export * from './types';
export * from './agents';
export * from './core/BaseAgent';
export * from './core/TradingEngine';
export * from './config/defaultConfig';
export * from './utils/helpers';
export * from './data';

import { TradingEngine } from './core/TradingEngine';
import { MarketData, Position, TradeSignal, RiskMetrics } from './types';
import { defaultConfig } from './config/defaultConfig';
import { generateId } from './utils/helpers';
import { BinanceDataLoader, FileDataLoader } from './data';

async function runDemo() {
  const useRealData = process.argv.includes('--real-data');
  const fromFile = process.argv.includes('--from-file');
  const symbol = process.argv.includes('--symbol')
    ? process.argv[process.argv.indexOf('--symbol') + 1]
    : 'BTCUSDT';
  const timeframe = (process.argv.includes('--timeframe')
    ? process.argv[process.argv.indexOf('--timeframe') + 1]
    : '15m') as any;

  console.log('=== Multi-Agent Trading System Demo ===\n');
  console.log(`Mode: ${useRealData ? 'REAL DATA (Binance)' : fromFile ? 'HISTORICAL FILE' : 'SIMULATED'}`);
  if (useRealData || fromFile) console.log(`Symbol: ${symbol} | Timeframe: ${timeframe}\n`);
  
  const engine = new TradingEngine();
  const dataLoader = useRealData ? new BinanceDataLoader() : null;
  const fileLoader = fromFile ? new FileDataLoader('./data/shared') : null;
  
  engine.setCallbacks({
    onSignal: (signal: TradeSignal) => {
      console.log(`\n📈 SIGNAL GENERATED:`);
      console.log(`   Symbol: ${signal.symbol}`);
      console.log(`   Side: ${signal.side.toUpperCase()}`);
      console.log(`   Mode: ${signal.mode.toUpperCase()}`);
      console.log(`   Entry: $${signal.entryPrice.toFixed(2)}`);
      console.log(`   Stop: $${signal.stopLoss.toFixed(2)}`);
      console.log(`   Target: $${signal.takeProfit.toFixed(2)}`);
      console.log(`   Leverage: ${signal.leverage}x`);
      console.log(`   Confidence: ${(signal.confidence * 100).toFixed(1)}%`);
      console.log(`   Reason: ${signal.reason}`);
    },
    onPositionUpdate: (positions: Position[]) => {
      const open = positions.filter(p => p.status === 'open');
      if (open.length > 0) {
        console.log(`\n📊 Positions Update: ${open.length} open`);
        for (const pos of open) {
          const pnlPct = ((pos.currentPrice - pos.entryPrice) / pos.entryPrice * 100 * (pos.side === 'long' ? 1 : -1)).toFixed(2);
          console.log(`   ${pos.symbol} ${pos.side} ${pos.mode} | PnL: ${pnlPct}% | Size: ${pos.size.toFixed(4)}`);
        }
      }
    },
    onRiskAlert: (alert) => {
      console.log(`\n⚠️  RISK ALERT: ${alert.action.toUpperCase()} (${(alert.confidence * 100).toFixed(0)}%)`);
      console.log(`   ${alert.reasoning}`);
    },
    onDailyReport: (report) => {
      console.log(`\n📋 DAILY REPORT: ${report.date}`);
      console.log(`   Trades: ${report.totalTrades} | Win Rate: ${(report.winRate * 100).toFixed(1)}%`);
      console.log(`   PnL: $${report.totalPnl.toFixed(2)} | Max DD: ${(report.maxDrawdown * 100).toFixed(2)}%`);
      console.log(`   Optimizations: ${report.optimizations.length}`);
    },
  });
  
  await engine.start();
  
  const processMarketDataArray = async (engine: any, data: MarketData[], stepLabel: string) => {
    for (let i = 0; i < data.length; i++) {
      await engine.processMarketData(data[i]);
      
      if (i % 100 === 0 && i > 0) {
        console.log(`\n--- Step ${i} (${stepLabel}) ---`);
        const status = engine.getSystemStatus();
        console.log(`System: ${status.isHalted ? 'HALTED' : 'RUNNING'} | Mode: ${status.currentMode} | Agents: ${status.activeAgents}/${status.totalAgents}`);
        
        const risk = engine.getRiskMetrics();
        console.log(`Margin: ${(risk.marginRatio * 100).toFixed(1)}% | Drawdown: ${(risk.currentDrawdown * 100).toFixed(2)}% | Open: ${risk.openPositions}`);
      }
      
      await new Promise<void>(r => setTimeout(r, 1));
    }
  };
  
  if (useRealData && dataLoader) {
    console.log(`\n--- Fetching real ${timeframe} data for ${symbol} from Binance ---\n`);
    try {
      const historicalData = await dataLoader.fetchOHLCV({ symbol, timeframe, limit: 500 });
      console.log(`Loaded ${historicalData.length} candles\n`);
      
      // Save to shared data dir for Python integration
      const sharedFileLoader = new FileDataLoader('./data/shared');
      await sharedFileLoader.saveOHLCV(historicalData);
      console.log('Saved to ./data/shared for Python integration\n');
      
      await processMarketDataArray(engine, historicalData, 'Binance');
    } catch (error) {
      console.error('Failed to load real data:', error);
      console.log('Falling back to simulated data...\n');
    }
  } else if (fromFile && fileLoader) {
    console.log(`\n--- Loading ${timeframe} data for ${symbol} from shared data ---\n`);
    try {
      const fileData = await fileLoader.fetchOHLCV({ symbol, timeframe });
      console.log(`Loaded ${fileData.length} candles from file\n`);
      await processMarketDataArray(engine, fileData, 'historical');
    } catch (error) {
      console.error('Failed to load historical data:', error);
      console.log('Falling back to simulated data...\n');
    }
  } else {
    console.log('\n--- Simulating Market Data ---\n');
    
    const symbols = ['BTCUSDT', 'ETHUSDT'];
    let basePrice: Record<string, number> = { BTCUSDT: 50000, ETHUSDT: 3000 };
    
    for (let i = 0; i < 100; i++) {
      for (const symbol of symbols) {
        const volatility = symbol === 'BTCUSDT' ? 0.02 : 0.025;
        const change = (Math.random() - 0.5) * 2 * volatility;
        basePrice[symbol] *= (1 + change);
        
        const price = basePrice[symbol];
        const spread = price * 0.0001;
        
        const marketData: MarketData = {
          symbol,
          timestamp: Date.now() + i * 60000,
          open: price * (1 + (Math.random() - 0.5) * 0.001),
          high: price * (1 + Math.random() * 0.005),
          low: price * (1 - Math.random() * 0.005),
          close: price,
          volume: Math.random() * 1000 + 100,
          timeframe: '15m',
        };
        
        await engine.processMarketData(marketData);
      }
      
      if (i % 20 === 0) {
        console.log(`\n--- Step ${i} ---`);
        const status = engine.getSystemStatus();
        console.log(`System: ${status.isHalted ? 'HALTED' : 'RUNNING'} | Mode: ${status.currentMode} | Agents: ${status.activeAgents}/${status.totalAgents}`);
        
        const risk = engine.getRiskMetrics();
        console.log(`Margin: ${(risk.marginRatio * 100).toFixed(1)}% | Drawdown: ${(risk.currentDrawdown * 100).toFixed(2)}% | Open: ${risk.openPositions}`);
      }
      
        await new Promise<void>(r => setTimeout(r, 10));
    }
  }
  
  console.log('\n--- Final Status ---');
  const finalStatus = engine.getSystemStatus();
  console.log(`System: ${finalStatus.isHalted ? 'HALTED' : 'RUNNING'} | Mode: ${finalStatus.currentMode}`);
  
  const positions = engine.getPositions();
  console.log(`Total positions: ${positions.length}`);
  console.log(`Open positions: ${positions.filter(p => p.status === 'open').length}`);
  console.log(`Closed positions: ${positions.filter(p => p.status === 'closed').length}`);
  
  const tradeMaster = engine.getManager().getSubAgent('trade_master_agent') as any;
  if (tradeMaster) {
    const summary = tradeMaster.getPerformanceSummary();
    console.log(`\nPerformance Summary:`);
    console.log(`  Total Trades: ${summary.totalTrades}`);
    console.log(`  Win Rate: ${(summary.winnerRate * 100).toFixed(1)}%`);
    console.log(`  Total PnL: $${summary.totalPnl.toFixed(2)}`);
    console.log(`  Best Agent: ${summary.bestAgent}`);
    console.log(`  Worst Agent: ${summary.worstAgent}`);
  }
  
  await engine.stop();
  console.log('\n=== Demo Complete ===');
}

runDemo().catch(console.error);