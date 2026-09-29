import sqlite3
from pathlib import Path

DB_PATH = Path("6thsense_state.db")

def _connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with _connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY, symbol TEXT, side TEXT, quantity INTEGER,
            price REAL, status TEXT, reason TEXT, created_at TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY, side TEXT, quantity INTEGER, entry REAL,
            stop_loss REAL, target REAL, opened_at TEXT
        )""")
        con.commit()

def save_order(order):
    with _connect() as con:
        con.execute("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?)",
                    (order.order_id,order.symbol,order.side,order.quantity,order.price,
                     order.status,order.reason,order.created_at))
        con.commit()

def save_position(symbol, position):
    with _connect() as con:
        if position:
            con.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?)",
                        (symbol,position["side"],position["qty"],position["entry"],
                         position["sl"],position["target"],str(position.get("time",""))))
        else:
            con.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        con.commit()

def load_position(symbol):
    with _connect() as con:
        row=con.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None

def load_orders(symbol=None, limit=200):
    with _connect() as con:
        if symbol:
            rows=con.execute("SELECT * FROM orders WHERE symbol=? ORDER BY created_at DESC LIMIT ?",(symbol,limit)).fetchall()
        else:
            rows=con.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) for r in rows]
