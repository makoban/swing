import pandas as pd
from sqlalchemy import create_engine
import numpy as np
import matplotlib.pyplot as plt

# 日本語フォント設定（文字化け対策）
import matplotlib_inline
from matplotlib import rcParams
rcParams['font.sans-serif'] = ['Meiryo', 'Yu Gothic', 'Hiragino Maru Gothic Pro']

# 接続情報
DB_CONNECTION_STRING = "postgresql://kokotomo_staging_user:MdaXINo3sbdaPy1cPwp7lvnm8O7SLdLq@dpg-d52du3nfte5s73d3ni6g-a.singapore-postgres.render.com/kokotomo_staging"

def plot_equity_curve():
    engine = create_engine(DB_CONNECTION_STRING)

    # データを取得
    print("📊 グラフ描画用データを取得中...")
    query = "SELECT date, ticker, close FROM market_data ORDER BY date"
    df = pd.read_sql(query, engine)

    # 整形
    data = df.pivot(index='date', columns='ticker', values='close')

    # 【修正ポイント】ここで日付を「Pandasが扱いやすい型」に強制変換します
    data.index = pd.to_datetime(data.index)

    data = data.ffill().dropna() # 欠損埋め（ffillを使用）
    returns = data.pct_change()
    target = returns['JPY=X'].shift(-1) # 翌日のドル円の動き

    # ==========================================
    # 最強戦略：金利連動のみを抽出
    # ==========================================
    # 金利が上がれば(>0) 買い(1)、下がれば 売り(-1)
    signal = np.where(returns['^TNX'] > 0, 1, -1)

    # 日々のリターン
    strategy_returns = signal * target

    # 累積リターン（資産曲線）を計算 (初期資産100として計算)
    equity_curve = (1 + strategy_returns).cumprod() * 100

    # ==========================================
    # グラフ描画
    # ==========================================
    print("📈 グラフを作成しています...")
    plt.figure(figsize=(12, 6))

    # 資産曲線
    plt.plot(equity_curve.index, equity_curve, label='Interest Rate Strategy', color='gold', linewidth=1)

    # 比較用：何もしないでドル円を持ち続けた場合（Buy & Hold）
    buy_hold = (1 + target).cumprod() * 100
    plt.plot(buy_hold.index, buy_hold, label='Buy & Hold (USD/JPY)', color='gray', linestyle='--', alpha=0.5)

    plt.title('Backtest: Interest Rate Strategy (1996-2026)', fontsize=14)
    plt.ylabel('Assets (Log Scale)')
    plt.yscale('log') # 桁が大きすぎるので対数グラフにする
    plt.grid(True, which="both", ls="-", alpha=0.2)
    plt.legend()

    # 保存して表示
    filename = "result_graph.png"
    plt.savefig(filename)
    print(f"✅ グラフを保存しました: {filename}")

    # 直近5年の成績を表示
    # data.indexを変換したので、ここでエラーが出なくなります
    recent = strategy_returns['2021':]

    print(f"\n📅 直近5年 (2021-2026) の成績:")
    roi_recent = ((1 + recent).prod() - 1) * 100
    win_rate_recent = len(recent[recent > 0]) / len(recent) * 100

    print(f"   ROI: {roi_recent:.2f}%")
    print(f"   Win Rate: {win_rate_recent:.2f}%")

if __name__ == "__main__":
    plot_equity_curve()
