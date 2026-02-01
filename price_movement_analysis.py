"""
0.3円変動分析 - どの時間幅で0.3円動くか？
"""
import yfinance as yf
import pandas as pd
import numpy as np

def analyze_price_movement():
    print("=" * 70)
    print("USD/JPY 価格変動分析 - 0.3円到達率")
    print("=" * 70)

    # 1時間足データ取得（最大60日）
    df = yf.download('JPY=X', period='60d', interval='1h', progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)
        close = df['JPY=X']
    else:
        close = df['Close']

    print(f"Period: {df.index[0]} - {df.index[-1]}")
    print(f"Data points: {len(df)} (hourly)")
    print()

    # 各時間幅での変動分析
    timeframes = [1, 2, 4, 6, 8, 12, 24]  # hours
    target = 0.3  # 0.3円

    print(f"Target: {target} yen")
    print("-" * 70)
    print(f"{'Hours':<10} {'Avg Move':>12} {'Max Move':>12} {'>=0.3Y Rate':>15} {'Trades/Day':>12}")
    print("-" * 70)

    results = []
    for hours in timeframes:
        # 価格変動
        diff = close - close.shift(hours)
        abs_diff = diff.abs()

        avg_move = abs_diff.mean()
        max_move = abs_diff.max()
        over_target = (abs_diff >= target).sum()
        total = len(abs_diff.dropna())
        rate = (over_target / total) * 100 if total > 0 else 0
        trades_per_day = 24 / hours

        results.append({
            'hours': hours,
            'avg_move': avg_move,
            'max_move': max_move,
            'rate': rate,
            'trades_per_day': trades_per_day
        })

        print(f"{hours}h   {avg_move:>11.3f}  {max_move:>11.3f}  {rate:>14.1f}%  {trades_per_day:>11.1f}")

    print("-" * 70)

    # 推奨
    print("\nAnalysis:")
    for r in results:
        if r['rate'] >= 30:  # 30%以上の確率で0.3円動く
            print(f"  {r['hours']}h: {r['rate']:.0f}% chance to move 0.3Y (avg: {r['avg_move']:.3f}Y)")

    # 日次変動
    print("\n" + "=" * 70)
    print("Daily Data Analysis")
    print("=" * 70)

    df_daily = yf.download('JPY=X', period='1y', interval='1d', progress=False)
    if isinstance(df_daily.columns, pd.MultiIndex):
        high = df_daily.xs('High', level=0, axis=1)['JPY=X']
        low = df_daily.xs('Low', level=0, axis=1)['JPY=X']
    else:
        high = df_daily['High']
        low = df_daily['Low']

    daily_range = high - low
    print(f"Daily range (High-Low):")
    print(f"  Average: {daily_range.mean():.3f} yen")
    print(f"  Median:  {daily_range.median():.3f} yen")
    print(f"  Min:     {daily_range.min():.3f} yen")
    print(f"  Max:     {daily_range.max():.3f} yen")

    over_03 = (daily_range >= 0.3).sum()
    total_days = len(daily_range.dropna())
    print(f"\n  Days with >= 0.3Y range: {over_03}/{total_days} ({over_03/total_days*100:.1f}%)")

if __name__ == "__main__":
    analyze_price_movement()
