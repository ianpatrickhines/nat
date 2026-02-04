"""
Stripe Webhook Lambda Handler

Handles Stripe webhook events for subscription management:
- checkout.session.completed: New subscription created
- customer.subscription.updated: Subscription status changed
- customer.subscription.deleted: Subscription cancelled
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
NATIONS_TABLE = os.environ.get("NATIONS_TABLE", "nat-nations-dev")
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "nat-tenants-dev")
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")
STRIPE_WEBHOOK_SECRET_NAME = os.environ.get(
    "STRIPE_WEBHOOK_SECRET_NAME", "nat/stripe-webhook-secret"
)

# NEW PRICING MODEL: Nation-level plans
# Nat: $29/mo, 500 queries/month
# Nat Pro: $79/mo, unlimited queries (represented as 0 for unlimited)
PLAN_QUERY_LIMITS: dict[str, int] = {
    "nat": 500,
    "nat_pro": 0,  # 0 = unlimited (checked explicitly in middleware)
    # Legacy plans (backwards compatibility)
    "starter": 500,
    "team": 2000,
    "org": 5000,
}

# Stripe price ID to plan mapping (configure these in production)
PRICE_TO_PLAN: dict[str, str] = {
    "price_nat_monthly": "nat",
    "price_nat_pro_monthly": "nat_pro",
    # Legacy price IDs (backwards compatibility)
    "price_starter_monthly": "starter",
    "price_team_monthly": "team",
    "price_org_monthly": "org",
}


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str
    headers: dict[str, str]


class WebhookEvent(TypedDict, total=False):
    """Stripe webhook event type."""

    id: str
    type: str
    data: dict[str, Any]
    created: int


def get_stripe_webhook_secret() -> str:
    """Retrieve Stripe webhook signing secret from Secrets Manager."""
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=STRIPE_WEBHOOK_SECRET_NAME)
        secret: str = response.get("SecretString", "")
        # Secret may be stored as JSON or plain string
        try:
            secret_data = json.loads(secret)
            webhook_secret = secret_data.get("webhook_secret", secret)
            return str(webhook_secret) if webhook_secret else secret
        except json.JSONDecodeError:
            return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve webhook secret: {e}")
        raise


def verify_stripe_signature(payload: str, signature: str, secret: str) -> bool:
    """
    Verify Stripe webhook signature.

    Stripe uses HMAC-SHA256 with a timestamp to prevent replay attacks.
    The signature header format is: t=timestamp,v1=signature
    """
    if not signature:
        return False

    try:
        # Parse signature header
        elements = {}
        for item in signature.split(","):
            key, value = item.split("=", 1)
            elements[key] = value

        timestamp = elements.get("t")
        v1_signature = elements.get("v1")

        if not timestamp or not v1_signature:
            logger.warning("Missing timestamp or signature in header")
            return False

        # Check timestamp tolerance (5 minutes)
        timestamp_int = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - timestamp_int) > 300:
            logger.warning("Webhook timestamp outside tolerance window")
            return False

        # Compute expected signature
        signed_payload = f"{timestamp}.{payload}"
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(expected_signature, v1_signature)

    except (ValueError, KeyError) as e:
        logger.error(f"Failed to parse signature header: {e}")
        return False


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def get_plan_from_price(price_id: str) -> str:
    """Map Stripe price ID to plan name."""
    # Default to extracting plan name from price ID if not in mapping
    if price_id in PRICE_TO_PLAN:
        return PRICE_TO_PLAN[price_id]

    # Try to extract plan name from price ID
    # New format: "price_nat_xyz" -> "nat", "price_nat_pro_xyz" -> "nat_pro"
    # Legacy format: "price_starter_xyz" -> "starter"
    for plan in ["nat_pro", "nat", "starter", "team", "org"]:
        if plan in price_id.lower():
            return plan

    return "nat"  # Default to nat (basic plan) if unknown


def handle_checkout_completed(session: dict[str, Any]) -> None:
    """
    Handle checkout.session.completed event.

    Creates a new nation record when a customer completes checkout.
    In the new model, subscriptions are tied to nations (not individual tenants).
    """
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    customer_email = session.get("customer_email") or session.get(
        "customer_details", {}
    ).get("email")

    if not customer_id:
        logger.error("No customer ID in checkout session")
        return

    logger.info(f"Processing checkout completed for customer: {customer_id}")

    # Get plan and nation_slug from metadata
    metadata = session.get("metadata", {})
    plan = metadata.get("plan", "nat")  # Default to nat (basic plan)
    nation_slug = metadata.get("nation_slug", "")

    if not nation_slug:
        logger.error(f"No nation_slug in metadata for customer {customer_id}")
        # This is critical - we cannot proceed without nation_slug
        # In production, consider alerting on this error
        raise ValueError(f"Missing nation_slug in checkout metadata for customer {customer_id}")

    # If subscription exists, we'll get more details from subscription.updated
    # For now, create the nation with basic info
    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    now = datetime.now(timezone.utc).isoformat()

    # Check if nation already exists
    try:
        response = nations_table.get_item(Key={"nation_slug": nation_slug})
        if response.get("Item"):
            logger.info(f"Nation {nation_slug} already exists, updating")
            # Update existing nation with subscription info
            nations_table.update_item(
                Key={"nation_slug": nation_slug},
                UpdateExpression=(
                    "SET stripe_customer_id = :cid, "
                    "stripe_subscription_id = :sid, "
                    "subscription_status = :status, "
                    "subscription_plan = :plan, "
                    "queries_limit = :limit, "
                    "admin_email = :email, "
                    "updated_at = :updated"
                ),
                ExpressionAttributeValues={
                    ":cid": customer_id,
                    ":sid": subscription_id or "",
                    ":status": "active",
                    ":plan": plan,
                    ":limit": PLAN_QUERY_LIMITS.get(plan, 500),
                    ":email": customer_email or "",
                    ":updated": now,
                },
            )
        else:
            # Create new nation record
            nation_item = {
                "nation_slug": nation_slug,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id or "",
                "subscription_status": "trialing",  # Start as trialing until confirmed
                "subscription_plan": "trial",  # Trial plan until Stripe confirms
                "admin_email": customer_email or "",
                "queries_used_this_period": 0,
                "queries_limit": 50,  # Limited trial queries
                "billing_period_start": now[:10],  # YYYY-MM-DD
                "created_at": now,
                "updated_at": now,
            }
            nations_table.put_item(Item=nation_item)
            logger.info(f"Created nation {nation_slug} for customer {customer_id}")

    except ClientError as e:
        logger.error(f"DynamoDB error creating/updating nation: {e}")
        raise


def handle_subscription_updated(subscription: dict[str, Any]) -> None:
    """
    Handle customer.subscription.updated event.

    Updates nation subscription status, plan, and query limits.
    In the new model, subscriptions are tied to nations (not tenants).
    """
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    status = subscription.get("status")

    if not customer_id:
        logger.error("No customer ID in subscription update")
        return

    logger.info(
        f"Processing subscription update for customer: {customer_id}, status: {status}"
    )

    # Determine plan from subscription items
    plan = "nat"  # Default to nat (basic plan)
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan = get_plan_from_price(price_id)

    # Get billing period start
    current_period_start = subscription.get("current_period_start")
    billing_period_start = None
    if current_period_start:
        billing_period_start = datetime.fromtimestamp(
            current_period_start, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    try:
        # Find nation by customer ID
        response = nations_table.query(
            IndexName="stripe-customer-index",
            KeyConditionExpression="stripe_customer_id = :cid",
            ExpressionAttributeValues={":cid": customer_id},
        )

        if not response.get("Items"):
            logger.warning(f"No nation found for customer {customer_id}")
            return

        nation = response["Items"][0]
        nation_slug = nation["nation_slug"]
        now = datetime.now(timezone.utc).isoformat()

        # Build update expression
        update_expr = (
            "SET stripe_subscription_id = :sid, "
            "subscription_status = :status, "
            "subscription_plan = :plan, "
            "queries_limit = :limit, "
            "updated_at = :updated"
        )
        expr_values: dict[str, Any] = {
            ":sid": subscription_id,
            ":status": status,
            ":plan": plan,
            ":limit": PLAN_QUERY_LIMITS.get(plan, 500),
            ":updated": now,
        }

        # Reset query count if billing cycle changed
        old_billing_start = nation.get("billing_period_start", "")
        if billing_period_start and billing_period_start != old_billing_start:
            update_expr += ", billing_period_start = :bps, queries_used_this_period = :zero"
            expr_values[":bps"] = billing_period_start
            expr_values[":zero"] = 0

        nations_table.update_item(
            Key={"nation_slug": nation_slug},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
        logger.info(f"Updated nation {nation_slug} subscription status to {status}")

    except ClientError as e:
        logger.error(f"DynamoDB error updating subscription: {e}")
        raise


def handle_subscription_deleted(subscription: dict[str, Any]) -> None:
    """
    Handle customer.subscription.deleted event.

    Marks nation subscription as cancelled.
    In the new model, subscriptions are tied to nations (not tenants).
    """
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")

    if not customer_id:
        logger.error("No customer ID in subscription delete")
        return

    logger.info(f"Processing subscription deletion for customer: {customer_id}")

    dynamodb = get_dynamodb_resource()
    nations_table = dynamodb.Table(NATIONS_TABLE)

    try:
        # Find nation by customer ID
        response = nations_table.query(
            IndexName="stripe-customer-index",
            KeyConditionExpression="stripe_customer_id = :cid",
            ExpressionAttributeValues={":cid": customer_id},
        )

        if not response.get("Items"):
            logger.warning(f"No nation found for customer {customer_id}")
            return

        nation = response["Items"][0]
        nation_slug = nation["nation_slug"]
        now = datetime.now(timezone.utc).isoformat()

        nations_table.update_item(
            Key={"nation_slug": nation_slug},
            UpdateExpression="SET subscription_status = :status, updated_at = :updated",
            ExpressionAttributeValues={
                ":status": "cancelled",
                ":updated": now,
            },
        )
        logger.info(f"Marked nation {nation_slug} subscription as cancelled")

    except ClientError as e:
        logger.error(f"DynamoDB error deleting subscription: {e}")
        raise


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """
    Lambda handler for Stripe webhooks.

    Verifies webhook signature and routes events to appropriate handlers.
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    try:
        # Get request body and signature
        body = event.get("body", "")
        stripe_signature = event.get("headers", {}).get("Stripe-Signature", "") or event.get("headers", {}).get("stripe-signature", "")

        if not body:
            logger.error("Empty request body")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Empty request body"}),
                "headers": headers,
            }

        # Verify webhook signature
        secret = get_stripe_webhook_secret()
        if not verify_stripe_signature(body, stripe_signature, secret):
            logger.error("Invalid webhook signature")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid signature"}),
                "headers": headers,
            }

        # Parse webhook event
        webhook_event: WebhookEvent = json.loads(body)
        event_type = webhook_event.get("type", "")
        event_data = webhook_event.get("data", {}).get("object", {})

        logger.info(f"Processing webhook event: {event_type}")

        # Route to appropriate handler
        if event_type == "checkout.session.completed":
            handle_checkout_completed(event_data)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(event_data)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(event_data)
        else:
            logger.info(f"Ignoring unhandled event type: {event_type}")

        return {
            "statusCode": 200,
            "body": json.dumps({"received": True}),
            "headers": headers,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook body: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON"}),
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
