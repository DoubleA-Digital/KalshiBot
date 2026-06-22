"""Kalshi RSA-PSS request signing.

Kalshi signs every authenticated request. The signed string is:
    f"{timestamp_ms}{METHOD}{path}"
where `path` is the URL path INCLUDING the API prefix (/trade-api/v2/...) but
EXCLUDING the query string. Signature is RSA-PSS over SHA-256 with MGF1-SHA256
and salt length equal to the digest length (32 bytes). Output is base64.
"""
from __future__ import annotations
import base64
import time
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .exceptions import AuthError


def load_private_key(path: Path) -> rsa.RSAPrivateKey:
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise AuthError(f"Cannot read private key at {path}: {e}") from e
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except Exception as e:
        raise AuthError(f"Invalid PEM private key at {path}: {e}") from e
    if not isinstance(key, rsa.RSAPrivateKey):
        raise AuthError("Kalshi requires an RSA private key")
    return key


def sign_request(
    private_key: rsa.RSAPrivateKey,
    method: str,
    path: str,
    timestamp_ms: int | None = None,
) -> Tuple[str, str]:
    """Return (timestamp_ms_str, base64_signature).

    `path` must include the /trade-api/v2 prefix and exclude the query string.
    """
    if "?" in path:
        raise AuthError("Signed path must not include query string")
    ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    message = f"{ts}{method.upper()}{path}".encode()
    sig = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return str(ts), base64.b64encode(sig).decode()
