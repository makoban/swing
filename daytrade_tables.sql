-- ==========================================
-- デイトレ戦略用テーブル
-- WAIT戦略とは完全に別
-- ==========================================

-- デイトレ設定
CREATE TABLE IF NOT EXISTS sim_daytrade_config (
    id SERIAL PRIMARY KEY,
    initial_capital NUMERIC DEFAULT 1000000,
    current_balance NUMERIC DEFAULT 1000000,
    lot_ratio NUMERIC DEFAULT 0.15,
    take_profit NUMERIC DEFAULT 0.15,
    stop_loss NUMERIC DEFAULT 0.20,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初期設定を挿入
INSERT INTO sim_daytrade_config (initial_capital, current_balance, lot_ratio, take_profit, stop_loss)
VALUES (1000000, 1000000, 0.15, 0.15, 0.20)
ON CONFLICT DO NOTHING;

-- デイトレポジション
CREATE TABLE IF NOT EXISTS sim_daytrade_positions (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(10) NOT NULL,
    entry_price NUMERIC NOT NULL,
    current_price NUMERIC,
    units INTEGER NOT NULL,
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(10) DEFAULT 'OPEN',
    unrealized_pnl NUMERIC DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- デイトレ取引履歴
CREATE TABLE IF NOT EXISTS sim_daytrade_history (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(10) NOT NULL,
    entry_price NUMERIC NOT NULL,
    exit_price NUMERIC NOT NULL,
    units INTEGER NOT NULL,
    pnl NUMERIC,
    action VARCHAR(20),
    exit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- デイトレ資産推移ログ
CREATE TABLE IF NOT EXISTS sim_daytrade_equity_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    balance NUMERIC,
    equity NUMERIC,
    unrealized_pnl NUMERIC,
    usdjpy_value NUMERIC
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_sim_daytrade_positions_status ON sim_daytrade_positions(status);
CREATE INDEX IF NOT EXISTS idx_sim_daytrade_history_exit_time ON sim_daytrade_history(exit_time);
CREATE INDEX IF NOT EXISTS idx_sim_daytrade_equity_log_timestamp ON sim_daytrade_equity_log(timestamp);
