# KalshiBot

Autonomous event-contract trading bot for Kalshi. **Real-money trading is OFF by default** and must be explicitly enabled.

This project is being built in strict sequence — see [Build Order](#build-order). Anything past the current step is intentionally not implemented yet.

## Status

- [x] **Step 1** — Project structure + Kalshi API client (auth, markets, orderbook, portfolio, orders) with rate limiting
- [ ] Step 2 — Data collection into SQLite
- [ ] Step 3 — Strategy interface + one concrete strategy
- [ ] Step 4 — EV engine + fractional Kelly sizing
- [ ] Step 5 — Backtester
- [ ] Step 6 — Paper trading mode (default)
- [ ] Step 7 — Risk management layer
- [ ] Step 8 — Autonomous loop

## Setup

```bash
cd ~/Desktop/Double-A-Digital/KalshiBot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Generate API key + private key in your Kalshi account, save key as kalshi_private_key.pem
# Edit .env: set KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH
```

`KALSHI_ENV=demo` points at the Kalshi sandbox. Switch to `prod` only when you're ready.

## Smoke-test the API client

```python
from kalshi import KalshiClient
c = KalshiClient()
print(c.get_balance())                          # auth check
print(c.list_markets(limit=5, status="open"))   # public data
```

## Safety contract

`place_order()` raises if `LIVE_TRADING` is not exactly `"true"` in your `.env`. This guard exists from day one so later layers (loop, CLI) can't accidentally fire real orders during development.

## Project layout

```
KalshiBot/
├── config.py            # env loader, base URLs, LIVE_TRADING flag
├── kalshi/              # API client (step 1)
│   ├── auth.py          # RSA-PSS signing (Kalshi's spec)
│   ├── client.py        # HTTP client, rate limiting, endpoint methods
│   └── exceptions.py
└── tests/
    └── test_auth.py     # verifies signing matches Kalshi's PSS params
```

## Build order

The sequence is deliberate: you cannot judge a strategy without a backtester, and you cannot backtest without stored data. Steps build on each other; skipping ahead defeats the point of the project.

## Adding a new strategy (later)

(Documented when step 3 lands.)
