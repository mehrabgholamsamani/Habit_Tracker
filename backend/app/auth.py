"""Small compatibility authentication bridge for the existing user-id API.

Production requests prove possession of a server-issued bearer token without
changing endpoint payloads. This is intentionally a bridge: a real login/token
issuance flow should replace pre-provisioned tokens for an internet-facing app.
"""

import hashlib
import hmac
import os

from fastapi import HTTPException


_PRODUCTION_ENVIRONMENTS = {"prod", "production"}
_MIN_SECRET_BYTES = 32


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def validate_auth_configuration() -> None:
    """Fail startup rather than silently trusting identity headers in production."""
    if not is_production():
        return
    secret = os.getenv("AUTH_SECRET", "").encode()
    if len(secret) < _MIN_SECRET_BYTES:
        raise RuntimeError("AUTH_SECRET must contain at least 32 bytes in production")


def issue_compatibility_token(user_id: int, secret: str | None = None) -> str:
    """Generate a pre-provisioned token; this is not an HTTP token-issuance flow."""
    key = (secret if secret is not None else os.getenv("AUTH_SECRET", "")).encode()
    if len(key) < _MIN_SECRET_BYTES:
        raise RuntimeError("AUTH_SECRET must contain at least 32 bytes")
    return hmac.new(key, str(user_id).encode("ascii"), hashlib.sha256).hexdigest()


def verify_identity_token(user_id: int, token: str | None) -> None:
    """Require an HMAC bearer credential in production, compare in constant time."""
    if not is_production():
        return
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication credential required")
    if len(token) != hashlib.sha256().digest_size * 2:
        raise HTTPException(status_code=403, detail="Invalid authentication credential")
    expected = issue_compatibility_token(user_id)
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid authentication credential")
