class KalshiError(Exception):
    """Base error for all Kalshi client errors."""


class AuthError(KalshiError):
    """Signing or credential failure."""


class RateLimitError(KalshiError):
    """HTTP 429 from Kalshi."""


class APIError(KalshiError):
    """Non-2xx response."""
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body
