"""
Unit tests for Nat Agent Lambda Handler
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lambdas.nat_agent.handler import (
    get_anthropic_api_key,
    get_nb_tokens,
    get_user_info,
    handler,
)


# Test data
TEST_USER_ID = "user-test-12345"
TEST_TENANT_ID = "tenant-test-67890"
TEST_NB_SLUG = "testnation"
TEST_NB_TOKEN = "nb_test_token_abc123"
TEST_API_KEY = "sk-ant-test-key"


def create_api_event(
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a mock API Gateway event."""
    return {
        "body": json.dumps(body) if body else "",
        "headers": headers or {},
        "httpMethod": "POST",
        "path": "/agent/query",
    }


class TestGetAnthropicApiKey:
    """Tests for Anthropic API key retrieval."""

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_api_key_plain_string(self, mock_get_client: MagicMock) -> None:
        """Test retrieving API key stored as plain string."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": TEST_API_KEY
        }
        mock_get_client.return_value = mock_client

        result = get_anthropic_api_key()
        assert result == TEST_API_KEY

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_api_key_json_format(self, mock_get_client: MagicMock) -> None:
        """Test retrieving API key stored as JSON."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": TEST_API_KEY})
        }
        mock_get_client.return_value = mock_client

        result = get_anthropic_api_key()
        assert result == TEST_API_KEY

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_api_key_missing_raises(self, mock_get_client: MagicMock) -> None:
        """Test that missing secret raises exception."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue"
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(ClientError):
            get_anthropic_api_key()


class TestGetNbTokens:
    """Tests for NationBuilder token retrieval."""

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_success(self, mock_get_client: MagicMock) -> None:
        """Test successful token retrieval."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "access_token": TEST_NB_TOKEN,
                "nb_slug": TEST_NB_SLUG,
            })
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens(TEST_USER_ID)
        assert result is not None
        assert result[0] == TEST_NB_TOKEN
        assert result[1] == TEST_NB_SLUG

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_not_found(self, mock_get_client: MagicMock) -> None:
        """Test that missing tokens return None."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue"
        )
        mock_get_client.return_value = mock_client

        result = get_nb_tokens(TEST_USER_ID)
        assert result is None

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_missing_fields(self, mock_get_client: MagicMock) -> None:
        """Test that tokens with missing fields return None."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "access_token": TEST_NB_TOKEN,
                # missing nb_slug
            })
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens(TEST_USER_ID)
        assert result is None

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_invalid_json(self, mock_get_client: MagicMock) -> None:
        """Test that invalid JSON returns None."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": "not valid json"
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens(TEST_USER_ID)
        assert result is None


class TestGetUserInfo:
    """Tests for user info retrieval."""

    @patch("src.lambdas.nat_agent.handler.get_dynamodb_resource")
    def test_get_user_success(self, mock_get_resource: MagicMock) -> None:
        """Test successful user retrieval."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "user_id": TEST_USER_ID,
                "tenant_id": TEST_TENANT_ID,
                "nb_connected": True,
                "nb_needs_reauth": False,
            }
        }
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_resource.return_value = mock_dynamodb

        result = get_user_info(TEST_USER_ID)
        assert result is not None
        assert result["user_id"] == TEST_USER_ID
        assert result["nb_connected"] is True

    @patch("src.lambdas.nat_agent.handler.get_dynamodb_resource")
    def test_get_user_not_found(self, mock_get_resource: MagicMock) -> None:
        """Test user not found returns None."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item key
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_resource.return_value = mock_dynamodb

        result = get_user_info(TEST_USER_ID)
        assert result is None


class TestHandler:
    """Tests for the main Lambda handler."""

    def test_empty_body(self) -> None:
        """Test that empty request body returns 400."""
        event = create_api_event(body=None)
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Empty request body" in body["error"]

    def test_invalid_json_body(self) -> None:
        """Test that invalid JSON returns 400."""
        event = {
            "body": "not valid json",
            "headers": {},
        }
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid JSON" in body["error"]

    def test_missing_query(self) -> None:
        """Test that missing query returns 400."""
        event = create_api_event(body={"user_id": TEST_USER_ID})
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "query" in body["error"]

    def test_missing_user_id(self) -> None:
        """Test that missing user_id returns 400."""
        event = create_api_event(body={"query": "test query"})
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "user_id" in body["error"]

    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_user_not_found(self, mock_get_user: MagicMock) -> None:
        """Test that unknown user returns 404."""
        mock_get_user.return_value = None

        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "not found" in body["error"]

    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_nb_not_connected(self, mock_get_user: MagicMock) -> None:
        """Test that NB not connected returns 403."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": False,
        }

        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "NB_NOT_CONNECTED"

    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_nb_needs_reauth(self, mock_get_user: MagicMock) -> None:
        """Test that NB needs reauth returns 403."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": True,
        }

        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "NB_NEEDS_REAUTH"

    @patch("src.lambdas.nat_agent.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_nb_tokens_missing(
        self, mock_get_user: MagicMock, mock_get_tokens: MagicMock
    ) -> None:
        """Test that missing NB tokens returns 403."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = None

        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "NB_TOKENS_MISSING"

    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_successful_query(
        self,
        mock_get_user: MagicMock,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Test successful agent query."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Mock the async query result
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "Found John Smith with email john@example.com",
            "error": None,
            "tool_calls": [{"name": "list_signups", "input": {"filter": {"email": "john@example.com"}}}],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body={
            "query": "Find person by email john@example.com",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "Found John Smith" in body["response"]
        assert len(body["tool_calls"]) == 1

    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_query_with_context(
        self,
        mock_get_user: MagicMock,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Test query with page context."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Mock the async query result
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "Added donation tag to John Smith",
            "error": None,
            "tool_calls": [],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body={
            "query": "Tag this person as a donor",
            "user_id": TEST_USER_ID,
            "context": {
                "page_type": "person",
                "person_name": "John Smith",
                "person_id": "12345",
            },
        })
        response = handler(event, None)

        assert response["statusCode"] == 200

    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent.handler.get_user_info")
    def test_agent_error(
        self,
        mock_get_user: MagicMock,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Test agent error handling."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Mock the async query result with error
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "",
            "error": "Claude API error: rate limited",
            "tool_calls": [],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error_code"] == "AGENT_ERROR"

    def test_user_id_from_header(self) -> None:
        """Test that user_id can be extracted from headers."""
        with patch("src.lambdas.nat_agent.handler.get_user_info") as mock_get_user:
            mock_get_user.return_value = None

            event = create_api_event(
                body={"query": "test query"},
                headers={"X-Nat-User-Id": TEST_USER_ID},
            )
            response = handler(event, None)

            # Should reach user lookup (returns 404 since user not found)
            assert response["statusCode"] == 404
            mock_get_user.assert_called_once_with(TEST_USER_ID)

    def test_user_id_from_lowercase_header(self) -> None:
        """Test that user_id can be extracted from lowercase headers."""
        with patch("src.lambdas.nat_agent.handler.get_user_info") as mock_get_user:
            mock_get_user.return_value = None

            event = create_api_event(
                body={"query": "test query"},
                headers={"x-nat-user-id": TEST_USER_ID},
            )
            response = handler(event, None)

            # Should reach user lookup (returns 404 since user not found)
            assert response["statusCode"] == 404
            mock_get_user.assert_called_once_with(TEST_USER_ID)

    def test_cors_headers_present(self) -> None:
        """Test that CORS headers are present in response."""
        event = create_api_event(body=None)
        response = handler(event, None)

        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
