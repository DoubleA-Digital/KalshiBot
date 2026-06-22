"""Storage layer tests — no network, exercises schema + dedupe."""
from __future__ import annotations
import time
from pathlib import Path

from storage.db import connect


def test_schema_initializes(tmp_path: Path):
    conn = connect(tmp_path / "t.db")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"markets", "price_snapshots", "orderbook_snapshots"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_price_snapshot_dedup_on_same_second(tmp_path: Path):
    conn = connect(tmp_path / "t.db")
    ts = int(time.time())
    for _ in range(3):
        conn.execute(
            "INSERT OR IGNORE INTO price_snapshots(ticker,ts,yes_bid,yes_ask,last_price,volume,open_interest)"
            " VALUES(?,?,?,?,?,?,?)", ("FOO", ts, 50, 55, 52, 100, 10),
        )
    n = conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    assert n == 1


def test_market_upsert_keeps_first_seen(tmp_path: Path):
    conn = connect(tmp_path / "t.db")
    t1, t2 = 1000, 2000
    conn.execute(
        "INSERT INTO markets(ticker,title,event_ticker,series_ticker,status,close_time,first_seen,last_seen)"
        " VALUES(?,?,?,?,?,?,?,?)", ("FOO", "Old", "EV", "SR", "open", None, t1, t1),
    )
    conn.execute(
        "INSERT INTO markets(ticker,title,event_ticker,series_ticker,status,close_time,first_seen,last_seen)"
        " VALUES(?,?,?,?,?,?,?,?)"
        " ON CONFLICT(ticker) DO UPDATE SET title=excluded.title, last_seen=excluded.last_seen",
        ("FOO", "New", "EV", "SR", "open", None, t2, t2),
    )
    row = conn.execute("SELECT title, first_seen, last_seen FROM markets WHERE ticker='FOO'").fetchone()
    assert row["title"] == "New"
    assert row["first_seen"] == t1
    assert row["last_seen"] == t2
