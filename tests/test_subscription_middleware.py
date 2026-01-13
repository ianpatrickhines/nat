"""
Unit tests for Subscription Verification Middleware
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.shared.subscription_middleware import (
    SubscriptionError,
    SubscriptionErrorCode,
    SubscriptionMiddleware,
    SubscriptionStatus,
    UserContext,
    extract_user_from_headers,
    get_tenant_subscription,
    get_user_tenant_id,
    verify_subscription,
)


# Test data
TEST_USER_ID = "user_test123"
TEST_TENANT_ID = "tenant_test456"
TEST_EMAIL = "test@example.com"


def create_mock_user(
    user_id: str = TEST_USER_ID,
    tenant_id: str = TEST_TENANT_ID,
    email: str = TEST_EMAIL,
) -> dict[str, Any]:
    """Create a mock user record."""
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": "admin",
        "nb_connected": False,
    }


def create_mock_tenant(
    tenant_id: str = TEST_TENANT_ID,
    status: str = "active",
    plan: str = "starter",
    queries_this_month: int = 0,
    queries_limit: int = 500,
) -> dict[str, Any]:
    """Create a mock tenant record."""
    return {
        "tenant_id": tenant_id,
        "stripe_customer_id": "cus_test123",
        "stripe_subscription_status": status,
        "plan": plan,
        "queries_this_month": queries_this_month,
        "queries_limit": queries_limit,
    }


class TestExtractUserFromHeaders:
    """Tests for extracting user identity from headers."""

    def test_extracts_user_id(self) -> None:
        """Test that user ID is extracted from headers."""
        headers = {"X-Nat-User-Id": TEST_USER_ID}
        result = extract_user_from_headers(headers)
        assert result.user_id == TEST_USER_ID
        assert result.tenant_id is None

    def test_extracts_tenant_id(self) -> None:
        """Test that optional tenant ID is extracted."""
        headers = {
            "X-Nat-User-Id": TEST_USER_ID,
            "X-Nat-Tenant-Id": TEST_TENANT_ID,
        }
        result = extract_user_from_headers(headers)
        assert result.user_id == TEST_USER_ID
        assert result.tenant_id == TEST_TENANT_ID

    def test_handles_lowercase_headers(self) -> None:
        """Test that lowercase headers are handled (API Gateway behavior)."""
        headers = {
            "x-nat-user-id": TEST_USER_ID,
            "x-nat-tenant-id": TEST_TENANT_ID,
        }
        result = extract_user_from_headers(headers)
        assert result.user_id == TEST_USER_ID
        assert result.tenant_id == TEST_TENANT_ID

    def test_missing_user_id_raises_error(self) -> None:
        """Test that missing user ID raises SubscriptionError."""
        with pytest.raises(SubscriptionError) as exc_info:
            extract_user_from_headers({})
        assert exc_info.value.code == SubscriptionErrorCode.MISSING_USER_ID
        assert exc_info.value.http_status == 401

    def test_empty_user_id_raises_error(self) -> None:
        """Test that empty user ID raises SubscriptionError."""
        with pytest.raises(SubscriptionError) as exc_info:
            extract_user_from_headers({"X-Nat-User-Id": ""})
        assert exc_info.value.code == SubscriptionErrorCode.MISSING_USER_ID


class TestGetUserTenantId:
    """Tests for looking up tenant ID from user."""

    @patch("src.lambdas.shared.subscription_middleware.get_dynamodb_resource")
    def test_returns_tenant_id(self, mock_dynamodb: MagicMock) -> None:
        """Test that tenant ID is returned for valid user."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": create_mock_user()}
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = get_user_tenant_id(TEST_USER_ID)
        assert result == TEST_TENANT_ID

    @patch("src.lambdas.shared.subscription_middleware.get_dynamodb_resource")
    def test_user_not_found_raises_error(self, mock_dynamodb: MagicMock) -> None:
        """Test that missing user raises SubscriptionError."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_dynamodb.return_value.Table.return_value = mock_table

        with pytest.raises(SubscriptionError) as exc_info:
            get_user_tenant_id("nonexistent_user")
        assert exc_info.value.code == SubscriptionErrorCode.USER_NOT_FOUND
        assert exc_info.value.http_status == 401

    @patch("src.lambdas.shared.subscription_middleware.get_dynamodb_resource")
    def test_user_without_tenant_raises_error(self, mock_dynamodb: MagicMock) -> None:
        """Test that user without tenant_id raises SubscriptionError."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"user_id": TEST_USER_ID}  # No tenant_id
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        with pytest.raises(SubscriptionError) as exc_info:
            get_user_tenant_id(TEST_USER_ID)
        assert exc_info.value.code == SubscriptionErrorCode.TENANT_NOT_FOUND


class TestGetTenantSubscription:
    """Tests for looking up tenant subscription."""

    @patch("src.lambdas.shared.subscription_middleware.get_dynamodb_resource")
    def test_returns_tenant(self, mock_dynamodb: MagicMock) -> None:
        """Test that tenant record is returned."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": create_mock_tenant()}
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = get_tenant_subscription(TEST_TENANT_ID)
        assert result["tenant_id"] == TEST_TENANT_ID
        assert result["stripe_subscription_status"] == "active"

    @patch("src.lambdas.shared.subscription_middleware.get_dynamodb_resource")
    def test_tenant_not_found_raises_error(self, mock_dynamodb: MagicMock) -> None:
        """Test that missing tenant raises SubscriptionError."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_dynamodb.return_value.Table.return_value = mock_table

        with pytest.raises(SubscriptionError) as exc_info:
            get_tenant_subscription("nonexistent_tenant")
        assert exc_info.value.code == SubscriptionErrorCode.TENANT_NOT_FOUND
        assert exc_info.value.http_status == 403


class TestVerifySubscription:
    """Tests for subscription verification."""

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_active_subscription_passes(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that active subscription returns valid status."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(status="active")

        result = verify_subscription(TEST_USER_ID)

        assert result["valid"] is True
        assert result["tenant_id"] == TEST_TENANT_ID
        assert result["subscription_status"] == "active"

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_trialing_subscription_passes(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that trialing subscription returns valid status."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(status="trialing")

        result = verify_subscription(TEST_USER_ID)

        assert result["valid"] is True
        assert result["subscription_status"] == "trialing"

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_cancelled_subscription_returns_402(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that cancelled subscription raises 402 error."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(status="cancelled")

        with pytest.raises(SubscriptionError) as exc_info:
            verify_subscription(TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_past_due_subscription_returns_402(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that past_due subscription raises 402 error."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(status="past_due")

        with pytest.raises(SubscriptionError) as exc_info:
            verify_subscription(TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_unpaid_subscription_returns_402(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that unpaid subscription raises 402 error."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(status="unpaid")

        with pytest.raises(SubscriptionError) as exc_info:
            verify_subscription(TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert exc_info.value.http_status == 402

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_query_limit_exceeded_returns_403(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that exceeding query limit raises 403 error."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(
            status="active",
            queries_this_month=500,
            queries_limit=500,
        )

        with pytest.raises(SubscriptionError) as exc_info:
            verify_subscription(TEST_USER_ID)

        assert exc_info.value.code == SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED
        assert exc_info.value.http_status == 403

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    @patch("src.lambdas.shared.subscription_middleware.get_user_tenant_id")
    def test_query_limit_not_exceeded_passes(
        self,
        mock_get_tenant_id: MagicMock,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that queries under limit pass."""
        mock_get_tenant_id.return_value = TEST_TENANT_ID
        mock_get_tenant.return_value = create_mock_tenant(
            status="active",
            queries_this_month=499,
            queries_limit=500,
        )

        result = verify_subscription(TEST_USER_ID)

        assert result["valid"] is True
        assert result["queries_this_month"] == 499
        assert result["queries_limit"] == 500

    @patch("src.lambdas.shared.subscription_middleware.get_tenant_subscription")
    def test_skips_user_lookup_when_tenant_id_provided(
        self,
        mock_get_tenant: MagicMock,
    ) -> None:
        """Test that tenant ID lookup is skipped when provided."""
        mock_get_tenant.return_value = create_mock_tenant(status="active")

        result = verify_subscription(TEST_USER_ID, tenant_id=TEST_TENANT_ID)

        assert result["valid"] is True
        # get_user_tenant_id should not be called
        mock_get_tenant.assert_called_once_with(TEST_TENANT_ID)


class TestSubscriptionMiddleware:
    """Tests for SubscriptionMiddleware class."""

    @patch("src.lambdas.shared.subscription_middleware.verify_subscription")
    def test_verify_extracts_headers_and_calls_verify(
        self,
        mock_verify: MagicMock,
    ) -> None:
        """Test that middleware extracts headers and verifies."""
        mock_verify.return_value = SubscriptionStatus(
            valid=True,
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            plan="starter",
            queries_this_month=0,
            queries_limit=500,
            subscription_status="active",
        )

        middleware = SubscriptionMiddleware()
        event = {
            "headers": {
                "X-Nat-User-Id": TEST_USER_ID,
                "X-Nat-Tenant-Id": TEST_TENANT_ID,
            }
        }

        result = middleware.verify(event)

        assert result["valid"] is True
        mock_verify.assert_called_once_with(
            user_id=TEST_USER_ID,
            tenant_id=TEST_TENANT_ID,
        )

    @patch("src.lambdas.shared.subscription_middleware.verify_subscription")
    def test_decorator_passes_subscription_status(
        self,
        mock_verify: MagicMock,
    ) -> None:
        """Test that decorator passes subscription status to handler."""
        mock_verify.return_value = SubscriptionStatus(
            valid=True,
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            plan="team",
            queries_this_month=10,
            queries_limit=2000,
            subscription_status="active",
        )

        @SubscriptionMiddleware()
        def handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: SubscriptionStatus,
        ) -> dict[str, Any]:
            return {
                "statusCode": 200,
                "body": json.dumps({"plan": subscription_status["plan"]}),
                "headers": {},
            }

        event = {"headers": {"X-Nat-User-Id": TEST_USER_ID}}
        result = handler(event, None)

        assert result["statusCode"] == 200
        assert json.loads(result["body"])["plan"] == "team"

    def test_decorator_returns_401_for_missing_user(self) -> None:
        """Test that decorator returns 401 for missing user ID."""

        @SubscriptionMiddleware()
        def handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: SubscriptionStatus,
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}", "headers": {}}

        event = {"headers": {}}
        result = handler(event, None)

        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "MISSING_USER_ID"

    @patch("src.lambdas.shared.subscription_middleware.verify_subscription")
    def test_decorator_returns_402_for_inactive_subscription(
        self,
        mock_verify: MagicMock,
    ) -> None:
        """Test that decorator returns 402 for inactive subscription."""
        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message="Subscription is not active",
            http_status=402,
        )

        @SubscriptionMiddleware()
        def handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: SubscriptionStatus,
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}", "headers": {}}

        event = {"headers": {"X-Nat-User-Id": TEST_USER_ID}}
        result = handler(event, None)

        assert result["statusCode"] == 402
        body = json.loads(result["body"])
        assert body["error"] == "SUBSCRIPTION_INACTIVE"

    @patch("src.lambdas.shared.subscription_middleware.verify_subscription")
    def test_decorator_returns_403_for_exceeded_limit(
        self,
        mock_verify: MagicMock,
    ) -> None:
        """Test that decorator returns 403 for exceeded query limit."""
        mock_verify.side_effect = SubscriptionError(
            code=SubscriptionErrorCode.QUERY_LIMIT_EXCEEDED,
            message="Query limit exceeded",
            http_status=403,
        )

        @SubscriptionMiddleware()
        def handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: SubscriptionStatus,
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}", "headers": {}}

        event = {"headers": {"X-Nat-User-Id": TEST_USER_ID}}
        result = handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert body["error"] == "QUERY_LIMIT_EXCEEDED"

    def test_handles_none_headers(self) -> None:
        """Test that middleware handles None headers gracefully."""

        @SubscriptionMiddleware()
        def handler(
            event: dict[str, Any],
            context: Any,
            subscription_status: SubscriptionStatus,
        ) -> dict[str, Any]:
            return {"statusCode": 200, "body": "{}", "headers": {}}

        event = {"headers": None}
        result = handler(event, None)

        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "MISSING_USER_ID"


class TestSubscriptionError:
    """Tests for SubscriptionError exception."""

    def test_error_attributes(self) -> None:
        """Test that SubscriptionError has correct attributes."""
        error = SubscriptionError(
            code=SubscriptionErrorCode.SUBSCRIPTION_INACTIVE,
            message="Test message",
            http_status=402,
        )

        assert error.code == SubscriptionErrorCode.SUBSCRIPTION_INACTIVE
        assert error.message == "Test message"
        assert error.http_status == 402
        assert str(error) == "Test message"

    def test_default_http_status(self) -> None:
        """Test that default HTTP status is 403."""
        error = SubscriptionError(
            code=SubscriptionErrorCode.TENANT_NOT_FOUND,
            message="Test",
        )
        assert error.http_status == 403
