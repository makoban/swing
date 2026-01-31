import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# 接続情報
DB_CONNECTION_STRING = "postgresql://kokotomo_staging_user:MdaXINo3sbdaPy1cPwp7lvnm8O7SLdLq@dpg-d52du3nfte5s73d3ni6g-a.singapore-postgres.render.com/kokotomo_staging"

def test_swing_strategy():
    print("🚀 データベースからデータを取得中...")
    engine = create_engine(DB_CONNECTION_STRING)

    # データを取得
    query = "SELECT date, ticker, close FROM market_data ORDER BY date"
    df = pd.read_sql(query, engine)
    data = df.pivot(index='date', columns='ticker', values='close').ffill().dropna()

    # 1. シグナル計算：昨日の金利(^TNX)と比較
    # shift(1)で「前日」の金利を見る
    prev_rate = data['^TNX'].shift(1)
    curr_rate = data['^TNX']

    # 金利が前日より高いなら「買いポジション(1)」、低いなら「売りポジション(-1)」
    # これを「その日ずっと持ち続ける」状態にする
    position = np.where(curr_rate > prev_rate, 1, -1)

    # positionを1つずらす（今日の金利を見て、明日ポジションを持つから）
    # これで「NYクローズ確認後にエントリー」を再現
    trade_position = pd.Series(position, index=data.index).shift(1).dropna()

    # 2. ドル円の日々の変動率
    jpy_returns = data['JPY=X'].pct_change().dropna()

    # インデックスを合わせる
    common_idx = trade_position.index.intersection(jpy_returns.index)
    trade_position = trade_position.loc[common_idx]
    jpy_returns = jpy_returns.loc[common_idx]

    # 3. 損益計算（持ちっぱなし）
    strategy_returns = trade_position * jpy_returns

    # 取引回数を計算（ポジションが入れ替わった回数）
    # diff()が0じゃない＝サインが変わった
    trade_count = (trade_position.diff() != 0).sum()

    # 結果集計
    cumulative_returns = (1 + strategy_returns).cumprod()
    final_roi = (cumulative_returns.iloc[-1] - 1) * 100
    win_days = len(strategy_returns[strategy_returns > 0])
    total_days = len(strategy_returns)
    win_rate = win_days / total_days * 100

    print("\n⚔️ 【スイングトレード（持ちっぱなし）】の結果 ⚔️")
    print("-" * 60)
    print(f"💰 最終ROI: {final_roi:,.0f}%")
    print(f"📊 勝率(日次): {win_rate:.2f}%")
    print(f"🔄 売買回数: {trade_count} 回 (30年間で)")
    print(f"📅 平均保有日数: {total_days / trade_count:.1f} 日")
    print("-" * 60)

    if final_roi > 1000:
         print("🎉 結論: これが正解です！「毎日売買」ではなく「トレンドに乗る」のが最強です。")

if __name__ == "__main__":
    test_swing_strategy()
