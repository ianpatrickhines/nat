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
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "nat-tenants-dev")
USERS_TABLE = os.environ.get("USERS_TABLE", "nat-users-dev")
STRIPE_WEBHOOK_SECRET_NAME = os.environ.get(
    "STRIPE_WEBHOOK_SECRET_NAME", "nat/stripe-webhook-secret"
)

# Plan configuration
PLAN_QUERY_LIMITS: dict[str, int] = {
    "starter": 500,
    "team": 2000,
    "org": 5000,
}

# Stripe price ID to plan mapping (configure these in production)
PRICE_TO_PLAN: dict[str, str] = {
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

    # Try to extract plan name from price ID (e.g., "price_starter_xyz" -> "starter")
    for plan in ["starter", "team", "org"]:
        if plan in price_id.lower():
            return plan

    return "starter"  # Default to starter if unknown


def handle_checkout_completed(session: dict[str, Any]) -> None:
    """
    Handle checkout.session.completed event.

    Creates a new tenant record when a customer completes checkout.
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

    # Get plan from line items or metadata
    metadata = session.get("metadata", {})
    plan = metadata.get("plan", "starter")

    # If subscription exists, we'll get more details from subscription.updated
    # For now, create the tenant with basic info
    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)
    users_table = dynamodb.Table(USERS_TABLE)

    now = datetime.now(timezone.utc).isoformat()
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    # Check if tenant already exists for this customer
    try:
        response = tenants_table.query(
            IndexName="stripe-customer-index",
            KeyConditionExpression="stripe_customer_id = :cid",
            ExpressionAttributeValues={":cid": customer_id},
        )
        if response.get("Items"):
            logger.info(f"Tenant already exists for customer {customer_id}")
            tenant_id = response["Items"][0]["tenant_id"]
        else:
            # Create new tenant
            tenant_item = {
                "tenant_id": tenant_id,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id or "",
                "stripe_subscription_status": "active",
                "plan": plan,
                "email": customer_email or "",
                "queries_this_month": 0,
                "queries_limit": PLAN_QUERY_LIMITS.get(plan, 500),
                "billing_cycle_start": now[:10],  # YYYY-MM-DD
                "created_at": now,
                "updated_at": now,
            }
            tenants_table.put_item(Item=tenant_item)
            logger.info(f"Created tenant {tenant_id} for customer {customer_id}")

    except ClientError as e:
        logger.error(f"DynamoDB error creating tenant: {e}")
        raise

    # Create initial user if email provided
    if customer_email:
        try:
            # Check if user exists
            response = users_table.query(
                IndexName="email-index",
                KeyConditionExpression="email = :email",
                ExpressionAttributeValues={":email": customer_email},
            )
            if not response.get("Items"):
                user_item = {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "email": customer_email,
                    "role": "admin",
                    "nb_connected": False,
                    "nb_needs_reauth": False,
                    "created_at": now,
                    "last_active_at": now,
                }
                users_table.put_item(Item=user_item)
                logger.info(f"Created user {user_id} for tenant {tenant_id}")
        except ClientError as e:
            logger.error(f"DynamoDB error creating user: {e}")
            # Don't raise - tenant creation succeeded


def handle_subscription_updated(subscription: dict[str, Any]) -> None:
    """
    Handle customer.subscription.updated event.

    Updates tenant subscription status, plan, and query limits.
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
    plan = "starter"
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan = get_plan_from_price(price_id)

    # Get billing period start
    current_period_start = subscription.get("current_period_start")
    billing_cycle_start = None
    if current_period_start:
        billing_cycle_start = datetime.fromtimestamp(
            current_period_start, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)

    try:
        # Find tenant by customer ID
        response = tenants_table.query(
            IndexName="stripe-customer-index",
            KeyConditionExpression="stripe_customer_id = :cid",
            ExpressionAttributeValues={":cid": customer_id},
        )

        if not response.get("Items"):
            logger.warning(f"No tenant found for customer {customer_id}")
            return

        tenant = response["Items"][0]
        tenant_id = tenant["tenant_id"]
        now = datetime.now(timezone.utc).isoformat()

        # Build update expression
        update_expr = "SET stripe_subscription_id = :sid, stripe_subscription_status = :status, #plan = :plan, queries_limit = :limit, updated_at = :updated"
        expr_values: dict[str, Any] = {
            ":sid": subscription_id,
            ":status": status,
            ":plan": plan,
            ":limit": PLAN_QUERY_LIMITS.get(plan, 500),
            ":updated": now,
        }

        # Reset query count if billing cycle changed
        old_billing_start = tenant.get("billing_cycle_start", "")
        if billing_cycle_start and billing_cycle_start != old_billing_start:
            update_expr += ", billing_cycle_start = :bcs, queries_this_month = :zero"
            expr_values[":bcs"] = billing_cycle_start
            expr_values[":zero"] = 0

        tenants_table.update_item(
            Key={"tenant_id": tenant_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#plan": "plan"},
            ExpressionAttributeValues=expr_values,
        )
        logger.info(f"Updated tenant {tenant_id} subscription status to {status}")

    except ClientError as e:
        logger.error(f"DynamoDB error updating subscription: {e}")
        raise


def handle_subscription_deleted(subscription: dict[str, Any]) -> None:
    """
    Handle customer.subscription.deleted event.

    Marks tenant subscription as cancelled.
    """
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")

    if not customer_id:
        logger.error("No customer ID in subscription delete")
        return

    logger.info(f"Processing subscription deletion for customer: {customer_id}")

    dynamodb = get_dynamodb_resource()
    tenants_table = dynamodb.Table(TENANTS_TABLE)

    try:
        # Find tenant by customer ID
        response = tenants_table.query(
            IndexName="stripe-customer-index",
            KeyConditionExpression="stripe_customer_id = :cid",
            ExpressionAttributeValues={":cid": customer_id},
        )

        if not response.get("Items"):
            logger.warning(f"No tenant found for customer {customer_id}")
            return

        tenant = response["Items"][0]
        tenant_id = tenant["tenant_id"]
        now = datetime.now(timezone.utc).isoformat()

        tenants_table.update_item(
            Key={"tenant_id": tenant_id},
            UpdateExpression="SET stripe_subscription_status = :status, updated_at = :updated",
            ExpressionAttributeValues={
                ":status": "cancelled",
                ":updated": now,
            },
        )
        logger.info(f"Marked tenant {tenant_id} subscription as cancelled")

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
