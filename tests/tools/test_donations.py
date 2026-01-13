"""
Unit tests for Donation tools.

Tools tested:
- list_donations
- get_donation
- create_donation
- update_donation
- delete_donation
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_donations,
    get_donation,
    create_donation,
    update_donation,
    delete_donation,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_DONATION,
)


class TestListDonations:
    """Tests for list_donations tool."""

    def test_list_donations_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations."""
        patch_get_client.list.return_value = create_list_response(
            "donations",
            [
                SAMPLE_DONATION,
                {**SAMPLE_DONATION, "id": "donation-2", "amount_in_cents": 25000},
            ],
        )

        result = run_async(list_donations({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_donations_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "donations",
            [SAMPLE_DONATION],
        )

        result = run_async(list_donations({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "donations",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
            sort=None,
        )

    def test_list_donations_with_sort(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations with sorting by amount."""
        patch_get_client.list.return_value = create_list_response(
            "donations",
            [SAMPLE_DONATION],
        )

        result = run_async(list_donations({
            "sort": "-amount_in_cents",
        }))

        patch_get_client.list.assert_called_once_with(
            "donations",
            filter=None,
            page_size=20,
            page_number=1,
            include=None,
            sort="-amount_in_cents",
        )

    def test_list_donations_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations with sideloaded signup."""
        patch_get_client.list.return_value = create_list_response(
            "donations",
            [SAMPLE_DONATION],
        )

        result = run_async(list_donations({
            "include": ["signup"],
        }))

        patch_get_client.list.assert_called_once_with(
            "donations",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup"],
            sort=None,
        )

    def test_list_donations_by_amount_range(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations filtered by amount."""
        patch_get_client.list.return_value = create_list_response(
            "donations",
            [SAMPLE_DONATION],
        )

        result = run_async(list_donations({
            "filter": {"amount_in_cents_gte": "5000"},
        }))

        assert "is_error" not in result or not result["is_error"]

    def test_list_donations_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing donations handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_donations({}))

        assert result["is_error"] is True


class TestGetDonation:
    """Tests for get_donation tool."""

    def test_get_donation_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single donation."""
        patch_get_client.get.return_value = create_single_response(
            "donations",
            SAMPLE_DONATION,
        )

        result = run_async(get_donation({"id": "donation-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "donation-1"
        assert data["data"]["attributes"]["amount_in_cents"] == 10000

    def test_get_donation_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting a donation with sideloaded data."""
        patch_get_client.get.return_value = create_single_response(
            "donations",
            SAMPLE_DONATION,
        )

        result = run_async(get_donation({
            "id": "donation-1",
            "include": ["signup", "donation_tracking_code"],
        }))

        patch_get_client.get.assert_called_once_with(
            "donations",
            "donation-1",
            include=["signup", "donation_tracking_code"],
        )

    def test_get_donation_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent donation."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_donation({"id": "invalid"}))

        assert result["is_error"] is True


class TestCreateDonation:
    """Tests for create_donation tool."""

    def test_create_donation_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating a donation."""
        patch_get_client.create.return_value = create_single_response(
            "donations",
            SAMPLE_DONATION,
        )

        result = run_async(create_donation({
            "signup_id": "12345",
            "amount_in_cents": 10000,
            "payment_type_name": "Credit Card",
            "succeeded_at": "2024-01-15T12:00:00Z",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_create_donation_with_tracking_code(self, patch_get_client: AsyncMock) -> None:
        """Test creating a donation with tracking code."""
        patch_get_client.create.return_value = create_single_response(
            "donations",
            {**SAMPLE_DONATION, "donation_tracking_code_id": "code-1"},
        )

        result = run_async(create_donation({
            "signup_id": "12345",
            "amount_in_cents": 10000,
            "payment_type_name": "Credit Card",
            "succeeded_at": "2024-01-15T12:00:00Z",
            "donation_tracking_code_id": "code-1",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["donation_tracking_code_id"] == "code-1"

    def test_create_donation_with_employer(self, patch_get_client: AsyncMock) -> None:
        """Test creating a donation with employer info."""
        patch_get_client.create.return_value = create_single_response(
            "donations",
            {**SAMPLE_DONATION, "employer": "Acme Corp", "occupation": "Engineer"},
        )

        result = run_async(create_donation({
            "signup_id": "12345",
            "amount_in_cents": 10000,
            "payment_type_name": "Check",
            "succeeded_at": "2024-01-15T12:00:00Z",
            "employer": "Acme Corp",
            "occupation": "Engineer",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["employer"] == "Acme Corp"
        assert call_args[0][1]["occupation"] == "Engineer"

    def test_create_donation_with_check(self, patch_get_client: AsyncMock) -> None:
        """Test creating a check donation."""
        patch_get_client.create.return_value = create_single_response(
            "donations",
            {**SAMPLE_DONATION, "payment_type_name": "Check", "check_number": "1234"},
        )

        result = run_async(create_donation({
            "signup_id": "12345",
            "amount_in_cents": 10000,
            "payment_type_name": "Check",
            "succeeded_at": "2024-01-15T12:00:00Z",
            "check_number": "1234",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["check_number"] == "1234"

    def test_create_donation_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test creating a donation with invalid signup."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(create_donation({
            "signup_id": "invalid",
            "amount_in_cents": 10000,
            "payment_type_name": "Credit Card",
            "succeeded_at": "2024-01-15T12:00:00Z",
        }))

        assert result["is_error"] is True


class TestUpdateDonation:
    """Tests for update_donation tool."""

    def test_update_donation_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating a donation."""
        patch_get_client.update.return_value = create_single_response(
            "donations",
            {**SAMPLE_DONATION, "note": "VIP donor"},
        )

        result = run_async(update_donation({
            "id": "donation-1",
            "note": "VIP donor",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "donations",
            "donation-1",
            {"note": "VIP donor"},
        )

    def test_update_donation_employer(self, patch_get_client: AsyncMock) -> None:
        """Test updating donation employer info."""
        patch_get_client.update.return_value = create_single_response(
            "donations",
            {**SAMPLE_DONATION, "employer": "New Corp"},
        )

        result = run_async(update_donation({
            "id": "donation-1",
            "employer": "New Corp",
            "occupation": "Manager",
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["employer"] == "New Corp"
        assert call_args[0][2]["occupation"] == "Manager"

    def test_update_donation_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent donation."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_donation({
            "id": "invalid",
            "note": "Test",
        }))

        assert result["is_error"] is True


class TestDeleteDonation:
    """Tests for delete_donation tool."""

    def test_delete_donation_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a donation."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_donation({"id": "donation-1"}))

        assert "Successfully deleted" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("donations", "donation-1")

    def test_delete_donation_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent donation."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_donation({"id": "invalid"}))

        assert result["is_error"] is True
