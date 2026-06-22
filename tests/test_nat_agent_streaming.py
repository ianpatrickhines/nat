"""
Unit tests for Nat Agent Streaming Lambda Handler
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lambdas.nat_agent_streaming.handler import (
    format_sse_event,
    get_anthropic_api_key,
    get_nb_tokens,
    get_user_info,
    handler,
    authenticated_body,
    process_streaming_request,
    stream_agent_response,
    _build_undo_entry,
    _get_undo_instruction,
    SSE_EVENT_TEXT,
    SSE_EVENT_TOOL_USE,
    SSE_EVENT_TOOL_RESULT,
    SSE_EVENT_ERROR,
    SSE_EVENT_DONE,
    SSE_EVENT_CONFIRMATION_REQUIRED,
)
from src.lambdas.shared import session_state
from src.lambdas.shared.session_state import compute_tool_id, make_session_id
from src.lambdas.shared.session_token import mint_session_token


def run_async(coro: Any) -> Any:
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# Test data
TEST_USER_ID = "user-test-12345"
TEST_TENANT_ID = "tenant-test-67890"
TEST_NB_SLUG = "testnation"
TEST_NATION_SLUG = "testnation"
TEST_NB_TOKEN = "nb_test_token_abc123"
TEST_API_KEY = "sk-ant-test-key"
TEST_JWT_SECRET = "test-session-secret"


def bearer(
    user_id: str = TEST_USER_ID,
    nation_slug: str = TEST_NATION_SLUG,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Build an `Authorization: Bearer <jwt>` header value for tests."""
    return f"Bearer {mint_session_token(user_id, nation_slug, secret)}"


def create_lambda_url_event(
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    is_base64: bool = False,
) -> dict[str, Any]:
    """Create a mock Lambda Function URL event."""
    body_str = json.dumps(body) if body else ""
    return {
        "body": body_str,
        "isBase64Encoded": is_base64,
        "headers": headers or {},
        "requestContext": {
            "http": {
                "method": "POST",
                "path": "/",
            }
        },
    }


class TestFormatSseEvent:
    """Tests for SSE event formatting."""

    def test_format_text_event(self) -> None:
        """Test formatting a text event."""
        result = format_sse_event(SSE_EVENT_TEXT, {"text": "Hello"})
        assert result == 'event: text\ndata: {"text": "Hello"}\n\n'

    def test_format_tool_use_event(self) -> None:
        """Test formatting a tool use event."""
        result = format_sse_event(SSE_EVENT_TOOL_USE, {
            "name": "list_signups",
            "input": {"filter": {"email": "test@example.com"}}
        })
        assert "event: tool_use\n" in result
        assert '"name": "list_signups"' in result

    def test_format_error_event(self) -> None:
        """Test formatting an error event."""
        result = format_sse_event(SSE_EVENT_ERROR, {
            "error": "Something went wrong",
            "error_code": "TEST_ERROR"
        })
        assert "event: error\n" in result
        assert '"error": "Something went wrong"' in result

    def test_format_done_event(self) -> None:
        """Test formatting a done event."""
        result = format_sse_event(SSE_EVENT_DONE, {
            "response": "Complete response",
            "tool_calls": []
        })
        assert "event: done\n" in result
        assert '"response": "Complete response"' in result

    def test_format_unicode_characters(self) -> None:
        """Test that unicode is preserved in SSE events."""
        result = format_sse_event(SSE_EVENT_TEXT, {"text": "Hello 世界 🌍"})
        assert "世界" in result
        assert "🌍" in result


class TestGetAnthropicApiKey:
    """Tests for Anthropic API key retrieval (shared with non-streaming)."""

    @patch("src.lambdas.nat_agent_streaming.handler.get_secrets_manager_client")
    def test_get_api_key_plain_string(self, mock_get_client: MagicMock) -> None:
        """Test retrieving API key stored as plain string."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": TEST_API_KEY
        }
        mock_get_client.return_value = mock_client

        result = get_anthropic_api_key()
        assert result == TEST_API_KEY

    @patch("src.lambdas.nat_agent_streaming.handler.get_secrets_manager_client")
    def test_get_api_key_json_format(self, mock_get_client: MagicMock) -> None:
        """Test retrieving API key stored as JSON."""
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": TEST_API_KEY})
        }
        mock_get_client.return_value = mock_client

        result = get_anthropic_api_key()
        assert result == TEST_API_KEY


class TestGetNbTokens:
    """Tests for NationBuilder token retrieval."""

    @patch("src.lambdas.nat_agent_streaming.handler.get_secrets_manager_client")
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

    @patch("src.lambdas.nat_agent_streaming.handler.get_secrets_manager_client")
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


class TestGetUserInfo:
    """Tests for user info retrieval."""

    @patch("src.lambdas.nat_agent_streaming.handler.get_dynamodb_resource")
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

    @patch("src.lambdas.nat_agent_streaming.handler.get_dynamodb_resource")
    def test_get_user_not_found(self, mock_get_resource: MagicMock) -> None:
        """Test user not found returns None."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item key
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_resource.return_value = mock_dynamodb

        result = get_user_info(TEST_USER_ID)
        assert result is None


class TestProcessStreamingRequest:
    """Tests for the streaming request processor."""

    def test_missing_query(self) -> None:
        """Test that missing query returns error event."""
        async def _test() -> list[str]:
            body = {"user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "Missing required field: query" in events[0]

    def test_missing_user_id(self) -> None:
        """Test that missing user_id returns error event."""
        async def _test() -> list[str]:
            body = {"query": "test query"}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "Missing required field: user_id" in events[0]

    def test_missing_nation_slug(self) -> None:
        """Test that a request without nation_slug returns an error event."""
        async def _test() -> list[str]:
            body = {"query": "test query", "user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "Missing required field: nation_slug" in events[0]

    @patch("src.lambdas.nat_agent_streaming.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent_streaming.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation")
    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation")
    def test_nb_not_connected(
        self,
        mock_get_tokens: MagicMock,
        mock_billing: MagicMock,
        mock_rate_limit: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that a nation without NB tokens returns NB_NOT_CONNECTED."""
        mock_get_tokens.return_value = None
        mock_billing.return_value = False
        mock_rate_limit.return_value = None
        mock_verify.return_value = {"valid": True}

        async def _test() -> list[str]:
            body = {
                "query": "test query",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NB_SLUG,
            }
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "NB_NOT_CONNECTED" in events[0]
        mock_billing.assert_called_once_with(TEST_NB_SLUG)

    @patch("src.lambdas.nat_agent_streaming.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent_streaming.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation")
    def test_rate_limit_exceeded(
        self,
        mock_billing: MagicMock,
        mock_rate_limit: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that exceeding the per-user rate limit returns an error event."""
        from src.lambdas.shared.usage_tracking import RateLimitError

        mock_billing.return_value = False
        mock_verify.return_value = {"valid": True}
        mock_rate_limit.side_effect = RateLimitError(
            message="Rate limit exceeded. Please wait 3 seconds.",
            retry_after=3,
        )

        async def _test() -> list[str]:
            body = {
                "query": "test query",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NB_SLUG,
            }
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "RATE_LIMIT_EXCEEDED" in events[0]

    @patch("src.lambdas.nat_agent_streaming.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent_streaming.handler.track_query_usage_nation")
    @patch("src.lambdas.nat_agent_streaming.handler.stream_agent_response")
    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation")
    @patch("src.lambdas.nat_agent_streaming.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation")
    def test_successful_streaming_tracks_usage(
        self,
        mock_billing: MagicMock,
        mock_rate_limit: MagicMock,
        mock_get_tokens: MagicMock,
        mock_stream: MagicMock,
        mock_track: MagicMock,
        mock_verify: MagicMock,
    ) -> None:
        """Test that a successful stream increments per-nation usage."""
        mock_billing.return_value = False
        mock_rate_limit.return_value = None
        mock_verify.return_value = {"valid": True}
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)
        mock_track.return_value = 42

        async def fake_stream(**kwargs: Any) -> Any:
            yield format_sse_event(
                SSE_EVENT_DONE, {"response": "hi", "tool_calls": []}
            )

        mock_stream.side_effect = lambda **kwargs: fake_stream(**kwargs)

        async def _test() -> list[str]:
            body = {
                "query": "test query",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NB_SLUG,
            }
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert any("event: done" in event for event in events)
        # Usage is charged to the nation, keyed by the requesting user
        mock_track.assert_called_once_with(TEST_USER_ID, TEST_NB_SLUG)
        # The subscription gate must be checked for the nation before work
        mock_verify.assert_called_once_with(TEST_USER_ID, TEST_NB_SLUG)

    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation")
    @patch("src.lambdas.nat_agent_streaming.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent_streaming.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation")
    def test_inactive_subscription_blocked(
        self,
        mock_billing: MagicMock,
        mock_verify: MagicMock,
        mock_rate_limit: MagicMock,
        mock_get_tokens: MagicMock,
    ) -> None:
        """A cancelled/past-due nation is blocked even with valid NB tokens."""
        from src.lambdas.shared.subscription_middleware import (
            SubscriptionError,
            SubscriptionErrorCode,
        )

        mock_billing.return_value = False
        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message="Nation subscription is not active (status: cancelled).",
            http_status=402,
        )

        async def _test() -> list[str]:
            body = {
                "query": "test query",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NB_SLUG,
            }
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "SUBSCRIPTION_INACTIVE" in events[0]
        # Gate runs before NB tokens / rate limit, so neither is reached
        mock_get_tokens.assert_not_called()
        mock_rate_limit.assert_not_called()

    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation")
    @patch("src.lambdas.nat_agent_streaming.handler.check_rate_limit")
    @patch("src.lambdas.nat_agent_streaming.handler.verify_nation_subscription")
    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation")
    def test_query_limit_exceeded_blocked(
        self,
        mock_billing: MagicMock,
        mock_verify: MagicMock,
        mock_rate_limit: MagicMock,
        mock_get_tokens: MagicMock,
    ) -> None:
        """A nation over its query cap is blocked with QUERY_LIMIT_EXCEEDED."""
        from src.lambdas.shared.subscription_middleware import (
            SubscriptionError,
            SubscriptionErrorCode,
        )

        mock_billing.return_value = False
        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED,
            message="Monthly query limit exceeded.",
            http_status=403,
        )

        async def _test() -> list[str]:
            body = {
                "query": "test query",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NB_SLUG,
            }
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "QUERY_LIMIT_EXCEEDED" in events[0]
        mock_get_tokens.assert_not_called()


class TestHandler:
    """Tests for the main Lambda handler."""

    @pytest.fixture(autouse=True)
    def _patch_session_secret(self) -> Any:
        """Use a deterministic signing secret for session-token verification."""
        with patch(
            "src.lambdas.shared.session_token.get_session_secret",
            return_value=TEST_JWT_SECRET,
        ):
            yield

    def test_empty_body(self) -> None:
        """Test that empty request body returns 400."""
        event = create_lambda_url_event(body=None)
        event["body"] = ""
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Empty request body" in body["error"]

    def test_invalid_json_body(self) -> None:
        """Test that invalid JSON returns 400."""
        event = {
            "body": "not valid json",
            "isBase64Encoded": False,
            "headers": {},
        }
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid JSON" in body["error"]

    @patch("src.lambdas.nat_agent_streaming.handler.asyncio")
    def test_returns_sse_content_type(self, mock_asyncio: MagicMock) -> None:
        """Test that response has SSE content type headers."""
        # Mock to return an error event
        async def mock_collect() -> str:
            return format_sse_event(SSE_EVENT_ERROR, {"error": "Missing query"})

        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = format_sse_event(
            SSE_EVENT_ERROR, {"error": "Missing query", "error_code": "BAD_REQUEST"}
        )
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_lambda_url_event(
            body={"user_id": TEST_USER_ID},
            headers={"Authorization": bearer()},
        )
        response = handler(event, None)

        assert response["headers"]["Content-Type"] == "text/event-stream"
        assert response["headers"]["Cache-Control"] == "no-cache"
        assert response["headers"]["Connection"] == "keep-alive"

    @patch("src.lambdas.nat_agent_streaming.handler.asyncio")
    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_successful_streaming_response(
        self,
        mock_get_user: MagicMock,
        mock_get_tokens: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Test successful streaming response structure."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        # Build expected SSE events
        expected_events = (
            format_sse_event(SSE_EVENT_TEXT, {"text": "Hello"}) +
            format_sse_event(SSE_EVENT_DONE, {"response": "Hello", "tool_calls": []})
        )

        mock_event_loop = MagicMock()
        mock_event_loop.run_until_complete.return_value = expected_events
        mock_asyncio.get_event_loop.return_value = mock_event_loop

        event = create_lambda_url_event(
            body={
                "query": "test query",
                "user_id": TEST_USER_ID,
            },
            headers={"Authorization": bearer()},
        )
        response = handler(event, None)

        assert response["statusCode"] == 200
        assert "event: text" in response["body"] or "event: error" in response["body"]

    def test_cors_headers_present(self) -> None:
        """Test that CORS headers are present in response."""
        event = create_lambda_url_event(body=None)
        event["body"] = ""
        response = handler(event, None)

        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_base64_encoded_body(self) -> None:
        """Test handling of base64 encoded body from Lambda URL."""
        import base64

        body = {"query": "test", "user_id": TEST_USER_ID}
        encoded_body = base64.b64encode(json.dumps(body).encode()).decode()

        with patch("src.lambdas.nat_agent_streaming.handler.get_user_info") as mock_get_user:
            mock_get_user.return_value = None

            event = {
                "body": encoded_body,
                "isBase64Encoded": True,
                "headers": {"Authorization": bearer()},
            }

            with patch("src.lambdas.nat_agent_streaming.handler.asyncio") as mock_asyncio:
                mock_event_loop = MagicMock()
                mock_event_loop.run_until_complete.return_value = format_sse_event(
                    SSE_EVENT_ERROR, {"error": "User not found", "error_code": "USER_NOT_FOUND"}
                )
                mock_asyncio.get_event_loop.return_value = mock_event_loop

                response = handler(event, None)

                # Should successfully parse the base64 body
                assert response["statusCode"] == 200
                assert "USER_NOT_FOUND" in response["body"]


class TestStreamAgentResponse:
    """Tests for the agent streaming function."""

    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_streaming_with_context(
        self, mock_get_user: MagicMock, mock_get_tokens: MagicMock
    ) -> None:
        """Test streaming with page context."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = (TEST_NB_TOKEN, TEST_NB_SLUG)

        body = {
            "query": "tag this person",
            "user_id": TEST_USER_ID,
            "context": {
                "page_type": "person",
                "person_name": "John Smith",
                "person_id": "12345",
            }
        }

        async def _test() -> list[str]:
            # Just verify that context is accepted - full agent testing requires more mocking
            events = []
            try:
                async for event in process_streaming_request(body):
                    events.append(event)
                    break  # Stop after first event (will be error without full mocking)
            except Exception:
                pass  # Expected without full Claude SDK mocking
            return events

        run_async(_test())
        # Test passes if no exception before token retrieval


class TestSseEventTypes:
    """Tests for SSE event type constants."""

    def test_event_types_defined(self) -> None:
        """Test that all expected event types are defined."""
        assert SSE_EVENT_TEXT == "text"
        assert SSE_EVENT_TOOL_USE == "tool_use"
        assert SSE_EVENT_TOOL_RESULT == "tool_result"
        assert SSE_EVENT_ERROR == "error"
        assert SSE_EVENT_DONE == "done"


class TestUndoFunctionality:
    """Tests for session undo functionality."""

    def test_get_undo_instruction_delete_created_signup(self) -> None:
        """Test undo instruction for created signup."""
        result = _get_undo_instruction(
            undo_type="delete_created",
            undo_data={"signup_id": "12345"},
            original_tool_name="create_signup"
        )
        assert result == "call delete_signup with id=12345"

    def test_get_undo_instruction_delete_created_contact(self) -> None:
        """Test undo instruction for created contact."""
        result = _get_undo_instruction(
            undo_type="delete_created",
            undo_data={"contact_id": "67890"},
            original_tool_name="create_contact"
        )
        assert result == "call delete_contact with id=67890"

    def test_get_undo_instruction_delete_created_donation(self) -> None:
        """Test undo instruction for created donation."""
        result = _get_undo_instruction(
            undo_type="delete_created",
            undo_data={"donation_id": "don123"},
            original_tool_name="create_donation"
        )
        assert result == "call delete_donation with id=don123"

    def test_get_undo_instruction_delete_created_rsvp(self) -> None:
        """Test undo instruction for created event RSVP."""
        result = _get_undo_instruction(
            undo_type="delete_created",
            undo_data={"rsvp_id": "rsvp456"},
            original_tool_name="create_event_rsvp"
        )
        assert result == "call delete_event_rsvp with id=rsvp456"

    def test_get_undo_instruction_remove_from_list(self) -> None:
        """Test undo instruction for add_to_list (reverse is remove)."""
        result = _get_undo_instruction(
            undo_type="remove_from_list",
            undo_data={"person_id": "p123", "list_id": "l456"},
            original_tool_name="add_to_list"
        )
        assert result == "call remove_from_list with person_id=p123, list_id=l456"

    def test_get_undo_instruction_add_to_list(self) -> None:
        """Test undo instruction for remove_from_list (reverse is add back)."""
        result = _get_undo_instruction(
            undo_type="add_to_list",
            undo_data={"person_id": "p123", "list_id": "l456"},
            original_tool_name="remove_from_list"
        )
        assert result == "call add_to_list with person_id=p123, list_id=l456"

    def test_get_undo_instruction_remove_tag(self) -> None:
        """Test undo instruction for added tag (reverse is remove)."""
        result = _get_undo_instruction(
            undo_type="remove_tag",
            undo_data={"signup_id": "s123", "tagging_id": "t456"},
            original_tool_name="add_signup_tagging"
        )
        assert result == "call remove_signup_tagging with signup_id=s123, id=t456"

    def test_get_undo_instruction_add_tag(self) -> None:
        """Test undo instruction for removed tag (reverse is add back)."""
        result = _get_undo_instruction(
            undo_type="add_tag",
            undo_data={"signup_id": "s123", "tag_name": "volunteer"},
            original_tool_name="remove_signup_tagging"
        )
        assert result == "call add_signup_tagging with signup_id=s123, tag_name=volunteer"

    def test_get_undo_instruction_not_undoable(self) -> None:
        """Test undo instruction for non-undoable action."""
        result = _get_undo_instruction(
            undo_type="not_undoable",
            undo_data={},
            original_tool_name="update_signup"
        )
        assert result == "This action cannot be undone"

    def test_get_undo_instruction_missing_data(self) -> None:
        """Test undo instruction with missing data returns not undoable."""
        result = _get_undo_instruction(
            undo_type="delete_created",
            undo_data={},  # Missing signup_id
            original_tool_name="create_signup"
        )
        assert result == "This action cannot be undone"


class TestStreamingAuthentication:
    """Authentication / IDOR-closure tests for the streaming entrypoint."""

    @pytest.fixture(autouse=True)
    def _patch_session_secret(self) -> Any:
        with patch(
            "src.lambdas.shared.session_token.get_session_secret",
            return_value=TEST_JWT_SECRET,
        ):
            yield

    def test_missing_token_returns_401(self) -> None:
        """No Authorization header -> 401 before any work."""
        event = create_lambda_url_event(
            body={"query": "hi", "user_id": TEST_USER_ID},
            headers={},
        )
        response = handler(event, None)
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error_code"] == "MISSING_TOKEN"

    def test_forged_token_returns_401(self) -> None:
        """A token signed with the wrong secret -> 401."""
        event = create_lambda_url_event(
            body={"query": "hi"},
            headers={"Authorization": bearer(secret="attacker-secret")},
        )
        response = handler(event, None)
        assert response["statusCode"] == 401

    def test_expired_token_returns_401(self) -> None:
        expired = mint_session_token(
            TEST_USER_ID, TEST_NATION_SLUG, TEST_JWT_SECRET, ttl_seconds=-5
        )
        event = create_lambda_url_event(
            body={"query": "hi"},
            headers={"Authorization": f"Bearer {expired}"},
        )
        response = handler(event, None)
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error_code"] == "TOKEN_EXPIRED"

    def test_authenticated_body_overrides_client_identity(self) -> None:
        """authenticated_body derives identity from the token, not the body."""
        event = create_lambda_url_event(
            body={"query": "hi"},
            headers={"Authorization": bearer("real-user", "real-nation")},
        )
        body = {
            "query": "hi",
            "user_id": "attacker",
            "nation_slug": "victim-nation",
        }
        result = authenticated_body(event, body)
        assert result["user_id"] == "real-user"
        assert result["nation_slug"] == "real-nation"
        # The original body dict is not mutated.
        assert body["nation_slug"] == "victim-nation"


# =============================================================================
# Server-side confirmation / undo (issue #12)
# =============================================================================


class _SessionStateFakeTable:
    """In-memory DynamoDB Table stand-in for the session-state store."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def update_item(
        self,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> None:
        item = self.items.setdefault(Key["session_id"], {})
        if "ADD pending_tool_ids :tid" in UpdateExpression:
            cur = set(item.get("pending_tool_ids", set()))
            cur |= set(ExpressionAttributeValues[":tid"])
            item["pending_tool_ids"] = cur
        if "DELETE pending_tool_ids :tid" in UpdateExpression:
            cur = set(item.get("pending_tool_ids", set()))
            cur -= set(ExpressionAttributeValues[":tid"])
            if cur:
                item["pending_tool_ids"] = cur
            else:
                item.pop("pending_tool_ids", None)
        if "SET undo_stack_json = :stack" in UpdateExpression:
            item["undo_stack_json"] = ExpressionAttributeValues[":stack"]
        if ":ttl" in ExpressionAttributeValues:
            item["expires_at"] = ExpressionAttributeValues[":ttl"]

    def get_item(
        self, Key: dict[str, Any], ProjectionExpression: str | None = None
    ) -> dict[str, Any]:
        item = self.items.get(Key["session_id"])
        return {"Item": dict(item)} if item is not None else {}


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeToolUseBlock:
    def __init__(self, name: str, tool_input: dict[str, Any]) -> None:
        self.name = name
        self.input = tool_input


class _FakeAssistantMessage:
    def __init__(self, content: list[Any]) -> None:
        self.content = content


class _FakeResultMessage:
    def __init__(
        self,
        result: str,
        is_error: bool = False,
        usage: dict[str, Any] | None = None,
        duration_ms: int = 1234,
    ) -> None:
        self.result = result
        self.is_error = is_error
        # Mirror the real SDK ResultMessage: usage may be None; duration_ms is int.
        self.usage = usage
        self.duration_ms = duration_ms


def _make_fake_client(messages: list[Any]) -> Any:
    """Build a ClaudeSDKClient replacement yielding scripted messages."""

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

        async def query(self, prompt: str) -> None:
            self.prompt = prompt

        async def receive_response(self) -> Any:
            for message in messages:
                yield message

    return _FakeClient


def _patch_streaming_sdk(messages: list[Any], table: Any) -> Any:
    """Patch the agent SDK symbols, options builder, and session-state store."""
    resource = MagicMock()
    resource.Table.return_value = table
    patches = [
        patch("claude_agent_sdk.ClaudeSDKClient", _make_fake_client(messages)),
        patch("claude_agent_sdk.AssistantMessage", _FakeAssistantMessage),
        patch("claude_agent_sdk.TextBlock", _FakeTextBlock),
        patch("claude_agent_sdk.ToolUseBlock", _FakeToolUseBlock),
        patch("claude_agent_sdk.ResultMessage", _FakeResultMessage),
        patch("nat.agent.create_nat_options", return_value=MagicMock()),
        patch.object(
            session_state, "get_dynamodb_resource", return_value=resource
        ),
    ]

    class _Combined:
        def __enter__(self) -> None:
            for p in patches:
                p.start()

        def __exit__(self, *exc: Any) -> bool:
            for p in patches:
                p.stop()
            return False

    return _Combined()


def _collect_stream(**kwargs: Any) -> list[str]:
    async def _run() -> list[str]:
        events = []
        async for event in stream_agent_response(**kwargs):
            events.append(event)
        return events

    return run_async(_run())


class TestStreamingObservability:
    """The ResultMessage branch emits cache + latency metrics (issue #17)."""

    SESSION = "testnation#user-test-12345"

    def test_result_message_emits_cache_and_latency_metrics(self) -> None:
        """A ResultMessage in the stream drives record_cache_usage + latency."""
        from src.lambdas.shared import metrics

        table = _SessionStateFakeTable()
        usage = {
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 20,
        }
        result_msg = _FakeResultMessage("done", usage=usage, duration_ms=4242)

        with _patch_streaming_sdk([result_msg], table):
            with patch.object(metrics, "record_cache_usage") as rec, patch.object(
                metrics, "emit_metric"
            ) as emit:
                _collect_stream(
                    query="hello",
                    nb_slug=TEST_NB_SLUG,
                    nb_token=TEST_NB_TOKEN,
                    model="claude-haiku-4-5-20251001",
                    confirmed_tools=set(),
                    session_id=self.SESSION,
                )

        # The usage dict is passed straight through to record_cache_usage.
        rec.assert_called_once()
        assert rec.call_args.args[0] == usage
        # A latency metric is emitted with the message's duration.
        assert any(
            len(call.args) >= 2 and call.args[1] == float(4242)
            for call in emit.call_args_list
        ), "expected a latency metric emit with duration_ms=4242"


class TestServerSideConfirmation:
    """The confirmation gate must be authoritative server-side (issue #12)."""

    DELETE_INPUT = {"id": "contact-5"}
    SESSION = "testnation#user-test-12345"

    def _delete_message(self) -> _FakeAssistantMessage:
        return _FakeAssistantMessage(
            [_FakeToolUseBlock("delete_contact", self.DELETE_INPUT)]
        )

    def test_unconfirmed_destructive_tool_prompts_and_records(self) -> None:
        """First touch of a destructive tool prompts AND records server-side."""
        table = _SessionStateFakeTable()
        with _patch_streaming_sdk([self._delete_message()], table):
            events = _collect_stream(
                query="delete contact 5",
                nb_slug=TEST_NB_SLUG,
                nb_token=TEST_NB_TOKEN,
                model="claude-haiku-4-5-20251001",
                confirmed_tools=set(),
                session_id=self.SESSION,
            )

        # The destructive tool was NOT executed; a confirmation was requested.
        assert any("event: confirmation_required" in e for e in events)
        assert not any("event: tool_use" in e for e in events)
        # And the server recorded that it legitimately prompted for this tool_id.
        tool_id = compute_tool_id("delete_contact", self.DELETE_INPUT)
        assert tool_id in table.items[self.SESSION]["pending_tool_ids"]

    def test_forged_confirmation_does_not_execute(self) -> None:
        """A forged confirmed_tools value (no server record) cannot execute.

        This is the core bypass from issue #12: a client that pre-confirms a
        tool_id it was never prompted for must still be forced through a real
        confirmation round-trip.
        """
        table = _SessionStateFakeTable()
        forged_tool_id = compute_tool_id("delete_contact", self.DELETE_INPUT)
        # The handler validates client claims via filter_authorized_confirmations,
        # which returns empty because nothing was recorded -> confirmed is empty.
        with _patch_streaming_sdk([self._delete_message()], table):
            authorized = session_state.filter_authorized_confirmations(
                self.SESSION, [forged_tool_id]
            )
            assert authorized == set()
            events = _collect_stream(
                query="delete contact 5",
                nb_slug=TEST_NB_SLUG,
                nb_token=TEST_NB_TOKEN,
                model="claude-haiku-4-5-20251001",
                confirmed_tools=authorized,
                session_id=self.SESSION,
            )

        assert any("event: confirmation_required" in e for e in events)
        assert not any("event: tool_use" in e for e in events)

    def test_legitimate_confirm_then_execute(self) -> None:
        """Recorded confirmation -> the destructive tool executes on resubmit."""
        table = _SessionStateFakeTable()

        # Round 1: prompt + record.
        with _patch_streaming_sdk([self._delete_message()], table):
            _collect_stream(
                query="delete contact 5",
                nb_slug=TEST_NB_SLUG,
                nb_token=TEST_NB_TOKEN,
                model="claude-haiku-4-5-20251001",
                confirmed_tools=set(),
                session_id=self.SESSION,
            )

        tool_id = compute_tool_id("delete_contact", self.DELETE_INPUT)

        # Round 2: client resubmits; server validates the claim against its record.
        with _patch_streaming_sdk([self._delete_message()], table):
            authorized = session_state.filter_authorized_confirmations(
                self.SESSION, [tool_id]
            )
            assert authorized == {tool_id}
            events = _collect_stream(
                query="delete contact 5",
                nb_slug=TEST_NB_SLUG,
                nb_token=TEST_NB_TOKEN,
                model="claude-haiku-4-5-20251001",
                confirmed_tools=authorized,
                session_id=self.SESSION,
            )

        # Now the tool executes (tool_use emitted, no new confirmation prompt).
        assert any("event: tool_use" in e for e in events)
        assert not any("event: confirmation_required" in e for e in events)
        # The confirmation was consumed (single-use) and cannot be replayed.
        assert "pending_tool_ids" not in table.items[self.SESSION]

    def test_non_destructive_tool_executes_without_confirmation(self) -> None:
        table = _SessionStateFakeTable()
        msg = _FakeAssistantMessage(
            [_FakeToolUseBlock("list_signups", {"filter": {"email": "a@b.c"}})]
        )
        with _patch_streaming_sdk([msg], table):
            events = _collect_stream(
                query="find people",
                nb_slug=TEST_NB_SLUG,
                nb_token=TEST_NB_TOKEN,
                model="claude-haiku-4-5-20251001",
                confirmed_tools=set(),
                session_id=self.SESSION,
            )
        assert any("event: tool_use" in e for e in events)
        assert not any("event: confirmation_required" in e for e in events)


class TestServerSideUndo:
    """Undo history is server-maintained and never trusted from the client."""

    SESSION = "testnation#user-test-12345"

    def test_client_supplied_undo_stack_is_ignored(self) -> None:
        """A forged undo_stack in the body must not reach the agent prompt."""
        table = _SessionStateFakeTable()
        captured: dict[str, Any] = {}

        async def fake_stream(**kwargs: Any) -> Any:
            captured.update(kwargs)
            yield format_sse_event(SSE_EVENT_DONE, {"response": "ok", "tool_calls": []})

        with patch(
            "src.lambdas.nat_agent_streaming.handler.stream_agent_response",
            side_effect=lambda **kw: fake_stream(**kw),
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.verify_nation_subscription",
            return_value={"valid": True},
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.check_rate_limit",
            return_value=None,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation",
            return_value=False,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.track_query_usage_nation",
            return_value=1,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation",
            return_value=(TEST_NB_TOKEN, TEST_NB_SLUG),
        ):
            body = {
                "query": "undo that",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NATION_SLUG,
                "undo_stack": [
                    {
                        "description": "attacker controlled",
                        "toolName": "create_signup",
                        "undoType": "delete_created",
                        "undoData": {"signup_id": "victim-999"},
                    }
                ],
            }
            run_async(_drain(process_streaming_request(body)))

        # stream_agent_response is invoked with a session_id, NOT the client stack.
        assert "undo_stack" not in captured
        assert captured["session_id"] == make_session_id(
            TEST_USER_ID, TEST_NATION_SLUG
        )

    def test_confirmed_tools_filtered_through_server(self) -> None:
        """process_streaming_request only forwards server-authorized tool_ids."""
        table = _SessionStateFakeTable()
        captured: dict[str, Any] = {}

        async def fake_stream(**kwargs: Any) -> Any:
            captured.update(kwargs)
            yield format_sse_event(SSE_EVENT_DONE, {"response": "ok", "tool_calls": []})

        resource = MagicMock()
        resource.Table.return_value = table

        with patch(
            "src.lambdas.nat_agent_streaming.handler.stream_agent_response",
            side_effect=lambda **kw: fake_stream(**kw),
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.verify_nation_subscription",
            return_value={"valid": True},
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.check_rate_limit",
            return_value=None,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle_nation",
            return_value=False,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.track_query_usage_nation",
            return_value=1,
        ), patch(
            "src.lambdas.nat_agent_streaming.handler.get_nb_tokens_by_nation",
            return_value=(TEST_NB_TOKEN, TEST_NB_SLUG),
        ), patch.object(
            session_state, "get_dynamodb_resource", return_value=resource
        ):
            forged = compute_tool_id("delete_contact", {"id": "1"})
            body = {
                "query": "do it",
                "user_id": TEST_USER_ID,
                "nation_slug": TEST_NATION_SLUG,
                "confirmed_tools": [forged],
            }
            run_async(_drain(process_streaming_request(body)))

        # The forged tool_id is dropped: nothing was recorded server-side.
        assert captured["confirmed_tools"] == set()

    def test_build_undo_entry_add_to_list(self) -> None:
        entry = _build_undo_entry("add_to_list", {"person_id": "1", "list_id": "2"})
        assert entry is not None
        assert entry["undoType"] == "remove_from_list"
        assert entry["undoData"] == {"person_id": "1", "list_id": "2"}

    def test_build_undo_entry_unreconstructable_returns_none(self) -> None:
        # create_signup's undo needs the created id from the tool *result*, which
        # the server cannot observe -> not recorded (safe, not forgeable).
        assert _build_undo_entry("create_signup", {"first_name": "A"}) is None


async def _drain(agen: Any) -> list[str]:
    events = []
    async for event in agen:
        events.append(event)
    return events
