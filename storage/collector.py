"""Pulls market data from Kalshi and persists it.

Two layers of data:
  1. price_snapshots — cheap; we grab one per market per tick.
  2. orderbook_snapshots — heavier (one API call per market). Off by default;
     enable for specific tickers you actually want to trade.

Dedup strategy: the (ticker, ts) primary key means re-running a tick within
the same second is a no-op. `INSERT OR IGNORE` keeps that cheap.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from kalshi import KalshiClient


@dataclass
class CollectorResult:
    ts: int
    markets_seen: int
    price_rows_written: int
    orderbook_rows_written: int
    errors: list[str]

    def summary(self) -> str:
        return (f"ts={self.ts} markets={self.markets_seen} "
                f"prices+{self.price_rows_written} obs+{self.orderbook_rows_written} "
                f"errors={len(self.errors)}")


def collect(
    client: KalshiClient,
    conn,
    *,
    status: str = "open",
    market_limit: int = 200,
    orderbook_tickers: Optional[Iterable[str]] = None,
) -> CollectorResult:
    ts = int(time.time())
    errors: list[str] = []

    # ----- markets + prices -----
    cursor = None
    markets: list[dict] = []
    pages = 0
    while True:
        try:
            page = client.list_markets(limit=min(market_limit, 200), cursor=cursor, status=status)
        except Exception as e:
            errors.append(f"list_markets: {e}")
            break
        markets.extend(page.get("markets", []))
        cursor = page.get("cursor")
        pages += 1
        if not cursor or len(markets) >= market_limit or pages >= 5:
            break

    price_rows = 0
    with conn:
        for m in markets:
            ticker = m.get("ticker")
            if not ticker:
                continue
            conn.execute(
                """INSERT INTO markets(ticker,title,event_ticker,series_ticker,status,close_time,first_seen,last_seen)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(ticker) DO UPDATE SET
                     title=excluded.title, status=excluded.status,
                     close_time=excluded.close_time, last_seen=excluded.last_seen""",
                (ticker, m.get("title"), m.get("event_ticker"), m.get("series_ticker"),
                 m.get("status"), m.get("close_time"), ts, ts),
            )
            cur = conn.execute(
                """INSERT OR IGNORE INTO price_snapshots
                   (ticker,ts,yes_bid,yes_ask,last_price,volume,open_interest)
                   VALUES(?,?,?,?,?,?,?)""",
                (ticker, ts, m.get("yes_bid"), m.get("yes_ask"),
                 m.get("last_price"), m.get("volume"), m.get("open_interest")),
            )
            price_rows += cur.rowcount

    # ----- orderbooks (optional, per-ticker API calls) -----
    ob_rows = 0
    if orderbook_tickers:
        with conn:
            for t in orderbook_tickers:
                try:
                    ob = client.get_orderbook(t)
                except Exception as e:
                    errors.append(f"orderbook {t}: {e}")
                    continue
                book = ob.get("orderbook") or ob
                cur = conn.execute(
                    """INSERT OR IGNORE INTO orderbook_snapshots(ticker,ts,yes_levels,no_levels)
                       VALUES(?,?,?,?)""",
                    (t, ts, json.dumps(book.get("yes") or []),
                     json.dumps(book.get("no") or [])),
                )
                ob_rows += cur.rowcount

    return CollectorResult(ts=ts, markets_seen=len(markets),
                           price_rows_written=price_rows,
                           orderbook_rows_written=ob_rows,
                           errors=errors)
