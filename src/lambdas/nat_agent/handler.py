"""
Nat Agent Lambda Handler

Processes user queries through the Nat AI agent, which has access to all 66
NationBuilder API tools via the Claude Agent SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, TypedDict

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


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str
    headers: dict[str, str]


class AgentRequest(TypedDict, total=False):
    """Request body for agent queries."""

    query: str
    user_id: str
    context: dict[str, Any]


class AgentResponse(TypedDict, total=False):
    """Response from agent."""

    response: str
    error: str | None
    tool_calls: list[dict[str, Any]]


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
        # Secret may be stored as JSON or plain string
        try:
            secret_data = json.loads(secret)
            api_key = secret_data.get("api_key", secret)
            return str(api_key) if api_key else secret
        except json.JSONDecodeError:
            return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve Anthropic API key: {e}")
        raise


def get_nb_tokens(user_id: str) -> tuple[str, str] | None:
    """
    Retrieve NationBuilder tokens for a user from Secrets Manager.

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


async def run_agent_query(
    query: str,
    nb_slug: str,
    nb_token: str,
    model: str,
    context: dict[str, Any] | None = None
) -> AgentResponse:
    """
    Run a query through the Nat agent.

    Args:
        query: The user's query
        nb_slug: NationBuilder nation slug
        nb_token: NationBuilder API token
        model: Claude model to use
        context: Optional page context from extension

    Returns:
        Agent response with message and any tool calls
    """
    # Import here to avoid module-level import issues in Lambda
    # These imports require the claude_agent_sdk package
    from claude_agent_sdk import (
        ClaudeSDKClient,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
    )
    from nat.agent import create_nat_options

    # Build the full prompt with context if provided
    full_prompt = query
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
            full_prompt = f"[Context: {', '.join(context_parts)}]\n\n{query}"

    options = create_nat_options(nb_slug, nb_token, model)

    response_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(full_prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append({
                                "name": block.name,
                                "input": block.input,
                            })
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        logger.warning(f"Tool error: {message.result}")

        return {
            "response": "".join(response_parts),
            "error": None,
            "tool_calls": tool_calls,
        }

    except Exception as e:
        logger.error(f"Agent query failed: {e}")
        return {
            "response": "",
            "error": str(e),
            "tool_calls": [],
        }


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """
    Lambda handler for Nat agent queries.

    Expected request body:
    {
        "query": "Find person by email john@example.com",
        "user_id": "uuid",
        "context": {
            "page_type": "person",
            "person_name": "John Smith",
            "person_id": "12345"
        }
    }

    Response:
    {
        "response": "I found John Smith...",
        "tool_calls": [{"name": "list_signups", "input": {...}}],
        "error": null
    }
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Nat-User-Id,X-Nat-Tenant-Id",
    }

    try:
        # Parse request body
        body_str = event.get("body", "")
        if not body_str:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Empty request body"}),
                "headers": headers,
            }

        try:
            body: AgentRequest = json.loads(body_str)
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON in request body"}),
                "headers": headers,
            }

        # Extract required fields
        query = body.get("query")
        user_id = body.get("user_id")
        page_context = body.get("context", {})

        # Also check headers for user_id (middleware may have set it)
        if not user_id:
            request_headers = event.get("headers", {})
            user_id = (
                request_headers.get("X-Nat-User-Id")
                or request_headers.get("x-nat-user-id")
            )

        if not query:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing required field: query"}),
                "headers": headers,
            }

        if not user_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing required field: user_id"}),
                "headers": headers,
            }

        logger.info(f"Processing query for user {user_id}: {query[:100]}...")

        # Get user info to verify NB is connected
        user_info = get_user_info(user_id)
        if not user_info:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "User not found"}),
                "headers": headers,
            }

        if not user_info.get("nb_connected"):
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "error": "NationBuilder not connected",
                    "error_code": "NB_NOT_CONNECTED"
                }),
                "headers": headers,
            }

        if user_info.get("nb_needs_reauth"):
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "error": "NationBuilder connection needs reauthorization",
                    "error_code": "NB_NEEDS_REAUTH"
                }),
                "headers": headers,
            }

        # Get tenant_id for usage tracking
        tenant_id = user_info.get("tenant_id", "")
        if not tenant_id:
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "error": "User has no tenant association",
                    "error_code": "NO_TENANT"
                }),
                "headers": headers,
            }

        # Check if billing cycle has reset
        check_and_reset_billing_cycle(tenant_id)

        # Check rate limit (5-second cooldown)
        try:
            check_rate_limit(user_id)
        except RateLimitError as e:
            return {
                "statusCode": 429,
                "body": json.dumps({
                    "error": e.message,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": e.retry_after,
                }),
                "headers": {
                    **headers,
                    "Retry-After": str(e.retry_after),
                },
            }

        # Get NB tokens
        tokens = get_nb_tokens(user_id)
        if not tokens:
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "error": "NationBuilder tokens not found",
                    "error_code": "NB_TOKENS_MISSING"
                }),
                "headers": headers,
            }

        nb_token, nb_slug = tokens

        # Run the agent query
        result = asyncio.get_event_loop().run_until_complete(
            run_agent_query(
                query=query,
                nb_slug=nb_slug,
                nb_token=nb_token,
                model=CLAUDE_MODEL,
                context=page_context,
            )
        )

        if result.get("error"):
            logger.error(f"Agent error: {result['error']}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "Agent processing failed",
                    "error_code": "AGENT_ERROR",
                    "details": result["error"],
                }),
                "headers": headers,
            }

        # Track usage after successful query
        new_query_count = track_query_usage(user_id, tenant_id)
        logger.info(f"Query successful. Tenant {tenant_id} now at {new_query_count} queries")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "response": result["response"],
                "tool_calls": result["tool_calls"],
            }),
            "headers": headers,
        }

    except ClientError as e:
        logger.error(f"AWS service error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": headers,
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": headers,
        }
