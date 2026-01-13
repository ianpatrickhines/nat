"""
Unit tests for NationBuilder OAuth Callback Lambda Handler
"""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.nb_oauth_callback.handler import (
    create_redirect_response,
    exchange_code_for_tokens,
    handler,
    store_nb_tokens,
    update_user_nb_status,
)


# Test data
TEST_USER_ID = "user-123"
TEST_NB_SLUG = "testnation"
TEST_CODE = "auth_code_12345"
TEST_ACCESS_TOKEN = "access_token_xyz"
TEST_REFRESH_TOKEN = "refresh_token_abc"
TEST_CLIENT_ID = "client_id_123"
TEST_CLIENT_SECRET = "client_secret_456"
TEST_REDIRECT_URI = "https://api.example.com/auth/nationbuilder/callback"


def create_state(user_id: str, nb_slug: str, redirect_uri: str) -> str:
    """Create a base64-encoded state parameter."""
    state_data = {
        "user_id": user_id,
        "nb_slug": nb_slug,
        "redirect_uri": redirect_uri,
    }
    return base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()


class MockDynamoDBTable:
    """Mock DynamoDB table for testing."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.update_calls: list[dict[str, Any]] = []

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
        raise Exception("ResourceNotFoundException")

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


class TestCreateRedirectResponse:
    """Tests for redirect response creation."""

    def test_creates_302_redirect(self) -> None:
        """Test that redirect response has correct status code."""
        response = create_redirect_response("https://example.com/success")
        assert response["statusCode"] == 302
        assert response["headers"]["Location"] == "https://example.com/success"

    def test_includes_cors_header(self) -> None:
        """Test that redirect response includes CORS header."""
        response = create_redirect_response("https://example.com/success")
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"


class TestStoreNBTokens:
    """Tests for storing NB tokens in Secrets Manager."""

    def test_updates_existing_secret(self) -> None:
        """Test that existing secret is updated."""
        mock_client = MockSecretsManagerClient()
        mock_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = "{}"

        with patch(
            "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            store_nb_tokens(
                user_id=TEST_USER_ID,
                access_token=TEST_ACCESS_TOKEN,
                refresh_token=TEST_REFRESH_TOKEN,
                expires_in=7200,
                nb_slug=TEST_NB_SLUG,
            )

        assert len(mock_client.put_calls) == 1
        secret_data = json.loads(mock_client.put_calls[0]["SecretString"])
        assert secret_data["access_token"] == TEST_ACCESS_TOKEN
        assert secret_data["refresh_token"] == TEST_REFRESH_TOKEN
        assert secret_data["nb_slug"] == TEST_NB_SLUG
        assert "expires_at" in secret_data

    def test_creates_new_secret_if_not_exists(self) -> None:
        """Test that new secret is created if it doesn't exist."""
        mock_client = MockSecretsManagerClient()

        # Simulate ResourceNotFoundException on put
        original_put = mock_client.put_secret_value

        def put_raises_not_found(SecretId: str, SecretString: str) -> None:
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException"}},
                "PutSecretValue",
            )

        mock_client.put_secret_value = put_raises_not_found  # type: ignore[method-assign]

        with patch(
            "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
            return_value=mock_client,
        ):
            store_nb_tokens(
                user_id=TEST_USER_ID,
                access_token=TEST_ACCESS_TOKEN,
                refresh_token=TEST_REFRESH_TOKEN,
                expires_in=7200,
                nb_slug=TEST_NB_SLUG,
            )

        assert len(mock_client.create_calls) == 1
        assert mock_client.create_calls[0]["Name"] == f"nat/user/{TEST_USER_ID}/nb-tokens"


class TestUpdateUserNBStatus:
    """Tests for updating user NB connection status."""

    def test_updates_user_record(self) -> None:
        """Test that user record is updated with NB status."""
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)

        with patch(
            "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            update_user_nb_status(
                user_id=TEST_USER_ID,
                nb_connected=True,
                nb_slug=TEST_NB_SLUG,
                expires_at=1704067200.0,  # 2024-01-01 00:00:00 UTC
            )

        assert len(users_table.update_calls) == 1
        update = users_table.update_calls[0]
        assert update["Key"] == {"user_id": TEST_USER_ID}
        assert update["ExpressionAttributeValues"][":connected"] is True
        assert update["ExpressionAttributeValues"][":slug"] == TEST_NB_SLUG
        assert update["ExpressionAttributeValues"][":needs_reauth"] is False


class TestExchangeCodeForTokens:
    """Tests for OAuth code exchange."""

    def test_successful_token_exchange(self) -> None:
        """Test successful code exchange."""
        mock_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_ACCESS_TOKEN,
                "refresh_token": TEST_REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 7200,
            }).encode(),
        )

        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with patch("urllib3.PoolManager", return_value=mock_http):
            tokens = exchange_code_for_tokens(
                code=TEST_CODE,
                redirect_uri=TEST_REDIRECT_URI,
                nb_slug=TEST_NB_SLUG,
                client_id=TEST_CLIENT_ID,
                client_secret=TEST_CLIENT_SECRET,
            )

        assert tokens["access_token"] == TEST_ACCESS_TOKEN
        assert tokens["refresh_token"] == TEST_REFRESH_TOKEN

    def test_failed_token_exchange_raises(self) -> None:
        """Test that failed exchange raises ValueError."""
        mock_response = MockHTTPResponse(
            status=400,
            data=b'{"error": "invalid_grant"}',
        )

        mock_http = MagicMock()
        mock_http.request.return_value = mock_response

        with patch("urllib3.PoolManager", return_value=mock_http):
            with pytest.raises(ValueError, match="Token exchange failed"):
                exchange_code_for_tokens(
                    code=TEST_CODE,
                    redirect_uri=TEST_REDIRECT_URI,
                    nb_slug=TEST_NB_SLUG,
                    client_id=TEST_CLIENT_ID,
                    client_secret=TEST_CLIENT_SECRET,
                )


class TestHandler:
    """Tests for the main Lambda handler."""

    def test_missing_code_redirects_to_error(self) -> None:
        """Test that missing code redirects to error page."""
        event = {
            "queryStringParameters": {"state": create_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)},
        }

        response = handler(event, None)

        assert response["statusCode"] == 302
        assert "error=missing_code" in response["headers"]["Location"]

    def test_missing_state_redirects_to_error(self) -> None:
        """Test that missing state redirects to error page."""
        event = {
            "queryStringParameters": {"code": TEST_CODE},
        }

        response = handler(event, None)

        assert response["statusCode"] == 302
        assert "error=missing_state" in response["headers"]["Location"]

    def test_invalid_state_redirects_to_error(self) -> None:
        """Test that invalid state redirects to error page."""
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": "invalid_base64!!!",
            },
        }

        response = handler(event, None)

        assert response["statusCode"] == 302
        assert "error=invalid_state" in response["headers"]["Location"]

    def test_state_missing_fields_redirects_to_error(self) -> None:
        """Test that state with missing fields redirects to error page."""
        # Create state without redirect_uri
        incomplete_state = base64.urlsafe_b64encode(
            json.dumps({"user_id": TEST_USER_ID}).encode()
        ).decode()

        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": incomplete_state,
            },
        }

        response = handler(event, None)

        assert response["statusCode"] == 302
        assert "error=invalid_state" in response["headers"]["Location"]

    def test_successful_oauth_flow(self) -> None:
        """Test successful OAuth flow end-to-end."""
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(users_table)
        mock_sm_client = MockSecretsManagerClient()
        mock_sm_client.secrets["nat/nb-client-id"] = TEST_CLIENT_ID
        mock_sm_client.secrets["nat/nb-client-secret"] = TEST_CLIENT_SECRET
        mock_sm_client.secrets[f"nat/user/{TEST_USER_ID}/nb-tokens"] = "{}"

        mock_token_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "access_token": TEST_ACCESS_TOKEN,
                "refresh_token": TEST_REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 7200,
            }).encode(),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_token_response

        state = create_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        event = {
            "queryStringParameters": {
                "code": TEST_CODE,
                "state": state,
            },
        }

        with (
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secrets_manager_client",
                return_value=mock_sm_client,
            ),
            patch(
                "src.lambdas.nb_oauth_callback.handler.get_secret",
                side_effect=[TEST_CLIENT_ID, TEST_CLIENT_SECRET],
            ),
            patch("urllib3.PoolManager", return_value=mock_http),
        ):
            response = handler(event, None)

        assert response["statusCode"] == 302
        assert "connected" in response["headers"]["Location"].lower()
        assert TEST_USER_ID in response["headers"]["Location"]

        # Verify user was updated
        assert len(users_table.update_calls) == 1

    def test_token_exchange_failure_redirects_to_error(self) -> None:
        """Test that token exchange failure redirects to error page."""
        mock_sm_client = MockSecretsManagerClient()
        mock_sm_client.secrets["nat/nb-client-id"] = TEST_CLIENT_ID
        mock_sm_client.secrets["nat/nb-client-secret"] = TEST_CLIENT_SECRET

        mock_token_response = MockHTTPResponse(
            status=400,
            data=b'{"error": "invalid_grant"}',
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_token_response

        state = create_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
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

        assert response["statusCode"] == 302
        assert "error" in response["headers"]["Location"]

    def test_null_query_params_handled(self) -> None:
        """Test that null queryStringParameters is handled."""
        event = {"queryStringParameters": None}

        response = handler(event, None)

        assert response["statusCode"] == 302
        assert "error=missing_code" in response["headers"]["Location"]

    def test_no_access_token_in_response(self) -> None:
        """Test handling when token response has no access_token."""
        mock_sm_client = MockSecretsManagerClient()

        mock_token_response = MockHTTPResponse(
            status=200,
            data=json.dumps({
                "token_type": "Bearer",
                "expires_in": 7200,
            }).encode(),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = mock_token_response

        state = create_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
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

        assert response["statusCode"] == 302
        assert "error=no_token" in response["headers"]["Location"]
