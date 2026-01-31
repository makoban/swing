from flask import Flask, render_template, jsonify
from sqlalchemy import create_engine, text
import os
from datetime import datetime
import pytz

app = Flask(__name__)

DB_URL = os.getenv("DB_CONNECTION_STRING")

def get_engine():
    return create_engine(DB_URL)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """現在の資産状況"""
    engine = get_engine()
    with engine.connect() as conn:
        # 設定取得
        result = conn.execute(text("SELECT initial_capital, current_balance FROM sim_config LIMIT 1"))
        config = result.fetchone()

        if not config:
            return jsonify({"error": "No config found"}), 404

        initial_capital = float(config[0])
        balance = float(config[1])

        # オープンポジション
        result = conn.execute(text("""
            SELECT id, direction, entry_price, current_price, units,
                   unrealized_pnl, swap_total, entry_time
            FROM sim_positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC
        """))
        positions = []
        total_unrealized = 0
        for row in result:
            unrealized = float(row[5]) if row[5] else 0
            swap = float(row[6]) if row[6] else 0
            total_pnl = unrealized + swap
            total_unrealized += total_pnl
            positions.append({
                "id": row[0],
                "direction": row[1],
                "entry_price": float(row[2]),
                "current_price": float(row[3]) if row[3] else None,
                "units": row[4],
                "unrealized_pnl": unrealized,
                "swap_total": swap,
                "total_pnl": total_pnl,
                "entry_time": row[7].isoformat() if row[7] else None
            })

        equity = balance + total_unrealized
        total_profit = equity - initial_capital
        profit_rate = (total_profit / initial_capital) * 100

        # 最新の金利情報
        result = conn.execute(text("""
            SELECT tnx_value, usdjpy_value, timestamp
            FROM sim_equity_log
            ORDER BY timestamp DESC LIMIT 1
        """))
        latest = result.fetchone()

        return jsonify({
            "initial_capital": initial_capital,
            "balance": balance,
            "equity": equity,
            "unrealized_pnl": total_unrealized,
            "total_profit": total_profit,
            "profit_rate": profit_rate,
            "positions": positions,
            "tnx_value": float(latest[0]) if latest and latest[0] else None,
            "usdjpy_value": float(latest[1]) if latest and latest[1] else None,
            "last_update": latest[2].isoformat() if latest and latest[2] else None
        })

@app.route('/api/history')
def api_history():
    """取引履歴"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, direction, entry_price, exit_price, units,
                   gross_pnl, spread_cost, swap_total, net_pnl,
                   entry_time, exit_time
            FROM sim_trade_history
            ORDER BY exit_time DESC
            LIMIT 50
        """))

        history = []
        for row in result:
            history.append({
                "id": row[0],
                "direction": row[1],
                "entry_price": float(row[2]),
                "exit_price": float(row[3]),
                "units": row[4],
                "gross_pnl": float(row[5]) if row[5] else 0,
                "spread_cost": float(row[6]) if row[6] else 0,
                "swap_total": float(row[7]) if row[7] else 0,
                "net_pnl": float(row[8]) if row[8] else 0,
                "entry_time": row[9].isoformat() if row[9] else None,
                "exit_time": row[10].isoformat() if row[10] else None
            })

        # 集計
        result = conn.execute(text("""
            SELECT COUNT(*), SUM(net_pnl),
                   SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM sim_trade_history
        """))
        stats = result.fetchone()
        total_trades = stats[0] or 0
        total_pnl = float(stats[1]) if stats[1] else 0
        wins = stats[2] or 0
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        return jsonify({
            "history": history,
            "stats": {
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "wins": wins,
                "losses": total_trades - wins,
                "win_rate": win_rate
            }
        })

@app.route('/api/equity')
def api_equity():
    """資産推移"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT timestamp, balance, equity, unrealized_pnl, tnx_value, usdjpy_value
            FROM sim_equity_log
            ORDER BY timestamp DESC
            LIMIT 168
        """))  # 過去7日分 (24h x 7days)

        data = []
        for row in result:
            data.append({
                "timestamp": row[0].isoformat() if row[0] else None,
                "balance": float(row[1]) if row[1] else 0,
                "equity": float(row[2]) if row[2] else 0,
                "unrealized_pnl": float(row[3]) if row[3] else 0,
                "tnx_value": float(row[4]) if row[4] else None,
                "usdjpy_value": float(row[5]) if row[5] else None
            })

        return jsonify({"equity_history": list(reversed(data))})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
