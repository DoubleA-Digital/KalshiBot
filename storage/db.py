"""SQLite schema + connection helper.

Single canonical store for market metadata, price snapshots, and orderbook
snapshots. The backtester (step 5) queries directly from here.

Design choices:
- `PRAGMA user_version` for forward migrations; no Alembic for a 3-table schema.
- `(ticker, ts)` is the hot index — every backtest scan filters on it.
- Orderbook levels stored as JSON. We rarely need to query *into* them; we
  just want to replay them. JSON keeps the schema flat.
- `ts` is integer unix-seconds. Easier to dedupe and arithmetic-friendly.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kalshi.db"

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    ticker        TEXT PRIMARY KEY,
    title         TEXT,
    event_ticker  TEXT,
    series_ticker TEXT,
    status        TEXT,
    close_time    TEXT,
    first_seen    INTEGER NOT NULL,
    last_seen     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    ticker        TEXT NOT NULL,
    ts            INTEGER NOT NULL,
    yes_bid       INTEGER,
    yes_ask       INTEGER,
    last_price    INTEGER,
    volume        INTEGER,
    open_interest INTEGER,
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS idx_price_ticker_ts ON price_snapshots(ticker, ts);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    ticker     TEXT NOT NULL,
    ts         INTEGER NOT NULL,
    yes_levels TEXT,  -- JSON: [[price, size], ...]
    no_levels  TEXT,
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS idx_ob_ticker_ts ON orderbook_snapshots(ticker, ts);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA user_version")
    version = cur.fetchone()[0]
    if version < 1:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    # future: if version < 2: ...
