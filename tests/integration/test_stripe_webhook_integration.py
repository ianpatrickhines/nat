"""
Integration tests for Stripe webhook handling flow.

Tests the complete Stripe webhook flow end-to-end with test events:
- checkout.session.completed
- customer.subscription.updated
- customer.subscription.deleted
- Signature verification
- Subscription status tracking
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from src.lambdas.stripe_webhook.handler import (
    PLAN_QUERY_LIMITS,
    handler,
)


# Test constants
TEST_WEBHOOK_SECRET = "whsec_integration_test_secret_12345"
TEST_CUSTOMER_ID = "cus_integration_test_123"
TEST_SUBSCRIPTION_ID = "sub_integration_test_456"
TEST_EMAIL = "integration.test@example.com"
TEST_TENANT_ID = "tenant_integration_789"


def create_stripe_signature(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Create a valid Stripe webhook signature for testing."""
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload}"
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def create_webhook_event(
    event_type: str,
    data: dict[str, Any],
    event_id: str | None = None,
) -> dict[str, Any]:
    """Create a Stripe webhook event payload."""
    return {
        "id": event_id or f"evt_{event_type.replace('.', '_')}",
        "type": event_type,
        "created": int(time.time()),
        "data": {"object": data},
        "livemode": False,
    }


class MockDynamoDBTable:
    """Mock DynamoDB table with full query/update support."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        if items:
            for item in items:
                key = item.get("tenant_id") or item.get("user_id")
                if key:
                    self._items[key] = item.copy()
        self.put_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.query_results: list[dict[str, Any]] = []

    def put_item(self, Item: dict[str, Any]) -> None:
        key = Item.get("tenant_id") or Item.get("user_id")
        if key:
            self._items[key] = Item.copy()
        self.put_calls.append(Item)

    def update_item(
        self,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
    ) -> None:
        self.update_calls.append({
            "Key": Key,
            "UpdateExpression": UpdateExpression,
            "ExpressionAttributeValues": ExpressionAttributeValues,
        })
        # Simulate update
        key = Key.get("tenant_id") or Key.get("user_id")
        if key and key in self._items:
            for attr_key, attr_val in ExpressionAttributeValues.items():
                attr_name = attr_key[1:]  # Remove leading :
                self._items[key][attr_name] = attr_val

    def query(
        self,
        IndexName: str,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> dict[str, Any]:
        self.query_calls.append({
            "IndexName": IndexName,
            "ExpressionAttributeValues": ExpressionAttributeValues,
        })
        return {"Items": self.query_results}

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        key = Key.get("tenant_id") or Key.get("user_id")
        if key and key in self._items:
            return {"Item": self._items[key]}
        return {}


class MockDynamoDBResource:
    """Mock DynamoDB resource."""

    def __init__(
        self,
        tenants_table: MockDynamoDBTable,
        users_table: MockDynamoDBTable,
    ) -> None:
        self.tenants_table = tenants_table
        self.users_table = users_table

    def Table(self, name: str) -> MockDynamoDBTable:
        if "tenant" in name.lower():
            return self.tenants_table
        return self.users_table


class TestCheckoutCompletedIntegration:
    """Integration tests for checkout.session.completed event."""

    def test_new_subscription_creates_tenant_and_user(self) -> None:
        """Test that a new checkout creates both tenant and user records."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        # Create checkout completed event
        checkout_data = {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
            "customer_email": TEST_EMAIL,
            "customer_details": {"email": TEST_EMAIL},
            "metadata": {"plan": "team"},
        }
        event_payload = create_webhook_event("checkout.session.completed", checkout_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        # Verify successful response
        assert response["statusCode"] == 200
        assert json.loads(response["body"]) == {"received": True}

        # Verify tenant was created with correct data
        assert len(tenants_table.put_calls) == 1
        tenant = tenants_table.put_calls[0]
        assert tenant["stripe_customer_id"] == TEST_CUSTOMER_ID
        assert tenant["stripe_subscription_id"] == TEST_SUBSCRIPTION_ID
        assert tenant["stripe_subscription_status"] == "active"
        assert tenant["plan"] == "team"
        assert tenant["queries_limit"] == PLAN_QUERY_LIMITS["team"]
        assert tenant["queries_this_month"] == 0
        assert "tenant_id" in tenant
        assert "billing_cycle_start" in tenant

        # Verify user was created
        assert len(users_table.put_calls) == 1
        user = users_table.put_calls[0]
        assert user["email"] == TEST_EMAIL
        assert user["role"] == "admin"
        assert user["nb_connected"] is False
        assert user["nb_needs_reauth"] is False
        assert "tenant_id" in user
        assert user["tenant_id"] == tenant["tenant_id"]

    def test_existing_customer_not_duplicated(self) -> None:
        """Test that existing customer's tenant is not duplicated."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = [{"tenant_id": TEST_TENANT_ID}]

        users_table = MockDynamoDBTable()
        users_table.query_results = [{"user_id": "existing-user"}]

        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        checkout_data = {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
            "customer_email": TEST_EMAIL,
        }
        event_payload = create_webhook_event("checkout.session.completed", checkout_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200
        # No new tenant should be created
        assert len(tenants_table.put_calls) == 0

    def test_checkout_with_different_plans(self) -> None:
        """Test checkout creates correct query limits for each plan."""
        for plan in ["starter", "team", "org"]:
            tenants_table = MockDynamoDBTable()
            users_table = MockDynamoDBTable()
            mock_resource = MockDynamoDBResource(tenants_table, users_table)

            checkout_data = {
                "customer": f"{TEST_CUSTOMER_ID}_{plan}",
                "subscription": TEST_SUBSCRIPTION_ID,
                "customer_email": TEST_EMAIL,
                "metadata": {"plan": plan},
            }
            event_payload = create_webhook_event("checkout.session.completed", checkout_data)
            body = json.dumps(event_payload)
            signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

            lambda_event = {
                "body": body,
                "headers": {"Stripe-Signature": signature},
            }

            with (
                patch(
                    "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                    return_value=TEST_WEBHOOK_SECRET,
                ),
                patch(
                    "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                    return_value=mock_resource,
                ),
            ):
                response = handler(lambda_event, None)

            assert response["statusCode"] == 200
            tenant = tenants_table.put_calls[0]
            assert tenant["plan"] == plan
            assert tenant["queries_limit"] == PLAN_QUERY_LIMITS[plan]


class TestSubscriptionUpdatedIntegration:
    """Integration tests for customer.subscription.updated event."""

    def test_subscription_status_update(self) -> None:
        """Test that subscription status is updated correctly."""
        tenants_table = MockDynamoDBTable([{
            "tenant_id": TEST_TENANT_ID,
            "stripe_customer_id": TEST_CUSTOMER_ID,
            "stripe_subscription_status": "trialing",
            "plan": "starter",
            "billing_cycle_start": "2025-01-01",
        }])
        tenants_table.query_results = [tenants_table._items[TEST_TENANT_ID]]

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        subscription_data = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
            "items": {
                "data": [{"price": {"id": "price_team_monthly"}}]
            },
        }
        event_payload = create_webhook_event("customer.subscription.updated", subscription_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200

        # Verify update was made
        assert len(tenants_table.update_calls) == 1
        update = tenants_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":status"] == "active"
        assert update["ExpressionAttributeValues"][":plan"] == "team"
        assert update["ExpressionAttributeValues"][":limit"] == PLAN_QUERY_LIMITS["team"]

    def test_billing_cycle_reset(self) -> None:
        """Test that usage is reset when billing cycle changes."""
        tenants_table = MockDynamoDBTable([{
            "tenant_id": TEST_TENANT_ID,
            "stripe_customer_id": TEST_CUSTOMER_ID,
            "billing_cycle_start": "2025-01-01",
            "queries_this_month": 150,  # Had usage in old cycle
        }])
        tenants_table.query_results = [tenants_table._items[TEST_TENANT_ID]]

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        # New billing period starts February 1st
        new_period_start = 1738368000  # 2025-02-01 00:00:00 UTC

        subscription_data = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
            "current_period_start": new_period_start,
            "items": {"data": []},
        }
        event_payload = create_webhook_event("customer.subscription.updated", subscription_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200

        # Verify usage was reset
        update = tenants_table.update_calls[0]
        assert ":zero" in update["ExpressionAttributeValues"]
        assert update["ExpressionAttributeValues"][":zero"] == 0
        assert "billing_cycle_start" in update["UpdateExpression"]

    def test_plan_upgrade(self) -> None:
        """Test that plan upgrade updates query limits."""
        tenants_table = MockDynamoDBTable([{
            "tenant_id": TEST_TENANT_ID,
            "stripe_customer_id": TEST_CUSTOMER_ID,
            "plan": "starter",
            "queries_limit": PLAN_QUERY_LIMITS["starter"],
            "billing_cycle_start": "2025-01-15",
        }])
        tenants_table.query_results = [tenants_table._items[TEST_TENANT_ID]]

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        # Upgrading to organization plan
        subscription_data = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
            "items": {
                "data": [{"price": {"id": "price_org_monthly"}}]
            },
        }
        event_payload = create_webhook_event("customer.subscription.updated", subscription_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200

        # Verify plan was upgraded
        update = tenants_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":plan"] == "org"
        assert update["ExpressionAttributeValues"][":limit"] == PLAN_QUERY_LIMITS["org"]


class TestSubscriptionDeletedIntegration:
    """Integration tests for customer.subscription.deleted event."""

    def test_subscription_cancelled(self) -> None:
        """Test that deleted subscription marks tenant as cancelled."""
        tenants_table = MockDynamoDBTable([{
            "tenant_id": TEST_TENANT_ID,
            "stripe_customer_id": TEST_CUSTOMER_ID,
            "stripe_subscription_status": "active",
        }])
        tenants_table.query_results = [tenants_table._items[TEST_TENANT_ID]]

        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        subscription_data = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
        }
        event_payload = create_webhook_event("customer.subscription.deleted", subscription_data)
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200

        # Verify subscription status was updated to cancelled
        assert len(tenants_table.update_calls) == 1
        update = tenants_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":status"] == "cancelled"


class TestSignatureVerificationIntegration:
    """Integration tests for webhook signature verification."""

    def test_valid_signature_accepted(self) -> None:
        """Test that valid signatures are accepted."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        event_payload = create_webhook_event("checkout.session.completed", {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
        })
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200

    def test_invalid_signature_rejected(self) -> None:
        """Test that invalid signatures are rejected with 401."""
        event_payload = create_webhook_event("checkout.session.completed", {})
        body = json.dumps(event_payload)
        # Sign with wrong secret
        signature = create_stripe_signature(body, "wrong_secret")

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
            return_value=TEST_WEBHOOK_SECRET,
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 401
        assert "Invalid signature" in json.loads(response["body"])["error"]

    def test_expired_timestamp_rejected(self) -> None:
        """Test that webhooks with expired timestamps are rejected."""
        event_payload = create_webhook_event("checkout.session.completed", {})
        body = json.dumps(event_payload)
        # Use timestamp from 10 minutes ago (beyond 5 minute tolerance)
        old_timestamp = int(time.time()) - 600
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET, old_timestamp)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
            return_value=TEST_WEBHOOK_SECRET,
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 401

    def test_tampered_payload_rejected(self) -> None:
        """Test that tampered payloads are rejected."""
        original_payload = create_webhook_event("checkout.session.completed", {
            "customer": TEST_CUSTOMER_ID,
        })
        original_body = json.dumps(original_payload)
        signature = create_stripe_signature(original_body, TEST_WEBHOOK_SECRET)

        # Tamper with the payload
        tampered_payload = create_webhook_event("checkout.session.completed", {
            "customer": "different_customer",
        })
        tampered_body = json.dumps(tampered_payload)

        lambda_event = {
            "body": tampered_body,  # Tampered body
            "headers": {"Stripe-Signature": signature},  # Original signature
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
            return_value=TEST_WEBHOOK_SECRET,
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 401

    def test_lowercase_header_accepted(self) -> None:
        """Test that lowercase stripe-signature header is accepted."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        event_payload = create_webhook_event("checkout.session.completed", {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
        })
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        # Use lowercase header (API Gateway sometimes normalizes)
        lambda_event = {
            "body": body,
            "headers": {"stripe-signature": signature},
        }

        with (
            patch(
                "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
                return_value=TEST_WEBHOOK_SECRET,
            ),
            patch(
                "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
                return_value=mock_resource,
            ),
        ):
            response = handler(lambda_event, None)

        assert response["statusCode"] == 200


class TestUnhandledEventsIntegration:
    """Tests for unhandled event types."""

    def test_unhandled_event_returns_200(self) -> None:
        """Test that unhandled events are acknowledged with 200."""
        event_payload = create_webhook_event("invoice.payment_succeeded", {
            "customer": TEST_CUSTOMER_ID,
        })
        body = json.dumps(event_payload)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        lambda_event = {
            "body": body,
            "headers": {"Stripe-Signature": signature},
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_stripe_webhook_secret",
            return_value=TEST_WEBHOOK_SECRET,
        ):
            response = handler(lambda_event, None)

        # Unhandled events should return 200 to prevent Stripe retries
        assert response["statusCode"] == 200
        assert json.loads(response["body"]) == {"received": True}
