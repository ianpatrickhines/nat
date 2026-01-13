"""
Unit tests for Usage Tracking Module
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.shared.usage_tracking import (
    RATE_LIMIT_COOLDOWN_SECONDS,
    RateLimitError,
    check_and_reset_billing_cycle,
    check_rate_limit,
    increment_query_count,
    track_query_usage,
    update_last_query_time,
)


# Test data
TEST_USER_ID = "user_test123"
TEST_TENANT_ID = "tenant_test456"


class TestCheckRateLimit:
    """Tests for rate limit checking."""

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_allows_request_when_cooldown_elapsed(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that request is allowed when cooldown has elapsed."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"last_query_at": 1000}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1000 + RATE_LIMIT_COOLDOWN_SECONDS + 1

        # Should not raise
        check_rate_limit(TEST_USER_ID)

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_blocks_request_during_cooldown(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that request is blocked during cooldown period."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"last_query_at": 1000}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1002  # Only 2 seconds elapsed

        with pytest.raises(RateLimitError) as exc_info:
            check_rate_limit(TEST_USER_ID)

        assert exc_info.value.retry_after == 3  # 5 - 2 = 3 seconds

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_allows_request_at_exact_cooldown(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that request is allowed exactly at cooldown boundary."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"last_query_at": 1000}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1000 + RATE_LIMIT_COOLDOWN_SECONDS

        # Should not raise - exactly at cooldown is allowed
        check_rate_limit(TEST_USER_ID)

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_allows_request_when_no_previous_query(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that request is allowed when user has no previous query."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {}  # No last_query_at
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        # Should not raise
        check_rate_limit(TEST_USER_ID)

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_allows_request_when_user_not_found(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that request is allowed when user doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamodb.return_value.Table.return_value = mock_table

        # Should not raise - fail open
        check_rate_limit(TEST_USER_ID)

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_handles_decimal_timestamp(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that Decimal timestamps from DynamoDB are handled."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"last_query_at": Decimal("1000")}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1002  # Only 2 seconds elapsed

        with pytest.raises(RateLimitError):
            check_rate_limit(TEST_USER_ID)


class TestUpdateLastQueryTime:
    """Tests for updating last query timestamp."""

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_updates_timestamp(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that timestamp is updated correctly."""
        mock_table = MagicMock()
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 12345

        update_last_query_time(TEST_USER_ID)

        mock_table.update_item.assert_called_once_with(
            Key={"user_id": TEST_USER_ID},
            UpdateExpression="SET last_query_at = :timestamp",
            ExpressionAttributeValues={":timestamp": 12345},
        )

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_handles_update_error_gracefully(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that update errors don't propagate."""
        from botocore.exceptions import ClientError

        mock_table = MagicMock()
        mock_table.update_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException"}},
            "UpdateItem"
        )
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 12345

        # Should not raise - non-fatal error
        update_last_query_time(TEST_USER_ID)


class TestIncrementQueryCount:
    """Tests for incrementing query count."""

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_increments_count(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that query count is incremented."""
        mock_table = MagicMock()
        mock_table.update_item.return_value = {
            "Attributes": {"queries_this_month": 42}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = increment_query_count(TEST_TENANT_ID)

        assert result == 42
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["Key"] == {"tenant_id": TEST_TENANT_ID}
        assert ":inc" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":inc"] == 1

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_handles_decimal_response(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that Decimal response is converted to int."""
        mock_table = MagicMock()
        mock_table.update_item.return_value = {
            "Attributes": {"queries_this_month": Decimal("100")}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = increment_query_count(TEST_TENANT_ID)

        assert result == 100
        assert isinstance(result, int)

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_initializes_from_zero(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that counter initializes to 1 if not exists."""
        mock_table = MagicMock()
        mock_table.update_item.return_value = {
            "Attributes": {"queries_this_month": 1}
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = increment_query_count(TEST_TENANT_ID)

        assert result == 1
        # Verify if_not_exists is used
        call_kwargs = mock_table.update_item.call_args.kwargs
        assert "if_not_exists" in call_kwargs["UpdateExpression"]


class TestCheckAndResetBillingCycle:
    """Tests for billing cycle reset checking."""

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_resets_when_past_billing_cycle_start(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that usage is reset when past billing cycle start."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "billing_cycle_start": 1000,
                "usage_reset_at": 500,  # Last reset was before current cycle
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1500  # Past billing cycle start

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is True
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":zero"] == 0

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_no_reset_when_already_reset(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that usage is not reset if already reset this cycle."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "billing_cycle_start": 1000,
                "usage_reset_at": 1200,  # Reset after cycle started
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1500

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is False
        mock_table.update_item.assert_not_called()

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_no_reset_when_before_billing_cycle(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that usage is not reset before billing cycle starts."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "billing_cycle_start": 2000,
                "usage_reset_at": 500,
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1500  # Before billing cycle start

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is False
        mock_table.update_item.assert_not_called()

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_no_reset_when_no_billing_cycle_start(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that no reset occurs when billing_cycle_start is not set."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {}  # No billing_cycle_start
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is False

    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_no_reset_when_tenant_not_found(
        self,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test that no reset occurs when tenant doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is False

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_handles_decimal_timestamps(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that Decimal timestamps from DynamoDB are handled."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "billing_cycle_start": Decimal("1000"),
                "usage_reset_at": Decimal("500"),
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1500

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is True

    @patch("src.lambdas.shared.usage_tracking.get_current_timestamp")
    @patch("src.lambdas.shared.usage_tracking.get_dynamodb_resource")
    def test_resets_when_usage_reset_at_is_none(
        self,
        mock_dynamodb: MagicMock,
        mock_timestamp: MagicMock,
    ) -> None:
        """Test that usage is reset when usage_reset_at is None."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "billing_cycle_start": 1000,
                # No usage_reset_at
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_timestamp.return_value = 1500

        result = check_and_reset_billing_cycle(TEST_TENANT_ID)

        assert result is True


class TestTrackQueryUsage:
    """Tests for the track_query_usage convenience function."""

    @patch("src.lambdas.shared.usage_tracking.increment_query_count")
    @patch("src.lambdas.shared.usage_tracking.update_last_query_time")
    def test_calls_both_functions(
        self,
        mock_update_time: MagicMock,
        mock_increment: MagicMock,
    ) -> None:
        """Test that track_query_usage calls both helper functions."""
        mock_increment.return_value = 42

        result = track_query_usage(TEST_USER_ID, TEST_TENANT_ID)

        assert result == 42
        mock_update_time.assert_called_once_with(TEST_USER_ID)
        mock_increment.assert_called_once_with(TEST_TENANT_ID)


class TestRateLimitError:
    """Tests for RateLimitError exception."""

    def test_error_attributes(self) -> None:
        """Test that RateLimitError has correct attributes."""
        error = RateLimitError(
            message="Rate limit exceeded",
            retry_after=3,
        )

        assert error.message == "Rate limit exceeded"
        assert error.retry_after == 3
        assert str(error) == "Rate limit exceeded"
