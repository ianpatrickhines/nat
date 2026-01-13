"""
Integration tests for NationBuilder OAuth callback flow.

Tests the complete OAuth callback flow end-to-end with mocked NB API:
- Authorization code exchange
- Token storage in Secrets Manager
- User record updates in DynamoDB
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.nb_oauth_callback.handler import handler


# Test constants
TEST_USER_ID = "integration-test-user-123"
TEST_TENANT_ID = "integration-test-tenant-456"
TEST_NB_SLUG = "democracylab"
TEST_CODE = "nb_auth_code_integration_test"
TEST_REDIRECT_URI = "https://api.natassistant.com/auth/nationbuilder/callback"
TEST_CLIENT_ID = "nb_client_id_12345"
TEST_CLIENT_SECRET = "nb_client_secret_67890"
TEST_ACCESS_TOKEN = "nb_access_token_abcdef"
TEST_REFRESH_TOKEN = "nb_refresh_token_ghijkl"


def create_oauth_state(
    user_id: str,
    nb_slug: str,
    redirect_uri: str,
) -> str:
    """Create a valid OAuth state parameter."""
    state_data = {
        "user_id": user_id,
        "nb_slug": nb_slug,
        "redirect_uri": redirect_uri,
    }
    return base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()


class MockDynamoDBTable:
    """Mock DynamoDB table that simulates real table behavior."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        if items:
            for item in items:
                key = item.get("user_id") or item.get("tenant_id")
                if key:
                    self.items[key] = item
        self.update_calls: list[dict[str, Any]] = []
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        self.get_calls.append(Key)
        key = Key.get("user_id") or Key.get("tenant_id")
        if key and key in self.items:
            return {"Item": self.items[key]}
        return {}

    def put_item(self, Item: dict[str, Any]) -> None:
        key = Item.get("user_id") or Item.get("tenant_id")
        if key:
            self.items[key] = Item
        self.put_calls.append(Item)

    def update_item(
        self,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
    ) -> None:
        self.update_calls.append({
            "Key": Key,
            "UpdateExpression": UpdateExpression,
            "ExpressionAttributeValues": ExpressionAttributeValues,
        })
        # Simulate the update
        key = Key.get("user_id") or Key.get("tenant_id")
        if key and key in self.items:
            for attr_key, attr_val in ExpressionAttributeValues.items():
                # Extract attribute name from :attr format
                attr_name = attr_key[1:]  # Remove leading :
                self.items[key][attr_name] = attr_val

    def query(
        self,
        IndexName: str,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> dict[str, Any]:
        return {"Items": []}


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
    """Mock Secrets Manager client that simulates real behavior."""

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
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

    def put_secret_value(self, SecretId: str, SecretString: str) -> None:
        self.put_calls.append({"SecretId": SecretId, "SecretString": SecretString})
        self.secrets[SecretId] = SecretString

    def create_secret(
        self,
        Name: str,
        SecretString: str,
        Description: str = "",
    ) -> None:
        self.create_calls.append({
            "Name": Name,
            "SecretString": SecretString,
            "Description": Description,
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


class TestOAuthCallbackIntegration:
    """Integration tests for the complete OAuth callback flow."""

    def test_complete_oauth_flow_new_user(self) -> None:
        """Test complete OAuth flow for a new user connecting NationBuilder."""
        # Setup: User exists in DB but hasn't connected NB yet
        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "email": "test@example.com",
            "nb_connected": False,
            "nb_needs_reauth": False,
        }])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
        })

        # Mock NB token endpoint response
        nb_token_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": "read write",
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_token_response

        # Create OAuth callback event
        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify redirect to success page
        assert response["statusCode"] == 302
        assert "connected" in response["headers"]["Location"].lower()
        assert TEST_USER_ID in response["headers"]["Location"]

        # Verify NB API was called with correct parameters
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "POST"
        assert f"https://{TEST_NB_SLUG}.nationbuilder.com/oauth/token" in call_args[0][1]

        # Verify tokens were stored in Secrets Manager
        token_secret_name = f"nat/user/{TEST_USER_ID}/nb-tokens"
        assert len(secrets_client.put_calls) > 0 or len(secrets_client.create_calls) > 0

        # Check if tokens exist in secrets
        assert token_secret_name in secrets_client.secrets
        stored_tokens = json.loads(secrets_client.secrets[token_secret_name])
        assert stored_tokens["access_token"] == TEST_ACCESS_TOKEN
        assert stored_tokens["refresh_token"] == TEST_REFRESH_TOKEN
        assert stored_tokens["nb_slug"] == TEST_NB_SLUG
        assert "expires_at" in stored_tokens

        # Verify user record was updated
        assert len(users_table.update_calls) == 1
        update = users_table.update_calls[0]
        assert update["Key"] == {"user_id": TEST_USER_ID}
        assert update["ExpressionAttributeValues"][":connected"] is True
        assert update["ExpressionAttributeValues"][":slug"] == TEST_NB_SLUG
        assert update["ExpressionAttributeValues"][":needs_reauth"] is False

    def test_oauth_flow_reconnecting_user(self) -> None:
        """Test OAuth flow for a user who needs to reconnect (reauth)."""
        # Setup: User previously connected but needs reauth
        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "email": "test@example.com",
            "nb_connected": True,
            "nb_needs_reauth": True,
            "nb_slug": TEST_NB_SLUG,
        }])

        # Existing token secret will be updated
        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
            f"nat/user/{TEST_USER_ID}/nb-tokens": json.dumps({
                "access_token": "old_token",
                "refresh_token": "old_refresh",
            }),
        })

        nb_token_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "token_type": "Bearer",
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_token_response

        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify success redirect
        assert response["statusCode"] == 302
        assert "error" not in response["headers"]["Location"]

        # Verify tokens were updated (put, not create)
        assert len(secrets_client.put_calls) == 1
        stored_tokens = json.loads(secrets_client.put_calls[0]["SecretString"])
        assert stored_tokens["access_token"] == TEST_ACCESS_TOKEN

        # Verify nb_needs_reauth was cleared
        update = users_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":needs_reauth"] is False

    def test_oauth_flow_nb_api_error(self) -> None:
        """Test OAuth flow when NationBuilder API returns an error."""
        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
        })

        # NB API returns error (invalid grant)
        nb_error_response = MockHTTPResponse(400, {
            "error": "invalid_grant",
            "error_description": "Authorization code has expired",
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_error_response

        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify redirect to error page
        assert response["statusCode"] == 302
        assert "error" in response["headers"]["Location"]

    def test_oauth_flow_nb_api_network_error(self) -> None:
        """Test OAuth flow when NationBuilder API is unreachable."""
        import urllib3

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
        })

        # Simulate network error
        mock_http = MagicMock()
        mock_http.request.side_effect = urllib3.exceptions.HTTPError("Connection refused")

        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify redirect to error page
        assert response["statusCode"] == 302
        assert "error" in response["headers"]["Location"]

    def test_oauth_flow_different_nations(self) -> None:
        """Test OAuth flow works for different NationBuilder nations."""
        nations = ["democracylab", "greenfuture", "changemakers"]

        for nb_slug in nations:
            users_table = MockDynamoDBTable([{
                "user_id": TEST_USER_ID,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": False,
            }])

            secrets_client = MockSecretsManagerClient({
                "nat/nb-client-id": TEST_CLIENT_ID,
                "nat/nb-client-secret": TEST_CLIENT_SECRET,
            })

            nb_token_response = MockHTTPResponse(200, {
                "access_token": f"token_for_{nb_slug}",
                "refresh_token": f"refresh_for_{nb_slug}",
                "expires_in": 7200,
            })
            mock_http = MagicMock()
            mock_http.request.return_value = nb_token_response

            state = create_oauth_state(TEST_USER_ID, nb_slug, TEST_REDIRECT_URI)
            event = {
                "queryStringParameters": {
                    "code": TEST_CODE,
                    "state": state,
                },
            }

            with (
                patch(
                    "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                    return_value=MockDynamoDBResource({"users": users_table}),
                ),
                patch(
                    "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                    return_value=secrets_client,
                ),
                patch(
                    "src.lambdas.nb_oauth_callback.handler.get_secret",
                    side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
                ),
                patch("urllib3.PoolManager", return_value=mock_http),
            ):
                response = handler(event, None)

            # Verify correct NB endpoint was called
            call_args = mock_http.request.call_args
            assert f"https://{nb_slug}.nationbuilder.com/oauth/token" in call_args[0][1]

            # Verify slug was stored
            update = users_table.update_calls[0]
            assert update["ExpressionAttributeValues"][":slug"] == nb_slug

    def test_oauth_flow_with_optional_fields(self) -> None:
        """Test OAuth flow when NB API response has optional fields missing."""
        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": False,
        }])

        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
        })

        # Response without refresh_token (some OAuth providers don't always return it)
        nb_token_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "token_type": "Bearer",
            "expires_in": 3600,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_token_response

        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Should still succeed
        assert response["statusCode"] == 302
        assert "connected" in response["headers"]["Location"].lower()

        # Verify empty refresh_token was stored
        token_secret_name = f"nat/user/{TEST_USER_ID}/nb-tokens"
        stored_tokens = json.loads(secrets_client.secrets[token_secret_name])
        assert stored_tokens["refresh_token"] == ""

    def test_oauth_flow_creates_new_secret_for_first_connection(self) -> None:
        """Test that a new secret is created when user first connects NB."""
        users_table = MockDynamoDBTable([{
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": False,
        }])

        # No existing token secret
        secrets_client = MockSecretsManagerClient({
            "nat/nb-client-id": TEST_CLIENT_ID,
            "nat/nb-client-secret": TEST_CLIENT_SECRET,
        })

        # Simulate put_secret_value raising ResourceNotFoundException
        original_put = secrets_client.put_secret_value

        def put_raises_not_found(SecretId: str, SecretString: str) -> None:
            from botocore.exceptions import ClientError
            if "nb-tokens" in SecretId:
                raise ClientError(
                    {"Error": {"Code": "ResourceNotFoundException"}},
                    "PutSecretValue",
                )
            original_put(SecretId, SecretString)

        secrets_client.put_secret_value = put_raises_not_found  # type: ignore[method-assign]

        nb_token_response = MockHTTPResponse(200, {
            "access_token": TEST_ACCESS_TOKEN,
            "refresh_token": TEST_REFRESH_TOKEN,
            "expires_in": 7200,
        })
        mock_http = MagicMock()
        mock_http.request.return_value = nb_token_response

        state = create_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                return_value=MockDynamoDBResource({"users": users_table}),
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                return_value=secrets_client,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        # Verify success
        assert response["statusCode"] == 302
        assert "connected" in response["headers"]["Location"].lower()

        # Verify create_secret was called
        assert len(secrets_client.create_calls) == 1
        assert "nb-tokens" in secrets_client.create_calls[0]["Name"]
