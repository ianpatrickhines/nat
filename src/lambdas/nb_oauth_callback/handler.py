"""
NationBuilder OAuth Callback Lambda Handler

Handles OAuth callback from NationBuilder:
- Receives authorization code from OAuth redirect
- Exchanges code for access_token and refresh_token
- Stores tokens in Secrets Manager
- Updates user record with NB connection status
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlencode

import boto3
import urllib3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")
NB_CLIENT_ID_SECRET = os.environ.get(
    "NB_CLIENT_ID_SECRET", "nat/nb-client-id"
)
NB_CLIENT_SECRET_SECRET = os.environ.get(
    "NB_CLIENT_SECRET_SECRET", "nat/nb-client-secret"
)
SUCCESS_REDIRECT_URL = os.environ.get(
    "SUCCESS_REDIRECT_URL", "https://natassistant.com/connected"
)
ERROR_REDIRECT_URL = os.environ.get(
    "ERROR_REDIRECT_URL", "https://natassistant.com/connection-error"
)


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str
    headers: dict[str, str]


class TokenResponse(TypedDict, total=False):
    """NationBuilder token response type."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: str


def get_secret(secret_name: str) -> str:
    """Retrieve a secret value from Secrets Manager."""
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret: str = response.get("SecretString", "")
        # Secret may be stored as JSON or plain string
        try:
            secret_data = json.loads(secret)
            # If JSON, look for common key names
            for key in ["value", "secret", "token", "key"]:
                if key in secret_data:
                    return str(secret_data[key])
            # If no common key, return first value
            if secret_data:
                return str(next(iter(secret_data.values())))
            return secret
        except json.JSONDecodeError:
            return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve secret {secret_name}: {e}")
        raise


def get_secrets_manager_client() -> Any:
    """Get Secrets Manager client (allows mocking in tests)."""
    return boto3.client("secretsmanager")


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def store_nb_tokens(
    user_id: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    nb_slug: str,
) -> None:
    """
    Store NationBuilder tokens in Secrets Manager.

    Secret path: nat/user/{user_id}/nb-tokens
    """
    client = get_secrets_manager_client()
    secret_name = f"nat/user/{user_id}/nb-tokens"

    now = datetime.now(timezone.utc)
    expires_at = now.timestamp() + expires_in

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "nb_slug": nb_slug,
        "updated_at": now.isoformat(),
    }

    try:
        # Try to update existing secret
        client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(token_data),
        )
        logger.info(f"Updated NB tokens for user {user_id}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            # Create new secret if it doesn't exist
            client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(token_data),
                Description=f"NationBuilder OAuth tokens for user {user_id}",
            )
            logger.info(f"Created NB tokens secret for user {user_id}")
        else:
            logger.error(f"Failed to store NB tokens for user {user_id}: {e}")
            raise


def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    nb_slug: str,
    client_id: str,
    client_secret: str,
) -> TokenResponse:
    """
    Exchange authorization code for access and refresh tokens.

    NationBuilder OAuth 2.0 token endpoint:
    POST https://{slug}.nationbuilder.com/oauth/token
    """
    token_url = f"https://{nb_slug}.nationbuilder.com/oauth/token"

    # NationBuilder expects form-encoded POST body
    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    http = urllib3.PoolManager()

    try:
        response = http.request(
            "POST",
            token_url,
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )

        if response.status != 200:
            logger.error(
                f"Token exchange failed: {response.status} - {response.data.decode('utf-8')}"
            )
            raise ValueError(f"Token exchange failed with status {response.status}")

        token_data: TokenResponse = json.loads(response.data.decode("utf-8"))
        return token_data

    except urllib3.exceptions.HTTPError as e:
        logger.error(f"HTTP error during token exchange: {e}")
        raise


def update_user_nb_status(
    user_id: str,
    nb_connected: bool,
    nb_slug: str,
    expires_at: float,
) -> None:
    """Update user record with NationBuilder connection status."""
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    now = datetime.now(timezone.utc).isoformat()
    expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    try:
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET nb_connected = :connected, "
                "nb_slug = :slug, "
                "nb_token_expires_at = :expires, "
                "nb_needs_reauth = :needs_reauth, "
                "last_active_at = :updated"
            ),
            ExpressionAttributeValues={
                ":connected": nb_connected,
                ":slug": nb_slug,
                ":expires": expires_at_iso,
                ":needs_reauth": False,
                ":updated": now,
            },
        )
        logger.info(f"Updated NB connection status for user {user_id}")
    except ClientError as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        raise


def create_redirect_response(url: str) -> LambdaResponse:
    """Create a redirect response."""
    return {
        "statusCode": 302,
        "body": "",
        "headers": {
            "Location": url,
            "Access-Control-Allow-Origin": "*",
        },
    }


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """
    Lambda handler for NationBuilder OAuth callback.

    Expected query parameters:
    - code: Authorization code from NationBuilder
    - state: Contains user_id and nb_slug as JSON (base64 encoded)

    The state parameter format: {"user_id": "xxx", "nb_slug": "xxx", "redirect_uri": "xxx"}
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    try:
        # Extract query parameters
        query_params = event.get("queryStringParameters") or {}
        code = query_params.get("code")
        state = query_params.get("state")

        if not code:
            logger.error("Missing authorization code")
            error_url = f"{ERROR_REDIRECT_URL}?error=missing_code"
            return create_redirect_response(error_url)

        if not state:
            logger.error("Missing state parameter")
            error_url = f"{ERROR_REDIRECT_URL}?error=missing_state"
            return create_redirect_response(error_url)

        # Parse state parameter
        try:
            import base64
            state_json = base64.urlsafe_b64decode(state).decode("utf-8")
            state_data = json.loads(state_json)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid state parameter: {e}")
            error_url = f"{ERROR_REDIRECT_URL}?error=invalid_state"
            return create_redirect_response(error_url)

        user_id = state_data.get("user_id")
        nb_slug = state_data.get("nb_slug")
        redirect_uri = state_data.get("redirect_uri")

        if not user_id or not nb_slug or not redirect_uri:
            logger.error("State missing required fields")
            error_url = f"{ERROR_REDIRECT_URL}?error=invalid_state"
            return create_redirect_response(error_url)

        logger.info(f"Processing OAuth callback for user {user_id}, nation {nb_slug}")

        # Get NB OAuth credentials from Secrets Manager
        client_id = get_secret(NB_CLIENT_ID_SECRET)
        client_secret = get_secret(NB_CLIENT_SECRET_SECRET)

        # Exchange code for tokens
        token_response = exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            nb_slug=nb_slug,
            client_id=client_id,
            client_secret=client_secret,
        )

        access_token = token_response.get("access_token", "")
        refresh_token = token_response.get("refresh_token", "")
        expires_in = token_response.get("expires_in", 7200)  # Default 2 hours

        if not access_token:
            logger.error("No access token in response")
            error_url = f"{ERROR_REDIRECT_URL}?error=no_token"
            return create_redirect_response(error_url)

        # Store tokens in Secrets Manager
        store_nb_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_in=expires_in,
            nb_slug=nb_slug,
        )

        # Calculate expiration timestamp
        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + expires_in

        # Update user record
        update_user_nb_status(
            user_id=user_id,
            nb_connected=True,
            nb_slug=nb_slug,
            expires_at=expires_at,
        )

        logger.info(f"Successfully connected NB for user {user_id}")

        # Redirect to success page
        success_url = f"{SUCCESS_REDIRECT_URL}?user_id={user_id}"
        return create_redirect_response(success_url)

    except ClientError as e:
        logger.error(f"AWS service error: {e}")
        error_url = f"{ERROR_REDIRECT_URL}?error=service_error"
        return create_redirect_response(error_url)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        error_url = f"{ERROR_REDIRECT_URL}?error=unexpected"
        return create_redirect_response(error_url)
