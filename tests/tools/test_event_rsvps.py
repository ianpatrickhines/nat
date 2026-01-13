"""
Unit tests for Event RSVP tools.

Tools tested:
- list_event_rsvps
- create_event_rsvp
- update_event_rsvp
- delete_event_rsvp
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_event_rsvps,
    create_event_rsvp,
    update_event_rsvp,
    delete_event_rsvp,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_EVENT_RSVP,
)


class TestListEventRsvps:
    """Tests for list_event_rsvps tool."""

    def test_list_rsvps_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all RSVPs."""
        patch_get_client.list.return_value = create_list_response(
            "event_rsvps",
            [
                SAMPLE_EVENT_RSVP,
                {**SAMPLE_EVENT_RSVP, "id": "rsvp-2", "signup_id": "12346"},
            ],
        )

        result = run_async(list_event_rsvps({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_rsvps_by_event(self, patch_get_client: AsyncMock) -> None:
        """Test listing RSVPs for a specific event."""
        patch_get_client.list.return_value = create_list_response(
            "event_rsvps",
            [SAMPLE_EVENT_RSVP],
        )

        result = run_async(list_event_rsvps({
            "filter": {"event_id": "event-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "event_rsvps",
            filter={"event_id": "event-1"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_rsvps_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing RSVPs for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "event_rsvps",
            [SAMPLE_EVENT_RSVP],
        )

        result = run_async(list_event_rsvps({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "event_rsvps",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_rsvps_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing RSVPs with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "event_rsvps",
            [SAMPLE_EVENT_RSVP],
        )

        result = run_async(list_event_rsvps({
            "include": ["signup", "event"],
        }))

        patch_get_client.list.assert_called_once_with(
            "event_rsvps",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "event"],
        )

    def test_list_rsvps_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing RSVPs with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "event_rsvps",
            [SAMPLE_EVENT_RSVP],
            total_pages=5,
            current_page=2,
        )

        result = run_async(list_event_rsvps({
            "page_size": 50,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "event_rsvps",
            filter=None,
            page_size=50,
            page_number=2,
            include=None,
        )

    def test_list_rsvps_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing RSVPs handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_event_rsvps({}))

        assert result["is_error"] is True


class TestCreateEventRsvp:
    """Tests for create_event_rsvp tool."""

    def test_create_rsvp_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating an RSVP."""
        patch_get_client.create.return_value = create_single_response(
            "event_rsvps",
            SAMPLE_EVENT_RSVP,
        )

        result = run_async(create_event_rsvp({
            "event_id": "event-1",
            "signup_id": "12345",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_create_rsvp_with_guests(self, patch_get_client: AsyncMock) -> None:
        """Test creating an RSVP with guests."""
        patch_get_client.create.return_value = create_single_response(
            "event_rsvps",
            {**SAMPLE_EVENT_RSVP, "guests_count": 3},
        )

        result = run_async(create_event_rsvp({
            "event_id": "event-1",
            "signup_id": "12345",
            "guests_count": 3,
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["guests_count"] == 3

    def test_create_rsvp_canceled(self, patch_get_client: AsyncMock) -> None:
        """Test creating a canceled RSVP."""
        patch_get_client.create.return_value = create_single_response(
            "event_rsvps",
            {**SAMPLE_EVENT_RSVP, "canceled": True},
        )

        result = run_async(create_event_rsvp({
            "event_id": "event-1",
            "signup_id": "12345",
            "canceled": True,
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["canceled"] is True

    def test_create_rsvp_invalid_event(self, patch_get_client: AsyncMock) -> None:
        """Test creating an RSVP for invalid event."""
        patch_get_client.create.side_effect = Exception("Event not found")

        result = run_async(create_event_rsvp({
            "event_id": "invalid",
            "signup_id": "12345",
        }))

        assert result["is_error"] is True

    def test_create_rsvp_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test creating an RSVP for invalid signup."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(create_event_rsvp({
            "event_id": "event-1",
            "signup_id": "invalid",
        }))

        assert result["is_error"] is True


class TestUpdateEventRsvp:
    """Tests for update_event_rsvp tool."""

    def test_update_rsvp_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating an RSVP."""
        patch_get_client.update.return_value = create_single_response(
            "event_rsvps",
            {**SAMPLE_EVENT_RSVP, "guests_count": 5},
        )

        result = run_async(update_event_rsvp({
            "id": "rsvp-1",
            "guests_count": 5,
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "event_rsvps",
            "rsvp-1",
            {"guests_count": 5},
        )

    def test_update_rsvp_cancel(self, patch_get_client: AsyncMock) -> None:
        """Test canceling an RSVP."""
        patch_get_client.update.return_value = create_single_response(
            "event_rsvps",
            {**SAMPLE_EVENT_RSVP, "canceled": True},
        )

        result = run_async(update_event_rsvp({
            "id": "rsvp-1",
            "canceled": True,
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["canceled"] is True

    def test_update_rsvp_attended(self, patch_get_client: AsyncMock) -> None:
        """Test marking an RSVP as attended."""
        patch_get_client.update.return_value = create_single_response(
            "event_rsvps",
            {**SAMPLE_EVENT_RSVP, "attended": True},
        )

        result = run_async(update_event_rsvp({
            "id": "rsvp-1",
            "attended": True,
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["attended"] is True

    def test_update_rsvp_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent RSVP."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_event_rsvp({
            "id": "invalid",
            "guests_count": 3,
        }))

        assert result["is_error"] is True


class TestDeleteEventRsvp:
    """Tests for delete_event_rsvp tool."""

    def test_delete_rsvp_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting an RSVP."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_event_rsvp({"id": "rsvp-1"}))

        assert "Successfully deleted" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("event_rsvps", "rsvp-1")

    def test_delete_rsvp_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent RSVP."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_event_rsvp({"id": "invalid"}))

        assert result["is_error"] is True
