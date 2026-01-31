"""
30-Year Performance Report with MA20 Filter
"""
import pandas as pd
import yfinance as yf
import numpy as np

INITIAL_CAPITAL = 1_000_000
SPREAD = 0.004
SWAP_PER_DAY = 100
LOT_RATIO = 0.02

def calculate_lot(balance):
    raw_lot = balance * LOT_RATIO
    lot = int(raw_lot // 10000) * 10000
    return max(lot, 10000)

def main():
    print("=" * 80)
    print("30-YEAR PERFORMANCE REPORT: TNX > MA20 Filter Strategy")
    print("=" * 80)

    df = yf.download(['^TNX', 'JPY=X'], period="max", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)

    data = df.dropna().copy()
    data['MA20'] = data['^TNX'].rolling(window=20).mean()

    tnx_change = data['^TNX'] - data['^TNX'].shift(1)
    data['DailySignal'] = np.where(tnx_change > 0, 1, 0)
    data['DailySignal'] = data['DailySignal'].shift(1)

    # Trend filter: TNX > MA20
    data['TrendOK'] = data['^TNX'] > data['MA20']

    print(f"Period: {data.index[0].date()} - {data.index[-1].date()}\n")

    # Simulation
    cash = INITIAL_CAPITAL
    position = 0
    current_lot = 0
    buy_price = 0

    yearly_data = []
    current_year = None
    year_start_equity = INITIAL_CAPITAL
    year_trades = 0
    year_wins = 0

    for i in range(len(data)):
        date = data.index[i]
        price = data['JPY=X'].iloc[i]
        daily_signal = data['DailySignal'].iloc[i]
        trend_ok = data['TrendOK'].iloc[i] if pd.notna(data['TrendOK'].iloc[i]) else False

        # Year change
        if current_year is not None and date.year != current_year:
            if position == 1:
                unrealized = (price - buy_price) * current_lot
                year_end_equity = cash + unrealized
            else:
                year_end_equity = cash

            year_pnl = year_end_equity - year_start_equity
            year_roi = (year_pnl / year_start_equity) * 100

            yearly_data.append({
                'year': current_year,
                'start': year_start_equity,
                'end': year_end_equity,
                'pnl': year_pnl,
                'roi': year_roi,
                'trades': year_trades,
                'wins': year_wins
            })

            year_start_equity = year_end_equity
            year_trades = 0
            year_wins = 0

        current_year = date.year

        # Trading logic with MA20 filter
        if position == 0 and daily_signal == 1 and trend_ok:
            position = 1
            current_lot = calculate_lot(cash)
            buy_price = price + SPREAD

        elif position == 1 and daily_signal == 0:
            position = 0
            sell_price = price
            profit = (sell_price - buy_price) * current_lot
            cash += profit
            year_trades += 1
            if profit > 0:
                year_wins += 1
            current_lot = 0
            buy_price = 0

        elif position == 1:
            daily_swap = SWAP_PER_DAY * (current_lot / 10000)
            cash += daily_swap

    # Final year
    if position == 1:
        final_equity = cash + (data['JPY=X'].iloc[-1] - buy_price) * current_lot
    else:
        final_equity = cash

    year_pnl = final_equity - year_start_equity
    year_roi = (year_pnl / year_start_equity) * 100
    yearly_data.append({
        'year': current_year,
        'start': year_start_equity,
        'end': final_equity,
        'pnl': year_pnl,
        'roi': year_roi,
        'trades': year_trades,
        'wins': year_wins
    })

    # Print results
    print(f"{'Year':<6} {'Start':>15} {'End':>15} {'P&L':>15} {'ROI':>10} {'Trades':>8}")
    print("-" * 80)

    for y in yearly_data:
        roi_str = f"{y['roi']:+.1f}%" if y['roi'] != 0 else "0.0%"
        pnl_str = f"{y['pnl']:+,.0f}" if y['pnl'] != 0 else "0"
        print(f"{y['year']:<6} {y['start']:>14,.0f}  {y['end']:>14,.0f}  {pnl_str:>14}  {roi_str:>9} {y['trades']:>7}")

    print("-" * 80)
    total_roi = ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    total_pnl = final_equity - INITIAL_CAPITAL
    print(f"{'TOTAL':<6} {INITIAL_CAPITAL:>14,.0f}  {final_equity:>14,.0f}  {total_pnl:>+14,.0f}  {total_roi:>+9.1f}%")
    print("=" * 80)

    # Summary
    positive_years = sum(1 for y in yearly_data if y['pnl'] > 0)
    negative_years = sum(1 for y in yearly_data if y['pnl'] < 0)

    print(f"\nSUMMARY:")
    print(f"  Positive years: {positive_years}")
    print(f"  Negative years: {negative_years}")
    print(f"  Win rate: {positive_years/(positive_years+negative_years)*100:.1f}%")
    print(f"  Final: {final_equity:,.0f} JPY (ROI: {total_roi:.1f}%)")

if __name__ == "__main__":
    main()
