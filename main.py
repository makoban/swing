import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta
import pytz

# 環境変数からDB接続情報を取得
DB_URL = os.getenv("DB_CONNECTION_STRING")

# ==========================================
# 🏄 金利トレンド・サーフィン戦略
# Version: 1.0.0
# ==========================================

# 銘柄
TNX = "^TNX"      # 米国10年債利回り
USDJPY = "JPY=X"  # ドル円

VERSION = "1.3.0"  # WAIT戦略 + デイトレ戦略統合バッチ

# ==========================================
# OANDA Japan シミュレーション設定
# ==========================================
# 予算: 100万円
# レバレッジ: 25倍
# ポジション: 残高の2%を通貨数に（複利対応）
#
# 🔬 バックテスト検証結果 (1996-2026, 30年間):
# - 60,000通貨: ❌ 資金ショート（リーマンショック等で死亡）
# - 25,000通貨: ⚠️ ギリギリ生存（最低残高31万円）
# - 20,000通貨: ✅ 安全圏（最低残高45万円、利益+57万円）
# ==========================================
INITIAL_CAPITAL = 1_000_000  # 初期資金: 100万円
SPREAD_PIPS = 0.4            # スプレッド: 0.4pips (原則固定)
SPREAD_YEN = 0.004           # スプレッド (円換算)
LEVERAGE = 25                # レバレッジ: 25倍
SWAP_LONG = 100              # スワップ: +100円/1万通貨/日 (金利差4%想定)

# 複利設定（残高に応じたロット計算）
LOT_RATIO = 0.02             # 残高の2%を通貨数に
MIN_UNITS = 10000            # 最小: 1万通貨
MAX_UNITS = 100000           # 最大: 10万通貨（リスク上限）

def calculate_lot(balance):
    """
    複利対応: 残高に応じた安全なロット数を計算

    例:
    - 100万円 → 20,000通貨
    - 150万円 → 30,000通貨
    - 200万円 → 40,000通貨
    """
    raw_lot = balance * LOT_RATIO
    lot = int(raw_lot // 10000) * 10000  # 1万通貨単位に丸め
    lot = max(lot, MIN_UNITS)  # 最低1万通貨
    lot = min(lot, MAX_UNITS)  # 最大10万通貨（リスク制限）
    return lot

# ==========================================
# 金利トレンド・サーフィン戦略 (ロング専用版)
# Interest Rate Trend Surfing Strategy
# バックテスト: ROI 625,260% (30年), 勝率58.26%
# ==========================================
# アクション表:
# 持ってない + 金利上昇 → 新規買い (ENTRY)
# 持ってない + 金利下落 → 何もしない (WAIT)
# 持っている + 金利上昇 → 持ち続ける (HOLD)
# 持っている + 金利下落 → 全決済 (EXIT)
# ==========================================

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
    """
    金利とドル円の現在値・前日比を取得

    【Ver 1.1.0 新機能】20日移動平均フィルター
    - TNX > 20日MA → 上昇トレンド → エントリー可
    - TNX < 20日MA → 下降トレンド → エントリー禁止
    """
    try:
        tnx = yf.Ticker(TNX)
        tnx_hist = tnx.history(period="30d")  # 20日MA計算のため30日取得
        if len(tnx_hist) < 21:
            return None, None, None, None, False

        tnx_current = float(tnx_hist['Close'].iloc[-1])
        tnx_prev = float(tnx_hist['Close'].iloc[-2])
        tnx_change = tnx_current - tnx_prev

        # 20日移動平均を計算
        ma20 = float(tnx_hist['Close'].rolling(window=20).mean().iloc[-1])

        # トレンドフィルター: TNX > 20日MA
        trend_ok = tnx_current > ma20

        # 日次シグナル判定
        if tnx_change > 0:
            daily_signal = "UP"
        else:
            daily_signal = "DOWN"

        usdjpy = yf.Ticker(USDJPY)
        usdjpy_hist = usdjpy.history(period="1d")
        if len(usdjpy_hist) == 0:
            return None, None, None, None, False

        usdjpy_current = float(usdjpy_hist['Close'].iloc[-1])

        print(f"📊 市場データ取得完了")
        print(f"   TNX: {tnx_current:.2f}% (前日比: {tnx_change:+.3f}%)")
        print(f"   20日MA: {ma20:.2f}% | トレンド: {'📈 上昇' if trend_ok else '📉 下降'}")
        print(f"   USD/JPY: {usdjpy_current:.2f}")

        # 最終シグナル判定
        if daily_signal == "UP" and trend_ok:
            print(f"   シグナル: 🟢 BUY (日次UP + トレンドOK)")
        elif daily_signal == "UP" and not trend_ok:
            print(f"   シグナル: ⏸️ WAIT (日次UPだがトレンドNG)")
        else:
            print(f"   シグナル: 🔴 EXIT/WAIT")

        return daily_signal, usdjpy_current, tnx_current, tnx_change, trend_ok
    except Exception as e:
        print(f"❌ 市場データ取得エラー: {e}")
        return None, None, None, None, False

def calculate_pnl(entry_price, current_price, units):
    """損益計算（ロングのみ、スプレッド込み）"""
    pnl = (current_price - entry_price - SPREAD_YEN) * units
    return pnl

def calculate_swap(units, hours=1):
    """スワップポイント計算（ロングのみ）

    OANDA Japan: +100円/1万通貨/日
    時間単位に変換: 100円 ÷ 24時間 = 約4.17円/時間/1万通貨
    """
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
    金利トレンド・サーフィン戦略 メインロジック (ロング専用版)

    アクション表:
    - 持ってない + 金利上昇 → 新規買い (ENTRY)
    - 持ってない + 金利下落 → 何もしない (WAIT)
    - 持っている + 金利上昇 → 持ち続ける (HOLD)
    - 持っている + 金利下落 → 全決済 (EXIT)
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
    print("🏄 金利トレンド・サーフィン戦略 (ロング専用)")
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
    daily_signal, usdjpy_price, tnx_value, tnx_change, trend_ok = get_market_data()
    if daily_signal is None:
        print("❌ 市場データ取得失敗")
        return

    # 複利ロット計算
    current_lot = calculate_lot(current_balance)
    required_margin = (current_lot * usdjpy_price) / LEVERAGE
    margin_rate = (current_balance / required_margin) * 100
    print(f"📋 複利ロット: {current_lot:,}通貨 | 必要証拠金: ¥{required_margin:,.0f} (維持率: {margin_rate:.1f}%)")

    # 現在ポジション確認
    position = get_current_position(engine)

    action = "WAIT"
    detail = ""

    if position is None:
        # ====================================
        # ポジションなしの場合
        # ====================================
        # 【Ver 1.1.0】20日MAフィルター: 日次UP + トレンドOK の両方が必要
        if daily_signal == "UP" and trend_ok:
            # 金利上昇 + 上昇トレンド → 新規買い (ENTRY)
            action = "ENTRY"

            # ★ 複利: 現在の残高からロット数を計算
            trade_units = calculate_lot(current_balance)
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

            detail = f"🟢 新規BUY {trade_units:,}通貨 @ {usdjpy_price:.2f}"
            print(detail)
            print(f"   📊 スプレッドコスト: ¥{spread_cost:,.0f} | 複利: 残高×{LOT_RATIO*100:.0f}%")
        elif daily_signal == "UP" and not trend_ok:
            # 金利上昇だがトレンドNG → 待機
            action = "WAIT"
            detail = "⏸️ 日次UP だがトレンドNG (TNX < 20日MA) - エントリー見送り"
            print(detail)
        else:
            # 金利下落 → 何もしない (WAIT)
            action = "WAIT"
            detail = "⏸️ 金利下落中 - エントリー待機"
            print(detail)
    else:
        # ====================================
        # ポジション保有中の場合
        # ====================================
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

        if daily_signal == "UP":
            # 金利上昇継続 → 持ち続ける (HOLD)
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
            # 金利下落 → 全決済 (EXIT)
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
            detail = f"🔴 全決済 @ {usdjpy_price:.2f} | P&L: ¥{net_pnl:+,.0f} {result_emoji}"
            print(detail)
            print(f"💰 新残高: ¥{new_balance:,.0f}")
            print("   📝 現金で休んで次のチャンスを待つ")

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
    print("✅ WAIT戦略 処理完了")

# ==========================================
# ⚡ デイトレ戦略 (10:00-18:00 JST)
# Ver 1.3.0 新機能
# ==========================================
# 設定:
# - 利確: +0.15円
# - 損切: -0.20円
# - LOT: 残高の15%（複利）
# - 強制決済: 18:00 JST
# ==========================================

DAYTRADE_TP = 0.15      # 利確: +0.15円
DAYTRADE_SL = 0.20      # 損切: -0.20円
DAYTRADE_LOT_RATIO = 0.15  # 複利: 残高の15%
DAYTRADE_START_HOUR = 10   # 取引開始: 10:00 JST
DAYTRADE_END_HOUR = 18     # 取引終了/強制決済: 18:00 JST

def calculate_daytrade_lot(balance):
    """デイトレ用ロット計算（15%）"""
    raw_lot = balance * DAYTRADE_LOT_RATIO
    lot = int(raw_lot // 10000) * 10000
    return max(lot, 10000)

def is_daytrade_hours():
    """デイトレ取引時間内かチェック（10:00-18:00 JST）"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    return DAYTRADE_START_HOUR <= now.hour < DAYTRADE_END_HOUR

def is_force_close_time():
    """強制決済時刻かチェック（18:00 JST以降）"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    return now.hour >= DAYTRADE_END_HOUR

def get_daytrade_trend(usdjpy_price, engine):
    """デイトレ用トレンド判定（5時間の価格変動）"""
    try:
        usdjpy = yf.Ticker(USDJPY)
        hist = usdjpy.history(period="1d", interval="1h")
        if len(hist) < 6:
            return None

        current = float(hist['Close'].iloc[-1])
        past = float(hist['Close'].iloc[-6])

        return "UP" if current > past + 0.02 else "DOWN"
    except:
        return None

def check_daytrade():
    """
    デイトレ戦略 メインロジック

    - 10:00-18:00 JST のみ取引
    - 利確: +0.15円、損切: -0.20円
    - 18:00 に強制決済
    """
    if not DB_URL:
        return

    if not is_market_open():
        return

    engine = create_engine(DB_URL)
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)

    print()
    print("=" * 60)
    print("⚡ デイトレ戦略 (Day Trade)")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} JST")
    print("=" * 60)

    # 設定取得
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT initial_capital, current_balance, take_profit, stop_loss
            FROM sim_daytrade_config LIMIT 1
        """))
        config = result.fetchone()

        if not config:
            print("⚠️ デイトレ設定なし - スキップ")
            return

        initial_capital = float(config[0])
        current_balance = float(config[1])

        # ポジション確認
        result = conn.execute(text("""
            SELECT id, entry_price, units, unrealized_pnl
            FROM sim_daytrade_positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC LIMIT 1
        """))
        position = result.fetchone()

    # 現在価格取得
    try:
        usdjpy = yf.Ticker(USDJPY)
        usdjpy_hist = usdjpy.history(period="1d")
        usdjpy_price = float(usdjpy_hist['Close'].iloc[-1])
    except:
        print("❌ 価格取得エラー")
        return

    print(f"💰 残高: ¥{current_balance:,.0f}")
    print(f"💹 USD/JPY: {usdjpy_price:.2f}")

    # ポジションなしの場合
    if position is None:
        if not is_daytrade_hours():
            print(f"⏰ 取引時間外 ({DAYTRADE_START_HOUR}:00-{DAYTRADE_END_HOUR}:00 JST)")
            return

        trend = get_daytrade_trend(usdjpy_price, engine)
        print(f"📈 トレンド: {trend}")

        if trend == "UP":
            # 新規エントリー
            trade_units = calculate_daytrade_lot(current_balance)
            entry_price = usdjpy_price + SPREAD_YEN

            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO sim_daytrade_positions
                    (direction, entry_price, current_price, units, entry_time, status, unrealized_pnl)
                    VALUES ('BUY', :price, :price, :units, :time, 'OPEN', :spread)
                """), {
                    "price": entry_price,
                    "units": trade_units,
                    "time": datetime.now(pytz.UTC),
                    "spread": -SPREAD_YEN * trade_units
                })
                conn.commit()

            print(f"🟢 ENTRY: BUY {trade_units:,} @ {entry_price:.2f}")
            print(f"   利確: {entry_price + DAYTRADE_TP:.2f} | 損切: {entry_price - DAYTRADE_SL:.2f}")
        else:
            print("⏸️ WAIT - トレンドDOWN")

    # ポジションありの場合
    else:
        pos_id = position[0]
        entry_price = float(position[1])
        units = int(position[2])

        pnl = usdjpy_price - entry_price
        pnl_jpy = pnl * units

        print(f"📍 ポジション: {units:,} @ {entry_price:.2f}")
        print(f"   現在損益: ¥{pnl_jpy:+,.0f}")

        action = None
        action_reason = ""

        # 強制決済チェック
        if is_force_close_time():
            action = "FORCE_CLOSE"
            action_reason = "18:00 強制決済"
        # 利確チェック
        elif pnl >= DAYTRADE_TP:
            action = "TAKE_PROFIT"
            action_reason = f"利確 +{pnl:.3f}円"
        # 損切チェック
        elif pnl <= -DAYTRADE_SL:
            action = "STOP_LOSS"
            action_reason = f"損切 {pnl:.3f}円"

        if action:
            new_balance = current_balance + pnl_jpy

            with engine.connect() as conn:
                # ポジションクローズ
                conn.execute(text("""
                    UPDATE sim_daytrade_positions
                    SET status = 'CLOSED', current_price = :price, unrealized_pnl = :pnl
                    WHERE id = :id
                """), {"price": usdjpy_price, "pnl": pnl_jpy, "id": pos_id})

                # 残高更新
                conn.execute(text("""
                    UPDATE sim_daytrade_config SET current_balance = :balance
                """), {"balance": new_balance})

                # 履歴記録
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

            emoji = "✅" if pnl_jpy > 0 else "❌"
            print(f"{emoji} {action_reason} | P&L: ¥{pnl_jpy:+,.0f}")
            print(f"💰 新残高: ¥{new_balance:,.0f}")
        else:
            # ポジション更新
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE sim_daytrade_positions
                    SET current_price = :price, unrealized_pnl = :pnl, updated_at = :time
                    WHERE id = :id
                """), {"price": usdjpy_price, "pnl": pnl_jpy, "id": pos_id, "time": datetime.now(pytz.UTC)})
                conn.commit()

            print("📊 HOLD - 継続保有")

    print("✅ デイトレ戦略 処理完了")

def main():
    """
    統合バッチ処理
    - WAIT戦略: 常時実行
    - デイトレ戦略: 常時実行（取引は10-18時のみ）
    """
    print()
    print("🚀 FX Trading Bot v1.3.0")
    print("=" * 60)

    # WAIT戦略
    check_and_execute()

    # デイトレ戦略
    check_daytrade()

    print()
    print("=" * 60)
    print("🏁 全処理完了")
    print("=" * 60)

if __name__ == "__main__":
    main()
