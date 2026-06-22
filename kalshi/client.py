"""Thin Kalshi HTTP client.

Design:
- One method per endpoint; returns parsed JSON dicts (not typed models — keeps
  step 1 minimal; we can add typed wrappers later if churn hurts).
- Every request flows through `_request`, which handles signing, rate limiting,
  429 backoff, and error mapping.
- Public market endpoints (markets, orderbook) do not technically require auth,
  but we sign them anyway when credentials are present; Kalshi accepts that.
"""
from __future__ import annotations
import threading
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from config import API_PREFIX, Config
from .auth import load_private_key, sign_request
from .exceptions import APIError, AuthError, RateLimitError


class _TokenBucket:
    """Simple thread-safe token bucket for outgoing request rate limiting."""

    def __init__(self, rps: float, burst: Optional[float] = None):
        self.rate = float(rps)
        self.capacity = float(burst if burst is not None else max(rps, 1.0))
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            sleep_for = (1 - self.tokens) / self.rate
        time.sleep(sleep_for)
        self.take()


class KalshiClient:
    def __init__(self, cfg: Optional[Config] = None, *, signed: bool = True):
        self.cfg = cfg or Config.load()
        self._bucket = _TokenBucket(self.cfg.rps)
        self._session = requests.Session()
        self._private_key = None
        if signed:
            if not self.cfg.key_id or not self.cfg.private_key_path:
                raise AuthError("KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set")
            self._private_key = load_private_key(self.cfg.private_key_path)

    # ----- low-level -----
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        full_path = f"{API_PREFIX}{path}"
        url = f"{self.cfg.base_url}{full_path}"
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"

        headers = {"Accept": "application/json"}
        if self._private_key is not None:
            ts, sig = sign_request(self._private_key, method, full_path)
            headers.update({
                "KALSHI-ACCESS-KEY": self.cfg.key_id,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": sig,
            })

        self._bucket.take()
        resp = self._session.request(method, url, headers=headers, json=json, timeout=15)

        if resp.status_code == 429:
            raise RateLimitError(resp.text)
        if not resp.ok:
            raise APIError(resp.status_code, resp.text)
        if not resp.content:
            return {}
        return resp.json()

    # ----- market data (public) -----
    def list_markets(
        self,
        *,
        limit: int = 100,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,  # "open" | "closed" | "settled"
    ) -> dict:
        return self._request("GET", "/markets", params={
            "limit": limit,
            "cursor": cursor,
            "event_ticker": event_ticker,
            "series_ticker": series_ticker,
            "status": status,
        })

    def get_market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, *, depth: Optional[int] = None) -> dict:
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})

    # ----- portfolio (auth required) -----
    def get_balance(self) -> dict:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self, *, limit: int = 100, cursor: Optional[str] = None) -> dict:
        return self._request("GET", "/portfolio/positions",
                             params={"limit": limit, "cursor": cursor})

    def list_orders(self, *, ticker: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 100, cursor: Optional[str] = None) -> dict:
        return self._request("GET", "/portfolio/orders", params={
            "ticker": ticker, "status": status, "limit": limit, "cursor": cursor,
        })

    def place_order(
        self,
        *,
        ticker: str,
        action: str,        # "buy" | "sell"
        side: str,          # "yes" | "no"
        type: str,          # "limit" | "market"
        count: int,
        yes_price: Optional[int] = None,   # cents, 1..99
        no_price: Optional[int] = None,
        client_order_id: Optional[str] = None,
        time_in_force: Optional[str] = None,
        expiration_ts: Optional[int] = None,
    ) -> dict:
        # SAFETY: live trading must be explicitly enabled.
        if not self.cfg.live_trading:
            raise AuthError(
                "place_order called but LIVE_TRADING is not 'true'. "
                "Real-money orders are disabled by default. "
                "Use paper trading mode for simulation."
            )
        body = {
            "ticker": ticker, "action": action, "side": side, "type": type,
            "count": count, "yes_price": yes_price, "no_price": no_price,
            "client_order_id": client_order_id, "time_in_force": time_in_force,
            "expiration_ts": expiration_ts,
        }
        body = {k: v for k, v in body.items() if v is not None}
        return self._request("POST", "/portfolio/orders", json=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")
