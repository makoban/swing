"""
複利運用バックテスト
残高に応じてロット数を動的に調整

安全比率: 残高の2%を通貨数に（100万円 → 2万通貨）
"""
import pandas as pd
import yfinance as yf
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 日本語フォント設定
rcParams['font.sans-serif'] = ['Meiryo', 'Yu Gothic', 'Hiragino Maru Gothic Pro']

# ==========================================
# 設定
# ==========================================
INITIAL_CAPITAL = 1_000_000  # 開始資金: 100万円
SPREAD = 0.004               # スプレッド: 0.4銭
SWAP_PER_DAY = 100           # スワップ: 1万通貨あたり1日100円
SAFETY_RATIO = 0.02          # 安全比率: 残高の2%を通貨数に

def calculate_lot(balance):
    """
    残高に応じた安全なロット数を計算

    100万円 → 20,000通貨
    150万円 → 30,000通貨
    200万円 → 40,000通貨

    1万通貨単位に丸める
    """
    raw_lot = balance * SAFETY_RATIO
    lot = int(raw_lot // 10000) * 10000  # 1万通貨単位に丸め
    return max(lot, 10000)  # 最低1万通貨

def run_compound_simulation():
    print("🚀 複利運用バックテストを開始します...")
    print(f"📊 安全比率: 残高の {SAFETY_RATIO*100:.0f}% を通貨数に変換")
    print("-" * 60)

    # データの取得
    df = yf.download(['^TNX', 'JPY=X'], period="max", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)

    data = df.dropna().copy()

    # トレンド判定
    tnx_change = data['^TNX'] - data['^TNX'].shift(1)
    signal = np.where(tnx_change > 0, 1, 0)
    data['Signal'] = pd.Series(signal, index=data.index).shift(1)

    # ==========================================
    # 複利シミュレーション
    # ==========================================
    cash = INITIAL_CAPITAL
    position = 0
    current_lot = 0
    buy_price = 0

    equity_curve = []
    lot_history = []

    print(f"📊 期間: {data.index[0].date()} 〜 {data.index[-1].date()}")
    print("-" * 60)

    for i in range(len(data)):
        price = data['JPY=X'].iloc[i]
        today_signal = data['Signal'].iloc[i]

        # --- アクション判定 ---

        # 新規買い
        if position == 0 and today_signal == 1:
            position = 1
            # ★ 複利: 現在の残高からロット数を計算
            current_lot = calculate_lot(cash)
            buy_price = price + SPREAD

        # 決済
        elif position == 1 and today_signal == 0:
            position = 0
            sell_price = price
            profit = (sell_price - buy_price) * current_lot
            cash += profit
            current_lot = 0
            buy_price = 0

        # 保有継続（スワップ獲得）
        elif position == 1 and today_signal == 1:
            daily_swap = SWAP_PER_DAY * (current_lot / 10000)
            cash += daily_swap

        # --- 資産評価 ---
        if position == 1:
            unrealized = (price - buy_price) * current_lot
            current_equity = cash + unrealized
        else:
            current_equity = cash

        equity_curve.append(current_equity)
        lot_history.append(current_lot if position == 1 else 0)

    data['Equity'] = equity_curve
    data['Lot'] = lot_history

    # ==========================================
    # 結果表示
    # ==========================================
    final_equity = data['Equity'].iloc[-1]
    roi = ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    max_drawdown = (data['Equity'].cummax() - data['Equity']).max()
    min_equity = data['Equity'].min()
    max_lot = max(lot_history)

    print(f"💰 開始資金: {INITIAL_CAPITAL:,} 円")
    print(f"🏁 終了資金: {final_equity:,.0f} 円")
    print(f"🚀 最終利益: +{final_equity - INITIAL_CAPITAL:,.0f} 円")
    print(f"📈 収益率 (ROI): {roi:,.2f} %")
    print("-" * 60)
    print(f"📊 最大ロット数: {max_lot:,} 通貨")
    print(f"⚠️ 最大ドローダウン: -{max_drawdown:,.0f} 円")
    print(f"💀 最低残高: {min_equity:,.0f} 円")

    # 年別パフォーマンス
    print("\n📅 年別パフォーマンス:")
    print("-" * 60)

    yearly_data = data['Equity'].resample('Y').last()
    prev_equity = INITIAL_CAPITAL

    for year, equity in yearly_data.items():
        yearly_profit = equity - prev_equity
        yearly_roi = (yearly_profit / prev_equity) * 100 if prev_equity > 0 else 0
        print(f"  {year.year}年: {equity:,.0f}円 (年利: {yearly_roi:+.1f}%)")
        prev_equity = equity

    # ロスカット判定
    print("-" * 60)
    if min_equity < 100000:
        print("❌ 【警告】途中で資金ショートしています！")
    else:
        print("✅ 【合格】安全に運用できました。")

    # グラフ化
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # 資産推移
    ax1.plot(data.index, data['Equity'], label='Equity (複利運用)', color='blue')
    ax1.axhline(y=INITIAL_CAPITAL, color='red', linestyle='--', label='Start (100万円)')
    ax1.set_title('複利運用バックテスト: 資産推移')
    ax1.set_ylabel('資産 (円)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # ロット推移
    ax2.fill_between(data.index, data['Lot'], alpha=0.5, label='ロット数', color='green')
    ax2.set_title('ロット数の推移（複利効果）')
    ax2.set_ylabel('通貨数')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("compound_result.png")
    print("\n📊 グラフを 'compound_result.png' に保存しました。")

    return final_equity, roi

if __name__ == "__main__":
    run_compound_simulation()
