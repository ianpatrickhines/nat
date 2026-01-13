"""
Unit tests for Stripe Checkout Session Lambda Handler
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.stripe_checkout.handler import (
    STRIPE_PRICE_IDS,
    create_checkout_session,
    get_stripe_secret_key,
    handler,
)


# Test data
TEST_STRIPE_SECRET_KEY = "sk_test_12345"
TEST_SESSION_ID = "cs_test_session_123"
TEST_CHECKOUT_URL = "https://checkout.stripe.com/pay/cs_test_session_123"


class TestGetStripeSecretKey:
    """Tests for retrieving Stripe secret key from Secrets Manager."""

    @patch("src.lambdas.stripe_checkout.handler.boto3.client")
    def test_get_secret_plain_string(self, mock_boto_client: MagicMock) -> None:
        """Test retrieving secret stored as plain string."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": TEST_STRIPE_SECRET_KEY
        }

        result = get_stripe_secret_key()
        assert result == TEST_STRIPE_SECRET_KEY

    @patch("src.lambdas.stripe_checkout.handler.boto3.client")
    def test_get_secret_json_format(self, mock_boto_client: MagicMock) -> None:
        """Test retrieving secret stored as JSON."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": TEST_STRIPE_SECRET_KEY})
        }

        result = get_stripe_secret_key()
        assert result == TEST_STRIPE_SECRET_KEY

    @patch("src.lambdas.stripe_checkout.handler.boto3.client")
    def test_get_secret_error(self, mock_boto_client: MagicMock) -> None:
        """Test error handling when secret retrieval fails."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue",
        )

        with pytest.raises(ClientError):
            get_stripe_secret_key()


class TestCreateCheckoutSession:
    """Tests for creating Stripe Checkout sessions."""

    def test_create_session_starter_plan(self) -> None:
        """Test creating checkout session for starter plan."""
        import urllib3
        with patch.object(urllib3, "PoolManager") as mock_pool_manager:
            mock_http = MagicMock()
            mock_pool_manager.return_value = mock_http
            mock_http.request.return_value = MagicMock(
                status=200,
                data=json.dumps({
                    "id": TEST_SESSION_ID,
                    "url": TEST_CHECKOUT_URL,
                }).encode("utf-8"),
            )

            result = create_checkout_session("starter", TEST_STRIPE_SECRET_KEY)

            assert result["id"] == TEST_SESSION_ID
            assert result["url"] == TEST_CHECKOUT_URL

            # Verify API call
            mock_http.request.assert_called_once()
            call_args = mock_http.request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "https://api.stripe.com/v1/checkout/sessions"
            assert f"Bearer {TEST_STRIPE_SECRET_KEY}" in str(call_args[1]["headers"])

    def test_create_session_team_plan(self) -> None:
        """Test creating checkout session for team plan."""
        import urllib3
        with patch.object(urllib3, "PoolManager") as mock_pool_manager:
            mock_http = MagicMock()
            mock_pool_manager.return_value = mock_http
            mock_http.request.return_value = MagicMock(
                status=200,
                data=json.dumps({
                    "id": TEST_SESSION_ID,
                    "url": TEST_CHECKOUT_URL,
                }).encode("utf-8"),
            )

            result = create_checkout_session("team", TEST_STRIPE_SECRET_KEY)
            assert result["id"] == TEST_SESSION_ID

    def test_create_session_organization_plan(self) -> None:
        """Test creating checkout session for organization plan."""
        import urllib3
        with patch.object(urllib3, "PoolManager") as mock_pool_manager:
            mock_http = MagicMock()
            mock_pool_manager.return_value = mock_http
            mock_http.request.return_value = MagicMock(
                status=200,
                data=json.dumps({
                    "id": TEST_SESSION_ID,
                    "url": TEST_CHECKOUT_URL,
                }).encode("utf-8"),
            )

            result = create_checkout_session("organization", TEST_STRIPE_SECRET_KEY)
            assert result["id"] == TEST_SESSION_ID

    def test_create_session_invalid_plan(self) -> None:
        """Test that invalid plan raises ValueError."""
        with pytest.raises(ValueError, match="Invalid plan"):
            create_checkout_session("invalid_plan", TEST_STRIPE_SECRET_KEY)

    def test_create_session_stripe_error(self) -> None:
        """Test handling Stripe API errors."""
        import urllib3
        with patch.object(urllib3, "PoolManager") as mock_pool_manager:
            mock_http = MagicMock()
            mock_pool_manager.return_value = mock_http
            mock_http.request.return_value = MagicMock(
                status=400,
                data=json.dumps({
                    "error": {
                        "message": "Invalid price ID",
                        "type": "invalid_request_error",
                    }
                }).encode("utf-8"),
            )

            with pytest.raises(RuntimeError, match="Invalid price ID"):
                create_checkout_session("starter", TEST_STRIPE_SECRET_KEY)


class TestHandler:
    """Tests for the Lambda handler function."""

    @patch("src.lambdas.stripe_checkout.handler.create_checkout_session")
    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_successful_checkout_starter(
        self, mock_get_key: MagicMock, mock_create_session: MagicMock
    ) -> None:
        """Test successful checkout session creation for starter plan."""
        mock_get_key.return_value = TEST_STRIPE_SECRET_KEY
        mock_create_session.return_value = {
            "id": TEST_SESSION_ID,
            "url": TEST_CHECKOUT_URL,
        }

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "starter"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["checkout_url"] == TEST_CHECKOUT_URL
        assert body["session_id"] == TEST_SESSION_ID

    @patch("src.lambdas.stripe_checkout.handler.create_checkout_session")
    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_successful_checkout_team(
        self, mock_get_key: MagicMock, mock_create_session: MagicMock
    ) -> None:
        """Test successful checkout session creation for team plan."""
        mock_get_key.return_value = TEST_STRIPE_SECRET_KEY
        mock_create_session.return_value = {
            "id": TEST_SESSION_ID,
            "url": TEST_CHECKOUT_URL,
        }

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "team"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["checkout_url"] == TEST_CHECKOUT_URL

    @patch("src.lambdas.stripe_checkout.handler.create_checkout_session")
    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_successful_checkout_organization(
        self, mock_get_key: MagicMock, mock_create_session: MagicMock
    ) -> None:
        """Test successful checkout session creation for organization plan."""
        mock_get_key.return_value = TEST_STRIPE_SECRET_KEY
        mock_create_session.return_value = {
            "id": TEST_SESSION_ID,
            "url": TEST_CHECKOUT_URL,
        }

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "organization"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 200

    @patch("src.lambdas.stripe_checkout.handler.create_checkout_session")
    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_plan_case_insensitive(
        self, mock_get_key: MagicMock, mock_create_session: MagicMock
    ) -> None:
        """Test that plan names are case-insensitive."""
        mock_get_key.return_value = TEST_STRIPE_SECRET_KEY
        mock_create_session.return_value = {
            "id": TEST_SESSION_ID,
            "url": TEST_CHECKOUT_URL,
        }

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "STARTER"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 200
        mock_create_session.assert_called_once_with("starter", TEST_STRIPE_SECRET_KEY)

    def test_options_preflight(self) -> None:
        """Test OPTIONS preflight request handling."""
        event: dict[str, Any] = {
            "httpMethod": "OPTIONS",
        }

        response = handler(event, None)

        assert response["statusCode"] == 200
        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Methods"] == "POST, OPTIONS"

    def test_missing_plan(self) -> None:
        """Test error when plan is missing."""
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing required field: plan" in body["error"]

    def test_invalid_plan(self) -> None:
        """Test error when plan is invalid."""
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "enterprise"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid plan" in body["error"]

    def test_invalid_json_body(self) -> None:
        """Test error handling for invalid JSON body."""
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": "not valid json",
        }

        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid JSON" in body["error"]

    def test_empty_body(self) -> None:
        """Test handling of empty request body."""
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": "",
        }

        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing required field: plan" in body["error"]

    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_secrets_manager_error(self, mock_get_key: MagicMock) -> None:
        """Test handling of Secrets Manager errors."""
        from botocore.exceptions import ClientError

        mock_get_key.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue",
        )

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "starter"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Internal server error" in body["error"]

    @patch("src.lambdas.stripe_checkout.handler.create_checkout_session")
    @patch("src.lambdas.stripe_checkout.handler.get_stripe_secret_key")
    def test_stripe_api_error(
        self, mock_get_key: MagicMock, mock_create_session: MagicMock
    ) -> None:
        """Test handling of Stripe API errors."""
        mock_get_key.return_value = TEST_STRIPE_SECRET_KEY
        mock_create_session.side_effect = RuntimeError("Stripe API error: Invalid price")

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "starter"}),
        }

        response = handler(event, None)

        assert response["statusCode"] == 502
        body = json.loads(response["body"])
        assert "Stripe API error" in body["error"]

    def test_cors_headers_present(self) -> None:
        """Test that CORS headers are present in responses."""
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "body": json.dumps({"plan": "invalid"}),
        }

        response = handler(event, None)

        assert response["headers"]["Access-Control-Allow-Origin"] == "*"


class TestPriceConfiguration:
    """Tests for price configuration."""

    def test_all_plans_have_price_ids(self) -> None:
        """Test that all expected plans have price IDs configured."""
        expected_plans = ["starter", "team", "organization"]
        for plan in expected_plans:
            assert plan in STRIPE_PRICE_IDS, f"Missing price ID for plan: {plan}"

    def test_price_ids_are_strings(self) -> None:
        """Test that all price IDs are strings."""
        for plan, price_id in STRIPE_PRICE_IDS.items():
            assert isinstance(price_id, str), f"Price ID for {plan} is not a string"
            assert len(price_id) > 0, f"Price ID for {plan} is empty"
