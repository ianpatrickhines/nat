"""
NationBuilder OAuth Init Lambda Handler.

Starts the NationBuilder OAuth connect flow. This is the *issuance* side of the
CSRF protection added in the OAuth callback: it mints a single-use, server-side
``state`` nonce (see :mod:`shared.oauth_state`) bound to the user and nation,
then redirects the browser to NationBuilder's authorize endpoint.

Flow:
  1. Read ``nb_slug`` (the nation being connected) from the query string.
  2. Use the caller-supplied ``user_id`` or generate a fresh one (the NB connect
     flow doubles as login, so a brand-new connect has no prior identity).
  3. Issue a single-use ``state`` bound to ``(user_id, nb_slug, redirect_uri)``,
     persisting its nonce in DynamoDB with a TTL.
  4. 302-redirect to ``https://{nb_slug}.nationbuilder.com/oauth/authorize``.

``redirect_uri`` is fixed server-side from ``OAUTH_CALLBACK_URL`` (which must be
on the allowlist) so it can never be influenced by the client.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, TypedDict
from urllib.parse import urlencode

import boto3
from botocore.exceptions import ClientError

try:  # Resolve in both pytest (repo root) and flattened Lambda packages.
    from src.lambdas.shared.oauth_state import (
        OAuthStateError,
        issue_oauth_state,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised only in Lambda
    from shared.oauth_state import (  # type: ignore[no-redef]
        OAuthStateError,
        issue_oauth_state,
    )

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NB_CLIENT_ID_SECRET = os.environ.get("NB_CLIENT_ID_SECRET", "nat/nb-client-id")
# The OAuth callback URI registered with NationBuilder. Must be on the
# OAUTH_REDIRECT_URI_ALLOWLIST so the callback accepts the resulting state.
OAUTH_CALLBACK_URL = os.environ.get("OAUTH_CALLBACK_URL", "")
ERROR_REDIRECT_URL = os.environ.get(
    "ERROR_REDIRECT_URL", "https://natassistant.com/connection-error"
)


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str
    headers: dict[str, str]


def get_secret(secret_name: str) -> str:
    """Retrieve a secret value from Secrets Manager (mirrors callback handler)."""
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret: str = response.get("SecretString", "")
    try:
        secret_data = json.loads(secret)
        for key in ["value", "secret", "token", "key"]:
            if key in secret_data:
                return str(secret_data[key])
        if secret_data:
            return str(next(iter(secret_data.values())))
        return secret
    except json.JSONDecodeError:
        return secret


def create_redirect_response(url: str) -> LambdaResponse:
    """Create a 302 redirect response."""
    return {
        "statusCode": 302,
        "body": "",
        "headers": {
            "Location": url,
            "Access-Control-Allow-Origin": "*",
        },
    }


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """Lambda handler for starting the NationBuilder OAuth flow.

    Expected query parameters:
      - ``nb_slug`` (required): the NationBuilder nation slug to connect.
      - ``user_id`` (optional): existing user identity; generated if absent.
    """
    try:
        query_params = event.get("queryStringParameters") or {}
        nb_slug = query_params.get("nb_slug")
        if not nb_slug:
            logger.error("Missing nb_slug")
            return create_redirect_response(
                f"{ERROR_REDIRECT_URL}?error=missing_nb_slug"
            )

        if not OAUTH_CALLBACK_URL:
            logger.error("OAUTH_CALLBACK_URL is not configured")
            return create_redirect_response(
                f"{ERROR_REDIRECT_URL}?error=server_misconfigured"
            )

        # NB connect doubles as login; mint a new user_id when none is supplied.
        user_id = query_params.get("user_id") or f"user-{uuid.uuid4().hex}"

        try:
            state = issue_oauth_state(
                user_id=user_id,
                nb_slug=nb_slug,
                redirect_uri=OAUTH_CALLBACK_URL,
            )
        except OAuthStateError as e:
            logger.error(f"Failed to issue OAuth state: {e}")
            return create_redirect_response(
                f"{ERROR_REDIRECT_URL}?error={e.error_slug}"
            )

        client_id = get_secret(NB_CLIENT_ID_SECRET)
        authorize_query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": OAUTH_CALLBACK_URL,
                "response_type": "code",
                "state": state,
            }
        )
        authorize_url = (
            f"https://{nb_slug}.nationbuilder.com/oauth/authorize?{authorize_query}"
        )
        logger.info(f"Starting OAuth flow for nation {nb_slug}, user {user_id}")
        return create_redirect_response(authorize_url)

    except ClientError as e:
        logger.error(f"AWS service error: {e}")
        return create_redirect_response(f"{ERROR_REDIRECT_URL}?error=service_error")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_redirect_response(f"{ERROR_REDIRECT_URL}?error=unexpected")
