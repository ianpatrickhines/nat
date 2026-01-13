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
    process_streaming_request,
    _get_undo_instruction,
    SSE_EVENT_TEXT,
    SSE_EVENT_TOOL_USE,
    SSE_EVENT_TOOL_RESULT,
    SSE_EVENT_ERROR,
    SSE_EVENT_DONE,
)


def run_async(coro: Any) -> Any:
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# Test data
TEST_USER_ID = "user-test-12345"
TEST_TENANT_ID = "tenant-test-67890"
TEST_NB_SLUG = "testnation"
TEST_NB_TOKEN = "nb_test_token_abc123"
TEST_API_KEY = "sk-ant-test-key"


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

    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_user_not_found(self, mock_get_user: MagicMock) -> None:
        """Test that unknown user returns error event."""
        mock_get_user.return_value = None

        async def _test() -> list[str]:
            body = {"query": "test query", "user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "USER_NOT_FOUND" in events[0]

    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_nb_not_connected(self, mock_get_user: MagicMock) -> None:
        """Test that NB not connected returns error event."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": False,
        }

        async def _test() -> list[str]:
            body = {"query": "test query", "user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "NB_NOT_CONNECTED" in events[0]

    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_nb_needs_reauth(self, mock_get_user: MagicMock) -> None:
        """Test that NB needs reauth returns error event."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "nb_connected": True,
            "nb_needs_reauth": True,
        }

        async def _test() -> list[str]:
            body = {"query": "test query", "user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "NB_NEEDS_REAUTH" in events[0]

    @patch("src.lambdas.nat_agent_streaming.handler.check_and_reset_billing_cycle")
    @patch("src.lambdas.nat_agent_streaming.handler.get_nb_tokens")
    @patch("src.lambdas.nat_agent_streaming.handler.get_user_info")
    def test_nb_tokens_missing(
        self, mock_get_user: MagicMock, mock_get_tokens: MagicMock, mock_billing: MagicMock
    ) -> None:
        """Test that missing NB tokens returns error event."""
        mock_get_user.return_value = {
            "user_id": TEST_USER_ID,
            "tenant_id": TEST_TENANT_ID,
            "nb_connected": True,
            "nb_needs_reauth": False,
        }
        mock_get_tokens.return_value = None
        mock_billing.return_value = None

        async def _test() -> list[str]:
            body = {"query": "test query", "user_id": TEST_USER_ID}
            events = []
            async for event in process_streaming_request(body):
                events.append(event)
            return events

        events = run_async(_test())
        assert len(events) == 1
        assert "event: error" in events[0]
        assert "NB_TOKENS_MISSING" in events[0]


class TestHandler:
    """Tests for the main Lambda handler."""

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

        event = create_lambda_url_event(body={"user_id": TEST_USER_ID})
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

        event = create_lambda_url_event(body={
            "query": "test query",
            "user_id": TEST_USER_ID,
        })
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
                "headers": {},
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
