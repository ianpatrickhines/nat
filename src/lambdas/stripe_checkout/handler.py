"""
Stripe Checkout Session Lambda Handler

Creates Stripe Checkout sessions for new subscriptions.
Redirects users to Stripe's hosted checkout page.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, TypedDict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
STRIPE_SECRET_KEY_NAME = os.environ.get(
    "STRIPE_SECRET_KEY_NAME", "nat/stripe-secret-key"
)
SUCCESS_URL = os.environ.get(
    "SUCCESS_URL", "https://natassistant.com/success?session_id={CHECKOUT_SESSION_ID}"
)
CANCEL_URL = os.environ.get("CANCEL_URL", "https://natassistant.com/pricing")

# Stripe Price IDs for each plan (configured in production via env vars)
STRIPE_PRICE_IDS: dict[str, str] = {
    "starter": os.environ.get("STRIPE_PRICE_STARTER", "price_starter_monthly"),
    "team": os.environ.get("STRIPE_PRICE_TEAM", "price_team_monthly"),
    "organization": os.environ.get("STRIPE_PRICE_ORG", "price_org_monthly"),
}


class LambdaResponse(TypedDict):
    """Lambda response type."""

    statusCode: int
    body: str
    headers: dict[str, str]


def get_stripe_secret_key() -> str:
    """Retrieve Stripe secret key from Secrets Manager."""
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=STRIPE_SECRET_KEY_NAME)
        secret: str = response.get("SecretString", "")
        # Secret may be stored as JSON or plain string
        try:
            secret_data = json.loads(secret)
            api_key = secret_data.get("api_key", secret)
            return str(api_key) if api_key else secret
        except json.JSONDecodeError:
            return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve Stripe secret key: {e}")
        raise


def create_checkout_session(
    plan: str, stripe_api_key: str
) -> dict[str, Any]:
    """
    Create a Stripe Checkout session.

    Uses urllib3 for HTTP requests since we want to keep dependencies minimal.
    """
    import urllib.parse
    import urllib3

    price_id = STRIPE_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Invalid plan: {plan}")

    http = urllib3.PoolManager()

    # Build request body
    data = {
        "mode": "subscription",
        "payment_method_types[0]": "card",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": SUCCESS_URL,
        "cancel_url": CANCEL_URL,
        "billing_address_collection": "auto",
        "customer_creation": "always",
        "metadata[plan]": plan,
    }

    # Encode as form data
    body = urllib.parse.urlencode(data)

    response = http.request(
        "POST",
        "https://api.stripe.com/v1/checkout/sessions",
        body=body,
        headers={
            "Authorization": f"Bearer {stripe_api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    if response.status != 200:
        error_data = json.loads(response.data.decode("utf-8"))
        logger.error(f"Stripe API error: {error_data}")
        raise RuntimeError(f"Stripe API error: {error_data.get('error', {}).get('message', 'Unknown error')}")

    result: dict[str, Any] = json.loads(response.data.decode("utf-8"))
    return result


def handler(event: dict[str, Any], context: Any) -> LambdaResponse:
    """
    Lambda handler for creating Stripe Checkout sessions.

    Expects POST request with JSON body containing:
    - plan: string ("starter", "team", or "organization")

    Returns:
    - checkout_url: URL to redirect user to Stripe Checkout
    - session_id: Stripe session ID for verification
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    # Handle OPTIONS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "body": "",
            "headers": headers,
        }

    try:
        # Parse request body
        body_str = event.get("body", "{}")
        if not body_str:
            body_str = "{}"
        body = json.loads(body_str)

        plan = body.get("plan", "").lower()
        if not plan:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing required field: plan"}),
                "headers": headers,
            }

        if plan not in STRIPE_PRICE_IDS:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": f"Invalid plan: {plan}. Valid plans: starter, team, organization"
                }),
                "headers": headers,
            }

        # Get Stripe API key
        stripe_api_key = get_stripe_secret_key()

        # Create checkout session
        session = create_checkout_session(plan, stripe_api_key)

        logger.info(f"Created checkout session {session.get('id')} for plan {plan}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "checkout_url": session.get("url"),
                "session_id": session.get("id"),
            }),
            "headers": headers,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse request body: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
            "headers": headers,
        }
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)}),
            "headers": headers,
        }
    except ClientError as e:
        logger.error(f"AWS service error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": headers,
        }
    except RuntimeError as e:
        logger.error(f"Stripe API error: {e}")
        return {
            "statusCode": 502,
            "body": json.dumps({"error": str(e)}),
            "headers": headers,
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": headers,
        }
