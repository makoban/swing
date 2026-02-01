"""
FX Day Trading Strategy - Main Script
金利サーフィン・デイトレード版

WAIT戦略とは完全に別のシステム
予算: 100万円

最適パラメータ:
- 利確: +0.15円
- 損切: -0.20円
- LOT: 残高の15%
- 取引時間: 10:00-18:00 JST
- 18:00に強制決済（持ち越しなし）
"""
import os
import yfinance as yf
from datetime import datetime
import pytz
from sqlalchemy import create_engine, text

# ==========================================
# バージョン情報
# ==========================================
VERSION = "1.0.0"  # デイトレ版初期リリース

# 戦略名
STRATEGY = "Day Trade Scalping"

# ==========================================
# 取引設定（最適化済み）
# ==========================================
TAKE_PROFIT = 0.15    # 利確: +0.15円
STOP_LOSS = 0.20      # 損切: -0.20円
LOT_RATIO = 0.15      # 複利: 残高の15%

# 取引時間（JST）
TRADE_START_HOUR = 10  # 10:00 JST
TRADE_END_HOUR = 18    # 18:00 JST（強制決済）

# OANDAシミュレーション設定
SPREAD = 0.004        # 0.4pips = 0.004円
INITIAL_CAPITAL = 1_000_000  # 100万円（WAIT戦略とは別予算）

# シンボル
TNX = "^TNX"
USDJPY = "JPY=X"

# ==========================================
# データベース接続
# ==========================================
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
engine = create_engine(DATABASE_URL) if DATABASE_URL else None

# ==========================================
# 複利ロット計算
# ==========================================
def calculate_lot(balance):
    """残高の15%をロットに（複利）"""
    raw_lot = balance * LOT_RATIO
    lot = int(raw_lot // 10000) * 10000
    return max(lot, 10000)

# ==========================================
# トレンド判定
# ==========================================
def get_trend():
    """
    5時間のトレンド判定
    - 上昇トレンド: +0.02円以上上昇
    """
    try:
        usdjpy = yf.Ticker(USDJPY)
        hist = usdjpy.history(period="1d", interval="1h")
        if len(hist) < 6:
            return None, None

        current = float(hist['Close'].iloc[-1])
        past = float(hist['Close'].iloc[-6])

        trend = "UP" if current > past + 0.02 else "DOWN"

        return trend, current
    except Exception as e:
        print(f"Error getting trend: {e}")
        return None, None

# ==========================================
# 現在時刻チェック
# ==========================================
def is_trading_hours():
    """取引時間内かチェック（10:00-18:00 JST）"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    return TRADE_START_HOUR <= now.hour < TRADE_END_HOUR

def is_force_close_time():
    """強制決済時刻かチェック（18:00 JST以降）"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    return now.hour >= TRADE_END_HOUR

# ==========================================
# メイン実行関数
# ==========================================
def check_and_execute():
    """メイン実行ロジック"""
    print("=" * 50)
    print(f"Day Trade Strategy v{VERSION}")
    print(f"Time: {datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 50)

    if not engine:
        print("DATABASE_URL not set")
        return

    # 現在のポジション取得
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, direction, entry_price, units
            FROM sim_daytrade_positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC LIMIT 1
        """))
        position = result.fetchone()

        # 残高取得
        result = conn.execute(text("""
            SELECT current_balance FROM sim_daytrade_config LIMIT 1
        """))
        config = result.fetchone()
        current_balance = float(config[0]) if config else INITIAL_CAPITAL

    # トレンドと価格取得
    trend, usdjpy_price = get_trend()
    if trend is None or usdjpy_price is None:
        print("Failed to get market data")
        return

    print(f"USD/JPY: {usdjpy_price:.2f}")
    print(f"Trend: {trend}")
    print(f"Balance: ¥{current_balance:,.0f}")

    # ポジションなしの場合
    if position is None:
        if not is_trading_hours():
            print("Outside trading hours (10:00-18:00 JST)")
            return

        if trend == "UP":
            # 新規エントリー
            trade_units = calculate_lot(current_balance)
            entry_price = usdjpy_price + SPREAD

            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO sim_daytrade_positions
                    (direction, entry_price, current_price, units, entry_time, status, unrealized_pnl)
                    VALUES ('BUY', :price, :price, :units, :time, 'OPEN', :spread)
                """), {
                    "price": entry_price,
                    "units": trade_units,
                    "time": datetime.now(pytz.UTC),
                    "spread": -SPREAD * trade_units
                })
                conn.commit()

            print(f"ENTRY: BUY {trade_units:,} units @ {entry_price:.2f}")
            print(f"Take Profit: {entry_price + TAKE_PROFIT:.2f}")
            print(f"Stop Loss: {entry_price - STOP_LOSS:.2f}")
        else:
            print("Trend is DOWN - waiting")

    # ポジションありの場合
    else:
        pos_id = position[0]
        entry_price = float(position[2])
        units = int(position[3])

        pnl = usdjpy_price - entry_price
        pnl_jpy = pnl * units

        action = None

        # 強制決済時刻チェック
        if is_force_close_time():
            action = "FORCE_CLOSE"
            print(f"FORCE CLOSE at 18:00 JST")
        # 利確チェック
        elif pnl >= TAKE_PROFIT:
            action = "TAKE_PROFIT"
            print(f"TAKE PROFIT: +{pnl:.3f} yen")
        # 損切チェック
        elif pnl <= -STOP_LOSS:
            action = "STOP_LOSS"
            print(f"STOP LOSS: {pnl:.3f} yen")
        else:
            # ホールド継続
            print(f"HOLDING: P&L = ¥{pnl_jpy:+,.0f}")
            print(f"  Entry: {entry_price:.2f} | Current: {usdjpy_price:.2f}")

            # ポジション更新
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sim_daytrade_positions
                    SET current_price = :price, unrealized_pnl = :pnl
                    WHERE id = :id
                """), {"price": usdjpy_price, "pnl": pnl_jpy, "id": pos_id})
                conn.commit()

        # 決済処理
        if action:
            new_balance = current_balance + pnl_jpy

            with engine.connect() as conn:
                # ポジションをクローズ
                conn.execute(text("""
                    UPDATE sim_daytrade_positions
                    SET status = 'CLOSED', current_price = :price, unrealized_pnl = :pnl
                    WHERE id = :id
                """), {"price": usdjpy_price, "pnl": pnl_jpy, "id": pos_id})

                # 残高更新
                conn.execute(text("""
                    UPDATE sim_daytrade_config SET current_balance = :balance
                """), {"balance": new_balance})

                # 取引履歴記録
                conn.execute(text("""
                    INSERT INTO sim_daytrade_history
                    (direction, entry_price, exit_price, units, pnl, action, exit_time)
                    VALUES ('BUY', :entry, :exit, :units, :pnl, :action, :time)
                """), {
                    "entry": entry_price,
                    "exit": usdjpy_price,
                    "units": units,
                    "pnl": pnl_jpy,
                    "action": action,
                    "time": datetime.now(pytz.UTC)
                })

                conn.commit()

            print(f"CLOSED: P&L = ¥{pnl_jpy:+,.0f}")
            print(f"New Balance: ¥{new_balance:,.0f}")

# ==========================================
# エントリーポイント
# ==========================================
if __name__ == "__main__":
    print(f"FX Day Trade Strategy v{VERSION}")
    print(f"Settings: TP={TAKE_PROFIT} SL={STOP_LOSS} LOT={LOT_RATIO*100:.0f}%")
    check_and_execute()
