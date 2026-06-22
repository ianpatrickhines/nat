"""
OAuth ``state`` (CSRF) protection for the NationBuilder OAuth flow.

The OAuth ``state`` parameter must be unforgeable and single-use to defend the
NationBuilder connect flow against two related attacks:

  - **CSRF / login-CSRF.** Previously ``state`` was just base64-encoded JSON
    (``{user_id, nb_slug, redirect_uri}``) with no secret or nonce. An attacker
    could craft a ``state`` carrying their *own* ``user_id``, lure a victim
    through the flow, and have the victim's freshly minted nation tokens stored
    under the attacker's account.
  - **Authorization-code interception.** ``redirect_uri`` was taken from
    ``state`` and used verbatim in the token exchange with no allowlist.

Design
------
At issuance (the OAuth init / authorize step) :func:`issue_oauth_state`:

  1. Validates ``redirect_uri`` against an allowlist.
  2. Generates a cryptographically random, single-use ``nonce``.
  3. Persists the ``nonce`` server-side in DynamoDB with a TTL, binding it to
     the ``{user_id, nb_slug, redirect_uri}`` it was issued for.
  4. Encodes ``{user_id, nb_slug, redirect_uri, nonce, created_at}`` as the
     base64url ``state`` string handed to NationBuilder.

At the callback :func:`validate_oauth_state`:

  1. Decodes ``state`` and validates ``redirect_uri`` against the allowlist.
  2. Atomically claims-and-deletes the ``nonce`` from DynamoDB. A missing
     record means the state is forged, already used (single-use), or
     expired-and-evicted -> reject.
  3. Compares the *stored* ``{user_id, nb_slug, redirect_uri}`` against the
     copy carried in ``state``. Any mismatch means the state was tampered with
     after issuance -> reject.
  4. Rejects if older than ``OAUTH_STATE_TTL_SECONDS`` (using ``created_at``).

The DynamoDB record is the trust anchor: because only the issuer writes nonces,
an attacker cannot fabricate a ``state`` that survives the lookup, and the
authoritative copy of the bound fields lives server-side where the client
cannot tamper with it. The delete is conditional (``attribute_exists``) so the
single-use guarantee holds even under concurrent replay.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# DynamoDB table holding single-use OAuth state nonces (PK: ``nonce``).
OAUTH_STATE_TABLE = os.environ.get("OAUTH_STATE_TABLE", "nat-oauth-state-dev")

# Maximum age of a state before it is rejected, in seconds. Also drives the
# DynamoDB TTL written on each record. Short: the connect round trip is quick.
OAUTH_STATE_TTL_SECONDS = int(os.environ.get("OAUTH_STATE_TTL_SECONDS", "600"))

# Comma-separated allowlist of exact redirect_uri values the OAuth flow may use.
# Empty / unset means deny-all (secure default); production sets this via the
# Lambda environment. Whitespace around entries is ignored.
OAUTH_REDIRECT_URI_ALLOWLIST = os.environ.get("OAUTH_REDIRECT_URI_ALLOWLIST", "")


class OAuthStateError(Exception):
    """Raised when an OAuth ``state`` is missing, malformed, forged, tampered,
    replayed, expired, or carries a disallowed ``redirect_uri``.

    ``error_slug`` is a short, safe token surfaced in the user-facing error
    redirect query string (never the raw exception detail).
    """

    def __init__(self, message: str, error_slug: str = "invalid_state") -> None:
        self.error_slug = error_slug
        super().__init__(message)


def get_dynamodb_resource() -> Any:
    """Return a DynamoDB resource (indirection allows mocking in tests)."""
    return boto3.resource("dynamodb")


def _get_table() -> Any:
    return get_dynamodb_resource().Table(OAUTH_STATE_TABLE)


def _allowed_redirect_uris() -> set[str]:
    return {
        uri.strip()
        for uri in OAUTH_REDIRECT_URI_ALLOWLIST.split(",")
        if uri.strip()
    }


def validate_redirect_uri(redirect_uri: str) -> bool:
    """Return ``True`` iff ``redirect_uri`` exactly matches an allowlist entry.

    Exact matching (scheme + host + path) is intentional: prefix/substring
    matching is a classic source of open-redirect and code-interception bugs.
    """
    if not redirect_uri:
        return False
    return redirect_uri in _allowed_redirect_uris()


def _encode_state(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_state(state: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(state)
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as e:
        raise OAuthStateError(f"Malformed state: {e}") from e
    if not isinstance(data, dict):
        raise OAuthStateError("State payload is not an object")
    return data


def issue_oauth_state(
    user_id: str,
    nb_slug: str,
    redirect_uri: str,
    now: float | None = None,
) -> str:
    """Mint a single-use OAuth ``state`` bound to ``(user_id, nb_slug,
    redirect_uri)`` and persist its nonce server-side with a TTL.

    Args:
        user_id: The user the flow is being initiated for.
        nb_slug: The NationBuilder nation slug being connected.
        redirect_uri: OAuth callback URI; must be on the allowlist.
        now: Override for the current epoch time (testing).

    Returns:
        The base64url-encoded ``state`` string to pass to NationBuilder.

    Raises:
        OAuthStateError: If any field is missing or ``redirect_uri`` is not
            allowlisted.
    """
    if not user_id or not nb_slug or not redirect_uri:
        raise OAuthStateError("user_id, nb_slug and redirect_uri are required")
    if not validate_redirect_uri(redirect_uri):
        raise OAuthStateError(
            f"redirect_uri not allowlisted: {redirect_uri}",
            error_slug="invalid_redirect_uri",
        )

    created_at = int(now if now is not None else time.time())
    nonce = secrets.token_urlsafe(32)

    _get_table().put_item(
        Item={
            "nonce": nonce,
            "user_id": user_id,
            "nb_slug": nb_slug,
            "redirect_uri": redirect_uri,
            "created_at": created_at,
            # DynamoDB TTL attribute (epoch seconds). Best-effort cleanup; the
            # created_at age check below is the authoritative expiry enforcement.
            "expires_at": created_at + OAUTH_STATE_TTL_SECONDS,
        }
    )

    return _encode_state(
        {
            "user_id": user_id,
            "nb_slug": nb_slug,
            "redirect_uri": redirect_uri,
            "nonce": nonce,
            "created_at": created_at,
        }
    )


def validate_oauth_state(state: str, now: float | None = None) -> dict[str, str]:
    """Validate, atomically consume, and return the claims of an OAuth ``state``.

    Args:
        state: The base64url ``state`` returned on the OAuth callback.
        now: Override for the current epoch time (testing).

    Returns:
        ``{"user_id", "nb_slug", "redirect_uri"}`` taken from the server-side
        record (the trusted copy).

    Raises:
        OAuthStateError: If the state is missing, malformed, carries a
            disallowed ``redirect_uri``, is unknown / already used / expired, or
            was tampered with after issuance.
    """
    if not state:
        raise OAuthStateError("Missing state", error_slug="missing_state")

    data = _decode_state(state)
    nonce = data.get("nonce")
    redirect_uri = data.get("redirect_uri")
    if not nonce or not isinstance(nonce, str):
        raise OAuthStateError("State missing nonce")
    if not redirect_uri or not isinstance(redirect_uri, str):
        raise OAuthStateError("State missing redirect_uri")

    # Reject disallowed redirect_uri before any DynamoDB work.
    if not validate_redirect_uri(redirect_uri):
        raise OAuthStateError(
            f"redirect_uri not allowlisted: {redirect_uri}",
            error_slug="invalid_redirect_uri",
        )

    # Atomically claim-and-delete the nonce. ConditionalCheckFailed means the
    # nonce never existed or was already consumed -> forged / replayed / evicted.
    table = _get_table()
    try:
        response = table.delete_item(
            Key={"nonce": nonce},
            ConditionExpression="attribute_exists(nonce)",
            ReturnValues="ALL_OLD",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise OAuthStateError(
                "State is unknown, already used, or expired"
            ) from e
        logger.error(f"DynamoDB error consuming OAuth state: {e}")
        raise

    stored = response.get("Attributes") or {}

    # Tamper check: the state's own copy of the bound fields must match the
    # authoritative server-side record exactly.
    for field in ("user_id", "nb_slug", "redirect_uri"):
        if str(data.get(field, "")) != str(stored.get(field, "")):
            raise OAuthStateError(f"State {field} does not match issued value")

    # Expiry check against the authoritative created_at (defence in depth on top
    # of the DynamoDB TTL, which is only best-effort/eventual).
    created_at = stored.get("created_at")
    current = int(now if now is not None else time.time())
    if created_at is None:
        raise OAuthStateError("State record missing created_at")
    try:
        issued_at = int(created_at)
    except (TypeError, ValueError) as e:
        raise OAuthStateError("State has invalid created_at") from e
    if current - issued_at > OAUTH_STATE_TTL_SECONDS:
        raise OAuthStateError("State has expired", error_slug="expired_state")

    return {
        "user_id": str(stored["user_id"]),
        "nb_slug": str(stored["nb_slug"]),
        "redirect_uri": str(stored["redirect_uri"]),
    }
