"""
Unit tests for Signup (People) tools.

Tools tested:
- list_signups
- get_signup
- create_signup
- update_signup
- delete_signup
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_signups,
    get_signup,
    create_signup,
    update_signup,
    delete_signup,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_SIGNUP,
)


class TestListSignups:
    """Tests for list_signups tool."""

    def test_list_signups_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups with default pagination."""
        patch_get_client.list.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP, {**SAMPLE_SIGNUP, "id": "12346", "email": "jane@example.com"}],
        )

        result = run_async(list_signups({}))

        assert "content" in result
        assert result["content"][0]["type"] == "text"
        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2
        patch_get_client.list.assert_called_once_with(
            "signups",
            filter=None,
            page_size=20,
            page_number=1,
            include=None,
            sort=None,
        )

    def test_list_signups_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups with email filter."""
        patch_get_client.list.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP],
        )

        result = run_async(list_signups({
            "filter": {"email": "john@example.com"},
        }))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 1
        patch_get_client.list.assert_called_once_with(
            "signups",
            filter={"email": "john@example.com"},
            page_size=20,
            page_number=1,
            include=None,
            sort=None,
        )

    def test_list_signups_with_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups with custom pagination."""
        patch_get_client.list.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP],
            total_pages=5,
            current_page=2,
        )

        result = run_async(list_signups({
            "page_size": 50,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "signups",
            filter=None,
            page_size=50,
            page_number=2,
            include=None,
            sort=None,
        )

    def test_list_signups_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups with sideloaded relationships."""
        patch_get_client.list.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP],
        )

        result = run_async(list_signups({
            "include": ["donations", "signup_tags"],
        }))

        patch_get_client.list.assert_called_once_with(
            "signups",
            filter=None,
            page_size=20,
            page_number=1,
            include=["donations", "signup_tags"],
            sort=None,
        )

    def test_list_signups_with_sort(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups with sorting."""
        patch_get_client.list.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP],
        )

        result = run_async(list_signups({
            "sort": "-created_at",
        }))

        patch_get_client.list.assert_called_once_with(
            "signups",
            filter=None,
            page_size=20,
            page_number=1,
            include=None,
            sort="-created_at",
        )

    def test_list_signups_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing signups handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_signups({}))

        assert result["is_error"] is True
        assert "Error: API Error" in result["content"][0]["text"]


class TestGetSignup:
    """Tests for get_signup tool."""

    def test_get_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single signup."""
        patch_get_client.get.return_value = create_single_response(
            "signups",
            SAMPLE_SIGNUP,
        )

        result = run_async(get_signup({"id": "12345"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "12345"
        patch_get_client.get.assert_called_once_with(
            "signups",
            "12345",
            include=None,
        )

    def test_get_signup_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting a signup with sideloaded data."""
        patch_get_client.get.return_value = create_single_response(
            "signups",
            SAMPLE_SIGNUP,
        )

        result = run_async(get_signup({
            "id": "12345",
            "include": ["donations", "contacts"],
        }))

        patch_get_client.get.assert_called_once_with(
            "signups",
            "12345",
            include=["donations", "contacts"],
        )

    def test_get_signup_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent signup."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_signup({"id": "99999"}))

        assert result["is_error"] is True
        assert "Not Found" in result["content"][0]["text"]


class TestCreateSignup:
    """Tests for create_signup tool."""

    def test_create_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating a new signup."""
        new_signup = {**SAMPLE_SIGNUP, "id": "new-1"}
        patch_get_client.create.return_value = create_single_response(
            "signups",
            new_signup,
        )

        result = run_async(create_signup({
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "Person",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.create.assert_called_once_with(
            "signups",
            {
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "Person",
            },
        )

    def test_create_signup_minimal(self, patch_get_client: AsyncMock) -> None:
        """Test creating a signup with minimal data."""
        patch_get_client.create.return_value = create_single_response(
            "signups",
            {"id": "new-1", "email": "minimal@example.com"},
        )

        result = run_async(create_signup({
            "email": "minimal@example.com",
        }))

        assert "is_error" not in result or not result["is_error"]

    def test_create_signup_with_volunteer_flag(self, patch_get_client: AsyncMock) -> None:
        """Test creating a volunteer signup."""
        patch_get_client.create.return_value = create_single_response(
            "signups",
            {"id": "new-1", "is_volunteer": True},
        )

        result = run_async(create_signup({
            "email": "volunteer@example.com",
            "first_name": "Volunteer",
            "is_volunteer": True,
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["is_volunteer"] is True

    def test_create_signup_error(self, patch_get_client: AsyncMock) -> None:
        """Test create signup handles validation error."""
        patch_get_client.create.side_effect = Exception("Validation failed: email required")

        result = run_async(create_signup({}))

        assert result["is_error"] is True
        assert "Validation failed" in result["content"][0]["text"]


class TestUpdateSignup:
    """Tests for update_signup tool."""

    def test_update_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating a signup."""
        updated = {**SAMPLE_SIGNUP, "first_name": "Johnny"}
        patch_get_client.update.return_value = create_single_response(
            "signups",
            updated,
        )

        result = run_async(update_signup({
            "id": "12345",
            "first_name": "Johnny",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "signups",
            "12345",
            {"first_name": "Johnny"},
        )

    def test_update_signup_multiple_fields(self, patch_get_client: AsyncMock) -> None:
        """Test updating multiple fields."""
        patch_get_client.update.return_value = create_single_response(
            "signups",
            SAMPLE_SIGNUP,
        )

        result = run_async(update_signup({
            "id": "12345",
            "first_name": "Johnny",
            "is_volunteer": False,
            "email_opt_in": False,
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["first_name"] == "Johnny"
        assert call_args[0][2]["is_volunteer"] is False

    def test_update_signup_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent signup."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_signup({
            "id": "99999",
            "first_name": "Nobody",
        }))

        assert result["is_error"] is True


class TestDeleteSignup:
    """Tests for delete_signup tool."""

    def test_delete_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a signup."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_signup({"id": "12345"}))

        assert "Successfully deleted" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("signups", "12345")

    def test_delete_signup_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent signup."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_signup({"id": "99999"}))

        assert result["is_error"] is True
        assert "Not Found" in result["content"][0]["text"]
