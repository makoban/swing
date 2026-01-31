"""
Trend Filter Comparison Backtest
"""
import pandas as pd
import yfinance as yf
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

rcParams['font.sans-serif'] = ['Meiryo', 'Yu Gothic', 'Hiragino Maru Gothic Pro']

INITIAL_CAPITAL = 1_000_000
SPREAD = 0.004
SWAP_PER_DAY = 100
LOT_RATIO = 0.02

def calculate_lot(balance):
    raw_lot = balance * LOT_RATIO
    lot = int(raw_lot // 10000) * 10000
    return max(lot, 10000)

def run_backtest(data, filter_name, filter_func):
    cash = INITIAL_CAPITAL
    position = 0
    current_lot = 0
    buy_price = 0
    equity_curve = []
    trades = 0
    wins = 0

    for i in range(len(data)):
        price = data['JPY=X'].iloc[i]
        daily_signal = data['DailySignal'].iloc[i]
        trend_ok = filter_func(data, i)

        if position == 0 and daily_signal == 1 and trend_ok:
            position = 1
            current_lot = calculate_lot(cash)
            buy_price = price + SPREAD

        elif position == 1 and daily_signal == 0:
            position = 0
            sell_price = price
            profit = (sell_price - buy_price) * current_lot
            cash += profit
            trades += 1
            if profit > 0:
                wins += 1
            current_lot = 0
            buy_price = 0

        elif position == 1:
            daily_swap = SWAP_PER_DAY * (current_lot / 10000)
            cash += daily_swap

        if position == 1:
            unrealized = (price - buy_price) * current_lot
            current_equity = cash + unrealized
        else:
            current_equity = cash

        equity_curve.append(current_equity)

    final_equity = equity_curve[-1]
    roi = ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    min_equity = min(equity_curve)
    win_rate = (wins / trades * 100) if trades > 0 else 0

    return {
        'name': filter_name,
        'final_equity': final_equity,
        'roi': roi,
        'trades': trades,
        'wins': wins,
        'win_rate': win_rate,
        'min_equity': min_equity,
        'equity_curve': equity_curve
    }

def filter_none(data, i):
    return True

def filter_ma20(data, i):
    if i < 20:
        return False
    return data['^TNX'].iloc[i] > data['MA20'].iloc[i]

def filter_cross(data, i):
    if i < 20:
        return False
    return data['MA5'].iloc[i] > data['MA20'].iloc[i]

def filter_ma20_slope(data, i):
    if i < 21:
        return False
    return data['MA20'].iloc[i] > data['MA20'].iloc[i-1]

def main():
    print("=" * 70)
    print("TREND FILTER COMPARISON BACKTEST")
    print("=" * 70)

    df = yf.download(['^TNX', 'JPY=X'], period="max", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)

    data = df.dropna().copy()

    data['MA5'] = data['^TNX'].rolling(window=5).mean()
    data['MA20'] = data['^TNX'].rolling(window=20).mean()

    tnx_change = data['^TNX'] - data['^TNX'].shift(1)
    data['DailySignal'] = np.where(tnx_change > 0, 1, 0)
    data['DailySignal'] = data['DailySignal'].shift(1)

    print(f"Period: {data.index[0].date()} - {data.index[-1].date()}")
    print(f"Data: {len(data)} days")

    filters = [
        ("1.No Filter", filter_none),
        ("2.TNX>MA20", filter_ma20),
        ("3.MA5>MA20 Cross", filter_cross),
        ("4.MA20 Slope Up", filter_ma20_slope),
    ]

    results = []
    for name, func in filters:
        print(f"Testing: {name}...")
        result = run_backtest(data, name, func)
        results.append(result)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"{'Filter':<20} {'Final':>15} {'ROI':>10} {'Trades':>8} {'WinRate':>8} {'MinBal':>12}")
    print("-" * 70)

    for r in results:
        print(f"{r['name']:<20} {r['final_equity']:>13,.0f}JPY {r['roi']:>9.1f}% {r['trades']:>7} {r['win_rate']:>7.1f}% {r['min_equity']:>10,.0f}JPY")

    best = max(results, key=lambda x: x['final_equity'])
    print("\n" + "=" * 70)
    print(f"BEST: {best['name']}")
    print(f"Final: {best['final_equity']:,.0f} JPY (ROI: {best['roi']:.1f}%)")
    print("=" * 70)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    colors = ['blue', 'green', 'orange', 'purple']

    for idx, r in enumerate(results):
        ax = axes[idx // 2, idx % 2]
        ax.plot(data.index[:len(r['equity_curve'])], r['equity_curve'], color=colors[idx])
        ax.axhline(y=INITIAL_CAPITAL, color='red', linestyle='--', alpha=0.5)
        ax.set_title(f"{r['name']} | ROI: {r['roi']:.1f}%")
        ax.set_ylabel('JPY')
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("trend_filter_comparison.png")
    print("\nSaved: trend_filter_comparison.png")

    return results

if __name__ == "__main__":
    main()
