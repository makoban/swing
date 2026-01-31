-- シミュレーション設定
CREATE TABLE IF NOT EXISTS sim_config (
    id SERIAL PRIMARY KEY,
    initial_capital NUMERIC DEFAULT 1000000,
    current_balance NUMERIC DEFAULT 1000000,
    leverage INTEGER DEFAULT 25,
    spread_pips NUMERIC DEFAULT 0.4,
    swap_long NUMERIC DEFAULT 18,
    swap_short NUMERIC DEFAULT -22,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初期設定を挿入
INSERT INTO sim_config (initial_capital, current_balance, leverage, spread_pips, swap_long, swap_short)
VALUES (1000000, 1000000, 25, 0.4, 18, -22)
ON CONFLICT DO NOTHING;

-- 仮想ポジション
CREATE TABLE IF NOT EXISTS sim_positions (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(10) NOT NULL,
    entry_price NUMERIC NOT NULL,
    current_price NUMERIC,
    units INTEGER NOT NULL,
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(10) DEFAULT 'OPEN',
    unrealized_pnl NUMERIC DEFAULT 0,
    swap_total NUMERIC DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 取引履歴
CREATE TABLE IF NOT EXISTS sim_trade_history (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(10) NOT NULL,
    entry_price NUMERIC NOT NULL,
    exit_price NUMERIC NOT NULL,
    units INTEGER NOT NULL,
    gross_pnl NUMERIC,
    spread_cost NUMERIC,
    swap_total NUMERIC,
    net_pnl NUMERIC,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 資産推移ログ
CREATE TABLE IF NOT EXISTS sim_equity_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    balance NUMERIC,
    equity NUMERIC,
    unrealized_pnl NUMERIC,
    tnx_value NUMERIC,
    usdjpy_value NUMERIC
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_sim_positions_status ON sim_positions(status);
CREATE INDEX IF NOT EXISTS idx_sim_trade_history_exit_time ON sim_trade_history(exit_time);
CREATE INDEX IF NOT EXISTS idx_sim_equity_log_timestamp ON sim_equity_log(timestamp);
