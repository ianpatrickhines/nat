"""
Unit tests for Stripe Webhook Lambda Handler
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.stripe_webhook.handler import (
    PLAN_QUERY_LIMITS,
    get_plan_from_price,
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_subscription_updated,
    handler,
    verify_stripe_signature,
)


# Test data
TEST_WEBHOOK_SECRET = "whsec_test_secret_12345"
TEST_CUSTOMER_ID = "cus_test123"
TEST_SUBSCRIPTION_ID = "sub_test456"
TEST_EMAIL = "test@example.com"


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


class TestVerifyStripeSignature:
    """Tests for webhook signature verification."""

    def test_valid_signature(self) -> None:
        """Test that valid signatures pass verification."""
        payload = '{"test": "data"}'
        signature = create_stripe_signature(payload, TEST_WEBHOOK_SECRET)
        assert verify_stripe_signature(payload, signature, TEST_WEBHOOK_SECRET) is True

    def test_invalid_signature(self) -> None:
        """Test that invalid signatures fail verification."""
        payload = '{"test": "data"}'
        signature = create_stripe_signature(payload, "wrong_secret")
        assert verify_stripe_signature(payload, signature, TEST_WEBHOOK_SECRET) is False

    def test_tampered_payload(self) -> None:
        """Test that tampered payloads fail verification."""
        original_payload = '{"test": "data"}'
        signature = create_stripe_signature(original_payload, TEST_WEBHOOK_SECRET)
        tampered_payload = '{"test": "tampered"}'
        assert verify_stripe_signature(tampered_payload, signature, TEST_WEBHOOK_SECRET) is False

    def test_expired_timestamp(self) -> None:
        """Test that expired timestamps fail verification."""
        payload = '{"test": "data"}'
        old_timestamp = int(time.time()) - 400  # 6+ minutes ago
        signature = create_stripe_signature(payload, TEST_WEBHOOK_SECRET, old_timestamp)
        assert verify_stripe_signature(payload, signature, TEST_WEBHOOK_SECRET) is False

    def test_empty_signature(self) -> None:
        """Test that empty signature fails."""
        assert verify_stripe_signature("payload", "", TEST_WEBHOOK_SECRET) is False

    def test_malformed_signature(self) -> None:
        """Test that malformed signature fails."""
        assert verify_stripe_signature("payload", "invalid", TEST_WEBHOOK_SECRET) is False


class TestGetPlanFromPrice:
    """Tests for price ID to plan mapping."""

    def test_explicit_mapping(self) -> None:
        """Test that explicitly mapped prices return correct plan."""
        # Note: These use the configured mappings
        assert get_plan_from_price("price_starter_monthly") == "starter"
        assert get_plan_from_price("price_team_monthly") == "team"
        assert get_plan_from_price("price_org_monthly") == "org"

    def test_inferred_plan(self) -> None:
        """Test that plan name is inferred from price ID."""
        assert get_plan_from_price("price_xxxxx_starter_yyyyy") == "starter"
        assert get_plan_from_price("prod_team_plan_abc") == "team"
        assert get_plan_from_price("price_org_enterprise") == "org"

    def test_unknown_defaults_to_starter(self) -> None:
        """Test that unknown price IDs default to starter."""
        assert get_plan_from_price("price_unknown_xyz") == "starter"


class MockDynamoDBTable:
    """Mock DynamoDB table for testing."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.put_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.query_results: list[dict[str, Any]] = []

    def put_item(self, Item: dict[str, Any]) -> None:
        key = Item.get("tenant_id") or Item.get("user_id")
        if key:
            self.items[key] = Item
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

    def query(
        self,
        IndexName: str,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> dict[str, Any]:
        return {"Items": self.query_results}


class MockDynamoDBResource:
    """Mock DynamoDB resource for testing."""

    def __init__(self, tenants_table: MockDynamoDBTable, users_table: MockDynamoDBTable) -> None:
        self.tenants_table = tenants_table
        self.users_table = users_table

    def Table(self, name: str) -> MockDynamoDBTable:
        if "tenant" in name.lower():
            return self.tenants_table
        return self.users_table


class TestHandleCheckoutCompleted:
    """Tests for checkout.session.completed event handling."""

    def test_creates_tenant_and_user(self) -> None:
        """Test that checkout creates new tenant and user."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        session = {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
            "customer_email": TEST_EMAIL,
            "metadata": {"plan": "team"},
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_checkout_completed(session)

        # Verify tenant created
        assert len(tenants_table.put_calls) == 1
        tenant = tenants_table.put_calls[0]
        assert tenant["stripe_customer_id"] == TEST_CUSTOMER_ID
        assert tenant["stripe_subscription_id"] == TEST_SUBSCRIPTION_ID
        assert tenant["plan"] == "team"
        assert tenant["queries_limit"] == PLAN_QUERY_LIMITS["team"]
        assert tenant["queries_this_month"] == 0

        # Verify user created
        assert len(users_table.put_calls) == 1
        user = users_table.put_calls[0]
        assert user["email"] == TEST_EMAIL
        assert user["role"] == "admin"
        assert user["nb_connected"] is False

    def test_existing_tenant_not_duplicated(self) -> None:
        """Test that existing tenant is not duplicated."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = [{"tenant_id": "existing-tenant-id"}]
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        session = {
            "customer": TEST_CUSTOMER_ID,
            "subscription": TEST_SUBSCRIPTION_ID,
            "customer_email": TEST_EMAIL,
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_checkout_completed(session)

        # Should not create new tenant
        assert len(tenants_table.put_calls) == 0

    def test_no_customer_id_returns_early(self) -> None:
        """Test that missing customer ID is handled gracefully."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        session = {"subscription": TEST_SUBSCRIPTION_ID}

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_checkout_completed(session)

        assert len(tenants_table.put_calls) == 0


class TestHandleSubscriptionUpdated:
    """Tests for customer.subscription.updated event handling."""

    def test_updates_subscription_status(self) -> None:
        """Test that subscription status is updated."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = [{"tenant_id": "test-tenant-id", "billing_cycle_start": "2025-01-01"}]
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        subscription = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
            "items": {
                "data": [{"price": {"id": "price_team_monthly"}}]
            },
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_subscription_updated(subscription)

        assert len(tenants_table.update_calls) == 1
        update = tenants_table.update_calls[0]
        assert update["Key"] == {"tenant_id": "test-tenant-id"}
        assert update["ExpressionAttributeValues"][":status"] == "active"
        assert update["ExpressionAttributeValues"][":plan"] == "team"
        assert update["ExpressionAttributeValues"][":limit"] == PLAN_QUERY_LIMITS["team"]

    def test_resets_usage_on_new_billing_cycle(self) -> None:
        """Test that query usage is reset when billing cycle changes."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = [{"tenant_id": "test-tenant-id", "billing_cycle_start": "2025-01-01"}]
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        # New billing cycle (February)
        new_period_start = 1738368000  # 2025-02-01

        subscription = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
            "current_period_start": new_period_start,
            "items": {"data": []},
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_subscription_updated(subscription)

        update = tenants_table.update_calls[0]
        assert ":zero" in update["ExpressionAttributeValues"]
        assert update["ExpressionAttributeValues"][":zero"] == 0
        assert "billing_cycle_start" in update["UpdateExpression"]

    def test_no_tenant_found(self) -> None:
        """Test that missing tenant is handled gracefully."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = []
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        subscription = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
            "status": "active",
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_subscription_updated(subscription)

        assert len(tenants_table.update_calls) == 0


class TestHandleSubscriptionDeleted:
    """Tests for customer.subscription.deleted event handling."""

    def test_marks_subscription_cancelled(self) -> None:
        """Test that subscription is marked as cancelled."""
        tenants_table = MockDynamoDBTable()
        tenants_table.query_results = [{"tenant_id": "test-tenant-id"}]
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        subscription = {
            "customer": TEST_CUSTOMER_ID,
            "id": TEST_SUBSCRIPTION_ID,
        }

        with patch(
            "src.lambdas.stripe_webhook.handler.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            handle_subscription_deleted(subscription)

        assert len(tenants_table.update_calls) == 1
        update = tenants_table.update_calls[0]
        assert update["ExpressionAttributeValues"][":status"] == "cancelled"


class TestHandler:
    """Tests for the main Lambda handler."""

    def test_valid_checkout_event(self) -> None:
        """Test successful processing of checkout event."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        event_body = {
            "id": "evt_test",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": TEST_CUSTOMER_ID,
                    "subscription": TEST_SUBSCRIPTION_ID,
                    "customer_email": TEST_EMAIL,
                }
            },
        }
        body = json.dumps(event_body)
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
        assert json.loads(response["body"]) == {"received": True}

    def test_invalid_signature_returns_401(self) -> None:
        """Test that invalid signature returns 401."""
        event_body = {"type": "checkout.session.completed", "data": {"object": {}}}
        body = json.dumps(event_body)
        signature = "t=123,v1=invalid_signature"

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

    def test_empty_body_returns_400(self) -> None:
        """Test that empty body returns 400."""
        lambda_event = {"body": "", "headers": {}}
        response = handler(lambda_event, None)
        assert response["statusCode"] == 400

    def test_invalid_json_returns_400(self) -> None:
        """Test that invalid JSON returns 400."""
        body = "not valid json"
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

        assert response["statusCode"] == 400

    def test_unhandled_event_type_returns_200(self) -> None:
        """Test that unhandled event types are acknowledged with 200."""
        event_body = {
            "type": "some.other.event",
            "data": {"object": {}},
        }
        body = json.dumps(event_body)
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

        assert response["statusCode"] == 200

    def test_lowercase_signature_header(self) -> None:
        """Test that lowercase signature header is accepted."""
        tenants_table = MockDynamoDBTable()
        users_table = MockDynamoDBTable()
        mock_resource = MockDynamoDBResource(tenants_table, users_table)

        event_body = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": TEST_CUSTOMER_ID,
                    "subscription": TEST_SUBSCRIPTION_ID,
                }
            },
        }
        body = json.dumps(event_body)
        signature = create_stripe_signature(body, TEST_WEBHOOK_SECRET)

        # Use lowercase header name (API Gateway sometimes normalizes these)
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
