import json
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
            order_id TEXT PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            quantity INTEGER,
            price REAL,
            status TEXT,
            reason TEXT,
            created_at TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            side TEXT,
            quantity INTEGER,
            entry REAL,
            stop_loss REAL,
            target REAL,
            opened_at TEXT,
            score REAL,
            confirmation TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS paper_sessions (
            symbol TEXT PRIMARY KEY,
            session_date TEXT NOT NULL,
            starting_equity REAL NOT NULL,
            cash REAL NOT NULL,
            realized_pnl REAL NOT NULL DEFAULT 0,
            trade_count INTEGER NOT NULL DEFAULT 0,
            emergency_stop INTEGER NOT NULL DEFAULT 0,
            previous_signal TEXT NOT NULL DEFAULT 'NONE',
            last_bar_timestamp TEXT,
            updated_at TEXT NOT NULL
        )""")

        # Migrate databases created by earlier versions.
        cols = {r["name"] for r in con.execute("PRAGMA table_info(positions)").fetchall()}
        if "score" not in cols:
            con.execute("ALTER TABLE positions ADD COLUMN score REAL")
        if "confirmation" not in cols:
            con.execute("ALTER TABLE positions ADD COLUMN confirmation TEXT")
        con.commit()


def save_order(order):
    init_db()
    with _connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?)",
            (
                order.order_id,
                order.symbol,
                order.side,
                order.quantity,
                order.price,
                order.status,
                order.reason,
                order.created_at,
            ),
        )
        con.commit()


def save_position(symbol, position):
    init_db()
    with _connect() as con:
        if position:
            con.execute(
                """INSERT OR REPLACE INTO positions
                   (symbol,side,quantity,entry,stop_loss,target,opened_at,score,confirmation)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    position["side"],
                    position["qty"],
                    position["entry"],
                    position["sl"],
                    position["target"],
                    str(position.get("time", "")),
                    float(position.get("score", 0.0)),
                    str(position.get("confirmation", "NOT USED")),
                ),
            )
        else:
            con.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        con.commit()


def load_position(symbol):
    init_db()
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM positions WHERE symbol=?", (symbol,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        return {
            "side": data["side"],
            "qty": int(data["quantity"]),
            "entry": float(data["entry"]),
            "sl": float(data["stop_loss"]),
            "target": float(data["target"]),
            "time": data.get("opened_at", ""),
            "score": float(data.get("score") or 0.0),
            "confirmation": data.get("confirmation") or "NOT USED",
        }


def load_orders(symbol=None, limit=200):
    init_db()
    with _connect() as con:
        if symbol:
            rows = con.execute(
                "SELECT * FROM orders WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def save_session(symbol, state):
    init_db()
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO paper_sessions
               (symbol,session_date,starting_equity,cash,realized_pnl,trade_count,
                emergency_stop,previous_signal,last_bar_timestamp,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                symbol,
                state["session_date"],
                float(state["starting_equity"]),
                float(state["cash"]),
                float(state["realized_pnl"]),
                int(state["trade_count"]),
                1 if state["emergency_stop"] else 0,
                state.get("previous_signal", "NONE"),
                state.get("last_bar_timestamp"),
                state["updated_at"],
            ),
        )
        con.commit()


def load_session(symbol):
    init_db()
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM paper_sessions WHERE symbol=?", (symbol,)
        ).fetchone()
        return dict(row) if row else None


def delete_session(symbol):
    init_db()
    with _connect() as con:
        con.execute("DELETE FROM paper_sessions WHERE symbol=?", (symbol,))
        con.commit()


def state_summary(symbol):
    return {
        "session": load_session(symbol),
        "position": load_position(symbol),
        "orders": load_orders(symbol, 50),
    }
