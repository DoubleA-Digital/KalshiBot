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

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)


def tick() -> dict:
    cfg = Config.load()
    # signed=False: snapshot uses public endpoints only, no API key required.
    # This lets the workflow run before the user wires up Kalshi secrets.
    client = KalshiClient(cfg=cfg, signed=False) if not cfg.key_id else KalshiClient(cfg=cfg)

    started = time.monotonic()
    page = client.list_markets(limit=50, status="open")
    markets = page.get("markets", [])

    summary = []
    for m in markets[:25]:  # cap to keep snapshot file small
        summary.append({
            "ticker": m.get("ticker"),
            "title": m.get("title"),
            "yes_bid": m.get("yes_bid"),
            "yes_ask": m.get("yes_ask"),
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
    print(f"tick ok: {s['open_markets_sampled']} markets in {s['tick_duration_ms']}ms")
