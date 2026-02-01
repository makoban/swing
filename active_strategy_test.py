"""
Active Trading Strategy Comparison
Monthly ~10 trades target

Strategies to compare:
1. Daily Signal Only (no MA filter) - trades on every TNX up/down
2. 5-day MA Filter - faster response
3. 3-day Momentum - very short term
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

def run_backtest(data, filter_name, entry_func, exit_func):
    cash = INITIAL_CAPITAL
    position = 0
    current_lot = 0
    buy_price = 0
    equity_curve = []
    trades = 0
    wins = 0

    for i in range(len(data)):
        price = data['JPY=X'].iloc[i]

        # Entry condition
        can_entry = entry_func(data, i)
        # Exit condition
        should_exit = exit_func(data, i)

        if position == 0 and can_entry:
            position = 1
            current_lot = calculate_lot(cash)
            buy_price = price + SPREAD

        elif position == 1 and should_exit:
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
    years = len(data) / 252  # trading days per year
    trades_per_month = trades / (years * 12)

    return {
        'name': filter_name,
        'final_equity': final_equity,
        'roi': roi,
        'trades': trades,
        'trades_per_month': trades_per_month,
        'wins': wins,
        'win_rate': win_rate,
        'min_equity': min_equity,
        'equity_curve': equity_curve
    }

def main():
    print("=" * 80)
    print("ACTIVE STRATEGY COMPARISON (Target: ~10 trades/month)")
    print("=" * 80)

    df = yf.download(['^TNX', 'JPY=X'], period="max", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)

    data = df.dropna().copy()

    # Indicators
    data['TNX_change'] = data['^TNX'] - data['^TNX'].shift(1)
    data['MA3'] = data['^TNX'].rolling(window=3).mean()
    data['MA5'] = data['^TNX'].rolling(window=5).mean()
    data['MA10'] = data['^TNX'].rolling(window=10).mean()
    data['MA20'] = data['^TNX'].rolling(window=20).mean()

    # Daily signal
    data['DailyUp'] = data['TNX_change'] > 0

    print(f"Period: {data.index[0].date()} - {data.index[-1].date()}")
    print(f"Days: {len(data)}")
    print()

    # Strategy definitions
    strategies = []

    # 1. Daily Only (no filter)
    def daily_entry(d, i):
        if i < 1: return False
        return d['DailyUp'].iloc[i]
    def daily_exit(d, i):
        if i < 1: return False
        return not d['DailyUp'].iloc[i]
    strategies.append(("1.Daily Only (no filter)", daily_entry, daily_exit))

    # 2. 5-day MA filter
    def ma5_entry(d, i):
        if i < 5: return False
        return d['DailyUp'].iloc[i] and d['^TNX'].iloc[i] > d['MA5'].iloc[i]
    def ma5_exit(d, i):
        if i < 5: return False
        return not d['DailyUp'].iloc[i]
    strategies.append(("2.MA5 Filter (active)", ma5_entry, ma5_exit))

    # 3. 3-day momentum (TNX rising for 2+ days)
    def mom3_entry(d, i):
        if i < 3: return False
        return d['TNX_change'].iloc[i] > 0 and d['TNX_change'].iloc[i-1] > 0
    def mom3_exit(d, i):
        if i < 1: return False
        return d['TNX_change'].iloc[i] < 0
    strategies.append(("3.2-Day Momentum", mom3_entry, mom3_exit))

    # 4. MA5 cross MA10 (medium term)
    def cross510_entry(d, i):
        if i < 10: return False
        return d['MA5'].iloc[i] > d['MA10'].iloc[i] and d['DailyUp'].iloc[i]
    def cross510_exit(d, i):
        if i < 10: return False
        return d['MA5'].iloc[i] < d['MA10'].iloc[i]
    strategies.append(("4.MA5/10 Cross", cross510_entry, cross510_exit))

    # 5. Trend + Quick Entry (MA10 filter + daily)
    def trend10_entry(d, i):
        if i < 10: return False
        return d['DailyUp'].iloc[i] and d['^TNX'].iloc[i] > d['MA10'].iloc[i]
    def trend10_exit(d, i):
        if i < 1: return False
        return not d['DailyUp'].iloc[i]
    strategies.append(("5.MA10 Filter", trend10_entry, trend10_exit))

    # 6. WAIT strategy (20MA - for comparison)
    def ma20_entry(d, i):
        if i < 20: return False
        return d['DailyUp'].iloc[i] and d['^TNX'].iloc[i] > d['MA20'].iloc[i]
    def ma20_exit(d, i):
        if i < 1: return False
        return not d['DailyUp'].iloc[i]
    strategies.append(("6.MA20 WAIT (current)", ma20_entry, ma20_exit))

    # Run backtests
    results = []
    for name, entry_f, exit_f in strategies:
        print(f"Testing: {name}...")
        result = run_backtest(data, name, entry_f, exit_f)
        results.append(result)

    # Results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"{'Strategy':<25} {'Final':>14} {'ROI':>8} {'Trades':>7} {'Per Mo':>7} {'WinRate':>8} {'MinBal':>12}")
    print("-" * 80)

    for r in results:
        print(f"{r['name']:<25} {r['final_equity']:>12,.0f}Y {r['roi']:>7.1f}% {r['trades']:>6} {r['trades_per_month']:>6.1f} {r['win_rate']:>7.1f}% {r['min_equity']:>10,.0f}Y")

    # Find best active strategy (excluding MA20 WAIT)
    active_results = [r for r in results if 'WAIT' not in r['name']]
    best_active = max(active_results, key=lambda x: x['final_equity'])

    # Strategies with ~10 trades/month
    monthly_10 = [r for r in results if 5 <= r['trades_per_month'] <= 15]

    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    print(f"Best Active: {best_active['name']}")
    print(f"  ROI: {best_active['roi']:.1f}% | Trades/Mo: {best_active['trades_per_month']:.1f}")

    if monthly_10:
        best_monthly = max(monthly_10, key=lambda x: x['final_equity'])
        print(f"\nBest ~10 trades/month: {best_monthly['name']}")
        print(f"  ROI: {best_monthly['roi']:.1f}% | Trades/Mo: {best_monthly['trades_per_month']:.1f}")

    print("=" * 80)

if __name__ == "__main__":
    main()
