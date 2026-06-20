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
    get_nb_tokens_by_nation,
    get_user_info,
    handler,
)


# Test data
TEST_USER_ID = "user-test-12345"
TEST_TENANT_ID = "tenant-test-67890"
TEST_NATION_SLUG = "testnation"
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


class TestGetNbTokensByNation:
    """Tests for per-nation NationBuilder token retrieval."""

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_success(self, mock_get_client: MagicMock) -> None:
        """Test successful per-nation token retrieval."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "access_token": TEST_NB_TOKEN,
                "nation_slug": TEST_NATION_SLUG,
            })
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens_by_nation(TEST_NATION_SLUG)
        assert result is not None
        assert result[0] == TEST_NB_TOKEN
        assert result[1] == TEST_NATION_SLUG
        # Tokens are read from the per-nation secret path
        mock_client.get_secret_value.assert_called_once_with(
            SecretId=f"nat/nation/{TEST_NATION_SLUG}/nb-tokens"
        )

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_falls_back_to_arg_slug(self, mock_get_client: MagicMock) -> None:
        """Test that the requested slug is returned when none is stored."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "access_token": TEST_NB_TOKEN,
                # no nation_slug stored
            })
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens_by_nation(TEST_NATION_SLUG)
        assert result is not None
        assert result == (TEST_NB_TOKEN, TEST_NATION_SLUG)

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_not_found(self, mock_get_client: MagicMock) -> None:
        """Test that a missing nation secret returns None."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue"
        )
        mock_get_client.return_value = mock_client

        result = get_nb_tokens_by_nation(TEST_NATION_SLUG)
        assert result is None

    @patch("src.lambdas.nat_agent.handler.get_secrets_manager_client")
    def test_get_tokens_missing_access_token(self, mock_get_client: MagicMock) -> None:
        """Test that a secret without an access_token returns None."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"nation_slug": TEST_NATION_SLUG})
        }
        mock_get_client.return_value = mock_client

        result = get_nb_tokens_by_nation(TEST_NATION_SLUG)
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
    """Tests for the main Lambda handler (per-nation architecture)."""

    def _valid_body(self, **overrides: Any) -> dict[str, Any]:
        """Build a request body with all required per-nation fields."""
        body: dict[str, Any] = {
            "query": "test query",
            "user_id": TEST_USER_ID,
            "nation_slug": TEST_NATION_SLUG,
        }
        body.update(overrides)
        return body

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
        event = create_api_event(body={
            "user_id": TEST_USER_ID,
            "nation_slug": TEST_NATION_SLUG,
        })
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "query" in body["error"]

    def test_missing_user_id(self) -> None:
        """Test that missing user_id returns 400."""
        event = create_api_event(body={
            "query": "test query",
            "nation_slug": TEST_NATION_SLUG,
        })
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "user_id" in body["error"]

    def test_missing_nation_slug(self) -> None:
        """Test that missing nation_slug returns 400."""
        event = create_api_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "nation_slug" in body["error"]

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_nb_not_connected(
        self,
        mock_get_tokens: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that a nation without NB tokens returns NB_NOT_CONNECTED."""
        mock_get_tokens.return_value = None

        event = create_api_event(body=self._valid_body())
        response = handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "NB_NOT_CONNECTED"
        # Billing reset is checked against the nation, not a tenant
        mock_billing.assert_called_once_with(TEST_NATION_SLUG)
        mock_get_tokens.assert_called_once_with(TEST_NATION_SLUG)

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    def test_rate_limit_exceeded(
        self,
        mock_rate: MagicMock,
        mock_billing: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that exceeding the per-user rate limit returns 429."""
        from src.lambdas.shared.usage_tracking import RateLimitError

        mock_rate.side_effect = RateLimitError(
            message="Rate limit exceeded. Please wait 3 seconds.",
            retry_after=3,
        )

        event = create_api_event(body=self._valid_body())
        response = handler(event, None)

        assert response["statusCode"] == 429
        body = json.loads(response["body"])
        assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert response["headers"]["Retry-After"] == "3"

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.track_query_usage_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_successful_query(
        self,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_track: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test successful agent query charges usage to the nation."""
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)
        mock_track.return_value = 42

        # Mock the async query result
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "Found John Smith with email john@example.com",
            "error": None,
            "tool_calls": [{"name": "list_signups", "input": {"filter": {"email": "john@example.com"}}}],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body=self._valid_body(
            query="Find person by email john@example.com",
        ))
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "Found John Smith" in body["response"]
        assert len(body["tool_calls"]) == 1
        # Usage is charged to the nation, keyed by the requesting user
        mock_track.assert_called_once_with(TEST_USER_ID, TEST_NATION_SLUG)
        # The subscription gate is checked for the nation before processing
        mock_verify.assert_called_once_with(TEST_USER_ID, TEST_NATION_SLUG)

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.track_query_usage_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_query_with_context(
        self,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_track: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test query with page context."""
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Mock the async query result
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "Added donation tag to John Smith",
            "error": None,
            "tool_calls": [],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body=self._valid_body(
            query="Tag this person as a donor",
            context={
                "page_type": "person",
                "person_name": "John Smith",
                "person_id": "12345",
            },
        ))
        response = handler(event, None)

        assert response["statusCode"] == 200

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.track_query_usage_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.asyncio")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_agent_error(
        self,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_track: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test agent error handling does not charge usage."""
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Mock the async query result with error
        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = {
            "response": "",
            "error": "Claude API error: rate limited",
            "tool_calls": [],
        }
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_api_event(body=self._valid_body())
        response = handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error_code"] == "AGENT_ERROR"
        # No usage should be charged when the agent fails
        mock_track.assert_not_called()

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_ids_from_headers(
        self,
        mock_get_tokens: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that user_id and nation_slug can be supplied via headers."""
        mock_get_tokens.return_value = None  # Stop after token lookup

        event = create_api_event(
            body={"query": "test query"},
            headers={
                "X-Nat-User-Id": TEST_USER_ID,
                "X-Nat-Nation-Slug": TEST_NATION_SLUG,
            },
        )
        response = handler(event, None)

        # Reaches per-nation token lookup, then returns NB_NOT_CONNECTED
        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "NB_NOT_CONNECTED"
        mock_get_tokens.assert_called_once_with(TEST_NATION_SLUG)
        mock_billing.assert_called_once_with(TEST_NATION_SLUG)

    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    def test_ids_from_lowercase_headers(
        self,
        mock_get_tokens: MagicMock,
        mock_billing: MagicMock,
        mock_rate: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that lowercase headers are honored for user_id and nation_slug."""
        mock_get_tokens.return_value = None

        event = create_api_event(
            body={"query": "test query"},
            headers={
                "x-nat-user-id": TEST_USER_ID,
                "x-nat-nation-slug": TEST_NATION_SLUG,
            },
        )
        response = handler(event, None)

        assert response["statusCode"] == 403
        mock_get_tokens.assert_called_once_with(TEST_NATION_SLUG)

    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    def test_inactive_subscription_returns_402(
        self,
        mock_billing: MagicMock,
        mock_verify: MagicMock,
        mock_rate: MagicMock,
        mock_get_tokens: MagicMock,
    ) -> None:
        """A cancelled/past-due nation is blocked with 402 before any work."""
        from src.lambdas.shared.subscription_middleware import (
            SubscriptionError,
            SubscriptionErrorCode,
        )

        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message="Nation subscription is not active (status: cancelled).",
            http_status=402,
        )

        event = create_api_event(body=self._valid_body())
        response = handler(event, None)

        assert response["statusCode"] == 402
        body = json.loads(response["body"])
        assert body["error_code"] == "SUBSCRIPTION_INACTIVE"
        # Gate runs before NB tokens / rate limit, so neither is reached
        mock_get_tokens.assert_not_called()
        mock_rate.assert_not_called()

    @patch("src.lambdas.nat_agent.handler.get_nb_tokens_by_nation")
    @patch("src.lambdas.nat_agent.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent.handler.check_and_reset_billing_cycle_nation")
    def test_query_limit_exceeded_returns_403(
        self,
        mock_billing: MagicMock,
        mock_verify: MagicMock,
        mock_rate: MagicMock,
        mock_get_tokens: MagicMock,
    ) -> None:
        """A nation over its query cap is blocked with 403."""
        from src.lambdas.shared.subscription_middleware import (
            SubscriptionError,
            SubscriptionErrorCode,
        )

        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED,
            message="Monthly query limit of 500 exceeded.",
            http_status=403,
        )

        event = create_api_event(body=self._valid_body())
        response = handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error_code"] == "QUERY_LIMIT_EXCEEDED"
        mock_get_tokens.assert_not_called()

    def test_cors_headers_present(self) -> None:
        """Test that CORS headers advertise the nation slug header."""
        event = create_api_event(body=None)
        response = handler(event, None)

        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
        assert "X-Nat-Nation-Slug" in response["headers"]["Access-Control-Allow-Headers"]
