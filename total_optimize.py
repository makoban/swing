"""
Total Optimization Grid Search
TP/SL/LOT の全組み合わせをテスト
"""
import pandas as pd
import numpy as np
import os
from itertools import product

DATA_DIR = "scalp_data"
INITIAL_CAPITAL = 1_000_000
SPREAD = 0.004
TRADE_START_UTC = 1
TRADE_END_UTC = 9

def load_data(filename):
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.read_csv(filepath, skiprows=3, header=None,
                     names=['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume'])
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    df.set_index('Datetime', inplace=True)
    return df

def get_trend(df, idx, lookback=5):
    if idx < lookback:
        return 0
    current = df['Close'].iloc[idx]
    past = df['Close'].iloc[idx - lookback]
    if current > past + 0.02:
        return 1
    return 0

def run_backtest(df, take_profit, stop_loss, lot_ratio):
    def calculate_lot(balance):
        raw_lot = balance * lot_ratio
        lot = int(raw_lot // 10000) * 10000
        return max(lot, 10000)

    cash = INITIAL_CAPITAL
    position = 0
    entry_price = 0
    current_units = 0
    min_cash = INITIAL_CAPITAL
    max_cash = INITIAL_CAPITAL
    trades = 0
    wins = 0

    for i in range(len(df)):
        if cash < 50000:  # 破産判定
            break

        price = df['Close'].iloc[i]
        hour_utc = df.index[i].hour
        is_trading_hour = TRADE_START_UTC <= hour_utc <= TRADE_END_UTC

        if position == 0:
            if is_trading_hour and cash > 100000:
                trend = get_trend(df, i, lookback=5)
                if trend == 1:
                    position = 1
                    current_units = calculate_lot(cash)
                    entry_price = price + SPREAD

        elif position == 1:
            pnl = price - entry_price
            pnl_jpy = pnl * current_units

            if pnl >= take_profit:
                cash += pnl_jpy
                trades += 1
                wins += 1
                position = 0
            elif pnl <= -stop_loss:
                cash += pnl_jpy
                trades += 1
                position = 0
            elif hour_utc >= TRADE_END_UTC:
                cash += pnl_jpy
                trades += 1
                if pnl_jpy > 0:
                    wins += 1
                position = 0

        if cash < min_cash:
            min_cash = cash
        if cash > max_cash:
            max_cash = cash

    roi = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    win_rate = wins / trades * 100 if trades > 0 else 0
    max_dd = max_cash - min_cash

    return {
        'tp': take_profit,
        'sl': stop_loss,
        'lot': lot_ratio * 100,
        'final': cash,
        'roi': roi,
        'trades': trades,
        'win_rate': win_rate,
        'max_dd': max_dd,
        'bankrupt': cash < 100000
    }

def main():
    print("=" * 100)
    print("TOTAL OPTIMIZATION: TP x SL x LOT% GRID SEARCH")
    print("=" * 100)

    df = load_data('usdjpy_1h_2y.csv')
    print(f"Data: 2 years ({len(df)} rows)")
    print()

    # パラメータグリッド
    take_profits = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    stop_losses = [0.05, 0.10, 0.15, 0.20]
    lot_ratios = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

    total_tests = len(take_profits) * len(stop_losses) * len(lot_ratios)
    print(f"Testing {total_tests} combinations...")
    print()

    results = []
    for tp, sl, lot in product(take_profits, stop_losses, lot_ratios):
        result = run_backtest(df, tp, sl, lot)
        results.append(result)

    # 破産しなかったものをフィルタ
    survivors = [r for r in results if not r['bankrupt']]
    bankrupts = [r for r in results if r['bankrupt']]

    # ROI順でソート
    survivors.sort(key=lambda x: x['roi'], reverse=True)

    print(f"Survivors: {len(survivors)} / Bankrupts: {len(bankrupts)}")
    print()

    # TOP 20
    print("=" * 100)
    print("TOP 20 STRATEGIES (by ROI)")
    print("=" * 100)
    print(f"{'Rank':<5} {'TP':>6} {'SL':>6} {'LOT%':>6} {'Trades':>7} {'Win%':>7} {'ROI':>10} {'Final':>14} {'MaxDD':>12}")
    print("-" * 100)

    for i, r in enumerate(survivors[:20]):
        print(f"{i+1:<5} {r['tp']:>6.2f} {r['sl']:>6.2f} {r['lot']:>5.0f}% {r['trades']:>6} {r['win_rate']:>6.1f}% {r['roi']:>+9.1f}% {r['final']:>13,.0f} {r['max_dd']:>11,.0f}")

    # 各LOT%での最良設定
    print()
    print("=" * 100)
    print("BEST SETTINGS FOR EACH LOT%")
    print("=" * 100)

    for lot_pct in [5, 10, 15, 20, 30, 40, 50, 60, 70, 80]:
        lot_results = [r for r in results if r['lot'] == lot_pct and not r['bankrupt']]
        if lot_results:
            best = max(lot_results, key=lambda x: x['roi'])
            print(f"LOT {lot_pct:>2}%: TP={best['tp']:.2f} SL={best['sl']:.2f} -> ROI={best['roi']:+.1f}% Final={best['final']:,.0f}")
        else:
            print(f"LOT {lot_pct:>2}%: ALL BANKRUPT")

    # 破産パターン分析
    print()
    print("=" * 100)
    print("BANKRUPT PATTERNS (LOT% threshold)")
    print("=" * 100)

    for tp in take_profits:
        for sl in stop_losses:
            pattern = [r for r in results if r['tp'] == tp and r['sl'] == sl]
            bankrupt_lots = [r['lot'] for r in pattern if r['bankrupt']]
            if bankrupt_lots:
                min_bankrupt = min(bankrupt_lots)
                print(f"TP={tp:.2f} SL={sl:.2f}: Bankrupt at LOT >= {min_bankrupt:.0f}%")
            else:
                print(f"TP={tp:.2f} SL={sl:.2f}: Never bankrupt (safe)")

    print()
    print("=" * 100)

if __name__ == "__main__":
    main()
