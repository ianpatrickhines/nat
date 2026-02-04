"""
Usage Tracking Module

Tracks query usage per nation and enforces rate limiting:
- Increments queries_used_this_period counter per nation after each successful query
- Enforces 5-second cooldown between queries per user (anti-abuse)
- Checks if billing cycle has reset and resets usage counter per nation
"""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
NATIONS_TABLE = os.environ.get("NATIONS_TABLE", "nat-nations-dev")
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "nat-tenants-dev")
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")

# Rate limit cooldown in seconds
RATE_LIMIT_COOLDOWN_SECONDS = 5


class RateLimitError(Exception):
    """Exception raised when rate limit (cooldown) is violated."""

    def __init__(self, message: str, retry_after: int) -> None:
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def get_current_timestamp() -> int:
    """Get current Unix timestamp (allows mocking in tests)."""
    return int(time.time())


def check_rate_limit(user_id: str) -> None:
    """
    Check if user is within rate limit (5-second cooldown).

    Args:
        user_id: The user making the request

    Raises:
        RateLimitError: If cooldown period has not elapsed since last query
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    try:
        response = users_table.get_item(
            Key={"user_id": user_id},
            ProjectionExpression="last_query_at",
        )
        item = response.get("Item")

        if not item:
            # User not found - let other checks handle this
            return

        last_query_at = item.get("last_query_at")
        if last_query_at is None:
            return

        # Convert from Decimal if needed
        if isinstance(last_query_at, Decimal):
            last_query_at = int(last_query_at)

        current_time = get_current_timestamp()
        elapsed = current_time - last_query_at

        if elapsed < RATE_LIMIT_COOLDOWN_SECONDS:
            retry_after = RATE_LIMIT_COOLDOWN_SECONDS - elapsed
            raise RateLimitError(
                message=f"Rate limit exceeded. Please wait {retry_after} seconds.",
                retry_after=retry_after,
            )

    except ClientError as e:
        logger.error(f"DynamoDB error checking rate limit: {e}")
        # On error, allow the request to proceed (fail open for rate limit)
        pass


def update_last_query_time(user_id: str) -> None:
    """
    Update the last_query_at timestamp for a user.

    Args:
        user_id: The user making the request
    """
    dynamodb = get_dynamodb_resource()
    users_table = dynamodb.Table(USERS_TABLE)

    current_time = get_current_timestamp()

    try:
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET last_query_at = :timestamp",
            ExpressionAttributeValues={":timestamp": current_time},
        )
    except ClientError as e:
        logger.error(f"Failed to update last_query_at for user {user_id}: {e}")
        # Non-fatal - don't block the query


def increment_query_count_nation(nation_slug: str) -> int:
    """
    Increment the queries_used_this_period counter for a nation.

    Uses atomic increment to handle concurrent requests safely.
    In the new architecture, nations (not tenants) track query usage.

    Args:
        nation_slug: The nation to increment

    Returns:
        The new query count after increment
    """
    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    try:
        response = nations_table.update_item(
            Key={"nation_slug": nation_slug},
            UpdateExpression="SET queries_used_this_period = if_not_exists(queries_used_this_period, :zero) + :inc",
            ExpressionAttributeValues={
                ":inc": 1,
                ":zero": 0,
            },
            ReturnValues="UPDATED_NEW",
        )

        new_count = response.get("Attributes", {}).get("queries_used_this_period", 0)
        if isinstance(new_count, Decimal):
            new_count = int(new_count)

        logger.info(f"Nation {nation_slug} query count incremented to {new_count}")
        return int(new_count)

    except ClientError as e:
        logger.error(f"Failed to increment query count for nation {nation_slug}: {e}")
        raise


def increment_query_count(tenant_id: str) -> int:
    """
    DEPRECATED: Increment the queries_this_month counter for a tenant.

    Uses atomic increment to handle concurrent requests safely.
    This function is kept for backwards compatibility.
    New code should use increment_query_count_nation().

    Args:
        tenant_id: The tenant to increment

    Returns:
        The new query count after increment
    """
    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)

    try:
        response = tenants_table.update_item(
            Key={"tenant_id": tenant_id},
            UpdateExpression="SET queries_this_month = if_not_exists(queries_this_month, :zero) + :inc",
            ExpressionAttributeValues={
                ":inc": 1,
                ":zero": 0,
            },
            ReturnValues="UPDATED_NEW",
        )

        new_count = response.get("Attributes", {}).get("queries_this_month", 0)
        if isinstance(new_count, Decimal):
            new_count = int(new_count)

        logger.info(f"Tenant {tenant_id} query count incremented to {new_count}")
        return int(new_count)

    except ClientError as e:
        logger.error(f"Failed to increment query count for tenant {tenant_id}: {e}")
        raise


def check_and_reset_billing_cycle_nation(nation_slug: str) -> bool:
    """
    Check if billing cycle has reset and reset usage counter if needed for a nation.

    This checks if billing_period_start is in the past and the usage hasn't
    been reset yet for this cycle. The Stripe webhook handles setting new
    billing_period_start dates.

    Args:
        nation_slug: The nation to check

    Returns:
        True if usage was reset, False otherwise
    """
    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    try:
        response = nations_table.get_item(
            Key={"nation_slug": nation_slug},
            ProjectionExpression="billing_period_start, usage_reset_at",
        )
        item = response.get("Item")

        if not item:
            return False

        billing_period_start = item.get("billing_period_start")
        usage_reset_at = item.get("usage_reset_at")

        if billing_period_start is None:
            return False

        # Convert from Decimal if needed
        if isinstance(billing_period_start, Decimal):
            billing_period_start = int(billing_period_start)
        if isinstance(usage_reset_at, Decimal):
            usage_reset_at = int(usage_reset_at)

        current_time = get_current_timestamp()

        # Check if we're past the billing period start and haven't reset yet
        # usage_reset_at tracks when we last reset the counter
        if current_time >= billing_period_start:
            if usage_reset_at is None or usage_reset_at < billing_period_start:
                # Need to reset the counter
                nations_table.update_item(
                    Key={"nation_slug": nation_slug},
                    UpdateExpression="SET queries_used_this_period = :zero, usage_reset_at = :now",
                    ExpressionAttributeValues={
                        ":zero": 0,
                        ":now": current_time,
                    },
                )
                logger.info(f"Reset usage counter for nation {nation_slug}")
                return True

        return False

    except ClientError as e:
        logger.error(f"Error checking billing cycle for nation {nation_slug}: {e}")
        # Don't block on error
        return False


def check_and_reset_billing_cycle(tenant_id: str) -> bool:
    """
    DEPRECATED: Check if billing cycle has reset and reset usage counter if needed.

    This checks if billing_cycle_start is in the past and the usage hasn't
    been reset yet for this cycle. The Stripe webhook handles setting new
    billing_cycle_start dates.
    
    This function is kept for backwards compatibility.
    New code should use check_and_reset_billing_cycle_nation().

    Args:
        tenant_id: The tenant to check

    Returns:
        True if usage was reset, False otherwise
    """
    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)

    try:
        response = tenants_table.get_item(
            Key={"tenant_id": tenant_id},
            ProjectionExpression="billing_cycle_start, usage_reset_at",
        )
        item = response.get("Item")

        if not item:
            return False

        billing_cycle_start = item.get("billing_cycle_start")
        usage_reset_at = item.get("usage_reset_at")

        if billing_cycle_start is None:
            return False

        # Convert from Decimal if needed
        if isinstance(billing_cycle_start, Decimal):
            billing_cycle_start = int(billing_cycle_start)
        if isinstance(usage_reset_at, Decimal):
            usage_reset_at = int(usage_reset_at)

        current_time = get_current_timestamp()

        # Check if we're past the billing cycle start and haven't reset yet
        # usage_reset_at tracks when we last reset the counter
        if current_time >= billing_cycle_start:
            if usage_reset_at is None or usage_reset_at < billing_cycle_start:
                # Need to reset the counter
                tenants_table.update_item(
                    Key={"tenant_id": tenant_id},
                    UpdateExpression="SET queries_this_month = :zero, usage_reset_at = :now",
                    ExpressionAttributeValues={
                        ":zero": 0,
                        ":now": current_time,
                    },
                )
                logger.info(f"Reset usage counter for tenant {tenant_id}")
                return True

        return False

    except ClientError as e:
        logger.error(f"Error checking billing cycle for tenant {tenant_id}: {e}")
        # Don't block on error
        return False


def track_query_usage_nation(user_id: str, nation_slug: str) -> int:
    """
    Track query usage - call this AFTER a successful query.

    This function:
    1. Updates the user's last_query_at timestamp (for rate limiting)
    2. Increments the nation's queries_used_this_period counter

    In the new architecture, usage is tracked per-nation (not per-tenant).

    Args:
        user_id: The user who made the query (for rate limiting)
        nation_slug: The nation to charge

    Returns:
        The new query count for the nation
    """
    # Update last query time for rate limiting (anti-abuse per-user)
    update_last_query_time(user_id)

    # Increment nation query counter
    new_count = increment_query_count_nation(nation_slug)

    return new_count


def track_query_usage(user_id: str, tenant_id: str) -> int:
    """
    DEPRECATED: Track query usage - call this AFTER a successful query.

    This function:
    1. Updates the user's last_query_at timestamp
    2. Increments the tenant's queries_this_month counter
    
    This function is kept for backwards compatibility.
    New code should use track_query_usage_nation().

    Args:
        user_id: The user who made the query
        tenant_id: The tenant to charge

    Returns:
        The new query count for the tenant
    """
    # Update last query time for rate limiting
    update_last_query_time(user_id)

    # Increment query counter
    new_count = increment_query_count(tenant_id)

    return new_count
