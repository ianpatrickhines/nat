"""
Nat Agent Streaming Lambda Handler

Processes user queries through the Nat AI agent with SSE streaming responses.
Uses Lambda response streaming via Lambda Function URLs for real-time output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator

import boto3
from botocore.exceptions import ClientError

from src.lambdas.shared.usage_tracking import (
    RateLimitError,
    check_rate_limit,
    track_query_usage,
    check_and_reset_billing_cycle,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "nat-tenants-dev")
ANTHROPIC_API_KEY_SECRET = os.environ.get(
    "ANTHROPIC_API_KEY_SECRET", "nat/anthropic-api-key"
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# SSE event types
SSE_EVENT_TEXT = "text"
SSE_EVENT_TOOL_USE = "tool_use"
SSE_EVENT_TOOL_RESULT = "tool_result"
SSE_EVENT_ERROR = "error"
SSE_EVENT_DONE = "done"
SSE_EVENT_CONFIRMATION_REQUIRED = "confirmation_required"

# Tools that require user confirmation before execution
DESTRUCTIVE_TOOLS = {
    "delete_signup",
    "delete_contact",
    "delete_donation",
    "delete_event",
    "delete_event_rsvp",
    "delete_path_journey",
    "remove_from_list",
    # Update operations that could significantly change data
    "update_signup",
    "update_donation",
    "update_event",
}


def get_secrets_manager_client() -> Any:
    """Get Secrets Manager client (allows mocking in tests)."""
    return boto3.client("secretsmanager")


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def get_anthropic_api_key() -> str:
    """Retrieve Anthropic API key from Secrets Manager."""
    client = get_secrets_manager_client()
    try:
        response = client.get_secret_value(SecretId=ANTHROPIC_API_KEY_SECRET)
        secret: str = response.get("SecretString", "")
        try:
            secret_data = json.loads(secret)
            api_key = secret_data.get("api_key", secret)
            return str(api_key) if api_key else secret
        except json.JSONDecodeError:
            return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve Anthropic API key: {e}")
        raise


def get_nb_tokens_by_nation(nation_slug: str) -> tuple[str, str] | None:
    """
    Retrieve NationBuilder tokens for a nation from Secrets Manager.
    
    In the new architecture, tokens are stored per-nation (not per-user),
    allowing any authenticated user of the nation to use Nat.

    Args:
        nation_slug: The nation slug

    Returns:
        Tuple of (access_token, nation_slug) or None if not found
    """
    client = get_secrets_manager_client()
    secret_id = f"nat/nation/{nation_slug}/nb-tokens"

    try:
        response = client.get_secret_value(SecretId=secret_id)
        secret_str: str = response.get("SecretString", "")
        secret_data = json.loads(secret_str)

        access_token = secret_data.get("access_token")
        stored_slug = secret_data.get("nation_slug")

        if not access_token:
            logger.error(f"Missing token for nation {nation_slug}")
            return None

        # Return the nation_slug for consistency
        return (str(access_token), str(stored_slug or nation_slug))

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            logger.warning(f"No NB tokens found for nation {nation_slug}")
            return None
        logger.error(f"Failed to retrieve NB tokens: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse NB tokens JSON: {e}")
        return None


def get_nb_tokens(user_id: str) -> tuple[str, str] | None:
    """
    DEPRECATED: Retrieve NationBuilder tokens for a user from Secrets Manager.
    
    This function is kept for backwards compatibility.
    New code should use get_nb_tokens_by_nation().

    Args:
        user_id: The user ID

    Returns:
        Tuple of (access_token, nb_slug) or None if not found
    """
    client = get_secrets_manager_client()
    secret_id = f"nat/user/{user_id}/nb-tokens"

    try:
        response = client.get_secret_value(SecretId=secret_id)
        secret_str: str = response.get("SecretString", "")
        secret_data = json.loads(secret_str)

        access_token = secret_data.get("access_token")
        nb_slug = secret_data.get("nb_slug")

        if not access_token or not nb_slug:
            logger.error(f"Missing token or slug for user {user_id}")
            return None

        return (str(access_token), str(nb_slug))

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            logger.warning(f"No NB tokens found for user {user_id}")
            return None
        logger.error(f"Failed to retrieve NB tokens: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse NB tokens JSON: {e}")
        return None


def get_user_info(user_id: str) -> dict[str, Any] | None:
    """
    Get user info from DynamoDB.

    Args:
        user_id: The user ID

    Returns:
        User record or None if not found
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    try:
        response = users_table.get_item(Key={"user_id": user_id})
        item: dict[str, Any] | None = response.get("Item")
        return item
    except ClientError as e:
        logger.error(f"Failed to get user info: {e}")
        return None


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    """
    Format data as a Server-Sent Event.

    Args:
        event_type: The event type (text, tool_use, tool_result, error, done)
        data: The data to send

    Returns:
        Formatted SSE string
    """
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


def generate_tool_summary(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Generate a human-readable summary of a tool action for confirmation dialogs.

    Args:
        tool_name: The name of the tool
        tool_input: The input parameters for the tool

    Returns:
        Human-readable summary of the action
    """
    summaries = {
        "delete_signup": lambda i: f"Delete person record {i.get('person_id', 'unknown')}",
        "delete_contact": lambda i: f"Delete contact record {i.get('id', 'unknown')}",
        "delete_donation": lambda i: f"Delete donation record {i.get('id', 'unknown')}",
        "delete_event": lambda i: f"Delete event {i.get('id', 'unknown')}",
        "delete_event_rsvp": lambda i: f"Delete RSVP {i.get('id', 'unknown')} from event",
        "delete_path_journey": lambda i: f"Delete journey {i.get('id', 'unknown')} from path",
        "remove_from_list": lambda i: f"Remove person {i.get('person_id', 'unknown')} from list {i.get('list_id', 'unknown')}",
        "update_signup": lambda i: f"Update person record {i.get('person_id', 'unknown')}",
        "update_donation": lambda i: f"Update donation record {i.get('id', 'unknown')}",
        "update_event": lambda i: f"Update event {i.get('id', 'unknown')}",
    }

    if tool_name in summaries:
        return summaries[tool_name](tool_input)
    return f"Execute {tool_name}"


def _get_undo_instruction(
    undo_type: str,
    undo_data: dict[str, Any],
    original_tool_name: str
) -> str:
    """
    Generate a human-readable instruction for how to undo an action.

    Args:
        undo_type: The type of undo operation
        undo_data: Data needed to perform the undo
        original_tool_name: The original tool that was called

    Returns:
        Human-readable instruction for the agent
    """
    if undo_type == "delete_created":
        if original_tool_name == "create_signup" and undo_data.get("signup_id"):
            return f"call delete_signup with id={undo_data['signup_id']}"
        if original_tool_name == "create_contact" and undo_data.get("contact_id"):
            return f"call delete_contact with id={undo_data['contact_id']}"
        if original_tool_name == "create_donation" and undo_data.get("donation_id"):
            return f"call delete_donation with id={undo_data['donation_id']}"
        if original_tool_name == "create_event_rsvp" and undo_data.get("rsvp_id"):
            return f"call delete_event_rsvp with id={undo_data['rsvp_id']}"

    elif undo_type == "remove_from_list":
        person_id = undo_data.get("person_id")
        list_id = undo_data.get("list_id")
        if person_id and list_id:
            return f"call remove_from_list with person_id={person_id}, list_id={list_id}"

    elif undo_type == "add_to_list":
        person_id = undo_data.get("person_id")
        list_id = undo_data.get("list_id")
        if person_id and list_id:
            return f"call add_to_list with person_id={person_id}, list_id={list_id}"

    elif undo_type == "remove_tag":
        signup_id = undo_data.get("signup_id")
        tagging_id = undo_data.get("tagging_id")
        if signup_id and tagging_id:
            return f"call remove_signup_tagging with signup_id={signup_id}, id={tagging_id}"

    elif undo_type == "add_tag":
        signup_id = undo_data.get("signup_id")
        tag_name = undo_data.get("tag_name")
        if signup_id and tag_name:
            return f"call add_signup_tagging with signup_id={signup_id}, tag_name={tag_name}"

    return "This action cannot be undone"


async def stream_agent_response(
    query: str,
    nb_slug: str,
    nb_token: str,
    model: str,
    context: dict[str, Any] | None = None,
    confirmed_tools: set[str] | None = None,
    undo_stack: list[dict[str, Any]] | None = None
) -> AsyncGenerator[str, None]:
    """
    Stream responses from the Nat agent as SSE events.

    Args:
        query: The user's query
        nb_slug: NationBuilder nation slug
        nb_token: NationBuilder API token
        model: Claude model to use
        context: Optional page context from extension
        confirmed_tools: Set of tool_id values that have been confirmed by user
        undo_stack: List of recent undoable actions from this session

    Yields:
        SSE formatted strings
    """
    # Import here to avoid module-level import issues in Lambda
    from claude_agent_sdk import (
        ClaudeSDKClient,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
    )
    from nat.agent import create_nat_options

    confirmed = confirmed_tools or set()

    # Build the full prompt with context if provided
    full_prompt = query
    context_sections: list[str] = []

    if context:
        context_parts = []
        if context.get("page_type"):
            context_parts.append(f"Page type: {context['page_type']}")
        if context.get("person_name"):
            context_parts.append(f"Viewing person: {context['person_name']}")
        if context.get("person_id"):
            context_parts.append(f"Person ID: {context['person_id']}")
        if context.get("list_name"):
            context_parts.append(f"Viewing list: {context['list_name']}")
        if context.get("event_name"):
            context_parts.append(f"Viewing event: {context['event_name']}")

        if context_parts:
            context_sections.append(f"[Context: {', '.join(context_parts)}]")

    # Add undo stack context if the user might be asking to undo
    # Check for common undo phrases
    query_lower = query.lower()
    undo_phrases = ["undo", "revert", "reverse", "take back", "cancel that", "nevermind"]
    is_undo_request = any(phrase in query_lower for phrase in undo_phrases)

    if is_undo_request and undo_stack and len(undo_stack) > 0:
        # Build undo context from the most recent actions (up to 5)
        recent_actions = undo_stack[-5:]
        undo_context_parts = [
            "[Recent Actions (can be undone):"
        ]
        for i, action in enumerate(reversed(recent_actions)):
            desc = action.get("description", "Unknown action")
            tool_name = action.get("toolName", "unknown")
            undo_type = action.get("undoType", "not_undoable")
            undo_data = action.get("undoData", {})

            # Generate the undo instruction based on undo type
            undo_instruction = _get_undo_instruction(undo_type, undo_data, tool_name)
            undo_context_parts.append(
                f"  {i + 1}. {desc} - To undo: {undo_instruction}"
            )

        undo_context_parts.append("]")
        context_sections.append("\n".join(undo_context_parts))

    if context_sections:
        full_prompt = "\n\n".join(context_sections) + "\n\n" + query

    options = create_nat_options(nb_slug, nb_token, model)
    full_response: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(full_prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            # Stream each text block as it arrives
                            full_response.append(block.text)
                            yield format_sse_event(SSE_EVENT_TEXT, {
                                "text": block.text
                            })
                        elif isinstance(block, ToolUseBlock):
                            # Check if this is a destructive tool requiring confirmation
                            tool_id = f"{block.name}_{hash(json.dumps(block.input, sort_keys=True))}"

                            if block.name in DESTRUCTIVE_TOOLS and tool_id not in confirmed:
                                # Send confirmation_required event and pause
                                yield format_sse_event(SSE_EVENT_CONFIRMATION_REQUIRED, {
                                    "tool_id": tool_id,
                                    "tool_name": block.name,
                                    "tool_input": block.input,
                                    "summary": generate_tool_summary(block.name, block.input),
                                })
                                # Return early - client must re-submit with confirmation
                                return

                            # Notify client about tool invocation
                            tool_info = {
                                "name": block.name,
                                "input": block.input,
                            }
                            tool_calls.append(tool_info)
                            yield format_sse_event(SSE_EVENT_TOOL_USE, tool_info)

                elif isinstance(message, ResultMessage):
                    # Send tool result notification
                    yield format_sse_event(SSE_EVENT_TOOL_RESULT, {
                        "result": str(message.result)[:500],  # Truncate long results
                        "is_error": message.is_error,
                    })

        # Send final done event with complete response
        yield format_sse_event(SSE_EVENT_DONE, {
            "response": "".join(full_response),
            "tool_calls": tool_calls,
        })

    except Exception as e:
        logger.error(f"Agent streaming error: {e}")
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": str(e),
            "error_code": "AGENT_ERROR",
        })
        yield format_sse_event(SSE_EVENT_DONE, {
            "response": "",
            "tool_calls": [],
            "error": str(e),
        })


async def process_streaming_request(body: dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Process a streaming request and yield SSE events.

    Args:
        body: Parsed request body

    Yields:
        SSE formatted strings
    """
    query = body.get("query")
    user_id = body.get("user_id")
    nation_slug = body.get("nation_slug")  # NEW: Nation identifier
    page_context = body.get("context", {})
    confirmed_tools_list: list[str] = body.get("confirmed_tools", [])
    confirmed_tools = set(confirmed_tools_list) if confirmed_tools_list else set()
    undo_stack: list[dict[str, Any]] = body.get("undo_stack", [])

    if not query:
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": "Missing required field: query",
            "error_code": "BAD_REQUEST",
        })
        return

    if not user_id:
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": "Missing required field: user_id",
            "error_code": "BAD_REQUEST",
        })
        return

    if not nation_slug:
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": "Missing required field: nation_slug",
            "error_code": "BAD_REQUEST",
        })
        return

    logger.info(f"Processing streaming query for nation {nation_slug}, user {user_id}: {query[:100]}...")

    # Import nation-based tracking functions
    from src.lambdas.shared.usage_tracking import (
        check_and_reset_billing_cycle_nation,
        track_query_usage_nation,
    )

    # Check if billing cycle has reset for this nation
    check_and_reset_billing_cycle_nation(nation_slug)

    # Check rate limit (5-second cooldown per user, anti-abuse)
    try:
        check_rate_limit(user_id)
    except RateLimitError as e:
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": e.message,
            "error_code": "RATE_LIMIT_EXCEEDED",
            "retry_after": e.retry_after,
        })
        return

    # Get NB tokens for the nation
    tokens = get_nb_tokens_by_nation(nation_slug)
    if not tokens:
        yield format_sse_event(SSE_EVENT_ERROR, {
            "error": "NationBuilder not connected for this nation",
            "error_code": "NB_NOT_CONNECTED",
        })
        return

    nb_token, verified_slug = tokens

    # Stream the agent response and track whether it succeeded
    stream_succeeded = False
    async for event in stream_agent_response(
        query=query,
        nb_slug=verified_slug,
        nb_token=nb_token,
        model=CLAUDE_MODEL,
        context=page_context,
        confirmed_tools=confirmed_tools,
        undo_stack=undo_stack,
    ):
        yield event
        # Check if this is a successful done event (no error in response)
        if SSE_EVENT_DONE in event and '"error":' not in event:
            stream_succeeded = True

    # Track usage after successful streaming completion (nation-based)
    if stream_succeeded:
        new_query_count = track_query_usage_nation(user_id, nation_slug)
        logger.info(f"Streaming query successful. Nation {nation_slug} now at {new_query_count} queries")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for streaming Nat agent queries via Lambda Function URL.

    This handler is designed to work with Lambda response streaming.
    It uses the RESPONSE_STREAM invocation mode.

    Expected request body:
    {
        "query": "Find person by email john@example.com",
        "user_id": "uuid",
        "nation_slug": "yournation",
        "context": {
            "page_type": "person",
            "person_name": "John Smith",
            "person_id": "12345"
        }
    }

    Response: SSE stream with events:
    - text: Partial text response
    - tool_use: Tool being invoked
    - tool_result: Result from tool
    - error: Error occurred
    - done: Stream complete with full response
    """
    # For Lambda Function URL with response streaming, we need to handle
    # the request and return a streaming response

    # Parse request body - Lambda Function URL may have different event structure
    body_str = ""
    if "body" in event:
        body_str = event.get("body", "")
        # Handle base64 encoded body from Lambda URL
        if event.get("isBase64Encoded"):
            import base64
            body_str = base64.b64decode(body_str).decode("utf-8")
    elif "queryStringParameters" in event:
        # GET request with query params (fallback)
        body_str = json.dumps(event.get("queryStringParameters", {}))

    if not body_str:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Empty request body"}),
        }

    try:
        body: dict[str, Any] = json.loads(body_str)
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }

    # For non-streaming invocation (testing), return accumulated response
    # The actual streaming is handled by the streaming handler wrapper
    async def collect_response() -> str:
        events: list[str] = []
        async for event in process_streaming_request(body):
            events.append(event)
        return "".join(events)

    sse_response = asyncio.get_event_loop().run_until_complete(collect_response())

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Nat-User-Id,X-Nat-Tenant-Id",
        },
        "body": sse_response,
    }


# Streaming handler for Lambda response streaming
# This is used when the Lambda is invoked with RESPONSE_STREAM mode
async def streaming_handler(event: dict[str, Any], response_stream: Any) -> None:
    """
    Async streaming handler for Lambda response streaming.

    This handler writes directly to the response stream for true SSE streaming.

    Args:
        event: Lambda event
        response_stream: awslambda.ResponseStream for writing chunks
    """
    # Write SSE headers
    await response_stream.write(b"")  # Initialize stream

    # Parse request body
    body_str = ""
    if "body" in event:
        body_str = event.get("body", "")
        if event.get("isBase64Encoded"):
            import base64
            body_str = base64.b64decode(body_str).decode("utf-8")

    if not body_str:
        error_event = format_sse_event(SSE_EVENT_ERROR, {
            "error": "Empty request body",
            "error_code": "BAD_REQUEST",
        })
        await response_stream.write(error_event.encode("utf-8"))
        return

    try:
        body: dict[str, Any] = json.loads(body_str)
    except json.JSONDecodeError:
        error_event = format_sse_event(SSE_EVENT_ERROR, {
            "error": "Invalid JSON in request body",
            "error_code": "BAD_REQUEST",
        })
        await response_stream.write(error_event.encode("utf-8"))
        return

    # Stream response events
    async for sse_event in process_streaming_request(body):
        await response_stream.write(sse_event.encode("utf-8"))
