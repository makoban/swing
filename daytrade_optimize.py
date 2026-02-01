"""
Day Trading Strategy Optimization
デイトレ戦略の最適化バックテスト（複利対応）

予算: 100万円（WAIT戦略とは完全に別）
複利: 残高の2%をロットに

テストパターン:
- 利確: 0.05, 0.10, 0.15, 0.20円
- 損切: 0.05, 0.10, 0.15円
- 時間足: 5分, 1時間
"""
import pandas as pd
import numpy as np
import os
from itertools import product

DATA_DIR = "scalp_data"
INITIAL_CAPITAL = 1_000_000  # 100万円（WAIT戦略とは別予算）
LOT_RATIO = 0.02  # 複利: 残高の2%

# 取引時間 (UTC) - 10:00-18:00 JST
TRADE_START_UTC = 1
TRADE_END_UTC = 9
SPREAD = 0.004

def calculate_lot(balance):
    """複利対応ロット計算"""
    raw_lot = balance * LOT_RATIO
    lot = int(raw_lot // 10000) * 10000
    return max(lot, 10000)

def load_data(filename):
    """データ読み込み"""
    filepath = os.path.join(DATA_DIR, filename)
    df = pd.read_csv(filepath, skiprows=3, header=None,
                     names=['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume'])
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    df.set_index('Datetime', inplace=True)
    return df

def get_trend(df, idx, lookback=5):
    """トレンド判定"""
    if idx < lookback:
        return 0
    current = df['Close'].iloc[idx]
    past = df['Close'].iloc[idx - lookback]
    if current > past + 0.02:
        return 1
    elif current < past - 0.02:
        return -1
    return 0

def run_backtest(df, take_profit, stop_loss, compound=True):
    """バックテスト実行（複利対応）"""
    cash = INITIAL_CAPITAL
    position = 0
    entry_price = 0
    entry_time = None
    current_units = 0

    trades = []
    equity_curve = [INITIAL_CAPITAL]

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        hour_utc = df.index[i].hour
        is_trading_hour = TRADE_START_UTC <= hour_utc <= TRADE_END_UTC

        if position == 0:
            if is_trading_hour:
                trend = get_trend(df, i, lookback=5)
                if trend == 1:
                    position = 1
                    current_units = calculate_lot(cash) if compound else 20000
                    entry_price = price + SPREAD
                    entry_time = df.index[i]

        elif position == 1:
            pnl = price - entry_price
            pnl_jpy = pnl * current_units

            # 利確
            if pnl >= take_profit:
                cash += pnl_jpy
                trades.append({'result': 'TP', 'pnl': pnl_jpy})
                position = 0

            # 損切
            elif pnl <= -stop_loss:
                cash += pnl_jpy
                trades.append({'result': 'SL', 'pnl': pnl_jpy})
                position = 0

            # 強制決済
            elif hour_utc >= TRADE_END_UTC:
                cash += pnl_jpy
                trades.append({'result': 'FORCED', 'pnl': pnl_jpy})
                position = 0

        equity_curve.append(cash)

    if len(trades) == 0:
        return None

    trades_df = pd.DataFrame(trades)
    wins = len(trades_df[trades_df['pnl'] > 0])
    total_trades = len(trades_df)

    return {
        'take_profit': take_profit,
        'stop_loss': stop_loss,
        'total_trades': total_trades,
        'wins': wins,
        'win_rate': wins / total_trades * 100 if total_trades > 0 else 0,
        'total_pnl': trades_df['pnl'].sum(),
        'final_capital': cash,
        'roi': (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
        'max_equity': max(equity_curve),
        'min_equity': min(equity_curve),
        'tp_count': len(trades_df[trades_df['result'] == 'TP']),
        'sl_count': len(trades_df[trades_df['result'] == 'SL']),
        'forced_count': len(trades_df[trades_df['result'] == 'FORCED'])
    }

def main():
    print("=" * 80)
    print("DAY TRADING STRATEGY OPTIMIZATION (Compound Interest)")
    print("=" * 80)
    print(f"Initial Capital: {INITIAL_CAPITAL:,} JPY (Separate from WAIT strategy)")
    print(f"Lot Calculation: Balance x {LOT_RATIO*100:.0f}% (Compound)")
    print(f"Trade Hours: 10:00-18:00 JST")
    print()

    # テストパターン
    take_profits = [0.05, 0.10, 0.15, 0.20]
    stop_losses = [0.05, 0.10, 0.15]

    all_results = []

    # 5分足テスト
    print("Testing 5-minute data...")
    if os.path.exists(os.path.join(DATA_DIR, 'usdjpy_5m_60d.csv')):
        df_5m = load_data('usdjpy_5m_60d.csv')
        for tp, sl in product(take_profits, stop_losses):
            result = run_backtest(df_5m, tp, sl, compound=True)
            if result:
                result['timeframe'] = '5min'
                all_results.append(result)

    # 1時間足テスト
    print("Testing 1-hour data...")
    if os.path.exists(os.path.join(DATA_DIR, 'usdjpy_1h_2y.csv')):
        df_1h = load_data('usdjpy_1h_2y.csv')
        for tp, sl in product(take_profits, stop_losses):
            result = run_backtest(df_1h, tp, sl, compound=True)
            if result:
                result['timeframe'] = '1hour'
                all_results.append(result)

    # 結果をソート（ROI順）
    all_results.sort(key=lambda x: x['roi'], reverse=True)

    # TOP 10表示
    print("\n" + "=" * 80)
    print("TOP 10 RESULTS (by ROI)")
    print("=" * 80)
    print(f"{'Rank':<5} {'TF':<6} {'TP':<6} {'SL':<6} {'Trades':>7} {'WinRate':>8} {'ROI':>10} {'Final':>14}")
    print("-" * 80)

    for i, r in enumerate(all_results[:10]):
        print(f"{i+1:<5} {r['timeframe']:<6} {r['take_profit']:.2f}  {r['stop_loss']:.2f}  {r['total_trades']:>6} {r['win_rate']:>7.1f}% {r['roi']:>+9.2f}% {r['final_capital']:>13,.0f}")

    # 最良の結果を詳細表示
    if all_results:
        best = all_results[0]
        print("\n" + "=" * 80)
        print("BEST STRATEGY DETAILS")
        print("=" * 80)
        print(f"Timeframe:     {best['timeframe']}")
        print(f"Take Profit:   +{best['take_profit']} yen")
        print(f"Stop Loss:     -{best['stop_loss']} yen")
        print(f"Risk:Reward:   1:{best['take_profit']/best['stop_loss']:.1f}")
        print(f"Total Trades:  {best['total_trades']}")
        print(f"  - TP:        {best['tp_count']}")
        print(f"  - SL:        {best['sl_count']}")
        print(f"  - Forced:    {best['forced_count']}")
        print(f"Win Rate:      {best['win_rate']:.1f}%")
        print(f"Total P&L:     {best['total_pnl']:+,.0f} JPY")
        print(f"Final Capital: {best['final_capital']:,.0f} JPY")
        print(f"ROI:           {best['roi']:+.2f}%")
        print(f"Max Equity:    {best['max_equity']:,.0f} JPY")
        print(f"Min Equity:    {best['min_equity']:,.0f} JPY")

    # 赤字パターンを表示
    print("\n" + "=" * 80)
    print("WORST 5 (to avoid)")
    print("=" * 80)
    for i, r in enumerate(all_results[-5:]):
        print(f"{r['timeframe']:<6} TP:{r['take_profit']:.2f} SL:{r['stop_loss']:.2f} -> ROI:{r['roi']:+.2f}%")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
