"""
Scalping Strategy Backtest
日中スキャルピング戦略（10:00-18:00 JST）

条件:
- 取引時間: 10:00-18:00 JST (UTC 01:00-09:00)
- 利確: +0.15円
- 損切: -0.10円
- 18:00に強制決済
- トレンド方向のみエントリー
"""
import pandas as pd
import numpy as np
import os

# 設定
DATA_DIR = "scalp_data"
INITIAL_CAPITAL = 1_000_000
UNITS = 20_000
SPREAD = 0.004  # 0.4pips
TAKE_PROFIT = 0.15  # 0.15円
STOP_LOSS = 0.10    # 0.10円

# 取引時間 (UTC)
TRADE_START_UTC = 1   # 10:00 JST = 01:00 UTC
TRADE_END_UTC = 9     # 18:00 JST = 09:00 UTC

def load_data(filename):
    """データ読み込み（yfinance MultiIndex CSV対応）"""
    filepath = os.path.join(DATA_DIR, filename)

    # yfinanceのCSVは最初の3行がヘッダー（Price, Ticker, Datetime）
    df = pd.read_csv(filepath, skiprows=3, header=None,
                     names=['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume'])

    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    df.set_index('Datetime', inplace=True)

    return df

def get_trend(df, idx, lookback=5):
    """
    直近のトレンド判定
    lookback期間の価格変化で判定
    """
    if idx < lookback:
        return 0

    current = df['Close'].iloc[idx]
    past = df['Close'].iloc[idx - lookback]

    if current > past + 0.02:  # 0.02円以上上昇
        return 1  # UP
    elif current < past - 0.02:  # 0.02円以上下落
        return -1  # DOWN
    return 0  # FLAT

def run_backtest(df, data_name):
    """バックテスト実行"""
    cash = INITIAL_CAPITAL
    position = 0  # 0: なし, 1: LONG
    entry_price = 0
    entry_time = None

    trades = []
    daily_forced_exits = 0

    for i in range(len(df)):
        row = df.iloc[i]
        price = row['Close']
        hour_utc = df.index[i].hour

        # 取引時間チェック
        is_trading_hour = TRADE_START_UTC <= hour_utc <= TRADE_END_UTC

        if position == 0:
            # ポジションなし
            if is_trading_hour:
                trend = get_trend(df, i, lookback=5)
                if trend == 1:  # 上昇トレンド
                    position = 1
                    entry_price = price + SPREAD  # スプレッド込み
                    entry_time = df.index[i]

        elif position == 1:
            # ポジション保有中
            pnl = price - entry_price

            # 利確
            if pnl >= TAKE_PROFIT:
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.index[i],
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_yen': pnl,
                    'pnl_jpy': pnl * UNITS,
                    'result': 'TP',
                    'hold_minutes': (df.index[i] - entry_time).total_seconds() / 60
                })
                cash += pnl * UNITS
                position = 0

            # 損切
            elif pnl <= -STOP_LOSS:
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.index[i],
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_yen': pnl,
                    'pnl_jpy': pnl * UNITS,
                    'result': 'SL',
                    'hold_minutes': (df.index[i] - entry_time).total_seconds() / 60
                })
                cash += pnl * UNITS
                position = 0

            # 18:00 強制決済
            elif hour_utc >= TRADE_END_UTC:
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.index[i],
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_yen': pnl,
                    'pnl_jpy': pnl * UNITS,
                    'result': 'FORCED',
                    'hold_minutes': (df.index[i] - entry_time).total_seconds() / 60
                })
                cash += pnl * UNITS
                position = 0
                daily_forced_exits += 1

    # 結果まとめ
    if len(trades) == 0:
        print(f"No trades for {data_name}")
        return None

    trades_df = pd.DataFrame(trades)

    wins = len(trades_df[trades_df['pnl_jpy'] > 0])
    losses = len(trades_df[trades_df['pnl_jpy'] <= 0])
    total_pnl = trades_df['pnl_jpy'].sum()
    win_rate = wins / len(trades_df) * 100

    tp_count = len(trades_df[trades_df['result'] == 'TP'])
    sl_count = len(trades_df[trades_df['result'] == 'SL'])
    forced_count = len(trades_df[trades_df['result'] == 'FORCED'])

    avg_hold = trades_df['hold_minutes'].mean()

    days = (df.index[-1] - df.index[0]).days
    trades_per_day = len(trades_df) / days if days > 0 else 0

    result = {
        'data': data_name,
        'total_trades': len(trades_df),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'final_capital': cash,
        'roi': (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
        'tp_count': tp_count,
        'sl_count': sl_count,
        'forced_count': forced_count,
        'avg_hold_min': avg_hold,
        'trades_per_day': trades_per_day,
        'days': days
    }

    return result

def main():
    print("=" * 70)
    print("SCALPING STRATEGY BACKTEST")
    print("=" * 70)
    print(f"Settings:")
    print(f"  Take Profit: +{TAKE_PROFIT} yen")
    print(f"  Stop Loss:   -{STOP_LOSS} yen")
    print(f"  Trade Hours: {TRADE_START_UTC+9}:00 - {TRADE_END_UTC+9}:00 JST")
    print(f"  Units:       {UNITS:,}")
    print()

    results = []

    # 5分足（60日）でバックテスト
    if os.path.exists(os.path.join(DATA_DIR, 'usdjpy_5m_60d.csv')):
        df = load_data('usdjpy_5m_60d.csv')
        result = run_backtest(df, '5min_60days')
        if result:
            results.append(result)

    # 1時間足（2年）でバックテスト
    if os.path.exists(os.path.join(DATA_DIR, 'usdjpy_1h_2y.csv')):
        df = load_data('usdjpy_1h_2y.csv')
        result = run_backtest(df, '1hour_2years')
        if result:
            results.append(result)

    # 結果表示
    print("-" * 70)
    print("RESULTS")
    print("-" * 70)

    for r in results:
        print(f"\n[{r['data']}]")
        print(f"  Period: {r['days']} days")
        print(f"  Trades: {r['total_trades']} (TP:{r['tp_count']}, SL:{r['sl_count']}, Forced:{r['forced_count']})")
        print(f"  Win Rate: {r['win_rate']:.1f}%")
        print(f"  Total P&L: {r['total_pnl']:+,.0f} JPY")
        print(f"  Final Capital: {r['final_capital']:,.0f} JPY")
        print(f"  ROI: {r['roi']:+.2f}%")
        print(f"  Trades/Day: {r['trades_per_day']:.1f}")
        print(f"  Avg Hold: {r['avg_hold_min']:.1f} min")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
