"""Verify the RSA-PSS signing contract.

We can't compare signatures byte-for-byte (PSS is randomized via salt), but we
can verify that a signature produced by sign_request validates against the
public key with the exact PSS parameters Kalshi requires. That proves we're
hashing the right message and using the right padding.
"""
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.auth import sign_request


def _make_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_signature_verifies_against_kalshi_pss_params(tmp_path):
    key = _make_key()
    ts, sig_b64 = sign_request(key, "GET", "/trade-api/v2/portfolio/balance", timestamp_ms=1700000000000)
    message = f"{ts}GET/trade-api/v2/portfolio/balance".encode()
    key.public_key().verify(
        base64.b64decode(sig_b64),
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_query_string_in_path_is_rejected():
    import pytest
    from kalshi.exceptions import AuthError
    key = _make_key()
    with pytest.raises(AuthError):
        sign_request(key, "GET", "/trade-api/v2/markets?limit=10")


def test_method_is_uppercased():
    key = _make_key()
    _, lower = sign_request(key, "get", "/x", timestamp_ms=1)
    _, upper = sign_request(key, "GET", "/x", timestamp_ms=1)
    # Both should verify against the same uppercased message
    message = b"1GET/x"
    for s in (lower, upper):
        key.public_key().verify(
            base64.b64decode(s), message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
