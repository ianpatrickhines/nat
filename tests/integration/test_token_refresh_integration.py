"""
Integration tests for NationBuilder token refresh flow.

Tests the complete token refresh flow end-to-end with mocked NB API:
- Finding users with expiring tokens
- Refreshing tokens via NB OAuth endpoint
- Updating tokens in Secrets Manager
- Handling refresh failures
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.token_refresh.handler import (
    find_users_with_expiring_tokens,
    handler,
    refresh_user_token,
)


# Test constants
TEST_USER_ID = "refresh-test-user-123"
TEST_USER_ID_2 = "refresh-test-user-456"
TEST_TENANT_ID = "refresh-test-tenant-789"
TEST_NB_SLUG = "testorganization"
TEST_CLIENT_ID = "nb_client_id_refresh"
TEST_CLIENT_SECRET = "nb_client_secret_refresh"
TEST_ACCESS_TOKEN = "new_access_token_abc"
TEST_REFRESH_TOKEN = "new_refresh_token_xyz"
TEST_OLD_REFRESH_TOKEN = "old_refresh_token_123"


class MockDynamoDBTable:
    """Mock DynamoDB table with scan support."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items: list[dict[str, Any]] = items or []
        self.scan_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def scan(
        self,
        FilterExpression: Any = None,
        ExclusiveStartKey: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.scan_calls.append({
            "FilterExpression": FilterExpression,
            "ExclusiveStartKey": ExclusiveStartKey,
        })
        # Return all items (filter is applied in real DynamoDB)
        # For testing, we pre-filter the items to match expected behavior
        return {"Items": self.items}

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        self.get_calls.append(Key)
        key = Key.get("user_id") or Key.get("tenant_id")
        for item in self.items:
            item_key = item.get("user_id") or item.get("tenant_id")
            if item_key == key:
                return {"Item": item}
        return {}

    def update_item(
        self,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> None:
        self.update_calls.append({
            "Key": Key,
            "UpdateExpression": UpdateExpression,
            "ExpressionAttributeValues": ExpressionAttributeValues,
        })
        # Simulate update
        key = Key.get("user_id") or Key.get("tenant_id")
        for item in self.items:
            item_key = item.get("user_id") or item.get("tenant_id")
            if item_key == key:
                for attr_key, attr_val in ExpressionAttributeValues.items():
                    attr_name = attr_key[1:]  # Remove :
                    item[attr_name] = attr_val


class MockDynamoDBResource:
    """Mock DynamoDB resource."""

    def __init__(self, tables: dict[str, MockDynamoDBTable]) -> None:
        self.tables = tables

    def Table(self, name: str) -> MockDynamoDBTable:
        for table_name, table in self.tables.items():
            if table_name in name.lower():
                return table
        return MockDynamoDBTable()


class MockSecretsManagerClient:
    """Mock Secrets Manager client."""

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self.secrets: dict[str, str] = secrets or {}
        self.put_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        self.get_calls.append(SecretId)
        if SecretId in self.secrets:
            return {"SecretString": self.secrets[SecretId]}
        from botocore.exceptions import ClientError
        raise ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "GetSecretValue",
        )

    def put_secret_value(self, SecretId: str, SecretString: str) -> None:
        self.put_calls.append({"SecretId": SecretId, "SecretString": SecretString})
        self.secrets[SecretId] = SecretString

    def create_secret(self, Name: str, SecretString: str, Description: str = "") -> None:
        self.create_calls.append({
            "Name": Name,
            "SecretString": SecretString,
        })
        self.secrets[Name] = SecretString


class MockHTTPResponse:
    """Mock urllib3 HTTP response."""

    def __init__(self, status: int, data: dict[str, Any] | str) -> None:
        self.status = status
        if isinstance(data, dict):
            self.data = json.dumps(data).encode()
        else:
            self.data = data.encode()


class TestTokenRefreshIntegration:
    """Integration tests for the complete token refresh flow."""

    def test_complete_refresh_flow_single_user(self) -> None:
        """Test complete token refresh for a single user with expiring token."""
        # Calculate expiration time within the refresh window (next 12 hours)
        now = datetime.now(timezone.utc)
        expires_soon = (now.timestamp() + 3600)  # 1 hour from now
        expires_soon_iso = datetime.fromtimestamp(expires_soon, tz=timezone.utc).isoformat()

        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
            "nb_token_expires_at": expires_soon_iso,
            "nb_slug": TEST_NB_SLUG,
        }])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old_access_token",
                "refresh_token": TEST_OLD_REFRESH_TOKEN,
                "nb_slug": TEST_NB_SLUG,
            }),
        })

        # Mock NB refresh response
        nb_refresh_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "token_type": "Bearer",
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_refresh_response

        event: dict[str, Any] = {}  # EventBridge event

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify success
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processed"] == 1
        assert body["succeeded"] == 1
        assert body["failed"] == 0

        # Verify NB API was called with correct parameters
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "POST"
        assert f"https://{TEST_NB_SLUG}.nationbuilder.com/oauth/token" in call_args[0][1]

        # Verify body contains refresh_token grant
        body_str = call_args[1]["body"]
        assert "grant_type=refresh_token" in body_str
        assert f"refresh_token={TEST_OLD_REFRESH_TOKEN}" in body_str

        # Verify new tokens were stored (single-use refresh tokens)
        token_secret_name = f"nat/user/{TEST_USER_ID}/nb-tokens"
        assert token_secret_name in secrets_client.secrets
        stored_tokens = json.loads(secrets_client.secrets[token_secret_name])
        assert stored_tokens["access_token"] == TEST_ACCESS_TOKEN
        assert stored_tokens["refresh_token"] == TEST_REFRESH_TOKEN  # New refresh token

        # Verify user record was updated
        assert len(users_table.update_calls) == 1
        update = users_table.update_calls[0]
        assert ":expires" in update["ExpressionAttributeValues"] or ":needs_reauth" in update["ExpressionAttributeValues"]

    def test_refresh_flow_multiple_users(self) -> None:
        """Test token refresh for multiple users with expiring tokens."""
        now = datetime.now(timezone.utc)
        expires_soon = datetime.fromtimestamp(now.timestamp() + 3600, tz=timezone.utc).isoformat()

        users_table = MockDynamoDBTable([
            {
                "user_id": TEST_USER_ID,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": expires_soon,
                "nb_slug": "org1",
            },
            {
                "user_id": TEST_USER_ID_2,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": expires_soon,
                "nb_slug": "org2",
            },
        ])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old1",
                "refresh_token": "refresh1",
                "nb_slug": "org1",
            }),
            f"nat/user/{TEST_USER_ID_2}/nb-tokens": json.dumps({
                "access_token": "old2",
                "refresh_token": "refresh2",
                "nb_slug": "org2",
            }),
        })

        nb_refresh_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_refresh_response

        event: dict[str, Any] = {}

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        body = json.loads(response["body"])
        assert body["processed"] == 2
        assert body["succeeded"] == 2
        assert body["failed"] == 0

        # Verify both users' tokens were refreshed
        assert mock_http.request.call_count == 2

    def test_refresh_flow_with_failures(self) -> None:
        """Test token refresh when some users fail."""
        now = datetime.now(timezone.utc)
        expires_soon = datetime.fromtimestamp(now.timestamp() + 3600, tz=timezone.utc).isoformat()

        users_table = MockDynamoDBTable([
            {
                "user_id": TEST_USER_ID,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": expires_soon,
                "nb_slug": "successorg",
            },
            {
                "user_id": TEST_USER_ID_2,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": expires_soon,
                "nb_slug": "failorg",
            },
        ])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old",
                "refresh_token": "refresh",
                "nb_slug": "successorg",
            }),
            f"nat/user/{TEST_USER_ID_2}/nb-tokens": json.dumps({
                "access_token": "old",
                "refresh_token": "invalid_refresh",  # This will fail
                "nb_slug": "failorg",
            }),
        })

        # Alternate between success and failure
        call_count = [0]

        def side_effect_request(*args: Any, **kwargs: Any) -> MockHTTPResponse:
            call_count[0] += 1
            if call_count[0] == 1:
                return MockHTTPResponse(200, {
                    "access_token": TEST_ACCESS_TOKEN,
                    "refresh_token": TEST_REFRESH_TOKEN,
                    "expires_in": 7200,
                })
            else:
                return MockHTTPResponse(400, {
                    "error": "invalid_grant",
                    "error_description": "Refresh token has expired",
                })

        mock_http = MagicMock()
        mock_http.request.side_effect = side_effect_request

        event: dict[str, Any] = {}

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        body = json.loads(response["body"])
        assert body["processed"] == 2
        assert body["succeeded"] == 1
        assert body["failed"] == 1

        # Verify failed user has nb_needs_reauth set
        needs_reauth_updates = [
            u for u in users_table.update_calls
            if u["ExpressionAttributeValues"].get(":needs_reauth") is True
        ]
        assert len(needs_reauth_updates) >= 1

    def test_refresh_flow_no_tokens_to_refresh(self) -> None:
        """Test token refresh when no users have expiring tokens."""
        # All tokens expire far in the future
        far_future = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + (24 * 3600 * 30),  # 30 days
            tz=timezone.utc,
        ).isoformat()

        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
            "nb_token_expires_at": far_future,
        }])

        # For this test, we need the scan to return empty (no expiring tokens)
        # Override the items to simulate the filter working
        users_table.items = []

        event: dict[str, Any] = {}

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
        ):
            response = handler(event, None)

        body = json.loads(response["body"])
        assert body["message"] == "No tokens need refreshing"
        assert body["processed"] == 0

    def test_refresh_flow_user_missing_refresh_token(self) -> None:
        """Test handling when user has no refresh token stored."""
        now = datetime.now(timezone.utc)
        expires_soon = datetime.fromtimestamp(now.timestamp() + 3600, tz=timezone.utc).isoformat()

        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
            "nb_token_expires_at": expires_soon,
            "nb_slug": TEST_NB_SLUG,
        }])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old",
                # No refresh_token!
                "nb_slug": TEST_NB_SLUG,
            }),
        })

        event: dict[str, Any] = {}

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
        ):
            response = handler(event, None)

        body = json.loads(response["body"])
        assert body["failed"] == 1
        assert body["failures"][0]["error"] == "No refresh token"

        # User should be marked as needing reauth
        update = users_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":needs_reauth"] is True

    def test_refresh_flow_preserves_nb_slug(self) -> None:
        """Test that nb_slug is preserved during token refresh."""
        now = datetime.now(timezone.utc)
        expires_soon = datetime.fromtimestamp(now.timestamp() + 3600, tz=timezone.utc).isoformat()

        original_slug = "originalorganization"
        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
            "nb_token_expires_at": expires_soon,
            "nb_slug": original_slug,
        }])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old",
                "refresh_token": TEST_OLD_REFRESH_TOKEN,
                "nb_slug": original_slug,
            }),
        })

        nb_refresh_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_refresh_response

        event: dict[str, Any] = {}

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify slug was preserved in stored tokens
        token_secret_name = f"nat/user/{TEST_USER_ID}/nb-tokens"
        stored_tokens = json.loads(secrets_client.secrets[token_secret_name])
        assert stored_tokens["nb_slug"] == original_slug

        # Verify correct NB endpoint was called
        call_args = mock_http.request.call_args
        assert f"https://{original_slug}.nationbuilder.com/oauth/token" in call_args[0][1]


class TestRefreshUserToken:
    """Tests for the refresh_user_token helper function."""

    def test_successful_refresh(self) -> None:
        """Test successful single user token refresh."""
        secrets_client = MockSecretsManagerClient({
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old",
                "refresh_token": TEST_OLD_REFRESH_TOKEN,
                "nb_slug": TEST_NB_SLUG,
            }),
        })

        users_table = MockDynamoDBTable()

        nb_refresh_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_refresh_response

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is True
        assert result["error"] is None

    def test_refresh_no_tokens_found(self) -> None:
        """Test refresh when no tokens exist for user."""
        secrets_client = MockSecretsManagerClient({})  # No tokens

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=secrets_client,
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is False
        assert result["error"] == "No tokens found"

    def test_refresh_no_nb_slug(self) -> None:
        """Test refresh when nb_slug is missing from tokens."""
        secrets_client = MockSecretsManagerClient({
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old",
                "refresh_token": TEST_OLD_REFRESH_TOKEN,
                # No nb_slug!
            }),
        })

        users_table = MockDynamoDBTable()

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is False
        assert result["error"] == "No NB slug"
