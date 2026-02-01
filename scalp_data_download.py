"""
Scalping Strategy - 1-Minute Data Downloader
Downloads historical USD/JPY 1-minute data for backtesting
"""
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# データ保存ディレクトリ
DATA_DIR = "scalp_data"

def download_yfinance_1m():
    """
    yfinanceから1分足データをダウンロード
    注意: yfinanceは過去7日間の1分足のみ取得可能
    """
    print("=" * 60)
    print("Downloading 1-minute data from yfinance")
    print("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)

    # 1分足（過去7日間のみ）
    df_1m = yf.download('JPY=X', period='7d', interval='1m', progress=True)
    if not df_1m.empty:
        filepath = os.path.join(DATA_DIR, 'usdjpy_1m_recent.csv')
        df_1m.to_csv(filepath)
        print(f"Saved: {filepath} ({len(df_1m)} rows)")

    # 5分足（過去60日間）
    df_5m = yf.download('JPY=X', period='60d', interval='5m', progress=True)
    if not df_5m.empty:
        filepath = os.path.join(DATA_DIR, 'usdjpy_5m_60d.csv')
        df_5m.to_csv(filepath)
        print(f"Saved: {filepath} ({len(df_5m)} rows)")

    # 1時間足（最大2年）
    df_1h = yf.download('JPY=X', period='2y', interval='1h', progress=True)
    if not df_1h.empty:
        filepath = os.path.join(DATA_DIR, 'usdjpy_1h_2y.csv')
        df_1h.to_csv(filepath)
        print(f"Saved: {filepath} ({len(df_1h)} rows)")

    return df_1m, df_5m, df_1h

def analyze_data(df, name):
    """データの基本統計を表示"""
    print(f"\n--- {name} ---")

    if isinstance(df.columns, pd.MultiIndex):
        close = df.xs('Close', level=0, axis=1)
        if 'JPY=X' in close.columns:
            close = close['JPY=X']
    else:
        close = df['Close']

    # 価格変動
    change = (close - close.shift(1)).abs()

    print(f"Period: {df.index[0]} - {df.index[-1]}")
    print(f"Data points: {len(df)}")
    print(f"Price range: {close.min():.2f} - {close.max():.2f}")
    print(f"Avg 1-bar move: {change.mean():.4f} yen")
    print(f"Max 1-bar move: {change.max():.4f} yen")

    # 10:00-18:00 JSTのデータをフィルタ
    # UTC -> JST は +9時間なので、UTC 01:00-09:00 = JST 10:00-18:00
    df_copy = df.copy()
    df_copy['hour_utc'] = df_copy.index.hour
    quiet_hours = df_copy[(df_copy['hour_utc'] >= 1) & (df_copy['hour_utc'] <= 9)]

    if len(quiet_hours) > 0:
        print(f"\nQuiet hours (10:00-18:00 JST) data points: {len(quiet_hours)}")

def main():
    print("Scalping Strategy Data Downloader")
    print("=" * 60)

    # yfinanceからダウンロード
    df_1m, df_5m, df_1h = download_yfinance_1m()

    # 分析
    if not df_1m.empty:
        analyze_data(df_1m, "1-Minute (7 days)")
    if not df_5m.empty:
        analyze_data(df_5m, "5-Minute (60 days)")
    if not df_1h.empty:
        analyze_data(df_1h, "1-Hour (2 years)")

    print("\n" + "=" * 60)
    print("DATA DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Files saved in: {os.path.abspath(DATA_DIR)}")
    print()
    print("For longer historical 1-minute data, visit:")
    print("  - https://www.histdata.com/download-free-forex-data/")
    print("  - Select: USD/JPY -> ASCII -> 1 Minute Bar")

if __name__ == "__main__":
    main()
