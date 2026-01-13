"""
Integration tests for subscription verification flow.

Tests the complete subscription verification flow end-to-end:
- User header extraction
- Tenant lookup
- Subscription status validation
- Query limit enforcement
- Middleware decorator pattern
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from src.lambdas.shared.subscription_middleware import (
    ACTIVE_STATUSES,
    SubscriptionError,
    SubscriptionErrorCode,
    SubscriptionMiddleware,
    extract_user_from_headers,
    get_tenant_subscription,
    get_user_tenant_id,
    verify_subscription,
)


# Test constants
TEST_USER_ID = "verify-test-user-123"
TEST_TENANT_ID = "verify-test-tenant-456"
TEST_EMAIL = "verify.test@example.com"


class MockDynamoDBTable:
    """Mock DynamoDB table with get_item support."""

    def __init__(self, items: dict[str, dict[str, Any]] | None = None) -> None:
        self.items: dict[str, dict[str, Any]] = items or {}
        self.get_calls: list[dict[str, Any]] = []

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        self.get_calls.append(Key)
        key = Key.get("user_id") or Key.get("tenant_id")
        if key and key in self.items:
            return {"Item": self.items[key]}
        return {}


class MockDynamoDBResource:
    """Mock DynamoDB resource."""

    def __init__(
        self,
        users_table: MockDynamoDBTable,
        tenants_table: MockDynamoDBTable,
    ) -> None:
        self.users_table = users_table
        self.tenants_table = tenants_table

    def Table(self, name: str) -> MockDynamoDBTable:
        if "tenant" in name.lower():
            return self.tenants_table
        return self.users_table


class TestExtractUserFromHeaders:
    """Tests for user extraction from request headers."""

    def test_extracts_user_id(self) -> None:
        """Test that user ID is extracted from headers."""
        headers = {
            "X-Nat-User-Id": TEST_USER_ID,
        }
        context = extract_user_from_headers(headers)
        assert context.user_id == TEST_USER_ID
        assert context.tenant_id is None

    def test_extracts_tenant_id_when_provided(self) -> None:
        """Test that tenant ID is extracted when provided."""
        headers = {
            "X-Nat-User-Id": TEST_USER_ID,
            "X-Nat-Tenant-Id": TEST_TENANT_ID,
        }
        context = extract_user_from_headers(headers)
        assert context.user_id == TEST_USER_ID
        assert context.tenant_id == TEST_TENANT_ID

    def test_handles_lowercase_headers(self) -> None:
        """Test that lowercase headers are handled (API Gateway normalization)."""
        headers = {
            "x-nat-user-id": TEST_USER_ID,
            "x-nat-tenant-id": TEST_TENANT_ID,
        }
        context = extract_user_from_headers(headers)
        assert context.user_id == TEST_USER_ID
        assert context.tenant_id == TEST_TENANT_ID

    def test_handles_mixed_case_headers(self) -> None:
        """Test that mixed case headers are handled."""
        headers = {
            "X-NAT-USER-ID": TEST_USER_ID,
        }
        context = extract_user_from_headers(headers)
        assert context.user_id == TEST_USER_ID

    def test_missing_user_id_raises_error(self) -> None:
        """Test that missing user ID raises appropriate error."""
        headers: dict[str, str] = {}
        with pytest.raises(SubscriptionError) as exc_info:
            extract_user_from_headers(headers)

        assert exc_info.value.code == SubscriptionErrorCode.MISSING_USER_ID
        assert exc_info.value.http_status == 401

    def test_empty_user_id_raises_error(self) -> None:
        """Test that empty user ID raises appropriate error."""
        headers = {"X-Nat-User-Id": ""}
        with pytest.raises(SubscriptionError) as exc_info:
            extract_user_from_headers(headers)

        assert exc_info.value.code == SubscriptionErrorCode.MISSING_USER_ID


class TestSubscriptionVerificationIntegration:
    """Integration tests for the complete subscription verification flow."""

    def test_active_subscription_with_capacity(self) -> None:
        """Test that active subscription with capacity is valid."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {
                "user_id": TEST_USER_ID,
                "tenant_id": TEST_TENANT_ID,
                "email": TEST_EMAIL,
            }
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "team",
                "queries_this_month": 100,
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id=TEST_USER_ID)

        assert status["valid"] is True
        assert status["user_id"] == TEST_USER_ID
        assert status["tenant_id"] == TEST_TENANT_ID
        assert status["plan"] == "team"
        assert status["queries_this_month"] == 100
        assert status["queries_limit"] == 2000
        assert status["subscription_status"] == "active"

    def test_trialing_subscription_allowed(self) -> None:
        """Test that trialing subscription is allowed."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "trialing",
                "plan": "starter",
                "queries_this_month": 0,
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id=TEST_USER_ID)

        assert status["valid"] is True
        assert status["subscription_status"] == "trialing"

    def test_cancelled_subscription_rejected(self) -> None:
        """Test that cancelled subscription returns 402."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "cancelled",
                "plan": "starter",
                "queries_this_month": 0,
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    def test_past_due_subscription_rejected(self) -> None:
        """Test that past_due subscription returns 402."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "past_due",
                "plan": "team",
                "queries_this_month": 50,
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    def test_unpaid_subscription_rejected(self) -> None:
        """Test that unpaid subscription returns 402."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "unpaid",
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    def test_query_limit_exceeded_rejected(self) -> None:
        """Test that exceeded query limit returns 403."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 500,  # At limit
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED
        assert exc_info.value.http_status == 403
        assert "500" in exc_info.value.message

    def test_query_limit_over_exceeded_rejected(self) -> None:
        """Test that over-exceeded query limit returns 403."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 550,  # Over limit
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED

    def test_user_not_found_rejected(self) -> None:
        """Test that missing user returns 401."""
        users_table = MockDynamoDBTable({})  # Empty table
        tenants_table = MockDynamoDBTable({})

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.USER_NOT_FOUND
        assert exc_info.value.http_status == 401

    def test_tenant_not_found_rejected(self) -> None:
        """Test that missing tenant returns 403."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })
        tenants_table = MockDynamoDBTable({})  # Empty table

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.TENANT_NOT_FOUND
        assert exc_info.value.http_status == 403

    def test_user_without_tenant_rejected(self) -> None:
        """Test that user without tenant association returns 403."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {
                "user_id": TEST_USER_ID,
                # No tenant_id field
            }
        })
        tenants_table = MockDynamoDBTable({})

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            with pytest.raises(SubscriptionError) as exc_info:
                verify_subscription(user_id=TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.TENANT_NOT_FOUND
        assert exc_info.value.http_status == 403

    def test_verification_with_tenant_id_skips_user_lookup(self) -> None:
        """Test that providing tenant ID skips user lookup."""
        users_table = MockDynamoDBTable({})  # Should not be queried

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "team",
                "queries_this_month": 0,
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(
                user_id=TEST_USER_ID,
                tenant_id=TEST_TENANT_ID,  # Provided directly
            )

        assert status["valid"] is True
        # User table should not have been queried
        assert len(users_table.get_calls) == 0


class TestSubscriptionMiddlewareIntegration:
    """Integration tests for the SubscriptionMiddleware class."""

    def test_middleware_verify_method(self) -> None:
        """Test middleware.verify() method."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 0,
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        event = {
            "headers": {"X-Nat-User-Id": TEST_USER_ID},
        }

        middleware = SubscriptionMiddleware()

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = middleware.verify(event)

        assert status["valid"] is True
        assert status["user_id"] == TEST_USER_ID

    def test_middleware_decorator_success(self) -> None:
        """Test middleware as decorator - successful case."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "team",
                "queries_this_month": 10,
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        # Create a test handler decorated with middleware
        @SubscriptionMiddleware()
        def test_handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Success",
                    "plan": subscription_status["plan"],
                }),
            }

        event = {
            "headers": {"X-Nat-User-Id": TEST_USER_ID},
        }

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            response = test_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["plan"] == "team"

    def test_middleware_decorator_subscription_inactive(self) -> None:
        """Test middleware as decorator - subscription inactive case."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "cancelled",
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        @SubscriptionMiddleware()
        def test_handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: dict[str, Any],
        ) -> dict[str, Any]:
            # This should not be reached
            return {"statusCode": 200, "body": "{}"}

        event = {
            "headers": {"X-Nat-User-Id": TEST_USER_ID},
        }

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            response = test_handler(event, None)

        assert response["statusCode"] == 402
        body = json.loads(response["body"])
        assert body["error"] == "SUBSCRIPTION_INACTIVE"

    def test_middleware_decorator_missing_user_header(self) -> None:
        """Test middleware as decorator - missing user header case."""
        @SubscriptionMiddleware()
        def test_handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: dict[str, Any],
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}"}

        event: dict[str, Any] = {
            "headers": {},  # No user ID header
        }

        response = test_handler(event, None)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"] == "MISSING_USER_ID"

    def test_middleware_decorator_limit_exceeded(self) -> None:
        """Test middleware as decorator - query limit exceeded case."""
        users_table = MockDynamoDBTable({
            TEST_USER_ID: {"user_id": TEST_USER_ID, "tenant_id": TEST_TENANT_ID}
        })

        tenants_table = MockDynamoDBTable({
            TEST_TENANT_ID: {
                "tenant_id": TEST_TENANT_ID,
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 500,
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        @SubscriptionMiddleware()
        def test_handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: dict[str, Any],
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}"}

        event = {
            "headers": {"X-Nat-User-Id": TEST_USER_ID},
        }

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            response = test_handler(event, None)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error"] == "QUERY_LIMIT_EXCEEDED"


class TestEndToEndSubscriptionFlow:
    """End-to-end tests simulating real user flows."""

    def test_new_user_first_query(self) -> None:
        """Test new user making their first query after subscription."""
        # Simulate a new subscriber who just completed checkout
        users_table = MockDynamoDBTable({
            "new-user-001": {
                "user_id": "new-user-001",
                "tenant_id": "new-tenant-001",
                "email": "new@example.com",
                "nb_connected": True,  # Already connected NB
            }
        })

        tenants_table = MockDynamoDBTable({
            "new-tenant-001": {
                "tenant_id": "new-tenant-001",
                "stripe_customer_id": "cus_new001",
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 0,  # First query
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id="new-user-001")

        assert status["valid"] is True
        assert status["queries_this_month"] == 0
        assert status["queries_limit"] == 500

    def test_heavy_user_approaching_limit(self) -> None:
        """Test user approaching their query limit."""
        users_table = MockDynamoDBTable({
            "heavy-user-001": {
                "user_id": "heavy-user-001",
                "tenant_id": "heavy-tenant-001",
            }
        })

        tenants_table = MockDynamoDBTable({
            "heavy-tenant-001": {
                "tenant_id": "heavy-tenant-001",
                "stripe_subscription_status": "active",
                "plan": "starter",
                "queries_this_month": 499,  # One query remaining
                "queries_limit": 500,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id="heavy-user-001")

        # Should still be valid (one query remaining)
        assert status["valid"] is True
        assert status["queries_this_month"] == 499
        assert status["queries_limit"] == 500

    def test_team_plan_higher_limit(self) -> None:
        """Test team plan has higher query limits."""
        users_table = MockDynamoDBTable({
            "team-user-001": {
                "user_id": "team-user-001",
                "tenant_id": "team-tenant-001",
            }
        })

        tenants_table = MockDynamoDBTable({
            "team-tenant-001": {
                "tenant_id": "team-tenant-001",
                "stripe_subscription_status": "active",
                "plan": "team",
                "queries_this_month": 600,  # Would be over starter limit
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id="team-user-001")

        # Should be valid - team plan has higher limit
        assert status["valid"] is True
        assert status["plan"] == "team"
        assert status["queries_this_month"] == 600
        assert status["queries_limit"] == 2000

    def test_organization_plan_highest_limit(self) -> None:
        """Test organization plan has highest query limits."""
        users_table = MockDynamoDBTable({
            "org-user-001": {
                "user_id": "org-user-001",
                "tenant_id": "org-tenant-001",
            }
        })

        tenants_table = MockDynamoDBTable({
            "org-tenant-001": {
                "tenant_id": "org-tenant-001",
                "stripe_subscription_status": "active",
                "plan": "org",
                "queries_this_month": 2500,  # Would be over team limit
                "queries_limit": 5000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        with patch(
            "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
            return_value=mock_resource,
        ):
            status = verify_subscription(user_id="org-user-001")

        # Should be valid - org plan has highest limit
        assert status["valid"] is True
        assert status["plan"] == "org"
        assert status["queries_limit"] == 5000

    def test_multiple_users_same_tenant(self) -> None:
        """Test multiple users from same tenant share query limits."""
        # Multiple users from same organization
        users_table = MockDynamoDBTable({
            "team-user-1": {"user_id": "team-user-1", "tenant_id": "shared-tenant"},
            "team-user-2": {"user_id": "team-user-2", "tenant_id": "shared-tenant"},
            "team-user-3": {"user_id": "team-user-3", "tenant_id": "shared-tenant"},
        })

        tenants_table = MockDynamoDBTable({
            "shared-tenant": {
                "tenant_id": "shared-tenant",
                "stripe_subscription_status": "active",
                "plan": "team",
                "queries_this_month": 1500,  # Combined usage
                "queries_limit": 2000,
            }
        })

        mock_resource = MockDynamoDBResource(users_table, tenants_table)

        # All users should see the same tenant-level usage
        for user_id in ["team-user-1", "team-user-2", "team-user-3"]:
            with patch(
                "src.lambdas.shared.subscription_middleware.get_dynamodb_resource",
                return_value=mock_resource,
            ):
                status = verify_subscription(user_id=user_id)

            assert status["valid"] is True
            assert status["tenant_id"] == "shared-tenant"
            assert status["queries_this_month"] == 1500
            assert status["queries_limit"] == 2000
