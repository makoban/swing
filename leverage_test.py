"""
Leverage Comparison Backtest
LOT_RATIO 2%, 5%, 10% の比較
"""
import pandas as pd
import numpy as np
import os

DATA_DIR = "scalp_data"
INITIAL_CAPITAL = 1_000_000
TAKE_PROFIT = 0.15
STOP_LOSS = 0.10
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

def run_backtest(df, lot_ratio):
    """バックテスト（指定したLOT_RATIOで）"""

    def calculate_lot(balance):
        raw_lot = balance * lot_ratio
        lot = int(raw_lot // 10000) * 10000
        return max(lot, 10000)

    cash = INITIAL_CAPITAL
    position = 0
    entry_price = 0
    current_units = 0

    trades = []
    equity_curve = [INITIAL_CAPITAL]

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        hour_utc = df.index[i].hour
        is_trading_hour = TRADE_START_UTC <= hour_utc <= TRADE_END_UTC

        if position == 0:
            if is_trading_hour and cash > 100000:  # 最低残高チェック
                trend = get_trend(df, i, lookback=5)
                if trend == 1:
                    position = 1
                    current_units = calculate_lot(cash)
                    entry_price = price + SPREAD

        elif position == 1:
            pnl = price - entry_price
            pnl_jpy = pnl * current_units

            if pnl >= TAKE_PROFIT:
                cash += pnl_jpy
                trades.append({'result': 'TP', 'pnl': pnl_jpy, 'units': current_units})
                position = 0
            elif pnl <= -STOP_LOSS:
                cash += pnl_jpy
                trades.append({'result': 'SL', 'pnl': pnl_jpy, 'units': current_units})
                position = 0
            elif hour_utc >= TRADE_END_UTC:
                cash += pnl_jpy
                trades.append({'result': 'FORCED', 'pnl': pnl_jpy, 'units': current_units})
                position = 0

        equity_curve.append(max(0, cash))

    if len(trades) == 0:
        return None

    trades_df = pd.DataFrame(trades)

    return {
        'lot_ratio': lot_ratio * 100,
        'total_trades': len(trades_df),
        'win_rate': len(trades_df[trades_df['pnl'] > 0]) / len(trades_df) * 100,
        'total_pnl': trades_df['pnl'].sum(),
        'final_capital': cash,
        'roi': (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
        'max_equity': max(equity_curve),
        'min_equity': min(equity_curve),
        'max_drawdown': max(equity_curve) - min(equity_curve[equity_curve.index(max(equity_curve)):]) if max(equity_curve) > 0 else 0,
        'avg_units': trades_df['units'].mean()
    }

def main():
    print("=" * 80)
    print("LEVERAGE COMPARISON BACKTEST")
    print("=" * 80)
    print(f"Take Profit: +{TAKE_PROFIT} yen | Stop Loss: -{STOP_LOSS} yen")
    print(f"Initial Capital: {INITIAL_CAPITAL:,} JPY")
    print()

    # Load data
    df = load_data('usdjpy_1h_2y.csv')
    print(f"Data: {len(df)} rows ({(df.index[-1] - df.index[0]).days} days)")
    print()

    # Test different LOT_RATIO
    lot_ratios = [0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]

    results = []
    for ratio in lot_ratios:
        result = run_backtest(df, ratio)
        if result:
            results.append(result)

    # Results
    print("-" * 80)
    print(f"{'LOT%':<8} {'Trades':>7} {'WinRate':>8} {'P&L':>14} {'Final':>14} {'ROI':>10} {'MaxDD':>12}")
    print("-" * 80)

    for r in results:
        print(f"{r['lot_ratio']:.0f}%     {r['total_trades']:>6} {r['win_rate']:>7.1f}% {r['total_pnl']:>+13,.0f} {r['final_capital']:>13,.0f} {r['roi']:>+9.1f}% {r['max_drawdown']:>11,.0f}")

    # Best
    best = max(results, key=lambda x: x['final_capital'])
    safest = min(results, key=lambda x: x['max_drawdown'])

    print()
    print("=" * 80)
    print(f"BEST ROI:     {best['lot_ratio']:.0f}% -> Final: {best['final_capital']:,.0f} JPY (ROI: {best['roi']:+.1f}%)")
    print(f"SAFEST:       {safest['lot_ratio']:.0f}% -> MaxDD: {safest['max_drawdown']:,.0f} JPY")
    print("=" * 80)

if __name__ == "__main__":
    main()
