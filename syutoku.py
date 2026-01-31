import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import time

# ==========================================
# 1. 設定：Renderの接続情報をここに貼る
# ==========================================
DB_CONNECTION_STRING = "postgresql://kokotomo_staging_user:MdaXINo3sbdaPy1cPwp7lvnm8O7SLdLq@dpg-d52du3nfte5s73d3ni6g-a.singapore-postgres.render.com/kokotomo_staging"

tickers = {
    'JPY=X': 'USD/JPY',      # ドル円
    '^N225': 'Nikkei 225',   # 日経平均
    '^GSPC': 'S&P 500',      # 米国株
    '^TNX':  'US 10Y Bond'   # 米国金利
}

def clean_and_fetch_data():
    engine = create_engine(DB_CONNECTION_STRING)

    print("🚀 データベースをリセットして、再構築を開始します...")

    # 2. テーブルを一度削除して作り直す
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS market_data;"))
        conn.execute(text("""
            CREATE TABLE market_data (
                date DATE NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                open NUMERIC,
                high NUMERIC,
                low NUMERIC,
                close NUMERIC,
                volume BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, ticker)
            );
        """))
        conn.commit()
        print("✨ テーブル 'market_data' を初期化しました。")

    # 3. データを取得して保存
    for symbol, name in tickers.items():
        print(f"\nProcessing: {name} ({symbol})")

        try:
            # データを取得
            df = yf.download(symbol, period="max", auto_adjust=True, progress=False)

            if df.empty:
                print(f"⚠️ データが見つかりませんでした: {symbol}")
                continue

            # 【ここが修正ポイント】
            # カラムが2段組（MultiIndex）になっている場合、1段目に強制変換する
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # データの整形
            df = df.reset_index()
            df['ticker'] = symbol

            # カラム名の修正（小文字に統一）
            df = df.rename(columns={
                'Date': 'date', 'Open': 'open', 'High': 'high',
                'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            })

            # 欠損値対策（金利データのVolumeなどがNaNの場合のエラー回避）
            df = df.fillna(0)

            # DBに入れるカラムだけを選別
            # ※稀にVolumeがないデータもあるので、存在確認してから選ぶ
            cols_to_keep = ['date', 'ticker', 'open', 'high', 'low', 'close']
            if 'volume' in df.columns:
                cols_to_keep.append('volume')
            else:
                df['volume'] = 0 # 無ければ0で作る
                cols_to_keep.append('volume')

            insert_df = df[cols_to_keep]

            # データ投入
            insert_df.to_sql('market_data', engine, if_exists='append', index=False, method='multi', chunksize=1000)
            print(f"✅ {len(insert_df)} 件のデータを保存しました: {name}")

        except Exception as e:
            print(f"❌ DB保存エラー ({name}): {e}")

    print("\n🎉 全ての処理が完了しました！DBeaverでデータを確認してください。")

if __name__ == "__main__":
    clean_and_fetch_data()
