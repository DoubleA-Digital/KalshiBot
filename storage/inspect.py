"""CLI: peek at what's been collected. `python -m storage.inspect`"""
from __future__ import annotations
from datetime import datetime, timezone

from .db import connect, DB_PATH


def main() -> None:
    if not DB_PATH.exists():
        print(f"no db yet at {DB_PATH} — run a tick first")
        return
    conn = connect()
    cur = conn.cursor()

    def one(q: str) -> int:
        return cur.execute(q).fetchone()[0]

    print(f"db:           {DB_PATH}")
    print(f"markets:      {one('SELECT COUNT(*) FROM markets')}")
    print(f"price rows:   {one('SELECT COUNT(*) FROM price_snapshots')}")
    print(f"ob rows:      {one('SELECT COUNT(*) FROM orderbook_snapshots')}")
    row = cur.execute("SELECT MIN(ts), MAX(ts) FROM price_snapshots").fetchone()
    if row and row[0]:
        lo = datetime.fromtimestamp(row[0], tz=timezone.utc).isoformat()
        hi = datetime.fromtimestamp(row[1], tz=timezone.utc).isoformat()
        print(f"price range:  {lo} → {hi}")

    print("\nTop 10 markets by snapshots collected:")
    rows = cur.execute("""
        SELECT ticker, COUNT(*) AS n
        FROM price_snapshots GROUP BY ticker ORDER BY n DESC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r['ticker']:32s} {r['n']:6d}")


if __name__ == "__main__":
    main()
