# FX自動売買システム

## 概要
米国10年債金利のトレンドに基づくドル円自動売買システム

## 戦略
- 金利上昇 → ドル買い (BUY)
- 金利下落 → ドル売り (SELL)
- トレンド反転時 → ドテン

## 環境変数
- `DB_CONNECTION_STRING`: PostgreSQL接続URL

## 実行
```bash
python main.py
```

## 依存関係
```bash
pip install -r requirements.txt
```
