"""
Unit tests for Token Refresh Lambda Handler
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from src.lambdas.token_refresh.handler import (
    find_users_with_expiring_tokens,
    get_user_tokens,
    handler,
    refresh_access_token,
    refresh_user_token,
    store_nb_tokens,
    update_user_token_status,
)


# Test data
TEST_USER_ID = "user-123"
TEST_NB_SLUG = "testnation"
TEST_ACCESS_TOKEN = "access_token_xyz"
TEST_REFRESH_TOKEN = "refresh_token_abc"
TEST_NEW_ACCESS_TOKEN = "new_access_token_xyz"
TEST_NEW_REFRESH_TOKEN = "new_refresh_token_abc"
TEST_CLIENT_ID = "client_id_123"
TEST_CLIENT_SECRET = "client_secret_456"


class MockDynamoDBTable:
    """Mock DynamoDB table for testing."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.scan_filter: Any = None

    def scan(
        self,
        FilterExpression: Any = None,
        ExclusiveStartKey: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.scan_filter = FilterExpression
        return {"Items": self.items}

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


class MockDynamoDBResource:
    """Mock DynamoDB resource for testing."""

    def __init__(self, users_table: MockDynamoDBTable) -> None:
        self.users_table = users_table

    def Table(self, name: str) -> MockDynamoDBTable:
        return self.users_table


class MockSecretsManagerClient:
    """Mock Secrets Manager client for testing."""

    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}
        self.put_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        if SecretId in self.secrets:
            return {"SecretString": self.secrets[SecretId]}
        raise ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "GetSecretValue",
        )

    def put_secret_value(self, SecretId: str, SecretString: str) -> None:
        self.put_calls.append({"SecretId": SecretId, "SecretString": SecretString})
        self.secrets[SecretId] = SecretString

    def create_secret(
        self, Name: str, SecretString: str, Description: str
    ) -> None:
        self.create_calls.append({
            "Name": Name,
            "SecretString": SecretString,
            "Description": Description,
        })
        self.secrets[Name] = SecretString


class MockHTTPResponse:
    """Mock HTTP response for urllib3."""

    def __init__(self, status: int, data: bytes) -> None:
        self.status = status
        self.data = data


class TestGetUserTokens:
    """Tests for retrieving user tokens from Secrets Manager."""

    def test_returns_tokens_when_exist(self) -> None:
        """Test that existing tokens are returned."""
        mock_client = MockSecretsManagerClient()
        token_data = {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "nb_slug": TEST_NB_SLUG,
            "expires_at": 1704067200.0,
        }
        mock_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = json.dumps(
            token_data
        )

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            result = get_user_tokens(TEST_USER_ID)

        assert result is not None
        assert result["access_token"] == TEST_ACCESS_TOKEN
        assert result["refresh_token"] == TEST_REFRESH_TOKEN

    def test_returns_none_when_not_found(self) -> None:
        """Test that None is returned when tokens don't exist."""
        mock_client = MockSecretsManagerClient()

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            result = get_user_tokens(TEST_USER_ID)

        assert result is None


class TestStoreNBTokens:
    """Tests for storing NB tokens in Secrets Manager."""

    def test_updates_existing_secret(self) -> None:
        """Test that existing secret is updated."""
        mock_client = MockSecretsManagerClient()
        mock_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = "{}"

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            store_nb_tokens(
                user_id=TEST_USER_ID,
                access_token=TEST_NEW_ACCESS_TOKEN,
                refresh_token=TEST_NEW_REFRESH_TOKEN,
                expires_in=7200,
                nb_slug=TEST_NB_SLUG,
            )

        assert len(mock_client.put_calls) == 1
        secret_data = json.loads(mock_client.put_calls[0]["SecretString"])
        assert secret_data["access_token"] == TEST_NEW_ACCESS_TOKEN
        assert secret_data["refresh_token"] == TEST_NEW_REFRESH_TOKEN

    def test_creates_new_secret_if_not_exists(self) -> None:
        """Test that new secret is created if it doesn't exist."""
        mock_client = MockSecretsManagerClient()

        # Simulate ResourceNotFoundException on put
        def put_raises_not_found(SecretId: str, SecretString: str) -> None:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException"}},
                "PutSecretValue",
            )

        mock_client.put_secret_value = put_raises_not_found  # type: ignore[method-assign]

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            store_nb_tokens(
                user_id=TEST_USER_ID,
                access_token=TEST_NEW_ACCESS_TOKEN,
                refresh_token=TEST_NEW_REFRESH_TOKEN,
                expires_in=7200,
                nb_slug=TEST_NB_SLUG,
            )

        assert len(mock_client.create_calls) == 1


class TestUpdateUserTokenStatus:
    """Tests for updating user token status."""

    def test_updates_token_expiry(self) -> None:
        """Test that token expiry is updated."""
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        with patch(
            "src.lambdas.token_refresh.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            update_user_token_status(
                user_id=TEST_USER_ID,
                expires_at=1704067200.0,
            )

        assert len(users_table.update_calls) == 1
        update = users_table.update_calls[0]
        assert update["Key"] == {"user_id": TEST_USER_ID}
        assert update["ExpressionAttributeValues"][":needs_reauth"] is False

    def test_sets_needs_reauth(self) -> None:
        """Test that needs_reauth flag is set on failure."""
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        with patch(
            "src.lambdas.token_refresh.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            update_user_token_status(
                user_id=TEST_USER_ID,
                needs_reauth=True,
            )

        assert len(users_table.update_calls) == 1
        update = users_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":needs_reauth"] is True


class TestRefreshAccessToken:
    """Tests for OAuth token refresh."""

    def test_successful_refresh(self) -> None:
        """Test successful token refresh."""
        mock_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_NEW_ACCESS_TOKEN,
                "refresh_token": TEST_NEW_REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 7200,
            }).encode(),
        )

        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with patch("urllib3.PoolManager", return_value=mock_http):
            tokens = refresh_access_token(
                refresh_token=TEST_REFRESH_TOKEN,
                nb_slug=TEST_NB_SLUG,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert tokens["access_token"] == TEST_NEW_ACCESS_TOKEN
        assert tokens["refresh_token"] == TEST_NEW_REFRESH_TOKEN

        # Verify the request was made correctly
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "POST"
        assert TEST_NB_SLUG in call_args[0][1]
        assert "grant_type=refresh_token" in call_args[1]["body"]

    def test_failed_refresh_raises(self) -> None:
        """Test that failed refresh raises ValueError."""
        mock_response = MockHTTPResponse(
            status=400,
            data=b'{"error": "invalid_grant"}',
        )

        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with patch("urllib3.PoolManager", return_value=mock_http):
            with pytest.raises(ValueError, match="Token refresh failed"):
                refresh_access_token(
                    refresh_token=TEST_REFRESH_TOKEN,
                    nb_slug=TEST_NB_SLUG,
                    client_id=TEST_CLIENT_ID,
                    client_secret=TEST_CLIENT_SECRET,
                )


class TestFindUsersWithExpiringTokens:
    """Tests for finding users with expiring tokens."""

    def test_returns_users_with_expiring_tokens(self) -> None:
        """Test that users with expiring tokens are returned."""
        users_table = MockDynamoDBTable()
        users_table.items = [
            {
                "user_id": TEST_USER_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": "2024-01-01T00:00:00+00:00",
            },
        ]
        mock_resource = MockDynamoDBResource(users_table)

        with patch(
            "src.lambdas.token_refresh.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            users = find_users_with_expiring_tokens(window_hours=12)

        assert len(users) == 1
        assert users[0]["user_id"] == TEST_USER_ID

    def test_returns_empty_list_when_no_expiring_tokens(self) -> None:
        """Test that empty list is returned when no tokens expiring."""
        users_table = MockDynamoDBTable()
        users_table.items = []
        mock_resource = MockDynamoDBResource(users_table)

        with patch(
            "src.lambdas.token_refresh.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            users = find_users_with_expiring_tokens(window_hours=12)

        assert len(users) == 0


class TestRefreshUserToken:
    """Tests for refreshing a single user's token."""

    def test_successful_refresh(self) -> None:
        """Test successful token refresh for a user."""
        mock_sm_client = MockSecretsManagerClient()
        token_data = {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "nb_slug": TEST_NB_SLUG,
            "expires_at": 1704067200.0,
        }
        mock_sm_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = json.dumps(
            token_data
        )

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        mock_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_NEW_ACCESS_TOKEN,
                "refresh_token": TEST_NEW_REFRESH_TOKEN,
                "expires_in": 7200,
            }).encode(),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
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

        # Verify tokens were stored
        assert len(mock_sm_client.put_calls) == 1

        # Verify user record was updated
        assert len(users_table.update_calls) == 1

    def test_no_tokens_found(self) -> None:
        """Test handling when no tokens found."""
        mock_sm_client = MockSecretsManagerClient()

        with patch(
            "src.lambdas.token_refresh.handler.get_secrets_manager_client",
            return_value=mock_sm_client,
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is False
        assert result["error"] == "No tokens found"

    def test_no_refresh_token(self) -> None:
        """Test handling when no refresh token in stored data."""
        mock_sm_client = MockSecretsManagerClient()
        token_data = {
            "access_token": TEST_ACCESS_TOKEN,
            "nb_slug": TEST_NB_SLUG,
            # No refresh_token
        }
        mock_sm_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = json.dumps(
            token_data
        )

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is False
        assert result["error"] == "No refresh token"

        # Verify needs_reauth was set
        assert len(users_table.update_calls) == 1
        assert users_table.update_calls[0]["ExpressionAttributeValues"][":needs_reauth"] is True

    def test_refresh_api_failure(self) -> None:
        """Test handling when refresh API call fails."""
        mock_sm_client = MockSecretsManagerClient()
        token_data = {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "nb_slug": TEST_NB_SLUG,
        }
        mock_sm_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = json.dumps(
            token_data
        )

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        mock_response = MockHTTPResponse(
            status=400,
            data=b'{"error": "invalid_grant"}',
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            result = refresh_user_token(
                user_id=TEST_USER_ID,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert result["success"] is False
        assert "Token refresh failed" in str(result["error"])

        # Verify needs_reauth was set
        assert len(users_table.update_calls) == 1
        assert users_table.update_calls[0]["ExpressionAttributeValues"][":needs_reauth"] is True


class TestHandler:
    """Tests for the main Lambda handler."""

    def test_no_tokens_to_refresh(self) -> None:
        """Test handler when no tokens need refreshing."""
        users_table = MockDynamoDBTable()
        users_table.items = []
        mock_resource = MockDynamoDBResource(users_table)
        mock_sm_client = MockSecretsManagerClient()
        mock_sm_client.secrets["nat/nb-client-id"] = TEST_CLIENT_ID
        mock_sm_client.secrets["nat/nb-client-secret"] = TEST_CLIENT_SECRET

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
        ):
            response = handler({}, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processed"] == 0
        assert body["succeeded"] == 0

    def test_successful_refresh_batch(self) -> None:
        """Test handler with multiple users to refresh."""
        users_table = MockDynamoDBTable()
        users_table.items = [
            {
                "user_id": "user-1",
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "user_id": "user-2",
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": "2024-01-01T00:00:00+00:00",
            },
        ]
        mock_resource = MockDynamoDBResource(users_table)

        mock_sm_client = MockSecretsManagerClient()
        mock_sm_client.secrets["nat/nb-client-id"] = TEST_CLIENT_ID
        mock_sm_client.secrets["nat/nb-client-secret"] = TEST_CLIENT_SECRET

        # Set up token data for both users
        for user_id in ["user-1", "user-2"]:
            token_data = {
                "access_token": TEST_ACCESS_TOKEN,
                "refresh_token": TEST_REFRESH_TOKEN,
                "nb_slug": TEST_NB_SLUG,
            }
            mock_sm_client.secrets[f"nat/user/{user_id}/nb-tokens"] = json.dumps(
                token_data
            )

        mock_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_NEW_ACCESS_TOKEN,
                "refresh_token": TEST_NEW_REFRESH_TOKEN,
                "expires_in": 7200,
            }).encode(),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler({}, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processed"] == 2
        assert body["succeeded"] == 2
        assert body["failed"] == 0

    def test_mixed_success_and_failure(self) -> None:
        """Test handler with mix of successful and failed refreshes."""
        users_table = MockDynamoDBTable()
        users_table.items = [
            {
                "user_id": "user-success",
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "user_id": "user-fail",
                "nb_connected": True,
                "nb_needs_reauth": False,
                "nb_token_expires_at": "2024-01-01T00:00:00+00:00",
            },
        ]
        mock_resource = MockDynamoDBResource(users_table)

        mock_sm_client = MockSecretsManagerClient()
        mock_sm_client.secrets["nat/nb-client-id"] = TEST_CLIENT_ID
        mock_sm_client.secrets["nat/nb-client-secret"] = TEST_CLIENT_SECRET

        # Only set up tokens for success user
        success_token_data = {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "nb_slug": TEST_NB_SLUG,
        }
        mock_sm_client.secrets["nat/user/user-success/nb-tokens"] = json.dumps(
            success_token_data
        )
        # user-fail has no tokens

        mock_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_NEW_ACCESS_TOKEN,
                "refresh_token": TEST_NEW_REFRESH_TOKEN,
                "expires_in": 7200,
            }).encode(),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with (
            patch(
                "src.lambdas.token_refresh.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.token_refresh.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler({}, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["processed"] == 2
        assert body["succeeded"] == 1
        assert body["failed"] == 1
        assert len(body["failures"]) == 1
        assert body["failures"][0]["user_id"] == "user-fail"

    def test_aws_error_returns_500(self) -> None:
        """Test that AWS errors return 500."""
        with patch(
            "src.lambdas.token_refresh.handler.get_secret",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDeniedException"}},
                "GetSecretValue",
            ),
        ):
            response = handler({}, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
