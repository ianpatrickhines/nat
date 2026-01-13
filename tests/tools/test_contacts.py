"""
Unit tests for Contact (Interaction Log) tools.

Tools tested:
- log_contact
- list_contacts
- get_contact
- update_contact
- delete_contact
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    log_contact,
    list_contacts,
    get_contact,
    update_contact,
    delete_contact,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_CONTACT,
)


class TestLogContact:
    """Tests for log_contact tool."""

    def test_log_contact_success(self, patch_get_client: AsyncMock) -> None:
        """Test logging a new contact."""
        patch_get_client.create.return_value = create_single_response(
            "contacts",
            SAMPLE_CONTACT,
        )

        result = run_async(log_contact({
            "signup_id": "12345",
            "author_id": "admin-1",
            "contact_method": "phone",
            "contact_status": "completed",
            "content": "Discussed volunteer opportunities",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.create.assert_called_once()

    def test_log_contact_phone_call(self, patch_get_client: AsyncMock) -> None:
        """Test logging a phone call contact."""
        patch_get_client.create.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "contact_method": "phone_call"},
        )

        result = run_async(log_contact({
            "signup_id": "12345",
            "author_id": "admin-1",
            "contact_method": "phone_call",
            "contact_status": "completed",
            "content": "Left voicemail",
        }))

        assert "is_error" not in result or not result["is_error"]

    def test_log_contact_email(self, patch_get_client: AsyncMock) -> None:
        """Test logging an email contact."""
        patch_get_client.create.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "contact_method": "email"},
        )

        result = run_async(log_contact({
            "signup_id": "12345",
            "author_id": "admin-1",
            "contact_method": "email",
            "contact_status": "sent",
            "content": "Sent follow-up email",
        }))

        assert "is_error" not in result or not result["is_error"]

    def test_log_contact_door_knock(self, patch_get_client: AsyncMock) -> None:
        """Test logging a door knock contact."""
        patch_get_client.create.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "contact_method": "door_knock"},
        )

        result = run_async(log_contact({
            "signup_id": "12345",
            "author_id": "admin-1",
            "contact_method": "door_knock",
            "contact_status": "not_home",
        }))

        assert "is_error" not in result or not result["is_error"]

    def test_log_contact_with_path(self, patch_get_client: AsyncMock) -> None:
        """Test logging a contact with path context."""
        patch_get_client.create.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "path_id": "path-1", "path_step_id": "step-1"},
        )

        result = run_async(log_contact({
            "signup_id": "12345",
            "author_id": "admin-1",
            "contact_method": "phone",
            "contact_status": "completed",
            "content": "Path follow-up",
            "path_id": "path-1",
            "path_step_id": "step-1",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["path_id"] == "path-1"

    def test_log_contact_error(self, patch_get_client: AsyncMock) -> None:
        """Test log contact handles errors."""
        patch_get_client.create.side_effect = Exception("Invalid signup_id")

        result = run_async(log_contact({
            "signup_id": "invalid",
            "author_id": "admin-1",
            "contact_method": "phone",
            "contact_status": "completed",
        }))

        assert result["is_error"] is True


class TestListContacts:
    """Tests for list_contacts tool."""

    def test_list_contacts_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all contacts."""
        patch_get_client.list.return_value = create_list_response(
            "contacts",
            [
                SAMPLE_CONTACT,
                {**SAMPLE_CONTACT, "id": "contact-2", "contact_method": "email"},
            ],
        )

        result = run_async(list_contacts({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_contacts_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing contacts for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "contacts",
            [SAMPLE_CONTACT],
        )

        result = run_async(list_contacts({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "contacts",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_contacts_by_author(self, patch_get_client: AsyncMock) -> None:
        """Test listing contacts by author."""
        patch_get_client.list.return_value = create_list_response(
            "contacts",
            [SAMPLE_CONTACT],
        )

        result = run_async(list_contacts({
            "filter": {"author_id": "admin-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "contacts",
            filter={"author_id": "admin-1"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_contacts_by_method(self, patch_get_client: AsyncMock) -> None:
        """Test listing contacts by contact method."""
        patch_get_client.list.return_value = create_list_response(
            "contacts",
            [SAMPLE_CONTACT],
        )

        result = run_async(list_contacts({
            "filter": {"contact_method": "phone"},
        }))

        patch_get_client.list.assert_called_once_with(
            "contacts",
            filter={"contact_method": "phone"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_contacts_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing contacts with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "contacts",
            [SAMPLE_CONTACT],
        )

        result = run_async(list_contacts({
            "include": ["signup", "author"],
        }))

        patch_get_client.list.assert_called_once_with(
            "contacts",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "author"],
        )

    def test_list_contacts_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing contacts handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_contacts({}))

        assert result["is_error"] is True


class TestGetContact:
    """Tests for get_contact tool."""

    def test_get_contact_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single contact."""
        patch_get_client.get.return_value = create_single_response(
            "contacts",
            SAMPLE_CONTACT,
        )

        result = run_async(get_contact({"id": "contact-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "contact-1"

    def test_get_contact_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting a contact with sideloaded data."""
        patch_get_client.get.return_value = create_single_response(
            "contacts",
            SAMPLE_CONTACT,
        )

        result = run_async(get_contact({
            "id": "contact-1",
            "include": ["signup"],
        }))

        patch_get_client.get.assert_called_once_with(
            "contacts",
            "contact-1",
            include=["signup"],
        )

    def test_get_contact_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent contact."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_contact({"id": "invalid"}))

        assert result["is_error"] is True


class TestUpdateContact:
    """Tests for update_contact tool."""

    def test_update_contact_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating a contact."""
        patch_get_client.update.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "content": "Updated content"},
        )

        result = run_async(update_contact({
            "id": "contact-1",
            "content": "Updated content",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "contacts",
            "contact-1",
            {"content": "Updated content"},
        )

    def test_update_contact_status(self, patch_get_client: AsyncMock) -> None:
        """Test updating a contact status."""
        patch_get_client.update.return_value = create_single_response(
            "contacts",
            {**SAMPLE_CONTACT, "contact_status": "needs_follow_up"},
        )

        result = run_async(update_contact({
            "id": "contact-1",
            "contact_status": "needs_follow_up",
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["contact_status"] == "needs_follow_up"

    def test_update_contact_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent contact."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_contact({
            "id": "invalid",
            "content": "New content",
        }))

        assert result["is_error"] is True


class TestDeleteContact:
    """Tests for delete_contact tool."""

    def test_delete_contact_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a contact."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_contact({"id": "contact-1"}))

        assert "Successfully deleted" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("contacts", "contact-1")

    def test_delete_contact_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent contact."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_contact({"id": "invalid"}))

        assert result["is_error"] is True
