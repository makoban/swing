import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta
import pytz

# 環境変数からDB接続情報を取得
DB_URL = os.getenv("DB_CONNECTION_STRING")

# 銘柄
TNX = "^TNX"      # 米国10年債利回り
USDJPY = "JPY=X"  # ドル円

# ==========================================
# OANDA証券シミュレーション設定
# ==========================================
SPREAD_PIPS = 0.4       # スプレッド (pips)
SPREAD_YEN = 0.004      # スプレッド (円) = 0.4pips
LEVERAGE = 25           # レバレッジ
SWAP_LONG = 18          # スワップ (買い/1万通貨/日)
SWAP_SHORT = -22        # スワップ (売り/1万通貨/日)

# ==========================================
# リスク管理設定（安全なポジションサイズ計算）
# ==========================================
MAX_RISK_PERCENT = 10   # 最大リスク: 資金の10%
MAX_ADVERSE_MOVE = 3.0  # 想定最大逆行: 3円（300pips）
MIN_UNITS = 10000       # 最小取引単位: 1万通貨
UNIT_STEP = 10000       # 取引単位の刻み: 1万通貨

def calculate_safe_position_size(balance, usdjpy_price):
    """
    安全なポジションサイズを計算（複利対応）

    ルール:
    1. 最大損失を資金の10%に制限
    2. 価格が3円逆行してもロスカットにならないサイズ
    3. 1万通貨単位で丸める
    """
    # 最大許容損失額
    max_loss = balance * (MAX_RISK_PERCENT / 100)

    # 3円の逆行に耐えられる通貨数
    # 損失 = 逆行幅(円) × 通貨数
    # 通貨数 = 最大許容損失 / 逆行幅
    safe_units = max_loss / MAX_ADVERSE_MOVE

    # 1万通貨単位に丸める（切り捨て）
    safe_units = int(safe_units // UNIT_STEP) * UNIT_STEP

    # 最小単位を保証
    safe_units = max(safe_units, MIN_UNITS)

    # レバレッジ制限チェック
    required_margin = (safe_units * usdjpy_price) / LEVERAGE
    if required_margin > balance * 0.8:  # 証拠金使用率80%上限
        safe_units = int((balance * 0.8 * LEVERAGE / usdjpy_price) // UNIT_STEP) * UNIT_STEP
        safe_units = max(safe_units, MIN_UNITS)

    return int(safe_units)

def is_market_open():
    """FX市場が開いているかチェック（月曜7時〜土曜7時 JST）"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    weekday = now.weekday()
    hour = now.hour

    if weekday == 6:  # 日曜
        return False
    if weekday == 5 and hour >= 7:  # 土曜7時以降
        return False
    if weekday == 0 and hour < 7:   # 月曜7時前
        return False
    return True

def get_market_data():
    """金利とドル円の現在値・前日比を取得"""
    try:
        tnx = yf.Ticker(TNX)
        tnx_hist = tnx.history(period="5d")
        if len(tnx_hist) < 2:
            return None, None, None, None

        tnx_current = float(tnx_hist['Close'].iloc[-1])
        tnx_prev = float(tnx_hist['Close'].iloc[-2])
        tnx_change = tnx_current - tnx_prev

        if tnx_change >= 0.01:
            tnx_trend = "UP"
        elif tnx_change <= -0.01:
            tnx_trend = "DOWN"
        else:
            tnx_trend = "NEUTRAL"

        usdjpy = yf.Ticker(USDJPY)
        usdjpy_hist = usdjpy.history(period="1d")
        if len(usdjpy_hist) == 0:
            return None, None, None, None

        usdjpy_current = float(usdjpy_hist['Close'].iloc[-1])

        print(f"📊 市場データ取得完了")
        print(f"   TNX: {tnx_current:.2f}% (前日比: {tnx_change:+.2f}%)")
        print(f"   USD/JPY: {usdjpy_current:.2f}")
        print(f"   トレンド: {tnx_trend}")

        return tnx_trend, usdjpy_current, tnx_current, tnx_change
    except Exception as e:
        print(f"❌ 市場データ取得エラー: {e}")
        return None, None, None, None

def calculate_pnl(direction, entry_price, current_price, units):
    """損益計算（スプレッド込み）"""
    if direction == "BUY":
        # 買いの場合：現在価格 - エントリー価格 - スプレッド
        pnl = (current_price - entry_price - SPREAD_YEN) * units
    else:
        # 売りの場合：エントリー価格 - 現在価格 - スプレッド
        pnl = (entry_price - current_price - SPREAD_YEN) * units
    return pnl

def calculate_swap(direction, units, hours=1):
    """スワップポイント計算（時間単位）"""
    daily_swap = SWAP_LONG if direction == "BUY" else SWAP_SHORT
    # 1万通貨あたりの日次スワップを時間単位に変換
    hourly_swap = (daily_swap / 24) * (units / 10000)
    return hourly_swap * hours

def get_current_position(engine):
    """現在のオープンポジションを取得"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, direction, entry_price, units, entry_time, swap_total
            FROM sim_positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC
            LIMIT 1
        """))
        return result.fetchone()

def get_config(engine):
    """シミュレーション設定を取得"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM sim_config LIMIT 1"))
        return result.fetchone()

def update_balance(engine, amount):
    """残高を更新"""
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE sim_config
            SET current_balance = current_balance + :amount,
                updated_at = :time
        """), {"amount": amount, "time": datetime.now(pytz.UTC)})
        conn.commit()

def check_and_execute():
    """メインロジック"""
    if not DB_URL:
        print("❌ 環境変数 DB_CONNECTION_STRING が設定されていません")
        return

    if not is_market_open():
        print("💤 市場クローズ中 - 処理スキップ")
        return

    engine = create_engine(DB_URL)
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)

    print("=" * 60)
    print("🚀 FX仮想取引シミュレーション")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} JST")
    print("=" * 60)

    # 設定取得
    config = get_config(engine)
    if not config:
        print("❌ sim_config が未設定です")
        return

    current_balance = float(config[2])  # current_balance
    print(f"💰 現在残高: ¥{current_balance:,.0f}")

    # 市場データ取得
    trend, usdjpy_price, tnx_value, tnx_change = get_market_data()
    if trend is None:
        print("❌ 市場データ取得失敗")
        return

    # 現在ポジション確認
    position = get_current_position(engine)

    action = "HOLD"
    detail = ""

    if trend == "NEUTRAL":
        action = "HOLD"
        detail = "金利変動小 - トレード見送り"
        print(f"⏸️ {detail}")

    elif position is None:
        # 新規エントリー
        direction = "BUY" if trend == "UP" else "SELL"
        action = "ENTRY"

        # 安全なポジションサイズを計算（複利対応）
        trade_units = calculate_safe_position_size(current_balance, usdjpy_price)

        # スプレッドコスト計算
        spread_cost = SPREAD_YEN * trade_units

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO sim_positions
                (direction, entry_price, current_price, units, entry_time, status, unrealized_pnl, swap_total)
                VALUES (:direction, :price, :price, :units, :time, 'OPEN', :spread_cost, 0)
            """), {
                "direction": direction,
                "price": usdjpy_price,
                "units": trade_units,
                "time": datetime.now(pytz.UTC),
                "spread_cost": -spread_cost  # スプレッドは初期コスト
            })
            conn.commit()

        # リスク情報を表示
        max_loss = trade_units * MAX_ADVERSE_MOVE
        detail = f"新規{direction} {trade_units:,}通貨 @ {usdjpy_price:.2f}"
        print(f"🟢 {detail}")
        print(f"   📊 最大リスク(3円逆行時): ¥{max_loss:,.0f} | スプレッドコスト: ¥{spread_cost:,.0f}")

    else:
        pos_id, pos_direction, entry_price, units, entry_time, swap_total = position
        entry_price = float(entry_price)
        units = int(units)
        swap_total = float(swap_total) if swap_total else 0

        expected_direction = "BUY" if trend == "UP" else "SELL"

        # スワップポイント加算（毎時）
        hourly_swap = calculate_swap(pos_direction, units)
        new_swap_total = swap_total + hourly_swap

        # 含み損益計算
        unrealized_pnl = calculate_pnl(pos_direction, entry_price, usdjpy_price, units)
        total_pnl = unrealized_pnl + new_swap_total

        if pos_direction == expected_direction:
            # ホールド
            action = "HOLD"

            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sim_positions
                    SET current_price = :price,
                        unrealized_pnl = :pnl,
                        swap_total = :swap,
                        updated_at = :time
                    WHERE id = :id
                """), {
                    "price": usdjpy_price,
                    "pnl": unrealized_pnl,
                    "swap": new_swap_total,
                    "time": datetime.now(pytz.UTC),
                    "id": pos_id
                })
                conn.commit()

            detail = f"継続保有 | 含み損益: ¥{unrealized_pnl:+,.0f} | スワップ累計: ¥{new_swap_total:+,.0f}"
            print(f"📌 {detail}")

        else:
            # 決済 & ドテン
            action = "REVERSE"

            # 最終損益
            net_pnl = unrealized_pnl + new_swap_total
            spread_cost = SPREAD_YEN * units

            with engine.connect() as conn:
                # ポジション決済
                conn.execute(text("""
                    UPDATE sim_positions
                    SET status = 'CLOSED',
                        current_price = :price,
                        unrealized_pnl = :pnl,
                        swap_total = :swap,
                        updated_at = :time
                    WHERE id = :id
                """), {
                    "price": usdjpy_price,
                    "pnl": unrealized_pnl,
                    "swap": new_swap_total,
                    "time": datetime.now(pytz.UTC),
                    "id": pos_id
                })

                # 取引履歴に記録
                conn.execute(text("""
                    INSERT INTO sim_trade_history
                    (direction, entry_price, exit_price, units, gross_pnl, spread_cost, swap_total, net_pnl, entry_time, exit_time)
                    VALUES (:direction, :entry_price, :exit_price, :units, :gross_pnl, :spread_cost, :swap, :net_pnl, :entry_time, :exit_time)
                """), {
                    "direction": pos_direction,
                    "entry_price": entry_price,
                    "exit_price": usdjpy_price,
                    "units": units,
                    "gross_pnl": unrealized_pnl,
                    "spread_cost": spread_cost,
                    "swap": new_swap_total,
                    "net_pnl": net_pnl,
                    "entry_time": entry_time,
                    "exit_time": datetime.now(pytz.UTC)
                })

                # 残高更新
                conn.execute(text("""
                    UPDATE sim_config
                    SET current_balance = current_balance + :pnl,
                        updated_at = :time
                """), {"pnl": net_pnl, "time": datetime.now(pytz.UTC)})

                # 新規ポジション（残高更新後の値で計算）
                new_balance = current_balance + net_pnl
                new_trade_units = calculate_safe_position_size(new_balance, usdjpy_price)
                new_spread_cost = SPREAD_YEN * new_trade_units
                conn.execute(text("""
                    INSERT INTO sim_positions
                    (direction, entry_price, current_price, units, entry_time, status, unrealized_pnl, swap_total)
                    VALUES (:direction, :price, :price, :units, :time, 'OPEN', :spread_cost, 0)
                """), {
                    "direction": expected_direction,
                    "price": usdjpy_price,
                    "units": new_trade_units,
                    "time": datetime.now(pytz.UTC),
                    "spread_cost": -new_spread_cost
                })

                conn.commit()

            detail = f"決済 {pos_direction} P&L: ¥{net_pnl:+,.0f} → 新規 {expected_direction} {new_trade_units:,}通貨"
            print(f"🔄 {detail}")
            print(f"💰 新残高: ¥{new_balance:,.0f}")

    # 資産推移ログ
    with engine.connect() as conn:
        # 最新残高取得
        result = conn.execute(text("SELECT current_balance FROM sim_config LIMIT 1"))
        row = result.fetchone()
        balance = float(row[0]) if row else current_balance

        # オープンポジションの含み損益
        result = conn.execute(text("""
            SELECT COALESCE(SUM(unrealized_pnl + swap_total), 0)
            FROM sim_positions WHERE status = 'OPEN'
        """))
        row = result.fetchone()
        total_unrealized = float(row[0]) if row else 0

        equity = balance + total_unrealized

        conn.execute(text("""
            INSERT INTO sim_equity_log (timestamp, balance, equity, unrealized_pnl, tnx_value, usdjpy_value)
            VALUES (:time, :balance, :equity, :unrealized, :tnx, :usdjpy)
        """), {
            "time": datetime.now(pytz.UTC),
            "balance": balance,
            "equity": equity,
            "unrealized": total_unrealized,
            "tnx": tnx_value,
            "usdjpy": usdjpy_price
        })
        conn.commit()

    print("=" * 60)
    print(f"📊 有効証拠金: ¥{equity:,.0f}")
    print("✅ 処理完了")

if __name__ == "__main__":
    check_and_execute()
