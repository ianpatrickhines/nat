"""
Token Refresh Lambda Handler

Proactively refreshes NationBuilder OAuth tokens before they expire:
- Scans Users table for tokens expiring in the next 12 hours
- Uses refresh_token to obtain new access_token
- Stores new tokens in Secrets Manager
- Sets nb_needs_reauth=true if refresh fails

Triggered by EventBridge every 12 hours.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, TypedDict
from urllib.parse import urlencode

import boto3
import urllib3
from boto3.dynamodb.conditions import Attr
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
# Refresh tokens expiring in the next N hours
TOKEN_EXPIRY_WINDOW_HOURS = int(os.environ.get("TOKEN_EXPIRY_WINDOW_HOURS", "12"))


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str


class TokenResponse(TypedDict, total=False):
    """NationBuilder token response type."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: str


class RefreshResult(TypedDict):
    """Result of a token refresh attempt."""

    user_id: str
    success: bool
    error: str | None


def get_secrets_manager_client() -> Any:
    """Get Secrets Manager client (allows mocking in tests)."""
    return boto3.client("secretsmanager")


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


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


def get_user_tokens(user_id: str) -> dict[str, Any] | None:
    """
    Retrieve NationBuilder tokens for a user from Secrets Manager.

    Returns None if tokens don't exist.
    """
    client = get_secrets_manager_client()
    secret_name = f"nat/user/{user_id}/nb-tokens"

    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret_string: str = response.get("SecretString", "")
        return dict(json.loads(secret_string))
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(f"No tokens found for user {user_id}")
            return None
        logger.error(f"Failed to retrieve tokens for user {user_id}: {e}")
        raise


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


def refresh_access_token(
    refresh_token: str,
    nb_slug: str,
    client_id: str,
    client_secret: str,
) -> TokenResponse:
    """
    Refresh NationBuilder access token using refresh_token.

    NationBuilder OAuth 2.0 token endpoint:
    POST https://{slug}.nationbuilder.com/oauth/token

    Note: NationBuilder refresh tokens are single-use. The response
    will include a new refresh_token that must be stored.
    """
    token_url = f"https://{nb_slug}.nationbuilder.com/oauth/token"

    # NationBuilder expects form-encoded POST body
    body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
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
                f"Token refresh failed: {response.status} - {response.data.decode('utf-8')}"
            )
            raise ValueError(f"Token refresh failed with status {response.status}")

        token_data: TokenResponse = json.loads(response.data.decode("utf-8"))
        return token_data

    except urllib3.exceptions.HTTPError as e:
        logger.error(f"HTTP error during token refresh: {e}")
        raise


def update_user_token_status(
    user_id: str,
    expires_at: float | None = None,
    needs_reauth: bool = False,
) -> None:
    """
    Update user record with token status.

    Args:
        user_id: The user ID
        expires_at: New expiration timestamp (if refresh succeeded)
        needs_reauth: True if refresh failed and user needs to reconnect
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    now = datetime.now(timezone.utc).isoformat()

    try:
        if needs_reauth:
            users_table.update_item(
                Key={"user_id": user_id},
                UpdateExpression=(
                    "SET nb_needs_reauth = :needs_reauth, "
                    "last_active_at = :updated"
                ),
                ExpressionAttributeValues={
                    ":needs_reauth": True,
                    ":updated": now,
                },
            )
            logger.info(f"Marked user {user_id} as needing reauth")
        else:
            expires_at_iso = datetime.fromtimestamp(
                expires_at or 0, tz=timezone.utc
            ).isoformat()
            users_table.update_item(
                Key={"user_id": user_id},
                UpdateExpression=(
                    "SET nb_token_expires_at = :expires, "
                    "nb_needs_reauth = :needs_reauth, "
                    "last_active_at = :updated"
                ),
                ExpressionAttributeValues={
                    ":expires": expires_at_iso,
                    ":needs_reauth": False,
                    ":updated": now,
                },
            )
            logger.info(f"Updated token expiry for user {user_id}")
    except ClientError as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        raise


def find_users_with_expiring_tokens(window_hours: int = 12) -> list[dict[str, Any]]:
    """
    Scan Users table for users with tokens expiring in the next N hours.

    Returns list of user records where:
    - nb_connected = true
    - nb_needs_reauth = false (not already flagged)
    - nb_token_expires_at is within the window
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    now = datetime.now(timezone.utc)
    window_end = now.timestamp() + (window_hours * 3600)
    window_end_iso = datetime.fromtimestamp(window_end, tz=timezone.utc).isoformat()

    # Scan for users with nb_connected=true and tokens expiring soon
    # Note: In production with many users, consider using a GSI on nb_token_expires_at
    try:
        response = users_table.scan(
            FilterExpression=(
                Attr("nb_connected").eq(True)
                & Attr("nb_needs_reauth").ne(True)
                & Attr("nb_token_expires_at").exists()
                & Attr("nb_token_expires_at").lte(window_end_iso)
            ),
        )

        users: list[dict[str, Any]] = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = users_table.scan(
                FilterExpression=(
                    Attr("nb_connected").eq(True)
                    & Attr("nb_needs_reauth").ne(True)
                    & Attr("nb_token_expires_at").exists()
                    & Attr("nb_token_expires_at").lte(window_end_iso)
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            users.extend(response.get("Items", []))

        logger.info(f"Found {len(users)} users with expiring tokens")
        return users

    except ClientError as e:
        logger.error(f"Failed to scan for expiring tokens: {e}")
        raise


def refresh_user_token(
    user_id: str,
    client_id: str,
    client_secret: str,
) -> RefreshResult:
    """
    Refresh tokens for a single user.

    Returns a RefreshResult indicating success or failure.
    """
    try:
        # Get current tokens from Secrets Manager
        tokens = get_user_tokens(user_id)
        if not tokens:
            return {
                "user_id": user_id,
                "success": False,
                "error": "No tokens found",
            }

        refresh_token = tokens.get("refresh_token")
        nb_slug = tokens.get("nb_slug")

        if not refresh_token:
            update_user_token_status(user_id, needs_reauth=True)
            return {
                "user_id": user_id,
                "success": False,
                "error": "No refresh token",
            }

        if not nb_slug:
            update_user_token_status(user_id, needs_reauth=True)
            return {
                "user_id": user_id,
                "success": False,
                "error": "No NB slug",
            }

        # Refresh the token
        token_response = refresh_access_token(
            refresh_token=refresh_token,
            nb_slug=nb_slug,
            client_id=client_id,
            client_secret=client_secret,
        )

        new_access_token = token_response.get("access_token", "")
        new_refresh_token = token_response.get("refresh_token", "")
        expires_in = token_response.get("expires_in", 7200)

        if not new_access_token:
            update_user_token_status(user_id, needs_reauth=True)
            return {
                "user_id": user_id,
                "success": False,
                "error": "No access token in response",
            }

        # Store new tokens (NB refresh tokens are single-use)
        store_nb_tokens(
            user_id=user_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token or refresh_token,
            expires_in=expires_in,
            nb_slug=nb_slug,
        )

        # Calculate new expiration
        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + expires_in

        # Update user record
        update_user_token_status(user_id, expires_at=expires_at)

        return {
            "user_id": user_id,
            "success": True,
            "error": None,
        }

    except ValueError as e:
        # Token refresh API call failed
        logger.error(f"Token refresh failed for user {user_id}: {e}")
        update_user_token_status(user_id, needs_reauth=True)
        return {
            "user_id": user_id,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Unexpected error refreshing token for user {user_id}: {e}")
        return {
            "user_id": user_id,
            "success": False,
            "error": str(e),
        }


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """
    Lambda handler for token refresh.

    Triggered by EventBridge every 12 hours.
    Scans for expiring tokens and refreshes them proactively.
    """
    logger.info("Starting token refresh job")

    try:
        # Get NB OAuth credentials from Secrets Manager
        client_id = get_secret(NB_CLIENT_ID_SECRET)
        client_secret = get_secret(NB_CLIENT_SECRET_SECRET)

        # Find users with expiring tokens
        users = find_users_with_expiring_tokens(TOKEN_EXPIRY_WINDOW_HOURS)

        if not users:
            logger.info("No tokens need refreshing")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "No tokens need refreshing",
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                }),
            }

        # Refresh tokens for each user
        results: list[RefreshResult] = []
        for user in users:
            user_id = user.get("user_id")
            if user_id:
                result = refresh_user_token(
                    user_id=user_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                results.append(result)

        succeeded = sum(1 for r in results if r["success"])
        failed = len(results) - succeeded

        logger.info(f"Token refresh complete: {succeeded} succeeded, {failed} failed")

        # Log failures for debugging
        for result in results:
            if not result["success"]:
                logger.warning(
                    f"Failed to refresh token for user {result['user_id']}: {result['error']}"
                )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Token refresh complete",
                "processed": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "failures": [r for r in results if not r["success"]],
            }),
        }

    except ClientError as e:
        logger.error(f"AWS service error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "AWS service error"}),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Unexpected error"}),
        }
