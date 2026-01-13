"""
Unit tests for miscellaneous NB API tools.

Tools tested:
- list_custom_fields
- list_pledges
- create_pledge
- list_broadcasters
- get_broadcaster
- list_elections
- list_voters
- list_pages
- get_page
- list_donation_tracking_codes
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_custom_fields,
    list_pledges,
    create_pledge,
    list_broadcasters,
    get_broadcaster,
    list_elections,
    list_voters,
    list_pages,
    get_page,
    list_donation_tracking_codes,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_PLEDGE,
    SAMPLE_BROADCASTER,
    SAMPLE_ELECTION,
    SAMPLE_PAGE,
)


class TestListCustomFields:
    """Tests for list_custom_fields tool."""

    def test_list_custom_fields_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all custom fields."""
        patch_get_client.list.return_value = create_list_response(
            "custom_fields",
            [
                {"id": "field-1", "name": "T-Shirt Size"},
                {"id": "field-2", "name": "Preferred Contact Method"},
            ],
        )

        result = run_async(list_custom_fields({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_custom_fields_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing custom fields with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "custom_fields",
            [{"id": "field-1", "name": "T-Shirt Size"}],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_custom_fields({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "custom_fields",
            page_size=10,
            page_number=2,
        )

    def test_list_custom_fields_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing custom fields when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "custom_fields",
            [],
        )

        result = run_async(list_custom_fields({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_custom_fields_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing custom fields handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_custom_fields({}))

        assert result["is_error"] is True


class TestListPledges:
    """Tests for list_pledges tool."""

    def test_list_pledges_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all pledges."""
        patch_get_client.list.return_value = create_list_response(
            "pledges",
            [
                SAMPLE_PLEDGE,
                {**SAMPLE_PLEDGE, "id": "pledge-2", "amount_in_cents": 100000},
            ],
        )

        result = run_async(list_pledges({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_pledges_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing pledges for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "pledges",
            [SAMPLE_PLEDGE],
        )

        result = run_async(list_pledges({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "pledges",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_pledges_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing pledges with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "pledges",
            [SAMPLE_PLEDGE],
        )

        result = run_async(list_pledges({
            "include": ["signup"],
        }))

        patch_get_client.list.assert_called_once_with(
            "pledges",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup"],
        )

    def test_list_pledges_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing pledges handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_pledges({}))

        assert result["is_error"] is True


class TestCreatePledge:
    """Tests for create_pledge tool."""

    def test_create_pledge_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating a pledge."""
        patch_get_client.create.return_value = create_single_response(
            "pledges",
            SAMPLE_PLEDGE,
        )

        result = run_async(create_pledge({
            "signup_id": "12345",
            "amount_in_cents": 50000,
            "pledged_at": "2024-01-15T12:00:00Z",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_create_pledge_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test creating pledge for invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(create_pledge({
            "signup_id": "invalid",
            "amount_in_cents": 50000,
            "pledged_at": "2024-01-15T12:00:00Z",
        }))

        assert result["is_error"] is True


class TestListBroadcasters:
    """Tests for list_broadcasters tool."""

    def test_list_broadcasters_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all broadcasters."""
        patch_get_client.list.return_value = create_list_response(
            "broadcasters",
            [
                SAMPLE_BROADCASTER,
                {"id": "broadcaster-2", "name": "Event Updates"},
            ],
        )

        result = run_async(list_broadcasters({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_broadcasters_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing broadcasters with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "broadcasters",
            [SAMPLE_BROADCASTER],
        )

        result = run_async(list_broadcasters({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "broadcasters",
            page_size=10,
            page_number=2,
        )

    def test_list_broadcasters_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing broadcasters handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_broadcasters({}))

        assert result["is_error"] is True


class TestGetBroadcaster:
    """Tests for get_broadcaster tool."""

    def test_get_broadcaster_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single broadcaster."""
        patch_get_client.get.return_value = create_single_response(
            "broadcasters",
            SAMPLE_BROADCASTER,
        )

        result = run_async(get_broadcaster({"id": "broadcaster-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "broadcaster-1"

    def test_get_broadcaster_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent broadcaster."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_broadcaster({"id": "invalid"}))

        assert result["is_error"] is True


class TestListElections:
    """Tests for list_elections tool."""

    def test_list_elections_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all elections."""
        patch_get_client.list.return_value = create_list_response(
            "elections",
            [
                SAMPLE_ELECTION,
                {"id": "election-2", "name": "2024 Primary Election"},
            ],
        )

        result = run_async(list_elections({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_elections_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing elections with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "elections",
            [SAMPLE_ELECTION],
        )

        result = run_async(list_elections({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "elections",
            page_size=10,
            page_number=2,
        )

    def test_list_elections_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing elections handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_elections({}))

        assert result["is_error"] is True


class TestListVoters:
    """Tests for list_voters tool."""

    def test_list_voters_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing voters."""
        patch_get_client.list.return_value = create_list_response(
            "voters",
            [
                {"id": "voter-1", "signup_id": "12345"},
                {"id": "voter-2", "signup_id": "12346"},
            ],
        )

        result = run_async(list_voters({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_voters_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing voters with filter."""
        patch_get_client.list.return_value = create_list_response(
            "voters",
            [{"id": "voter-1", "signup_id": "12345"}],
        )

        result = run_async(list_voters({
            "filter": {"registered": "true"},
        }))

        patch_get_client.list.assert_called_once_with(
            "voters",
            filter={"registered": "true"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_voters_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing voters with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "voters",
            [{"id": "voter-1", "signup_id": "12345"}],
        )

        result = run_async(list_voters({
            "include": ["signup"],
        }))

        patch_get_client.list.assert_called_once_with(
            "voters",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup"],
        )

    def test_list_voters_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing voters handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_voters({}))

        assert result["is_error"] is True


class TestListPages:
    """Tests for list_pages tool."""

    def test_list_pages_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all pages."""
        patch_get_client.list.return_value = create_list_response(
            "pages",
            [
                SAMPLE_PAGE,
                {"id": "page-2", "name": "Volunteer Signup"},
            ],
        )

        result = run_async(list_pages({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_pages_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing pages with filter."""
        patch_get_client.list.return_value = create_list_response(
            "pages",
            [SAMPLE_PAGE],
        )

        result = run_async(list_pages({
            "filter": {"page_type": "donate"},
        }))

        patch_get_client.list.assert_called_once_with(
            "pages",
            filter={"page_type": "donate"},
            page_size=20,
            page_number=1,
        )

    def test_list_pages_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing pages with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "pages",
            [SAMPLE_PAGE],
        )

        result = run_async(list_pages({
            "page_size": 50,
            "page_number": 3,
        }))

        patch_get_client.list.assert_called_once_with(
            "pages",
            filter=None,
            page_size=50,
            page_number=3,
        )

    def test_list_pages_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing pages handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_pages({}))

        assert result["is_error"] is True


class TestGetPage:
    """Tests for get_page tool."""

    def test_get_page_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single page."""
        patch_get_client.get.return_value = create_single_response(
            "pages",
            SAMPLE_PAGE,
        )

        result = run_async(get_page({"id": "page-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "page-1"
        assert data["data"]["attributes"]["name"] == "Donate Now"

    def test_get_page_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent page."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_page({"id": "invalid"}))

        assert result["is_error"] is True


class TestListDonationTrackingCodes:
    """Tests for list_donation_tracking_codes tool."""

    def test_list_codes_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all donation tracking codes."""
        patch_get_client.list.return_value = create_list_response(
            "donation_tracking_codes",
            [
                {"id": "code-1", "name": "Website"},
                {"id": "code-2", "name": "Email Campaign"},
            ],
        )

        result = run_async(list_donation_tracking_codes({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_codes_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing codes with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "donation_tracking_codes",
            [{"id": "code-1", "name": "Website"}],
        )

        result = run_async(list_donation_tracking_codes({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "donation_tracking_codes",
            page_size=10,
            page_number=2,
        )

    def test_list_codes_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing codes when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "donation_tracking_codes",
            [],
        )

        result = run_async(list_donation_tracking_codes({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_codes_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing codes handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_donation_tracking_codes({}))

        assert result["is_error"] is True
