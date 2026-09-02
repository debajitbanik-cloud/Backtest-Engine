-- PostgreSQL initialization script for trading system
-- Run on first container startup

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS execution;
CREATE SCHEMA IF NOT EXISTS intelligence;

-- Set search path
ALTER DATABASE trading SET search_path = trading, analytics, execution, intelligence, public;

-- Trading schema tables
CREATE TABLE IF NOT EXISTS trading.strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    parameters JSONB NOT NULL DEFAULT '{}',
    tags JSONB NOT NULL DEFAULT '[]',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS trading.strategy_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES trading.strategies(id) ON DELETE CASCADE,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(20) NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    metrics JSONB NOT NULL,
    trades_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_performance_strategy
ON trading.strategy_performance (strategy_id);

CREATE INDEX IF NOT EXISTS idx_strategy_performance_symbol_timeframe
ON trading.strategy_performance (symbol, timeframe);

-- Analytics schema tables
CREATE TABLE IF NOT EXISTS analytics.features (
    name VARCHAR(255) PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    formula TEXT NOT NULL,
    source_data JSONB NOT NULL DEFAULT '[]',
    lookback INTEGER NOT NULL,
    normalization VARCHAR(50) NOT NULL DEFAULT 'none',
    normalization_params JSONB NOT NULL DEFAULT '{}',
    availability_timestamp VARCHAR(50) NOT NULL DEFAULT 'close',
    description TEXT DEFAULT '',
    tags JSONB NOT NULL DEFAULT '[]',
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    fingerprint VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analytics.feature_lineage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_id VARCHAR(255) NOT NULL,
    feature_set_id VARCHAR(255) NOT NULL,
    feature_fingerprints JSONB NOT NULL,
    dataset_snapshot_id VARCHAR(255) NOT NULL,
    raw_source_hashes JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Execution schema tables
CREATE TABLE IF NOT EXISTS execution.orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_order_id VARCHAR(255),
    strategy_id VARCHAR(255) NOT NULL,
    instrument_symbol VARCHAR(50) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8),
    stop_price NUMERIC(20, 8),
    time_in_force VARCHAR(10) NOT NULL DEFAULT 'GTC',
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    filled_quantity NUMERIC(20, 8) DEFAULT 0,
    average_fill_price NUMERIC(20, 8),
    commission NUMERIC(20, 8) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS execution.fills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES execution.orders(id),
    strategy_id VARCHAR(255) NOT NULL,
    instrument_symbol VARCHAR(50) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    commission NUMERIC(20, 8) DEFAULT 0,
    commission_currency VARCHAR(10) DEFAULT 'USDT',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'FILLED',
    liquidity VARCHAR(20),
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS execution.positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id VARCHAR(255) NOT NULL,
    instrument_symbol VARCHAR(50) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    entry_price NUMERIC(20, 8) NOT NULL,
    current_price NUMERIC(20, 8),
    unrealized_pnl NUMERIC(20, 8) DEFAULT 0,
    realized_pnl NUMERIC(20, 8) DEFAULT 0,
    margin_used NUMERIC(20, 8) DEFAULT 0,
    leverage NUMERIC(10, 4) DEFAULT 1,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Intelligence schema tables
CREATE TABLE IF NOT EXISTS intelligence.agent_policies (
    name VARCHAR(100) PRIMARY KEY,
    allowed_tools JSONB NOT NULL DEFAULT '[]',
    allowed_venues JSONB NOT NULL DEFAULT '[]',
    requires_approval JSONB NOT NULL DEFAULT '[]',
    max_position_pct NUMERIC(5, 4) DEFAULT 0.10,
    max_daily_trades INTEGER DEFAULT 50,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intelligence.execution_intents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id UUID NOT NULL,
    strategy_id VARCHAR(255) NOT NULL,
    instrument_symbol VARCHAR(50) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    order_json JSONB NOT NULL,
    risk_checks_passed BOOLEAN DEFAULT FALSE,
    risk_notes JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_strategies_updated_at
    BEFORE UPDATE ON trading.strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON execution.orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON execution.positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA trading TO trader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics TO trader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA execution TO trader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA intelligence TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA trading TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA analytics TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA execution TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA intelligence TO trader;

-- Insert default agent policies
INSERT INTO intelligence.agent_policies (name, allowed_tools, allowed_venues, requires_approval, max_position_pct, max_daily_trades)
VALUES
    ('market_research', '["fetch_market_data", "compute_features", "detect_regime"]', '[]', '[]', 0.00, 0),
    ('feature_research', '["register_feature", "compute_features", "check_leakage"]', '[]', '[]', 0.00, 0),
    ('strategy', '["backtest_strategy", "optimize_parameters", "register_strategy"]', '[]', '["deploy_strategy"]', 0.10, 50),
    ('validation', '["run_wfo", "run_cpcv", "run_monte_carlo", "evaluate_gates"]', '[]', '[]', 0.00, 0),
    ('risk', '["evaluate_signal", "evaluate_intent", "check_limits", "kill_switch"]', '[]', '["override_risk"]', 0.00, 0),
    ('report', '["generate_report", "export_data", "create_dashboard"]', '[]', '[]', 0.00, 0)
ON CONFLICT (name) DO NOTHING;