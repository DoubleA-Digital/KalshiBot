"""One iteration of the bot. Runs from GitHub Actions on a cron.

Right now this is a smoke pipeline: it pulls a snapshot of open markets via
the PUBLIC Kalshi endpoints (no auth needed) and writes:
  - data/state.json     latest snapshot, read by the dashboard
  - data/snapshots.jsonl append-only log of every tick

When later build-order steps land, this is where the strategy/EV/risk/paper
trading layers slot in. The Actions workflow commits whatever this writes
back to the repo, which is how we get persistence without a real disk.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from kalshi import KalshiClient
from config import Config
from storage import connect, collect

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)


def tick() -> dict:
    cfg = Config.load()
    # signed=False: snapshot uses public endpoints only, no API key required.
    # This lets the workflow run before the user wires up Kalshi secrets.
    client = KalshiClient(cfg=cfg, signed=False) if not cfg.key_id else KalshiClient(cfg=cfg)

    started = time.monotonic()

    # Persist to SQLite (canonical store for backtesting).
    conn = connect()
    result = collect(client, conn, status="open", market_limit=200)

    # Dashboard snapshot: only TRADABLE markets (have a yes_bid/ask), sorted by volume.
    # Pulls multiple pages so we don't get a screen full of illiquid parlays.
    tradable: list[dict] = []
    cursor = None
    for _ in range(5):
        page = client.list_markets(limit=200, status="open", cursor=cursor)
        for m in page.get("markets", []):
            if m.get("yes_bid") is not None and m.get("yes_ask") is not None:
                tradable.append(m)
        cursor = page.get("cursor")
        if not cursor or len(tradable) >= 200:
            break

    tradable.sort(key=lambda x: x.get("volume") or 0, reverse=True)

    def _title(t: str | None) -> str:
        if not t:
            return ""
        return (t[:120] + "…") if len(t) > 120 else t

    summary = []
    for m in tradable[:30]:
        yb, ya = m.get("yes_bid"), m.get("yes_ask")
        mid = (yb + ya) / 2 if (yb is not None and ya is not None) else None
        summary.append({
            "ticker": m.get("ticker"),
            "title": _title(m.get("title")),
            "yes_bid": yb,
            "yes_ask": ya,
            "mid": mid,
            "implied_prob": mid / 100 if mid is not None else None,
            "last_price": m.get("last_price"),
            "volume": m.get("volume"),
            "close_time": m.get("close_time"),
        })

    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "env": cfg.env,
        "live_trading": cfg.live_trading,
        "tick_duration_ms": int((time.monotonic() - started) * 1000),
        "open_markets_sampled": len(summary),
        "tradable_markets_found": len(tradable),
        "collector": {
            "markets_seen": result.markets_seen,
            "price_rows_written": result.price_rows_written,
            "errors": result.errors,
        },
        "markets": summary,
        # Placeholders the dashboard already renders; later steps populate them.
        "bankroll": None,
        "open_positions": [],
        "trades_today": 0,
        "win_rate": None,
        "predicted_ev": None,
        "realized_ev": None,
    }

    (DATA / "state.json").write_text(json.dumps(state, indent=2))
    with (DATA / "snapshots.jsonl").open("a") as f:
        f.write(json.dumps({"t": state["generated_at"], "n": len(summary)}) + "\n")
    return state


if __name__ == "__main__":
    s = tick()
    c = s["collector"]
    print(f"tick ok: {s['open_markets_sampled']} sampled, "
          f"{c['markets_seen']} stored, +{c['price_rows_written']} price rows, "
          f"{s['tick_duration_ms']}ms")
