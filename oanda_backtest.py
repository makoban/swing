import pandas as pd
import yfinance as yf
import numpy as np
import matplotlib.pyplot as plt
import matplotlib_inline
from matplotlib import rcParams

# 日本語フォント設定
rcParams['font.sans-serif'] = ['Meiryo', 'Yu Gothic', 'Hiragino Maru Gothic Pro']

# ==========================================
# ⚙️ OANDAシミュレーション設定 (予算100万円)
# ==========================================
INITIAL_CAPITAL = 1_000_000  # 開始資金: 100万円
LOT_SIZE = 60_000            # 取引数量: 6万通貨
SPREAD = 0.004               # スプレッド: 0.4銭 (0.004円)
SWAP_PER_DAY = 100           # スワップ: 1万通貨あたり1日100円 (買い)
                             # ※実際は金利差で変動しますが、平均値として固定計算します

def run_oanda_simulation():
    print("🚀 OANDA仕様でバックテストを開始します...")

    # 1. データの取得
    # ^TNX(金利) と JPY=X(ドル円)
    tickers = ['^TNX', 'JPY=X']
    df = yf.download(tickers, period="max", auto_adjust=True, progress=False)

    # MultiIndex対策
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs('Close', level=0, axis=1)

    # データ整形
    data = df.dropna()

    # 2. トレンド判定 (金利が前日より上がったら買い)
    # shift(1) = 昨日の値
    tnx_change = data['^TNX'] - data['^TNX'].shift(1)

    # シグナル: 1=買い相場, 0=休み(現金)
    # ※「前日の金利」を見て「今日の朝」判断するため、シグナルを1日ずらす(shift 1)
    signal = np.where(tnx_change > 0, 1, 0)
    data['Signal'] = pd.Series(signal, index=data.index).shift(1) # 当日の朝の行動

    # ==========================================
    # 💰 資産推移の計算 (1日ごとの残高計算)
    # ==========================================
    cash = INITIAL_CAPITAL
    position = 0 # 0 or 1 (持ってるか持ってないか)
    equity_curve = [] # 資産推移の記録用

    buy_price = 0 # エントリー価格

    print(f"📊 期間: {data.index[0].date()} 〜 {data.index[-1].date()}")
    print("-" * 60)

    # 1行ずつループして「財布の中身」を計算 (これが一番正確)
    for i in range(len(data)):
        date = data.index[i]
        price = data['JPY=X'].iloc[i]     # 今日の終値
        today_signal = data['Signal'].iloc[i] # 今日の指示

        # 前日の状態を引き継ぐ
        current_equity = cash

        # --- アクション判定 ---

        # A. 新規買い (ポジションなし & 買いシグナル)
        if position == 0 and today_signal == 1:
            position = 1
            # スプレッドコストを引いた価格で買う（不利になる）
            buy_price = price + SPREAD
            # 証拠金はcash内にあるとみなす（余力計算は省略）

        # B. 決済して逃げる (ポジションあり & 休みシグナル)
        elif position == 1 and today_signal == 0:
            position = 0
            sell_price = price # 売値

            # 利益確定 or 損切り
            profit = (sell_price - buy_price) * LOT_SIZE
            cash += profit

            buy_price = 0 # リセット

        # C. 保有継続 (ポジションあり & 買いシグナル)
        elif position == 1 and today_signal == 1:
            # 何もしないが、スワップポイントが貰える
            # 6万通貨なら、1万通貨あたり100円 × 6 = 600円/日
            daily_swap = (SWAP_PER_DAY * (LOT_SIZE / 10000))
            cash += daily_swap

        # --- 資産評価額の計算 (含み益込み) ---
        if position == 1:
            # (今の価格 - 買った価格) * 数量 + 現金(確定済み利益+スワップ)
            unrealized_pnl = (price - buy_price) * LOT_SIZE
            current_equity = cash + unrealized_pnl
        else:
            current_equity = cash

        equity_curve.append(current_equity)

    # データフレームに追加
    data['Equity'] = equity_curve

    # ==========================================
    # 📈 結果表示
    # ==========================================
    final_equity = data['Equity'].iloc[-1]
    roi = ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    max_drawdown = (data['Equity'].cummax() - data['Equity']).max()
    min_equity = data['Equity'].min()

    print(f"💰 開始資金: {INITIAL_CAPITAL:,} 円")
    print(f"🏁 終了資金: {final_equity:,.0f} 円")
    print(f"🚀 最終利益: +{final_equity - INITIAL_CAPITAL:,.0f} 円")
    print(f"📈 収益率 (ROI): {roi:,.2f} %")
    print("-" * 60)
    print(f"⚠️ 最大ドローダウン(一時的な評価損): -{max_drawdown:,.0f} 円")
    print(f"💀 最も資金が減った時の残高: {min_equity:,.0f} 円")

    if min_equity < 370000: # 証拠金(約37万)を割ったらアウト
        print("❌ 【警告】途中で資金ショート(ロスカット)しています！ロットを減らしてください。")
    else:
        print("✅ 【合格】一度もロスカットされずに運用できました。")

    # グラフ化
    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data['Equity'], label='Total Equity (Cash + Position)', color='blue')
    plt.axhline(y=INITIAL_CAPITAL, color='red', linestyle='--', label='Start Line (100万)')
    plt.title('OANDA Simulation: Long Only Strategy (Swap & Spread Included)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.savefig("oanda_result.png")
    print("📊 資産推移グラフを 'oanda_result.png' に保存しました。")

if __name__ == "__main__":
    run_oanda_simulation()
