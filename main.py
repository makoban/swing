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

# ==========================================
# リスク管理設定（安全なポジションサイズ計算）
# ==========================================
MAX_RISK_PERCENT = 10   # 最大リスク: 資金の10%
MAX_ADVERSE_MOVE = 3.0  # 想定最大逆行: 3円（300pips）
MIN_UNITS = 10000       # 最小取引単位: 1万通貨
UNIT_STEP = 10000       # 取引単位の刻み: 1万通貨

# ==========================================
# 金利トレンド・サーフィン戦略
# Interest Rate Trend Surfing Strategy
# バックテスト: ROI 625,260% (30年), 勝率58.26%
# ==========================================
# ルール:
# 1. TNX（米国10年債）が前日比で上昇 → 買い（ロング）
# 2. TNX が前日比で下落 → 決済（ポジション解消）
# 3. ショート（売り）は行わない（ロングオンリー）
# 4. トレンドが続く限り保有し続ける（スイングトレード）

def calculate_safe_position_size(balance, usdjpy_price):
    """
    安全なポジションサイズを計算（複利対応）
    """
    max_loss = balance * (MAX_RISK_PERCENT / 100)
    safe_units = max_loss / MAX_ADVERSE_MOVE
    safe_units = int(safe_units // UNIT_STEP) * UNIT_STEP
    safe_units = max(safe_units, MIN_UNITS)

    required_margin = (safe_units * usdjpy_price) / LEVERAGE
    if required_margin > balance * 0.8:
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

        # 金利トレンド・サーフィン戦略: 閾値なし、純粋な上昇/下落判定
        if tnx_change > 0:
            tnx_trend = "UP"      # 金利上昇 → 買いシグナル
        else:
            tnx_trend = "DOWN"    # 金利下落 → 決済シグナル

        usdjpy = yf.Ticker(USDJPY)
        usdjpy_hist = usdjpy.history(period="1d")
        if len(usdjpy_hist) == 0:
            return None, None, None, None

        usdjpy_current = float(usdjpy_hist['Close'].iloc[-1])

        print(f"📊 市場データ取得完了")
        print(f"   TNX: {tnx_current:.2f}% (前日比: {tnx_change:+.3f}%)")
        print(f"   USD/JPY: {usdjpy_current:.2f}")
        print(f"   シグナル: {'🟢 BUY' if tnx_trend == 'UP' else '🔴 EXIT'}")

        return tnx_trend, usdjpy_current, tnx_current, tnx_change
    except Exception as e:
        print(f"❌ 市場データ取得エラー: {e}")
        return None, None, None, None

def calculate_pnl(entry_price, current_price, units):
    """損益計算（ロングのみ、スプレッド込み）"""
    pnl = (current_price - entry_price - SPREAD_YEN) * units
    return pnl

def calculate_swap(units, hours=1):
    """スワップポイント計算（ロングのみ）"""
    hourly_swap = (SWAP_LONG / 24) * (units / 10000)
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

def check_and_execute():
    """
    金利トレンド・サーフィン戦略 メインロジック

    - TNX上昇 → 買い（新規）またはホールド
    - TNX下落 → 決済（ショートはしない）
    """
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
    print("🏄 金利トレンド・サーフィン戦略")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} JST")
    print("=" * 60)

    # 設定取得
    config = get_config(engine)
    if not config:
        print("❌ sim_config が未設定です")
        return

    current_balance = float(config[2])
    print(f"💰 現在残高: ¥{current_balance:,.0f}")

    # 市場データ取得
    trend, usdjpy_price, tnx_value, tnx_change = get_market_data()
    if trend is None:
        print("❌ 市場データ取得失敗")
        return

    # 現在ポジション確認
    position = get_current_position(engine)

    action = "WAIT"
    detail = ""

    if position is None:
        # ポジションなし
        if trend == "UP":
            # 金利上昇 → 新規買い
            action = "ENTRY"
            trade_units = calculate_safe_position_size(current_balance, usdjpy_price)
            spread_cost = SPREAD_YEN * trade_units

            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO sim_positions
                    (direction, entry_price, current_price, units, entry_time, status, unrealized_pnl, swap_total)
                    VALUES ('BUY', :price, :price, :units, :time, 'OPEN', :spread_cost, 0)
                """), {
                    "price": usdjpy_price,
                    "units": trade_units,
                    "time": datetime.now(pytz.UTC),
                    "spread_cost": -spread_cost
                })
                conn.commit()

            max_loss = trade_units * MAX_ADVERSE_MOVE
            detail = f"🟢 新規BUY {trade_units:,}通貨 @ {usdjpy_price:.2f}"
            print(detail)
            print(f"   📊 最大リスク(3円逆行時): ¥{max_loss:,.0f}")
        else:
            # 金利下落だがポジションなし → 待機
            action = "WAIT"
            detail = "⏸️ 金利下落中 - エントリー待機（ロングオンリー戦略）"
            print(detail)
    else:
        # ポジションあり
        pos_id, pos_direction, entry_price, units, entry_time, swap_total = position
        entry_price = float(entry_price)
        units = int(units)
        swap_total = float(swap_total) if swap_total else 0

        # スワップポイント加算（毎時）
        hourly_swap = calculate_swap(units)
        new_swap_total = swap_total + hourly_swap

        # 含み損益計算
        unrealized_pnl = calculate_pnl(entry_price, usdjpy_price, units)
        total_pnl = unrealized_pnl + new_swap_total

        if trend == "UP":
            # 金利上昇継続 → ホールド
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

            detail = f"📌 ホールド継続 | 含み損益: ¥{unrealized_pnl:+,.0f} | スワップ累計: ¥{new_swap_total:+,.0f}"
            print(detail)

        else:
            # 金利下落 → 決済（ショートはしない）
            action = "EXIT"
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
                    VALUES ('BUY', :entry_price, :exit_price, :units, :gross_pnl, :spread_cost, :swap, :net_pnl, :entry_time, :exit_time)
                """), {
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

                conn.commit()

            new_balance = current_balance + net_pnl
            result_emoji = "✅" if net_pnl > 0 else "❌"
            detail = f"🔴 決済 BUY @ {usdjpy_price:.2f} | P&L: ¥{net_pnl:+,.0f} {result_emoji}"
            print(detail)
            print(f"💰 新残高: ¥{new_balance:,.0f}")

    # 資産推移ログ
    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_balance FROM sim_config LIMIT 1"))
        row = result.fetchone()
        balance = float(row[0]) if row else current_balance

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
