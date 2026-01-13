"""
Unit tests for List tools.

Tools tested:
- list_lists
- get_list
- get_list_members
- add_to_list
- remove_from_list
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_lists,
    get_list,
    get_list_members,
    add_to_list,
    remove_from_list,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_LIST,
    SAMPLE_SIGNUP,
)


class TestListLists:
    """Tests for list_lists tool."""

    def test_list_lists_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all lists."""
        patch_get_client.list.return_value = create_list_response(
            "lists",
            [
                SAMPLE_LIST,
                {"id": "list-2", "name": "Major Donors"},
            ],
        )

        result = run_async(list_lists({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_lists_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing lists with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "lists",
            [SAMPLE_LIST],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_lists({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "lists",
            page_size=10,
            page_number=2,
        )

    def test_list_lists_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing lists when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "lists",
            [],
        )

        result = run_async(list_lists({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_lists_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing lists handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_lists({}))

        assert result["is_error"] is True


class TestGetList:
    """Tests for get_list tool."""

    def test_get_list_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single list."""
        patch_get_client.get.return_value = create_single_response(
            "lists",
            SAMPLE_LIST,
        )

        result = run_async(get_list({"id": "list-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "list-1"
        assert data["data"]["attributes"]["name"] == "Active Volunteers"

    def test_get_list_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent list."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_list({"id": "invalid"}))

        assert result["is_error"] is True


class TestGetListMembers:
    """Tests for get_list_members tool."""

    def test_get_members_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting list members."""
        patch_get_client.list_related.return_value = create_list_response(
            "signups",
            [
                SAMPLE_SIGNUP,
                {**SAMPLE_SIGNUP, "id": "12346", "email": "jane@example.com"},
            ],
        )

        result = run_async(get_list_members({"list_id": "list-1"}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2
        patch_get_client.list_related.assert_called_once_with(
            "lists",
            "list-1",
            "signups",
            page_size=20,
            page_number=1,
        )

    def test_get_members_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test getting list members with pagination."""
        patch_get_client.list_related.return_value = create_list_response(
            "signups",
            [SAMPLE_SIGNUP],
            total_pages=5,
            current_page=3,
        )

        result = run_async(get_list_members({
            "list_id": "list-1",
            "page_size": 50,
            "page_number": 3,
        }))

        patch_get_client.list_related.assert_called_once_with(
            "lists",
            "list-1",
            "signups",
            page_size=50,
            page_number=3,
        )

    def test_get_members_empty(self, patch_get_client: AsyncMock) -> None:
        """Test getting members from empty list."""
        patch_get_client.list_related.return_value = create_list_response(
            "signups",
            [],
        )

        result = run_async(get_list_members({"list_id": "list-1"}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_get_members_list_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting members from non-existent list."""
        patch_get_client.list_related.side_effect = Exception("List not found")

        result = run_async(get_list_members({"list_id": "invalid"}))

        assert result["is_error"] is True


class TestAddToList:
    """Tests for add_to_list tool."""

    def test_add_to_list_success(self, patch_get_client: AsyncMock) -> None:
        """Test adding a signup to a list."""
        patch_get_client.add_related.return_value = {"data": []}

        result = run_async(add_to_list({
            "list_id": "list-1",
            "signup_id": "12345",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.add_related.assert_called_once_with(
            "lists",
            "list-1",
            "signups",
            ["12345"],
        )

    def test_add_to_list_invalid_list(self, patch_get_client: AsyncMock) -> None:
        """Test adding to non-existent list fails."""
        patch_get_client.add_related.side_effect = Exception("List not found")

        result = run_async(add_to_list({
            "list_id": "invalid",
            "signup_id": "12345",
        }))

        assert result["is_error"] is True

    def test_add_to_list_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test adding non-existent signup fails."""
        patch_get_client.add_related.side_effect = Exception("Signup not found")

        result = run_async(add_to_list({
            "list_id": "list-1",
            "signup_id": "invalid",
        }))

        assert result["is_error"] is True


class TestRemoveFromList:
    """Tests for remove_from_list tool."""

    def test_remove_from_list_success(self, patch_get_client: AsyncMock) -> None:
        """Test removing a signup from a list."""
        patch_get_client.remove_related.return_value = True

        result = run_async(remove_from_list({
            "list_id": "list-1",
            "signup_id": "12345",
        }))

        assert "Successfully removed" in result["content"][0]["text"]
        patch_get_client.remove_related.assert_called_once_with(
            "lists",
            "list-1",
            "signups",
            ["12345"],
        )

    def test_remove_from_list_invalid_list(self, patch_get_client: AsyncMock) -> None:
        """Test removing from non-existent list fails."""
        patch_get_client.remove_related.side_effect = Exception("List not found")

        result = run_async(remove_from_list({
            "list_id": "invalid",
            "signup_id": "12345",
        }))

        assert result["is_error"] is True

    def test_remove_from_list_not_member(self, patch_get_client: AsyncMock) -> None:
        """Test removing signup that isn't a member."""
        patch_get_client.remove_related.side_effect = Exception("Signup not in list")

        result = run_async(remove_from_list({
            "list_id": "list-1",
            "signup_id": "99999",
        }))

        assert result["is_error"] is True
