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

def get_market_data():
    """金利とドル円の現在値・前日比を取得"""
    # 米国10年債利回り
    tnx = yf.Ticker(TNX)
    tnx_hist = tnx.history(period="5d")
    if len(tnx_hist) < 2:
        print("⚠️ TNXデータ不足")
        return None, None, None, None

    tnx_current = float(tnx_hist['Close'].iloc[-1])
    tnx_prev = float(tnx_hist['Close'].iloc[-2])
    tnx_change = tnx_current - tnx_prev

    # 金利トレンド判定 (+0.01以上で上昇、-0.01以下で下落)
    if tnx_change >= 0.01:
        tnx_trend = "UP"  # 金利上昇 → ドル高(買い)
    elif tnx_change <= -0.01:
        tnx_trend = "DOWN"  # 金利下落 → ドル安(売り)
    else:
        tnx_trend = "NEUTRAL"  # 横ばい

    # ドル円の現在値
    usdjpy = yf.Ticker(USDJPY)
    usdjpy_hist = usdjpy.history(period="1d")
    if len(usdjpy_hist) == 0:
        print("⚠️ USDJPYデータ不足")
        return None, None, None, None

    usdjpy_current = float(usdjpy_hist['Close'].iloc[-1])

    print(f"📊 市場データ取得完了")
    print(f"   TNX: {tnx_current:.2f}% (前日比: {tnx_change:+.2f}%) → トレンド: {tnx_trend}")
    print(f"   USD/JPY: {usdjpy_current:.2f}")

    return tnx_trend, usdjpy_current, tnx_current, tnx_change

def check_and_execute():
    """メインロジック"""
    if not DB_URL:
        print("❌ 環境変数 DB_CONNECTION_STRING が設定されていません")
        return

    # DB接続
    engine = create_engine(DB_URL)

    print("🚀 FX自動売買システム起動")
    print(f"⏰ 実行時刻: {datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    # 1. 市場データの取得
    trend, usdjpy_price, tnx_value, tnx_change = get_market_data()
    if trend is None:
        print("❌ 市場データ取得失敗")
        return

    # 2. 現在のポジション確認
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, direction, entry_price, entry_time
            FROM positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC
            LIMIT 1
        """))
        open_position = result.fetchone()

    # 3. 判断ロジック
    action = None
    detail = ""

    if trend == "NEUTRAL":
        # 横ばい時は何もしない
        action = "HOLD"
        detail = "金利変動が小さいためトレード見送り"
        print(f"⏸️ {detail}")

    elif open_position is None:
        # Case 1: ポジションなし → 新規エントリー
        direction = "BUY" if trend == "UP" else "SELL"
        action = "ENTRY"
        detail = f"新規{direction}エントリー (金利{trend}トレンド)"

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO positions (direction, entry_price, entry_time, status)
                VALUES (:direction, :price, :time, 'OPEN')
            """), {"direction": direction, "price": usdjpy_price, "time": datetime.now(pytz.UTC)})
            conn.commit()

        print(f"🟢 {detail} @ {usdjpy_price:.2f}")

    else:
        pos_id, pos_direction, entry_price, entry_time = open_position
        expected_direction = "BUY" if trend == "UP" else "SELL"

        if pos_direction == expected_direction:
            # Case 2: トレンド継続 → ホールド
            action = "HOLD"
            pnl = (usdjpy_price - entry_price) if pos_direction == "BUY" else (entry_price - usdjpy_price)
            detail = f"ポジション継続中 (P&L: {pnl:+.2f}円)"

            # 含み損益を更新
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE positions
                    SET unrealized_pnl = :pnl, last_check_price = :price, updated_at = :time
                    WHERE id = :id
                """), {"pnl": pnl, "price": usdjpy_price, "time": datetime.now(pytz.UTC), "id": pos_id})
                conn.commit()

            print(f"📌 {detail}")

        else:
            # Case 3: トレンド反転 → 決済 & ドテン
            action = "REVERSE"
            pnl = (usdjpy_price - entry_price) if pos_direction == "BUY" else (entry_price - usdjpy_price)
            detail = f"トレンド反転検出! {pos_direction}決済(P&L:{pnl:+.2f}円) → {expected_direction}新規"

            with engine.connect() as conn:
                # 既存ポジションを決済
                conn.execute(text("""
                    UPDATE positions
                    SET status = 'CLOSED', unrealized_pnl = :pnl, last_check_price = :price, updated_at = :time
                    WHERE id = :id
                """), {"pnl": pnl, "price": usdjpy_price, "time": datetime.now(pytz.UTC), "id": pos_id})

                # 新規ポジションを建てる
                conn.execute(text("""
                    INSERT INTO positions (direction, entry_price, entry_time, status)
                    VALUES (:direction, :price, :time, 'OPEN')
                """), {"direction": expected_direction, "price": usdjpy_price, "time": datetime.now(pytz.UTC)})
                conn.commit()

            print(f"🔄 {detail}")

    # 4. ログ記録
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO trade_logs (timestamp, tnx_value, usd_jpy_value, action, detail)
            VALUES (:time, :tnx, :usdjpy, :action, :detail)
        """), {
            "time": datetime.now(pytz.UTC),
            "tnx": tnx_value,
            "usdjpy": usdjpy_price,
            "action": action,
            "detail": detail
        })
        conn.commit()

    print("-" * 50)
    print("✅ 処理完了。ログをDBに記録しました。")

if __name__ == "__main__":
    check_and_execute()
