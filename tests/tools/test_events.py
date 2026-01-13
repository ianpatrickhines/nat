"""
Unit tests for Event tools.

Tools tested:
- list_events
- get_event
- create_event
- update_event
- delete_event
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_events,
    get_event,
    create_event,
    update_event,
    delete_event,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_EVENT,
)


class TestListEvents:
    """Tests for list_events tool."""

    def test_list_events_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing events."""
        patch_get_client.list.return_value = create_list_response(
            "events",
            [
                SAMPLE_EVENT,
                {**SAMPLE_EVENT, "id": "event-2", "name": "Fundraiser Gala"},
            ],
        )

        result = run_async(list_events({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_events_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing events with status filter."""
        patch_get_client.list.return_value = create_list_response(
            "events",
            [SAMPLE_EVENT],
        )

        result = run_async(list_events({
            "filter": {"status": "published"},
        }))

        patch_get_client.list.assert_called_once_with(
            "events",
            filter={"status": "published"},
            page_size=20,
            page_number=1,
            include=None,
            sort=None,
        )

    def test_list_events_with_sort(self, patch_get_client: AsyncMock) -> None:
        """Test listing events with sorting by start_time."""
        patch_get_client.list.return_value = create_list_response(
            "events",
            [SAMPLE_EVENT],
        )

        result = run_async(list_events({
            "sort": "start_time",
        }))

        patch_get_client.list.assert_called_once_with(
            "events",
            filter=None,
            page_size=20,
            page_number=1,
            include=None,
            sort="start_time",
        )

    def test_list_events_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing events with sideloaded RSVPs."""
        patch_get_client.list.return_value = create_list_response(
            "events",
            [SAMPLE_EVENT],
        )

        result = run_async(list_events({
            "include": ["event_rsvps"],
        }))

        patch_get_client.list.assert_called_once_with(
            "events",
            filter=None,
            page_size=20,
            page_number=1,
            include=["event_rsvps"],
            sort=None,
        )

    def test_list_events_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing events with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "events",
            [SAMPLE_EVENT],
            total_pages=5,
            current_page=3,
        )

        result = run_async(list_events({
            "page_size": 10,
            "page_number": 3,
        }))

        patch_get_client.list.assert_called_once_with(
            "events",
            filter=None,
            page_size=10,
            page_number=3,
            include=None,
            sort=None,
        )

    def test_list_events_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing events handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_events({}))

        assert result["is_error"] is True


class TestGetEvent:
    """Tests for get_event tool."""

    def test_get_event_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single event."""
        patch_get_client.get.return_value = create_single_response(
            "events",
            SAMPLE_EVENT,
        )

        result = run_async(get_event({"id": "event-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "event-1"
        assert data["data"]["attributes"]["name"] == "Campaign Rally"

    def test_get_event_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting an event with sideloaded RSVPs."""
        patch_get_client.get.return_value = create_single_response(
            "events",
            SAMPLE_EVENT,
        )

        result = run_async(get_event({
            "id": "event-1",
            "include": ["event_rsvps"],
        }))

        patch_get_client.get.assert_called_once_with(
            "events",
            "event-1",
            include=["event_rsvps"],
        )

    def test_get_event_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent event."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_event({"id": "invalid"}))

        assert result["is_error"] is True


class TestCreateEvent:
    """Tests for create_event tool."""

    def test_create_event_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating an event."""
        patch_get_client.create.return_value = create_single_response(
            "events",
            SAMPLE_EVENT,
        )

        result = run_async(create_event({
            "name": "Campaign Rally",
            "status": "published",
            "start_time": "2024-03-01T18:00:00Z",
            "end_time": "2024-03-01T21:00:00Z",
            "venue_name": "Community Center",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_create_event_with_capacity(self, patch_get_client: AsyncMock) -> None:
        """Test creating an event with capacity."""
        patch_get_client.create.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "capacity": 100},
        )

        result = run_async(create_event({
            "name": "Town Hall",
            "status": "published",
            "start_time": "2024-03-01T18:00:00Z",
            "end_time": "2024-03-01T21:00:00Z",
            "capacity": 100,
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["capacity"] == 100

    def test_create_event_with_venue(self, patch_get_client: AsyncMock) -> None:
        """Test creating an event with full venue details."""
        patch_get_client.create.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "venue_address": "123 Main St"},
        )

        result = run_async(create_event({
            "name": "Fundraiser",
            "status": "draft",
            "start_time": "2024-03-01T18:00:00Z",
            "end_time": "2024-03-01T21:00:00Z",
            "venue_name": "Grand Ballroom",
            "venue_address": "123 Main St",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["venue_address"] == "123 Main St"

    def test_create_event_with_contact(self, patch_get_client: AsyncMock) -> None:
        """Test creating an event with contact email."""
        patch_get_client.create.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "contact_email": "events@example.com"},
        )

        result = run_async(create_event({
            "name": "Volunteer Meetup",
            "status": "published",
            "start_time": "2024-03-01T18:00:00Z",
            "end_time": "2024-03-01T21:00:00Z",
            "contact_email": "events@example.com",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["contact_email"] == "events@example.com"

    def test_create_event_error(self, patch_get_client: AsyncMock) -> None:
        """Test create event handles validation errors."""
        patch_get_client.create.side_effect = Exception("Invalid time format")

        result = run_async(create_event({
            "name": "Test Event",
            "status": "published",
            "start_time": "invalid",
            "end_time": "invalid",
        }))

        assert result["is_error"] is True


class TestUpdateEvent:
    """Tests for update_event tool."""

    def test_update_event_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating an event."""
        patch_get_client.update.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "name": "Updated Rally Name"},
        )

        result = run_async(update_event({
            "id": "event-1",
            "name": "Updated Rally Name",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "events",
            "event-1",
            {"name": "Updated Rally Name"},
        )

    def test_update_event_status(self, patch_get_client: AsyncMock) -> None:
        """Test updating event status."""
        patch_get_client.update.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "status": "cancelled"},
        )

        result = run_async(update_event({
            "id": "event-1",
            "status": "cancelled",
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["status"] == "cancelled"

    def test_update_event_time(self, patch_get_client: AsyncMock) -> None:
        """Test updating event times."""
        patch_get_client.update.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "start_time": "2024-03-02T18:00:00Z"},
        )

        result = run_async(update_event({
            "id": "event-1",
            "start_time": "2024-03-02T18:00:00Z",
            "end_time": "2024-03-02T21:00:00Z",
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["start_time"] == "2024-03-02T18:00:00Z"

    def test_update_event_capacity(self, patch_get_client: AsyncMock) -> None:
        """Test updating event capacity."""
        patch_get_client.update.return_value = create_single_response(
            "events",
            {**SAMPLE_EVENT, "capacity": 200},
        )

        result = run_async(update_event({
            "id": "event-1",
            "capacity": 200,
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["capacity"] == 200

    def test_update_event_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent event."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_event({
            "id": "invalid",
            "name": "Test",
        }))

        assert result["is_error"] is True


class TestDeleteEvent:
    """Tests for delete_event tool."""

    def test_delete_event_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting an event."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_event({"id": "event-1"}))

        assert "Successfully deleted" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("events", "event-1")

    def test_delete_event_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent event."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_event({"id": "invalid"}))

        assert result["is_error"] is True
