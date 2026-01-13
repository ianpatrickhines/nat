"""
Subscription Verification Middleware

Verifies subscription status for API requests:
- Extracts user identity and nation from request headers
- Checks nation subscription status in DynamoDB
- Returns 402 Payment Required if subscription inactive
- Returns 403 Forbidden if query limit exceeded
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
NATIONS_TABLE = os.environ.get("NATIONS_TABLE", "nat-nations-dev")
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "nat-tenants-dev")
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")

# Subscription statuses that allow API access
ACTIVE_STATUSES = {"active", "trialing"}


class SubscriptionErrorCode(Enum):
    """Error codes for subscription verification failures."""

    MISSING_USER_ID = "MISSING_USER_ID"
    MISSING_NATION_SLUG = "MISSING_NATION_SLUG"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    NATION_NOT_FOUND = "NATION_NOT_FOUND"
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    SUBSCRIPTION_INACTIVE = "SUBSCRIPTION_INACTIVE"
    QUERY_LIMIT_EXCEEDED = "QUERY_LIMIT_EXCEEDED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class NationSubscriptionStatus(TypedDict):
    """Status returned from nation subscription verification."""

    valid: bool
    nation_slug: str
    user_id: str
    plan: str
    queries_used_this_period: int
    queries_limit: int
    subscription_status: str


class SubscriptionStatus(TypedDict):
    """DEPRECATED: Status returned from subscription verification."""

    valid: bool
    tenant_id: str
    user_id: str
    plan: str
    queries_this_month: int
    queries_limit: int
    subscription_status: str


class SubscriptionError(Exception):
    """Exception raised when subscription verification fails."""

    def __init__(
        self,
        code: SubscriptionErrorCode,
        message: str,
        http_status: int = 403,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


@dataclass
class NationContext:
    """Nation context extracted from request headers."""

    user_id: str
    nation_slug: str


@dataclass
class UserContext:
    """DEPRECATED: User context extracted from request headers."""

    user_id: str
    tenant_id: str | None = None


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def extract_nation_from_headers(headers: dict[str, str]) -> NationContext:
    """
    Extract user and nation identity from request headers.

    Headers:
    - X-Nat-User-Id: Required user identifier (for rate limiting)
    - X-Nat-Nation-Slug: Required nation identifier (for subscription check)
    """
    # Handle case-insensitive headers (API Gateway may lowercase them)
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    user_id = normalized_headers.get("x-nat-user-id", "")
    nation_slug = normalized_headers.get("x-nat-nation-slug", "")

    if not user_id:
        raise SubscriptionError(
            code=SubscriptionErrorCode.MISSING_USER_ID,
            message="Missing X-Nat-User-Id header",
            http_status=401,
        )

    if not nation_slug:
        raise SubscriptionError(
            code=SubscriptionErrorCode.MISSING_NATION_SLUG,
            message="Missing X-Nat-Nation-Slug header",
            http_status=401,
        )

    return NationContext(user_id=user_id, nation_slug=nation_slug)


def get_nation_subscription(nation_slug: str) -> dict[str, Any]:
    """
    Get nation subscription details from NationsTable.

    Returns the full nation record from DynamoDB.
    """
    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    try:
        response = nations_table.get_item(Key={"nation_slug": nation_slug})
        item = response.get("Item")

        if not item:
            raise SubscriptionError(
                code=SubscriptionErrorCode.NATION_NOT_FOUND,
                message=f"Nation {nation_slug} not found. Please connect your NationBuilder account first.",
                http_status=404,
            )

        return dict(item)

    except ClientError as e:
        logger.error(f"DynamoDB error looking up nation: {e}")
        raise


def verify_nation_subscription(
    user_id: str,
    nation_slug: str,
) -> NationSubscriptionStatus:
    """
    Verify a nation's subscription is active and within limits.

    In the new architecture, subscriptions are tied to nations (not users).
    Any user authenticated to the nation can use Nat if the nation subscribes.

    Args:
        user_id: The user making the request (for logging/rate limiting)
        nation_slug: The nation to check subscription for

    Returns:
        NationSubscriptionStatus with verification result

    Raises:
        SubscriptionError: If subscription is inactive or limits exceeded
    """
    # Get nation subscription details
    nation = get_nation_subscription(nation_slug)

    subscription_status = nation.get("subscription_status", "none")
    plan = nation.get("subscription_plan", "trial")
    queries_used = int(nation.get("queries_used_this_period", 0))
    queries_limit = int(nation.get("queries_limit", 50))

    # Check subscription status
    if subscription_status not in ACTIVE_STATUSES:
        raise SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message=f"Nation subscription is not active (status: {subscription_status}). Please subscribe at https://natassistant.com/pricing",
            http_status=402,
        )

    # Check query limit (0 means unlimited, skip check)
    if queries_limit > 0 and queries_used >= queries_limit:
        raise SubscriptionError(
            code=SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED,
            message=f"Monthly query limit of {queries_limit} exceeded for nation {nation_slug}. Upgrade your plan for more queries.",
            http_status=403,
        )

    return NationSubscriptionStatus(
        valid=True,
        nation_slug=nation_slug,
        user_id=user_id,
        plan=plan,
        queries_used_this_period=queries_used,
        queries_limit=queries_limit,
        subscription_status=subscription_status,
    )


def extract_user_from_headers(headers: dict[str, str]) -> UserContext:
    """
    DEPRECATED: Extract user identity from request headers.
    
    This function is kept for backwards compatibility.
    New code should use extract_nation_from_headers().

    Headers:
    - X-Nat-User-Id: Required user identifier
    - X-Nat-Tenant-Id: Optional tenant identifier (for optimization)
    """
    # Handle case-insensitive headers (API Gateway may lowercase them)
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    user_id = normalized_headers.get("x-nat-user-id", "")
    tenant_id = normalized_headers.get("x-nat-tenant-id")

    if not user_id:
        raise SubscriptionError(
            code=SubscriptionErrorCode.MISSING_USER_ID,
            message="Missing X-Nat-User-Id header",
            http_status=401,
        )

    return UserContext(user_id=user_id, tenant_id=tenant_id)


def get_user_nation_slug(user_id: str) -> str:
    """
    Look up nation_slug for a user.

    Returns the nation_slug associated with the user.
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    try:
        response = users_table.get_item(Key={"user_id": user_id})
        item = response.get("Item")

        if not item:
            raise SubscriptionError(
                code=SubscriptionErrorCode.USER_NOT_FOUND,
                message=f"User {user_id} not found",
                http_status=401,
            )

        nation_slug: str = item.get("nation_slug", "")
        if not nation_slug:
            raise SubscriptionError(
                code=SubscriptionErrorCode.NATION_NOT_FOUND,
                message=f"User {user_id} has no nation association",
                http_status=403,
            )

        return nation_slug

    except ClientError as e:
        logger.error(f"DynamoDB error looking up user: {e}")
        raise


def get_user_tenant_id(user_id: str) -> str:
    """
    DEPRECATED: Look up tenant ID for a user.

    Returns the tenant_id associated with the user.
    
    This function is kept for backwards compatibility.
    New code should use get_user_nation_slug().
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    try:
        response = users_table.get_item(Key={"user_id": user_id})
        item = response.get("Item")

        if not item:
            raise SubscriptionError(
                code=SubscriptionErrorCode.USER_NOT_FOUND,
                message=f"User {user_id} not found",
                http_status=401,
            )

        tenant_id: str = item.get("tenant_id", "")
        if not tenant_id:
            raise SubscriptionError(
                code=SubscriptionErrorCode.TENANT_NOT_FOUND,
                message=f"User {user_id} has no tenant association",
                http_status=403,
            )

        return tenant_id

    except ClientError as e:
        logger.error(f"DynamoDB error looking up user: {e}")
        raise


def get_tenant_subscription(tenant_id: str) -> dict[str, Any]:
    """
    Get tenant subscription details.

    Returns the full tenant record from DynamoDB.
    """
    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)

    try:
        response = tenants_table.get_item(Key={"tenant_id": tenant_id})
        item = response.get("Item")

        if not item:
            raise SubscriptionError(
                code=SubscriptionErrorCode.TENANT_NOT_FOUND,
                message=f"Tenant {tenant_id} not found",
                http_status=403,
            )

        return dict(item)

    except ClientError as e:
        logger.error(f"DynamoDB error looking up tenant: {e}")
        raise


def verify_subscription(
    user_id: str,
    tenant_id: str | None = None,
) -> SubscriptionStatus:
    """
    Verify a user's subscription is active and within limits.

    Args:
        user_id: The user making the request
        tenant_id: Optional tenant ID (optimization to skip user lookup)

    Returns:
        SubscriptionStatus with verification result

    Raises:
        SubscriptionError: If subscription is inactive or limits exceeded
    """
    # Get tenant ID from user if not provided
    if not tenant_id:
        tenant_id = get_user_tenant_id(user_id)

    # Get tenant subscription details
    tenant = get_tenant_subscription(tenant_id)

    subscription_status = tenant.get("stripe_subscription_status", "")
    plan = tenant.get("plan", "starter")
    queries_this_month = int(tenant.get("queries_this_month", 0))
    queries_limit = int(tenant.get("queries_limit", 500))

    # Check subscription status
    if subscription_status not in ACTIVE_STATUSES:
        raise SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message="Subscription is not active. Please update your payment method.",
            http_status=402,
        )

    # Check query limit
    if queries_this_month >= queries_limit:
        raise SubscriptionError(
            code=SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED,
            message=f"Monthly query limit of {queries_limit} exceeded. Upgrade your plan for more queries.",
            http_status=403,
        )

    return SubscriptionStatus(
        valid=True,
        tenant_id=tenant_id,
        user_id=user_id,
        plan=plan,
        queries_this_month=queries_this_month,
        queries_limit=queries_limit,
        subscription_status=subscription_status,
    )


class SubscriptionMiddleware:
    """
    Middleware class for subscription verification.

    Can be used as a decorator or called directly.

    Usage as decorator:
        @SubscriptionMiddleware()
        def handler(event, context, subscription_status):
            # subscription_status contains verified subscription info
            pass

    Usage directly:
        middleware = SubscriptionMiddleware()
        try:
            status = middleware.verify(event)
        except SubscriptionError as e:
            return {"statusCode": e.http_status, "body": e.message}
    """

    def __init__(self) -> None:
        self._dynamodb = None

    def verify(self, event: dict[str, Any]) -> SubscriptionStatus:
        """
        Verify subscription from Lambda event.

        Args:
            event: Lambda event containing headers

        Returns:
            SubscriptionStatus if verified

        Raises:
            SubscriptionError: If verification fails
        """
        headers = event.get("headers", {}) or {}
        user_context = extract_user_from_headers(headers)

        return verify_subscription(
            user_id=user_context.user_id,
            tenant_id=user_context.tenant_id,
        )

    def __call__(self, func: Any) -> Any:
        """Decorator usage for Lambda handlers."""
        import functools
        import json

        @functools.wraps(func)
        def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
            cors_headers = {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            }

            try:
                subscription_status = self.verify(event)
                result: dict[str, Any] = func(event, context, subscription_status)
                return result

            except SubscriptionError as e:
                logger.warning(
                    f"Subscription verification failed: {e.code.value} - {e.message}"
                )
                return {
                    "statusCode": e.http_status,
                    "body": json.dumps(
                        {
                            "error": e.code.value,
                            "message": e.message,
                        }
                    ),
                    "headers": cors_headers,
                }

        return wrapper


class NationSubscriptionMiddleware:
    """
    Middleware class for nation-based subscription verification.

    Can be used as a decorator or called directly.
    
    In the new architecture, subscriptions are tied to nations (organizations)
    rather than individual users.

    Usage as decorator:
        @NationSubscriptionMiddleware()
        def handler(event, context, subscription_status):
            # subscription_status contains verified nation subscription info
            pass

    Usage directly:
        middleware = NationSubscriptionMiddleware()
        try:
            status = middleware.verify(event)
        except SubscriptionError as e:
            return {"statusCode": e.http_status, "body": e.message}
    """

    def __init__(self) -> None:
        self._dynamodb = None

    def verify(self, event: dict[str, Any]) -> NationSubscriptionStatus:
        """
        Verify nation subscription from Lambda event.

        Args:
            event: Lambda event containing headers with nation_slug

        Returns:
            NationSubscriptionStatus if verified

        Raises:
            SubscriptionError: If verification fails
        """
        headers = event.get("headers", {}) or {}
        nation_context = extract_nation_from_headers(headers)

        return verify_nation_subscription(
            user_id=nation_context.user_id,
            nation_slug=nation_context.nation_slug,
        )

    def __call__(self, func: Any) -> Any:
        """Decorator usage for Lambda handlers."""
        import functools
        import json

        @functools.wraps(func)
        def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
            cors_headers = {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            }

            try:
                subscription_status = self.verify(event)
                result: dict[str, Any] = func(event, context, subscription_status)
                return result

            except SubscriptionError as e:
                logger.warning(
                    f"Nation subscription verification failed: {e.code.value} - {e.message}"
                )
                return {
                    "statusCode": e.http_status,
                    "body": json.dumps(
                        {
                            "error": e.code.value,
                            "message": e.message,
                        }
                    ),
                    "headers": cors_headers,
                }

        return wrapper
