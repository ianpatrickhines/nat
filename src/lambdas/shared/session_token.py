"""
Session Token (JWT) helper.

Mints and verifies short-lived HS256 JSON Web Tokens that authenticate Nat API
callers and bind each request to a specific ``(user_id, nation_slug)`` pair.

The token is implemented with only the Python standard library so it can be
bundled into a Lambda deployment package without adding a third-party
dependency (this mirrors the codebase convention of using ``urllib3`` / stdlib
instead of extra packages).

Security model
--------------
The signed claims are the source of truth for caller identity. Handlers MUST
derive ``user_id`` and ``nation_slug`` from a verified token rather than from
client-supplied headers or body fields, which are forgeable. This is what
closes the IDOR where any caller could read another nation's data by naming its
slug.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# Secrets Manager path for the signing secret (per environment in production).
SESSION_JWT_SECRET_NAME = os.environ.get(
    "SESSION_JWT_SECRET_NAME", "nat/session-jwt-secret"
)

# Default token lifetime. Short-lived: on expiry the extension re-authenticates
# (re-runs the NationBuilder OAuth connect flow) to mint a fresh token.
DEFAULT_TTL_SECONDS = int(os.environ.get("SESSION_TOKEN_TTL_SECONDS", "86400"))

_JWT_HEADER = {"alg": "HS256", "typ": "JWT"}

# Cache the signing secret across warm Lambda invocations.
_cached_secret: str | None = None


class SessionTokenError(Exception):
    """Raised when a session token is missing, malformed, expired, or forged."""

    def __init__(
        self,
        message: str,
        code: str = "INVALID_TOKEN",
        http_status: int = 401,
    ) -> None:
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


@dataclass
class SessionContext:
    """Authenticated caller identity derived from a verified session token."""

    user_id: str
    nation_slug: str


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding (JWT segment encoding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Base64url-decode a JWT segment, restoring stripped padding."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _sign(signing_input: bytes, secret: str) -> str:
    """Compute the base64url HMAC-SHA256 signature for a signing input."""
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(digest)


def get_secrets_manager_client() -> Any:
    """Get Secrets Manager client (allows mocking in tests)."""
    return boto3.client("secretsmanager")


def get_session_secret() -> str:
    """
    Retrieve the JWT signing secret from Secrets Manager.

    The secret may be stored as a plain string or as JSON containing a
    ``secret`` / ``value`` / ``key`` field. Cached for warm invocations.
    """
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    client = get_secrets_manager_client()
    try:
        response = client.get_secret_value(SecretId=SESSION_JWT_SECRET_NAME)
    except ClientError as e:
        logger.error(f"Failed to retrieve session JWT secret: {e}")
        raise

    secret_str: str = response.get("SecretString", "")
    try:
        data = json.loads(secret_str)
    except json.JSONDecodeError:
        _cached_secret = secret_str
        return secret_str

    if isinstance(data, dict):
        for key in ("secret", "value", "key", "jwt_secret"):
            if key in data:
                _cached_secret = str(data[key])
                return _cached_secret
        if data:
            _cached_secret = str(next(iter(data.values())))
            return _cached_secret

    _cached_secret = secret_str
    return secret_str


def reset_secret_cache() -> None:
    """Clear the cached signing secret (used in tests)."""
    global _cached_secret
    _cached_secret = None


def mint_session_token(
    user_id: str,
    nation_slug: str,
    secret: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """
    Mint a signed HS256 session token binding a user to a nation.

    Args:
        user_id: Authenticated user identifier.
        nation_slug: Nation the user is authorized for.
        secret: HMAC signing secret.
        ttl_seconds: Lifetime of the token in seconds.
        now: Override for the current time (testing). Defaults to ``time.time()``.

    Returns:
        Encoded JWT string (``header.payload.signature``).
    """
    if not user_id or not nation_slug:
        raise ValueError("user_id and nation_slug are required to mint a session token")

    issued_at = int(now if now is not None else time.time())
    claims: dict[str, Any] = {
        "user_id": user_id,
        "nation_slug": nation_slug,
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
    }

    header_segment = _b64url_encode(
        json.dumps(_JWT_HEADER, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url_encode(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = _sign(signing_input, secret)
    return f"{header_segment}.{payload_segment}.{signature}"


def verify_session_token(
    token: str,
    secret: str,
    now: float | None = None,
) -> dict[str, Any]:
    """
    Verify a session token's signature and expiry and return its claims.

    Raises:
        SessionTokenError: If the token is missing, malformed, signed with the
            wrong secret/algorithm, tampered with, or expired.
    """
    if not token:
        raise SessionTokenError("Missing session token", code="MISSING_TOKEN")

    parts = token.split(".")
    if len(parts) != 3:
        raise SessionTokenError("Malformed session token")

    header_segment, payload_segment, signature = parts
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_sig = _sign(signing_input, secret)

    # Constant-time comparison; rejects tampered payloads and "alg: none".
    if not hmac.compare_digest(expected_sig, signature):
        raise SessionTokenError("Invalid token signature")

    try:
        header = json.loads(_b64url_decode(header_segment))
        claims = json.loads(_b64url_decode(payload_segment))
    except (ValueError, json.JSONDecodeError):
        raise SessionTokenError("Malformed session token payload")

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise SessionTokenError("Unsupported token algorithm")

    if not isinstance(claims, dict):
        raise SessionTokenError("Malformed session token claims")

    exp = claims.get("exp")
    current = int(now if now is not None else time.time())
    if not isinstance(exp, (int, float)) or current >= int(exp):
        raise SessionTokenError("Session token expired", code="TOKEN_EXPIRED")

    user_id = claims.get("user_id")
    nation_slug = claims.get("nation_slug")
    if not user_id or not nation_slug:
        raise SessionTokenError("Session token missing identity claims")

    return claims


def extract_bearer_token(headers: dict[str, str]) -> str:
    """
    Extract the bearer token from a case-insensitive ``Authorization`` header.

    Raises:
        SessionTokenError: If the header is missing or not a bearer token.
    """
    normalized = {k.lower(): v for k, v in (headers or {}).items()}
    auth = normalized.get("authorization", "")
    if not auth:
        raise SessionTokenError(
            "Missing Authorization header", code="MISSING_TOKEN"
        )

    pieces = auth.split(" ", 1)
    if len(pieces) != 2 or pieces[0].lower() != "bearer" or not pieces[1].strip():
        raise SessionTokenError(
            "Malformed Authorization header", code="MISSING_TOKEN"
        )
    return pieces[1].strip()


def authenticate_request(
    event: dict[str, Any],
    secret: str | None = None,
) -> SessionContext:
    """
    Authenticate a Lambda request from its ``Authorization: Bearer`` token.

    Returns the verified caller identity. ``user_id`` and ``nation_slug`` come
    exclusively from the signed claims — any client-supplied header or body
    values are ignored, closing the IDOR.

    Raises:
        SessionTokenError: If authentication fails (caller should return 401).
    """
    headers = event.get("headers", {}) or {}
    token = extract_bearer_token(headers)
    signing_secret = secret if secret is not None else get_session_secret()
    claims = verify_session_token(token, signing_secret)
    return SessionContext(
        user_id=str(claims["user_id"]),
        nation_slug=str(claims["nation_slug"]),
    )
