import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# 接続情報
DB_CONNECTION_STRING = "postgresql://kokotomo_staging_user:MdaXINo3sbdaPy1cPwp7lvnm8O7SLdLq@dpg-d52du3nfte5s73d3ni6g-a.singapore-postgres.render.com/kokotomo_staging"

def compare_timing():
    print("🚀 データベースからデータを取得中...")
    engine = create_engine(DB_CONNECTION_STRING)

    # openとcloseの両方を取得
    query = "SELECT date, ticker, open, close FROM market_data ORDER BY date"
    df = pd.read_sql(query, engine)

    # データをピボット（整形）
    # 終値の表
    close_data = df.pivot(index='date', columns='ticker', values='close').ffill().dropna()
    # 始値の表
    open_data = df.pivot(index='date', columns='ticker', values='open').ffill().dropna()

    # 共通の期間に揃える
    common_index = close_data.index.intersection(open_data.index)
    close_data = close_data.loc[common_index]
    open_data = open_data.loc[common_index]

    # 1. シグナル計算：昨日の金利(^TNX)が上がったかどうか？
    # 前日の終値ベースで計算
    rate_change = close_data['^TNX'].pct_change().shift(1)

    # シグナル: 金利上昇なら1(買い)、下落なら-1(売り)
    signal = np.where(rate_change > 0, 1, -1)

    # -------------------------------------------------------
    # 2. 戦略比較
    # -------------------------------------------------------

    # 【パターンA】前回と同じ（Close to Close）
    # 昨日持っていたポジションを持ち越した場合のリターン
    # (今日の終値 - 昨日の終値) / 昨日の終値
    ret_close_to_close = close_data['JPY=X'].pct_change()
    strat_A = signal * ret_close_to_close

    # 【パターンB】今回の提案（Open to Close）
    # 朝イチ(Open)でエントリーして、その日の終わり(Close)で決済
    # (今日の終値 - 今日の始値) / 今日の始値
    ret_open_to_close = (close_data['JPY=X'] - open_data['JPY=X']) / open_data['JPY=X']
    strat_B = signal * ret_open_to_close

    # -------------------------------------------------------
    # 3. 結果発表
    # -------------------------------------------------------
    print("\n⚔️ 【朝のエントリー】vs【持ち越し】どっちが勝てる？ ⚔️")
    print("-" * 60)

    # パターンAの結果
    roi_A = ((1 + strat_A).cumprod().iloc[-1] - 1) * 100
    win_A = len(strat_A[strat_A > 0]) / len(strat_A) * 100
    print(f"🅰️ パターンA (昨日の終値から保有):")
    print(f"   ROI: {roi_A:,.0f}% | 勝率: {win_A:.2f}%")

    print("-" * 30)

    # パターンBの結果
    roi_B = ((1 + strat_B).cumprod().iloc[-1] - 1) * 100
    win_B = len(strat_B[strat_B > 0]) / len(strat_B) * 100
    print(f"🅱️ パターンB (朝イチOpenでエントリー):")
    print(f"   ROI: {roi_B:,.0f}% | 勝率: {win_B:.2f}%")

    print("-" * 60)

    if roi_B > roi_A:
        print("🎉 結論: 「朝起きてから注文」の方が優秀です！時系列の心配はありません。")
    else:
        print("🤔 結論: 「NY時間からの持ち越し」の方が利益が大きいです。夜ふかしが必要かも？")

if __name__ == "__main__":
    compare_timing()
