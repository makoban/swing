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

        # 20日MA計算（過去20件の平均）
        result = conn.execute(text("""
            SELECT AVG(tnx_value)
            FROM (SELECT tnx_value FROM sim_equity_log ORDER BY timestamp DESC LIMIT 20) sub
        """))
        ma20_row = result.fetchone()
        tnx_ma20 = float(ma20_row[0]) if ma20_row and ma20_row[0] else None

        # トレンド判定
        tnx_value = float(latest[0]) if latest and latest[0] else None
        if tnx_value and tnx_ma20:
            trend_status = "UP" if tnx_value > tnx_ma20 else "DOWN"
        else:
            trend_status = "UNKNOWN"

        return jsonify({
            "initial_capital": initial_capital,
            "balance": balance,
            "equity": equity,
            "unrealized_pnl": total_unrealized,
            "total_profit": total_profit,
            "profit_rate": profit_rate,
            "positions": positions,
            "tnx_value": tnx_value,
            "tnx_ma20": tnx_ma20,
            "trend_status": trend_status,
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

# ==========================================
# デイトレ戦略用API
# ==========================================

@app.route('/api/daytrade/status')
def api_daytrade_status():
    """デイトレ戦略の現在状況"""
    engine = get_engine()
    with engine.connect() as conn:
        # 設定取得
        result = conn.execute(text("""
            SELECT initial_capital, current_balance, lot_ratio, take_profit, stop_loss
            FROM sim_daytrade_config LIMIT 1
        """))
        config = result.fetchone()

        if not config:
            return jsonify({"error": "No daytrade config found", "exists": False}), 200

        initial_capital = float(config[0])
        balance = float(config[1])
        lot_ratio = float(config[2])
        take_profit = float(config[3])
        stop_loss = float(config[4])

        # オープンポジション
        result = conn.execute(text("""
            SELECT id, direction, entry_price, current_price, units, unrealized_pnl, entry_time
            FROM sim_daytrade_positions
            WHERE status = 'OPEN'
            ORDER BY entry_time DESC LIMIT 1
        """))
        position = result.fetchone()

        pos_data = None
        total_unrealized = 0
        if position:
            unrealized = float(position[5]) if position[5] else 0
            total_unrealized = unrealized
            pos_data = {
                "id": position[0],
                "direction": position[1],
                "entry_price": float(position[2]),
                "current_price": float(position[3]) if position[3] else None,
                "units": position[4],
                "unrealized_pnl": unrealized,
                "entry_time": position[6].isoformat() if position[6] else None
            }

        equity = balance + total_unrealized
        total_profit = equity - initial_capital
        profit_rate = (total_profit / initial_capital) * 100

        # 取引統計
        result = conn.execute(text("""
            SELECT COUNT(*), SUM(pnl),
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN action = 'TAKE_PROFIT' THEN 1 ELSE 0 END) as tp_count,
                   SUM(CASE WHEN action = 'STOP_LOSS' THEN 1 ELSE 0 END) as sl_count,
                   SUM(CASE WHEN action = 'FORCE_CLOSE' THEN 1 ELSE 0 END) as forced_count
            FROM sim_daytrade_history
        """))
        stats = result.fetchone()

        return jsonify({
            "exists": True,
            "initial_capital": initial_capital,
            "balance": balance,
            "equity": equity,
            "unrealized_pnl": total_unrealized,
            "total_profit": total_profit,
            "profit_rate": profit_rate,
            "settings": {
                "lot_ratio": lot_ratio,
                "take_profit": take_profit,
                "stop_loss": stop_loss
            },
            "position": pos_data,
            "stats": {
                "total_trades": stats[0] or 0,
                "total_pnl": float(stats[1]) if stats[1] else 0,
                "wins": stats[2] or 0,
                "tp_count": stats[3] or 0,
                "sl_count": stats[4] or 0,
                "forced_count": stats[5] or 0,
                "win_rate": ((stats[2] or 0) / (stats[0] or 1)) * 100
            }
        })

@app.route('/api/daytrade/history')
def api_daytrade_history():
    """デイトレ取引履歴"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, direction, entry_price, exit_price, units, pnl, action, exit_time
            FROM sim_daytrade_history
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
                "pnl": float(row[5]) if row[5] else 0,
                "action": row[6],
                "exit_time": row[7].isoformat() if row[7] else None
            })

        return jsonify({"history": history})

# ==========================================
# 統合API（2つの財布ビュー用）
# ==========================================

@app.route('/api/wallets')
def api_wallets():
    """2つの戦略の財布サマリー"""
    engine = get_engine()
    with engine.connect() as conn:
        wallets = []

        # === スイング戦略 (WAIT) ===
        result = conn.execute(text("SELECT initial_capital, current_balance FROM sim_config LIMIT 1"))
        swing_config = result.fetchone()

        if swing_config:
            initial = float(swing_config[0])
            balance = float(swing_config[1])

            # ポジション集計
            result = conn.execute(text("""
                SELECT SUM(units), SUM(unrealized_pnl), SUM(swap_total),
                       STRING_AGG(direction, ',')
                FROM sim_positions WHERE status = 'OPEN'
            """))
            pos = result.fetchone()
            total_units = pos[0] or 0
            unrealized = float(pos[1] or 0) + float(pos[2] or 0)
            direction = pos[3].split(',')[0] if pos[3] else None

            equity = balance + unrealized
            profit_rate = ((equity - initial) / initial) * 100

            wallets.append({
                "strategy": "WAIT",
                "label": "🏄 スイング",
                "initial_capital": initial,
                "balance": balance,
                "equity": equity,
                "unrealized_pnl": unrealized,
                "profit_rate": profit_rate,
                "total_units": total_units,
                "direction": direction
            })

        # === デイトレ戦略 ===
        result = conn.execute(text("SELECT initial_capital, current_balance FROM sim_daytrade_config LIMIT 1"))
        dt_config = result.fetchone()

        if dt_config:
            initial = float(dt_config[0])
            balance = float(dt_config[1])

            # ポジション
            result = conn.execute(text("""
                SELECT units, unrealized_pnl, direction
                FROM sim_daytrade_positions WHERE status = 'OPEN' LIMIT 1
            """))
            pos = result.fetchone()
            total_units = pos[0] if pos else 0
            unrealized = float(pos[1]) if pos and pos[1] else 0
            direction = pos[2] if pos else None

            equity = balance + unrealized
            profit_rate = ((equity - initial) / initial) * 100

            wallets.append({
                "strategy": "DAY",
                "label": "⚡ デイトレ",
                "initial_capital": initial,
                "balance": balance,
                "equity": equity,
                "unrealized_pnl": unrealized,
                "profit_rate": profit_rate,
                "total_units": total_units,
                "direction": direction
            })

        return jsonify({"wallets": wallets})

@app.route('/api/history/combined')
def api_history_combined():
    """両戦略の取引履歴を統合"""
    engine = get_engine()
    with engine.connect() as conn:
        combined = []

        # スイング戦略の履歴
        result = conn.execute(text("""
            SELECT direction, entry_price, exit_price, units, net_pnl, exit_time
            FROM sim_trade_history
            ORDER BY exit_time DESC LIMIT 25
        """))
        for row in result:
            combined.append({
                "strategy": "WAIT",
                "strategy_label": "🏄 WAIT",
                "direction": row[0],
                "entry_price": float(row[1]),
                "exit_price": float(row[2]),
                "units": row[3],
                "pnl": float(row[4]) if row[4] else 0,
                "exit_time": row[5].isoformat() if row[5] else None
            })

        # デイトレ戦略の履歴
        result = conn.execute(text("""
            SELECT direction, entry_price, exit_price, units, pnl, exit_time
            FROM sim_daytrade_history
            ORDER BY exit_time DESC LIMIT 25
        """))
        for row in result:
            combined.append({
                "strategy": "DAY",
                "strategy_label": "⚡ DAY",
                "direction": row[0],
                "entry_price": float(row[1]),
                "exit_price": float(row[2]),
                "units": row[3],
                "pnl": float(row[4]) if row[4] else 0,
                "exit_time": row[5].isoformat() if row[5] else None
            })

        # 日時でソート
        combined.sort(key=lambda x: x["exit_time"] or "", reverse=True)

        return jsonify({"history": combined[:50]})

# ==========================================
# 実資金デイトレ用API (live_daytrade_*)
# ==========================================

# テーブル未作成時に返すデフォルト値
_LIVE_DEFAULT_BALANCE = 250000

def _table_exists(conn, table_name: str) -> bool:
    """指定テーブルがDBに存在するか確認する"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :tname
        )
    """), {"tname": table_name})
    row = result.fetchone()
    return bool(row and row[0])


@app.route('/live')
def live_dashboard():
    """実資金デイトレ ダッシュボード"""
    return render_template('live_dashboard.html')


@app.route('/api/live/status')
def api_live_status():
    """実資金デイトレの設定・残高・当日の状態"""
    default = {
        "initial_balance": _LIVE_DEFAULT_BALANCE,
        "current_balance": _LIVE_DEFAULT_BALANCE,
        "is_active": False,
        "environment": "practice",
        "settings": {
            "lot_ratio": 0.15,
            "take_profit": 0.15,
            "stop_loss": 0.20
        }
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_config"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT initial_balance, current_balance, is_active, environment,
                       lot_ratio, take_profit, stop_loss
                FROM live_daytrade_config LIMIT 1
            """))
            row = result.fetchone()
            if not row:
                return jsonify(default)

            return jsonify({
                "initial_balance": float(row[0]),
                "current_balance": float(row[1]),
                "is_active": bool(row[2]),
                "environment": row[3],
                "settings": {
                    "lot_ratio": float(row[4]),
                    "take_profit": float(row[5]),
                    "stop_loss": float(row[6])
                }
            })
    except Exception:
        return jsonify(default)


@app.route('/api/live/positions')
def api_live_positions():
    """実資金デイトレの現在保有ポジション"""
    default = {"positions": []}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_positions"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT oanda_trade_id, side, units, entry_price,
                       take_profit_price, stop_loss_price,
                       entry_reason, unrealized_pnl, opened_at
                FROM live_daytrade_positions
                WHERE status = 'OPEN'
                ORDER BY opened_at DESC
            """))

            positions = []
            for row in result:
                positions.append({
                    "oanda_trade_id": row[0],
                    "side": row[1],
                    "units": row[2],
                    "entry_price": float(row[3]),
                    "take_profit_price": float(row[4]) if row[4] else None,
                    "stop_loss_price": float(row[5]) if row[5] else None,
                    "entry_reason": row[6],
                    "unrealized_pnl": float(row[7]) if row[7] else 0,
                    "opened_at": row[8].isoformat() if row[8] else None
                })

            return jsonify({"positions": positions})
    except Exception:
        return jsonify(default)


@app.route('/api/live/history')
def api_live_history():
    """実資金デイトレの日付別売買理由付き履歴"""
    default = {"by_date": []}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_history"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT id, side, units, entry_price, exit_price,
                       entry_reason, exit_reason, pnl,
                       spread_cost, commission, swap, net_pnl,
                       opened_at, closed_at,
                       EXTRACT(EPOCH FROM (closed_at - opened_at)) / 60 AS holding_minutes,
                       DATE(closed_at AT TIME ZONE 'Asia/Tokyo') AS trade_date
                FROM live_daytrade_history
                ORDER BY closed_at DESC
                LIMIT 200
            """))

            # 日付ごとに集計
            from collections import defaultdict
            date_map: dict = defaultdict(lambda: {
                "date": None,
                "daily_pnl": 0.0,
                "trade_count": 0,
                "win_count": 0,
                "trades": []
            })

            for row in result:
                net_pnl = float(row[11]) if row[11] else 0.0
                trade_date = str(row[15])

                date_map[trade_date]["date"] = trade_date
                date_map[trade_date]["daily_pnl"] += net_pnl
                date_map[trade_date]["trade_count"] += 1
                if net_pnl > 0:
                    date_map[trade_date]["win_count"] += 1

                date_map[trade_date]["trades"].append({
                    "id": row[0],
                    "side": row[1],
                    "units": row[2],
                    "entry_price": float(row[3]),
                    "exit_price": float(row[4]) if row[4] else None,
                    "entry_reason": row[5],
                    "exit_reason": row[6],
                    "pnl": float(row[7]) if row[7] else 0,
                    "spread_cost": float(row[8]) if row[8] else 0,
                    "commission": float(row[9]) if row[9] else 0,
                    "swap": float(row[10]) if row[10] else 0,
                    "net_pnl": net_pnl,
                    "opened_at": row[12].isoformat() if row[12] else None,
                    "closed_at": row[13].isoformat() if row[13] else None,
                    "holding_minutes": round(float(row[14]), 1) if row[14] else None
                })

            by_date = sorted(date_map.values(), key=lambda d: d["date"] or "", reverse=True)
            return jsonify({"by_date": by_date})
    except Exception:
        return jsonify(default)


@app.route('/api/live/equity')
def api_live_equity():
    """実資金デイトレの資産推移ログ"""
    default = {
        "equity_log": [],
        "initial_balance": _LIVE_DEFAULT_BALANCE
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_equity_log"):
                return jsonify(default)

            # initial_balance を config から取得
            initial_balance = _LIVE_DEFAULT_BALANCE
            if _table_exists(conn, "live_daytrade_config"):
                r = conn.execute(text("SELECT initial_balance FROM live_daytrade_config LIMIT 1"))
                row = r.fetchone()
                if row:
                    initial_balance = float(row[0])

            result = conn.execute(text("""
                SELECT logged_at, balance, equity, unrealized_pnl, daily_pnl, roi_pct
                FROM live_daytrade_equity_log
                ORDER BY logged_at DESC
                LIMIT 500
            """))

            equity_log = []
            for row in result:
                equity_log.append({
                    "logged_at": row[0].isoformat() if row[0] else None,
                    "balance": float(row[1]) if row[1] else 0,
                    "equity": float(row[2]) if row[2] else 0,
                    "unrealized_pnl": float(row[3]) if row[3] else 0,
                    "daily_pnl": float(row[4]) if row[4] else 0,
                    "roi_pct": float(row[5]) if row[5] else 0
                })

            return jsonify({
                "equity_log": list(reversed(equity_log)),
                "initial_balance": initial_balance
            })
    except Exception:
        return jsonify(default)


@app.route('/api/live/costs')
def api_live_costs():
    """実資金デイトレの月別実コスト集計"""
    default = {
        "by_month": [],
        "total": {
            "spread_cost": 0,
            "commission": 0,
            "swap": 0,
            "total_cost": 0
        }
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_history"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT
                    TO_CHAR(closed_at AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS month,
                    SUM(spread_cost)   AS spread_cost,
                    SUM(commission)    AS commission,
                    SUM(swap)          AS swap,
                    SUM(spread_cost + commission - swap) AS total_cost,
                    COUNT(*)           AS trade_count
                FROM live_daytrade_history
                WHERE closed_at IS NOT NULL
                GROUP BY month
                ORDER BY month DESC
            """))

            by_month = []
            grand_spread = grand_commission = grand_swap = grand_total = 0.0

            for row in result:
                spread = float(row[1]) if row[1] else 0.0
                commission = float(row[2]) if row[2] else 0.0
                swap = float(row[3]) if row[3] else 0.0
                total = float(row[4]) if row[4] else 0.0

                by_month.append({
                    "month": row[0],
                    "spread_cost": spread,
                    "commission": commission,
                    "swap": swap,
                    "total_cost": total,
                    "trade_count": row[5]
                })

                grand_spread += spread
                grand_commission += commission
                grand_swap += swap
                grand_total += total

            return jsonify({
                "by_month": by_month,
                "total": {
                    "spread_cost": grand_spread,
                    "commission": grand_commission,
                    "swap": grand_swap,
                    "total_cost": grand_total
                }
            })
    except Exception:
        return jsonify(default)


@app.route('/api/live/daily-risk')
def api_live_daily_risk():
    """日次損失制限の状態"""
    jst = pytz.timezone('Asia/Tokyo')
    today_str = datetime.now(jst).strftime('%Y-%m-%d')

    default = {
        "trade_date": today_str,
        "daily_loss_limit": 12500,
        "daily_loss_realized": 0,
        "remaining": 12500,
        "is_trading_halted": False,
        "halt_reason": None
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daily_risk"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT trade_date, daily_loss_limit, daily_loss_realized,
                       is_trading_halted, halt_reason
                FROM live_daily_risk
                WHERE trade_date = CURRENT_DATE
                LIMIT 1
            """))
            row = result.fetchone()
            if not row:
                return jsonify(default)

            limit = float(row[1]) if row[1] else 12500.0
            realized = float(row[2]) if row[2] else 0.0

            return jsonify({
                "trade_date": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                "daily_loss_limit": limit,
                "daily_loss_realized": realized,
                "remaining": limit - realized,
                "is_trading_halted": bool(row[3]),
                "halt_reason": row[4]
            })
    except Exception:
        return jsonify(default)


@app.route('/api/live/summary')
def api_live_summary():
    """実資金デイトレの累計実績サマリー"""
    default = {
        "total_pnl": 0,
        "roi_pct": 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_spread_cost": 0,
        "total_commission": 0,
        "total_swap": 0,
        "total_cost": 0,
        "avg_holding_minutes": 0
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not _table_exists(conn, "live_daytrade_history"):
                return jsonify(default)

            result = conn.execute(text("""
                SELECT
                    COUNT(*)                                    AS total_trades,
                    SUM(net_pnl)                               AS total_pnl,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                    SUM(spread_cost)                           AS total_spread_cost,
                    SUM(commission)                            AS total_commission,
                    SUM(swap)                                  AS total_swap,
                    SUM(spread_cost + commission - swap)       AS total_cost,
                    AVG(EXTRACT(EPOCH FROM (closed_at - opened_at)) / 60) AS avg_holding_minutes
                FROM live_daytrade_history
                WHERE closed_at IS NOT NULL
            """))
            row = result.fetchone()

            if not row or not row[0]:
                return jsonify(default)

            # initial_balance で ROI を計算
            initial_balance = float(_LIVE_DEFAULT_BALANCE)
            if _table_exists(conn, "live_daytrade_config"):
                r = conn.execute(text("SELECT initial_balance FROM live_daytrade_config LIMIT 1"))
                cfg = r.fetchone()
                if cfg:
                    initial_balance = float(cfg[0])

            total_trades = int(row[0])
            total_pnl = float(row[1]) if row[1] else 0.0
            wins = int(row[2]) if row[2] else 0
            losses = total_trades - wins
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            roi_pct = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0.0

            return jsonify({
                "total_pnl": total_pnl,
                "roi_pct": round(roi_pct, 2),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2),
                "total_spread_cost": float(row[3]) if row[3] else 0,
                "total_commission": float(row[4]) if row[4] else 0,
                "total_swap": float(row[5]) if row[5] else 0,
                "total_cost": float(row[6]) if row[6] else 0,
                "avg_holding_minutes": round(float(row[7]), 1) if row[7] else 0
            })
    except Exception:
        return jsonify(default)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

