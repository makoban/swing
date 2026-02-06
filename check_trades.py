from sqlalchemy import create_engine, text
import os
from datetime import timezone, timedelta

DB_URL = os.getenv("DB_CONNECTION_STRING")
engine = create_engine(DB_URL)
JST = timezone(timedelta(hours=9))

with engine.connect() as conn:
    print("WAIT Strategy (A Plan) Trade History")
    print("=" * 50)

    # Closed trades
    r = conn.execute(text("""
        SELECT direction, entry_time, exit_time, entry_price, exit_price, units, net_pnl
        FROM sim_trade_history ORDER BY entry_time
    """)).fetchall()

    print(f"\nClosed Trades: {len(r)}")
    for row in r:
        entry_jst = row[1].replace(tzinfo=timezone.utc).astimezone(JST)
        exit_jst = row[2].replace(tzinfo=timezone.utc).astimezone(JST) if row[2] else None
        print(f"  {row[0]} | Entry: {entry_jst.strftime('%Y-%m-%d %H:%M')} JST | Exit: {exit_jst.strftime('%Y-%m-%d %H:%M') if exit_jst else '-'} JST | {row[5]:,} units | PnL: {row[6]:+,.0f}")

    # Open positions
    r2 = conn.execute(text("""
        SELECT direction, entry_time, entry_price, current_price, units, unrealized_pnl, swap_total
        FROM sim_positions WHERE status = 'OPEN' ORDER BY entry_time
    """)).fetchall()

    print(f"\nOpen Positions: {len(r2)}")
    for row in r2:
        entry_jst = row[1].replace(tzinfo=timezone.utc).astimezone(JST)
        print(f"  {row[0]} | Entry: {entry_jst.strftime('%Y-%m-%d %H:%M')} JST @ {row[2]:.2f} | {row[4]:,} units | P/L: {row[5]:+,.0f} Swap: {row[6]:+,.0f}")
