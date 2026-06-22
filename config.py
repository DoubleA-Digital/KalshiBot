"""Central config. Reads .env if present; otherwise uses os.environ."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# Kalshi base URLs. Override via KALSHI_BASE_URL if these change.
BASE_URLS = {
    "demo": "https://demo-api.kalshi.co",
    "prod": "https://api.elections.kalshi.com",
}
API_PREFIX = "/trade-api/v2"


@dataclass(frozen=True)
class Config:
    key_id: str
    private_key_path: Path
    env: str
    base_url: str
    live_trading: bool
    rps: float

    @classmethod
    def load(cls) -> "Config":
        env = os.environ.get("KALSHI_ENV", "demo").lower()
        base = os.environ.get("KALSHI_BASE_URL") or BASE_URLS.get(env)
        if not base:
            raise ValueError(f"Unknown KALSHI_ENV={env!r}; set KALSHI_BASE_URL explicitly")
        return cls(
            key_id=os.environ.get("KALSHI_KEY_ID", ""),
            private_key_path=Path(os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")),
            env=env,
            base_url=base.rstrip("/"),
            live_trading=os.environ.get("LIVE_TRADING", "false").lower() == "true",
            rps=float(os.environ.get("KALSHI_RPS", "8")),
        )
