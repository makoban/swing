import pandas as pd
import yfinance as yf
import numpy as np

# 設定
INITIAL_CAPITAL = 1_000_000  # 予算100万円
SPREAD = 0.004
SWAP_PER_DAY = 100

def find_optimal_lot():
    print("🚀 最適なロット数を探しています...")

    # データ取得
    df = yf.download(['^TNX', 'JPY=X'], period="max", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)
    data = df.dropna()

    # シグナル生成
    tnx_change = data['^TNX'] - data['^TNX'].shift(1)
    signal = np.where(tnx_change > 0, 1, 0)
    data['Signal'] = pd.Series(signal, index=data.index).shift(1)

    # ロット数を 0.5万 〜 6万 まで変えてテスト
    best_lot = 0
    best_profit = 0
    safe_lot_limit = 0

    # 0.1万通貨（1000通貨）刻みでループ
    for lot in range(1000, 61000, 1000):
        cash = INITIAL_CAPITAL
        position = 0
        min_equity = INITIAL_CAPITAL
        buy_price = 0

        # 高速化のため簡易計算ループ
        equity_history = []

        for i in range(len(data)):
            price = data['JPY=X'].iloc[i]
            today_signal = data['Signal'].iloc[i]

            # 資産評価
            current_equity = cash
            if position == 1:
                unrealized = (price - buy_price) * lot
                current_equity += unrealized

            # 最低資金を更新
            if current_equity < min_equity:
                min_equity = current_equity

            # ロスカット判定 (証拠金維持率無視で、単純に資金枯渇を見る)
            if current_equity <= 100000: # 証拠金込みで残り10万切ったら死亡とみなす
                min_equity = -1 # 死亡フラグ
                break

            # アクション
            if position == 0 and today_signal == 1:
                position = 1
                buy_price = price + SPREAD
            elif position == 1 and today_signal == 0:
                position = 0
                profit = (price - buy_price) * lot
                cash += profit
            elif position == 1 and today_signal == 1:
                daily_swap = (SWAP_PER_DAY * (lot / 10000))
                cash += daily_swap

        # 生存チェック
        if min_equity > 300000: # 最悪期でも30万以上残った
            safe_lot_limit = lot
            final_profit = cash - INITIAL_CAPITAL

            if final_profit > best_profit:
                best_profit = final_profit
                best_lot = lot

            print(f"✅ {lot/10000}万通貨: 生存 (最低残高: {min_equity:,.0f}円) -> 利益: {final_profit:,.0f}円")
        else:
            print(f"💀 {lot/10000}万通貨: 死亡 (資金ショート)")
            # これ以上増やしても死ぬだけなのでループ終了
            break

    print("-" * 50)
    print(f"👑 結論: 予算100万円での最強ロットは 【 {best_lot} 通貨 ({best_lot/10000}万通貨) 】 です！")
    print(f"💰 その場合の30年利益: +{best_profit:,.0f} 円")

if __name__ == "__main__":
    find_optimal_lot()
