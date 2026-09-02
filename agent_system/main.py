"""
Main entry point for the Trading Agent System.
Initializes and runs all agents.
"""
from __future__ import annotations
import asyncio
import signal
import sys
import os
from decimal import Decimal
from pathlib import Path

# Add project root and parent to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.event_bus import EventBus, event_bus
from core.agent_registry import AgentRegistry, agent_registry
from core.base_agent import AgentConfig
from config import config_loader

# Import all agents
from agents.leverage_adjustment_agent import LeverageAdjustmentAgent
from agents.bias_determining_agent import BiasDeterminingAgent
from agents.multitimeframe_confluence_agent import MultiTimeframeConfluenceAgent
from agents.position_sizing_agent import PositionSizingAgent
from agents.style_managing_agent import StyleManagingAgent
from agents.risk_checking_agent import RiskCheckingAgent
from agents.trade_master_agent import TradeMasterAgent
from agents.manager_agent import ManagerAgent
from agents.timeframe_recommendation_agent import TimeframeRecommendationAgent
from data.delta_exchange_feed import DeltaDataFeedAgent, DeltaConfig, DeltaEnvironment
from data.free_crypto_feed import FreeCryptoFeedAgent, FreeFeedConfig
from data.file_data_feed import FileDataFeedAgent
from data.ingestion import DeltaIngestion, get_event_backbone, get_normalizer
from execution.contracts import (
    PortfolioState,
    RiskLimits,
    adapter_registry,
    Venue,
)
from execution.engine import ExecutionEngine, ExecutionConfig, DefaultRiskOverlay, get_execution_engine
from execution.adapters.delta_adapter import DeltaAdapter
from execution.adapters.mt5_adapter import MT5Adapter, MT5_AVAILABLE
from bridge.python_bridge import PythonBridge, BridgeConfig
import sys
sys.path.append(str(Path(__file__).parent.parent / 'ui'))
from server import start_ui_server


class TradingSystem:
    """Main trading system orchestrator."""
    
    def __init__(self):
        self.event_bus = event_bus
        self.registry = agent_registry
        self.data_feed: DeltaDataFeedAgent = None
        self.delta_ingestion: DeltaIngestion = None
        self.event_backbone = None
        self.execution_engine: ExecutionEngine = None
        self.portfolio_state: PortfolioState = None
        self.bridge: PythonBridge = None
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize all agents and connections."""
        print("Initializing Trading Agent System...")
        
        # Initialize event backbone (Redis Streams)
        print("  Initializing event backbone...")
        self.event_backbone = await get_event_backbone()
        print("  Event backbone connected")
        
        # Initialize canonical normalizer
        print("  Initializing canonical normalizer...")
        get_normalizer()
        print("  Normalizer ready")
        
        # Initialize Delta ingestion service (canonical pipeline)
        print("  Initializing Delta ingestion...")
        data_feed_config = config_loader.get_data_feed_config("delta_exchange")
        self.delta_ingestion = DeltaIngestion(
            api_key=data_feed_config.get("api_key", ""),
            api_secret=data_feed_config.get("api_secret", ""),
            base_url=data_feed_config.get("rest_url", "https://api.india.delta.exchange"),
            ws_url=data_feed_config.get("ws_url", "wss://socket.delta.exchange"),
            symbols=data_feed_config.get("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
            timeframes=data_feed_config.get("timeframes", ["1m", "5m", "15m", "1h", "4h"]),
            event_backbone=self.event_backbone,
        )
        await self.delta_ingestion.initialize()
        print("  Delta ingestion ready")
        
        # Initialize Execution Engine
        print("  Initializing execution engine...")
        trading_config = config_loader.get_trading_config()
        delta_config = config_loader.get_data_feed_config("delta_exchange")
        
        # Create portfolio state with risk limits
        risk_limits = RiskLimits(
            max_portfolio_drawdown=Decimal(str(trading_config.get("max_drawdown", "0.10"))),
            max_daily_loss=Decimal(str(trading_config.get("max_daily_loss", "0.03"))),
            max_position_size_pct=Decimal(str(trading_config.get("max_position_pct", "0.20"))),
            max_leverage=Decimal(str(trading_config.get("max_leverage", "20.0"))),
        )
        
        self.portfolio_state = PortfolioState(
            positions={},
            total_equity=Decimal("0"),
            available_margin=Decimal("0"),
            used_margin=Decimal("0"),
            daily_pnl=Decimal("0"),
            open_orders=[],
            risk_limits=risk_limits,
        )
        
        # Register Delta adapter
        delta_adapter = DeltaAdapter(
            api_key=delta_config.get("api_key", ""),
            api_secret=delta_config.get("api_secret", ""),
            base_url=delta_config.get("rest_url", "https://api.india.delta.exchange"),
            ws_url=delta_config.get("ws_url", "wss://socket.delta.exchange"),
        )
        adapter_registry.register(delta_adapter)
        
        # Register MT5 adapter if available
        if MT5_AVAILABLE:
            mt5_config = config_loader.get_data_feed_config("mt5")
            mt5_adapter = MT5Adapter(
                login=mt5_config.get("login", 0),
                password=mt5_config.get("password", ""),
                server=mt5_config.get("server", ""),
                path=mt5_config.get("path"),
            )
            adapter_registry.register(mt5_adapter)
            print("  MT5 adapter registered")
        
        # Create execution engine
        self.execution_engine = get_execution_engine(
            config=ExecutionConfig(
                default_venue=Venue.DELTA,
                enable_reconciliation=True,
                reconciliation_interval_seconds=30,
            ),
            risk_overlay=DefaultRiskOverlay(risk_limits),
        )
        
        # Initialize execution engine
        await self.execution_engine.initialize(self.portfolio_state)
        print("  Execution engine ready")
        
        # Load configurations
        agent_configs = config_loader.get_all_agent_configs()
        data_feed_config = config_loader.get_data_feed_config("delta_exchange")
        free_crypto_config = config_loader.get_data_feed_config("free_crypto")
        
        # Create agents with configurations
        agents = []
        
        # Leverage Adjustment Agent
        if agent_configs.get("leverage_adjustment", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "LeverageAdjustmentAgent",
                LeverageAdjustmentAgent(AgentConfig(
                    name="LeverageAdjustmentAgent",
                    enabled=True,
                    config=agent_configs["leverage_adjustment"].config
                )),
                []  # No dependencies
            ))
        
        # Bias Determining Agent
        if agent_configs.get("bias_determining", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "BiasDeterminingAgent",
                BiasDeterminingAgent(AgentConfig(
                    name="BiasDeterminingAgent",
                    enabled=True,
                    config=agent_configs["bias_determining"].config
                )),
                []
            ))
        
        # Multi-Timeframe Confluence Agent
        if agent_configs.get("multitimeframe_confluence", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "MultiTimeframeConfluenceAgent",
                MultiTimeframeConfluenceAgent(AgentConfig(
                    name="MultiTimeframeConfluenceAgent",
                    enabled=True,
                    config=agent_configs["multitimeframe_confluence"].config
                )),
                ["BiasDeterminingAgent"]  # Depends on bias signals
            ))
        
        # Position Sizing Agent
        if agent_configs.get("position_sizing", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "PositionSizingAgent",
                PositionSizingAgent(AgentConfig(
                    name="PositionSizingAgent",
                    enabled=True,
                    config=agent_configs["position_sizing"].config
                )),
                ["MultiTimeframeConfluenceAgent", "BiasDeterminingAgent", "LeverageAdjustmentAgent"]
            ))
        
        # Style Managing Agent
        if agent_configs.get("style_managing", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "StyleManagingAgent",
                StyleManagingAgent(AgentConfig(
                    name="StyleManagingAgent",
                    enabled=True,
                    config=agent_configs["style_managing"].config
                )),
                ["BiasDeterminingAgent", "MultiTimeframeConfluenceAgent"]
            ))
        
        # Risk Checking Agent
        if agent_configs.get("risk_checking", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "RiskCheckingAgent",
                RiskCheckingAgent(AgentConfig(
                    name="RiskCheckingAgent",
                    enabled=True,
                    config=agent_configs["risk_checking"].config
                )),
                ["PositionSizingAgent", "LeverageAdjustmentAgent"]
            ))
        
        # Trade Master Agent
        if agent_configs.get("trade_master", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "TradeMasterAgent",
                TradeMasterAgent(AgentConfig(
                    name="TradeMasterAgent",
                    enabled=True,
                    config=agent_configs["trade_master"].config
                )),
                ["PositionSizingAgent", "RiskCheckingAgent", "StyleManagingAgent"]
            ))
        
        # Timeframe Recommendation Agent (aggregates all upstream signals)
        agents.append((
            "TimeframeRecommendationAgent",
            TimeframeRecommendationAgent(AgentConfig(
                name="TimeframeRecommendationAgent",
                enabled=True,
                config={
                    "recommendation": {
                        "available_timeframes": ["1m", "5m", "15m", "1h", "4h"],
                        "preferred_timeframes": ["15m", "1h"],
                        "min_confidence": 0.55,
                        "confluence_weight": 0.35,
                        "bias_weight": 0.30,
                        "risk_weight": 0.20,
                        "mode_weight": 0.15,
                    }
                }
            )),
            ["BiasDeterminingAgent", "MultiTimeframeConfluenceAgent", "StyleManagingAgent", "RiskCheckingAgent"]
        ))
        
        # Manager Agent (orchestrator)
        if agent_configs.get("manager", AgentConfig(name="", enabled=False)).enabled:
            agents.append((
                "ManagerAgent",
                ManagerAgent(AgentConfig(
                    name="ManagerAgent",
                    enabled=True,
                    config=agent_configs["manager"].config
                ), registry=self.registry),
                ["TradeMasterAgent", "RiskCheckingAgent", "StyleManagingAgent"]
            ))
        
        # Register all agents with dependencies
        for name, agent, deps in agents:
            self.registry.register(agent, dependencies=deps)
            print(f"  Registered: {name}")
        
        # Initialize all agents
        await self.registry.initialize_all()
        print("All agents initialized")
        
        # NOTE: Data feed start moved to start() so agents are subscribed first
        feed_mode = os.environ.get("DATA_FEED", "file")
        feed_type = data_feed_config.get("type", "free_crypto")
        
        if feed_mode == "delta":
            delta_config = DeltaConfig(
                api_key=data_feed_config.get("api_key", ""),
                api_secret=data_feed_config.get("api_secret", ""),
                environment=DeltaEnvironment(data_feed_config.get("environment", "production")),
                ws_url=data_feed_config.get("ws_url", "wss://socket.delta.exchange"),
                rest_url=data_feed_config.get("rest_url", "https://api.india.delta.exchange"),
            )
            self.data_feed = DeltaDataFeedAgent(delta_config, self.event_bus)
            symbols = trading_config.get("symbols", ["BTCUSDT", "ETHUSDT"])
        elif feed_mode == "live" and feed_type == "free_crypto":
            free_config = FreeFeedConfig(
                exchange=free_crypto_config.get("exchange", "binance"),
                symbols=free_crypto_config.get("symbols", ["BTC/USDT", "ETH/USDT"]),
                timeframes=free_crypto_config.get("timeframes", ["1m", "5m", "15m"]),
                cache_dir=free_crypto_config.get("cache_dir", "data/cache"),
                rate_limit=free_crypto_config.get("rate_limit", True),
            )
            self.data_feed = FreeCryptoFeedAgent(free_config, self.event_bus)
        else:
            # File-based feed - reads aggregated historical data
            shared_dir = str(Path(__file__).parent.parent / "data" / "shared")
            self.data_feed = FileDataFeedAgent(
                data_dir=shared_dir,
                event_bus=self.event_bus,
                symbols=trading_config.get("file_symbols", ["SOLUSDT", "XAUTUSDT"]),
                timeframes=trading_config.get("file_timeframes", ["15m", "1h"]),
                replay_speed=0.0  # Fastest replay
            )
        
        # Start bridge server for TypeScript integration
        bridge_config = BridgeConfig(
            host="127.0.0.1",
            port=8088,
            shared_data_dir="./data/shared"
        )
        self.bridge = PythonBridge(bridge_config, self.event_bus)
        await self.bridge.start()
        
        # Start admin UI server
        self._ui_runner = await start_ui_server(port=3000)
        
        self._running = True
    
    async def start(self) -> None:
        """Start all agents, then start data feed and ingestion."""
        print("Starting all agents...")
        await self.registry.start_all()
        print("All agents started")
        
        # Start execution engine
        if self.execution_engine:
            await self.execution_engine.start()
            print("Execution engine started")
        
        # Start Delta ingestion pipeline (canonical data pipeline)
        if self.delta_ingestion:
            await self.delta_ingestion.start()
            print("Delta ingestion pipeline started")
        
        # Start data feed AFTER agents are subscribed
        if self.data_feed:
            if isinstance(self.data_feed, DeltaDataFeedAgent):
                symbols = self.data_feed._symbols or ["BTCUSDT", "ETHUSDT"]
                await self.data_feed.start(symbols)
                print(f"Delta Exchange feed started for symbols: {symbols}")
            else:
                await self.data_feed.start()
                print(f"{type(self.data_feed).__name__} started")
    
    async def stop(self) -> None:
        """Stop all agents gracefully."""
        print("Stopping Trading Agent System...")
        self._running = False
        
        # Stop execution engine
        if self.execution_engine:
            await self.execution_engine.stop()
            print("Execution engine stopped")
        
        # Stop Delta ingestion pipeline
        if self.delta_ingestion:
            await self.delta_ingestion.stop()
            print("Delta ingestion pipeline stopped")
        
        # Stop event backbone
        if self.event_backbone:
            await self.event_backbone.disconnect()
            print("Event backbone disconnected")
        
        # Stop data feed
        if self.data_feed:
            await self.data_feed.stop()
        
        # Stop all agents
        await self.registry.stop_all()
        
        # Stop UI server
        if hasattr(self, '_ui_runner') and self._ui_runner:
            await self._ui_runner.cleanup()
        
        self._shutdown_event.set()
        print("System stopped")
    
    async def run(self) -> None:
        """Run the system until shutdown."""
        await self.initialize()
        await self.start()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        await self.stop()


async def main():
    """Main entry point."""
    system = TradingSystem()
    
    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        print("\nShutdown signal received")
        asyncio.create_task(system.stop())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        await system.run()
    except KeyboardInterrupt:
        await system.stop()
    except Exception as e:
        print(f"System error: {e}")
        await system.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())