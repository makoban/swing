import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# ==========================================
# 1. 設定：Renderの接続情報
# ==========================================
DB_CONNECTION_STRING = "postgresql://kokotomo_staging_user:MdaXINo3sbdaPy1cPwp7lvnm8O7SLdLq@dpg-d52du3nfte5s73d3ni6g-a.singapore-postgres.render.com/kokotomo_staging"

def run_backtest():
    print("🚀 データベースからデータを取得中...")
    engine = create_engine(DB_CONNECTION_STRING)

    # 全データを取得（必要なカラムだけ）
    query = "SELECT date, ticker, close FROM market_data ORDER BY date"
    df = pd.read_sql(query, engine)

    # 2. データを分析しやすい形（ピボット）に変換
    # 日付をインデックスに、銘柄を列にする
    # 結果イメージ:
    # date       | JPY=X  | ^TNX  | ^GSPC
    # 2000-01-01 | 102.5  | 6.5   | 1450
    data = df.pivot(index='date', columns='ticker', values='close')

    # 欠損値を前の日の値で埋める（土日や祝日のズレ対策）
    data = data.fillna(method='ffill').dropna()

    # 3. 前日比（変化率）を計算
    returns = data.pct_change()

    # ドル円の翌日の動き（これを予測したい＝正解データ）
    # shift(-1)で「1日後の変化率」を現在の行に持ってくる
    target = returns['JPY=X'].shift(-1)

    print(f"📊 分析対象期間: {data.index.min()} 〜 {data.index.max()}")
    print(f"📅 データ数: {len(data)} 日分\n")

    # ==========================================
    # 4. 戦略の定義（ここにアイデアを詰め込む）
    # ==========================================
    strategies = {}

    # 【戦略A】米国金利連動（金利が上がれば買い、下がれば売り）
    # ロジック: 今日の金利(^TNX)が前日比プラスなら、明日ドル円を買う
    strategies['Interest_Rate_Follow'] = np.where(returns['^TNX'] > 0, 1, -1)

    # 【戦略B】米国株連動（株が上がれば買い）
    # ロジック: S&P500(^GSPC)がプラスなら買い
    strategies['Stock_Risk_On'] = np.where(returns['^GSPC'] > 0, 1, -1)

    # 【戦略C】日経平均連動（日経が上がれば買い）
    strategies['Nikkei_Follow'] = np.where(returns['^N225'] > 0, 1, -1)

    # 【戦略D】トレンドフォロー（ドル円自体の勢いに乗る）
    # ロジック: ドル円が今日上がっていれば明日も買い
    strategies['Momentum_Follow'] = np.where(returns['JPY=X'] > 0, 1, -1)

    # 【戦略E】逆張り（ドル円が下がっていたら、反発狙いで買い）
    strategies['Mean_Reversion'] = np.where(returns['JPY=X'] < 0, 1, -1)

    # ==========================================
    # 5. シミュレーション実行と結果集計
    # ==========================================
    results = []

    print("⚔️  バックテスト結果ランキング (ROI順) ⚔️")
    print("-" * 60)
    print(f"{'Strategy Name':<25} | {'ROI (%)':<10} | {'Win Rate':<10} | {'Trade Count'}")
    print("-" * 60)

    for name, signal in strategies.items():
        # 損益計算: シグナル(1 or -1) × 翌日のドル円の動き
        # ※取引コスト（スプレッド）は一旦考慮せず、純粋な予測力を測る
        strategy_returns = signal * target

        # 累積リターン（複利）を計算
        cumulative_returns = (1 + strategy_returns).cumprod()

        # 最終的なROI（何倍になったか - 1）* 100
        final_roi = (cumulative_returns.iloc[-2] - 1) * 100

        # 勝率計算
        wins = len(strategy_returns[strategy_returns > 0])
        total = len(strategy_returns.dropna())
        win_rate = (wins / total) * 100 if total > 0 else 0

        results.append({
            'name': name,
            'roi': final_roi,
            'win_rate': win_rate,
            'count': total
        })

    # ROIが高い順にソートして表示
    results.sort(key=lambda x: x['roi'], reverse=True)

    for res in results:
        print(f"{res['name']:<25} | {res['roi']:>9.2f}% | {res['win_rate']:>9.2f}% | {res['count']}")
    print("-" * 60)

if __name__ == "__main__":
    run_backtest()
