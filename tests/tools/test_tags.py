"""
Unit tests for Signup Tag tools.

Tools tested:
- list_signup_tags
- create_signup_tag
- tag_signup
- untag_signup
- list_signup_taggings
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_signup_tags,
    create_signup_tag,
    tag_signup,
    untag_signup,
    list_signup_taggings,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_SIGNUP_TAG,
)


class TestListSignupTags:
    """Tests for list_signup_tags tool."""

    def test_list_tags_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all tags."""
        patch_get_client.list.return_value = create_list_response(
            "signup_tags",
            [
                SAMPLE_SIGNUP_TAG,
                {"id": "tag-2", "name": "Donor"},
                {"id": "tag-3", "name": "Event Attendee"},
            ],
        )

        result = run_async(list_signup_tags({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 3
        patch_get_client.list.assert_called_once_with(
            "signup_tags",
            page_size=20,
            page_number=1,
        )

    def test_list_tags_with_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing tags with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "signup_tags",
            [SAMPLE_SIGNUP_TAG],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_signup_tags({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "signup_tags",
            page_size=10,
            page_number=2,
        )

    def test_list_tags_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing tags when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "signup_tags",
            [],
        )

        result = run_async(list_signup_tags({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_tags_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing tags handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_signup_tags({}))

        assert result["is_error"] is True


class TestCreateSignupTag:
    """Tests for create_signup_tag tool."""

    def test_create_tag_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating a new tag."""
        patch_get_client.create.return_value = create_single_response(
            "signup_tags",
            {"id": "new-tag", "name": "VIP"},
        )

        result = run_async(create_signup_tag({"name": "VIP"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["attributes"]["name"] == "VIP"
        patch_get_client.create.assert_called_once_with(
            "signup_tags",
            {"name": "VIP"},
        )

    def test_create_tag_duplicate(self, patch_get_client: AsyncMock) -> None:
        """Test creating a duplicate tag fails."""
        patch_get_client.create.side_effect = Exception("Tag already exists")

        result = run_async(create_signup_tag({"name": "Volunteer"}))

        assert result["is_error"] is True
        assert "already exists" in result["content"][0]["text"]


class TestTagSignup:
    """Tests for tag_signup tool."""

    def test_tag_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test adding a tag to a signup."""
        patch_get_client.create.return_value = create_single_response(
            "signup_taggings",
            {
                "id": "tagging-1",
                "signup_id": "12345",
                "signup_tag_id": "tag-1",
            },
        )

        result = run_async(tag_signup({
            "signup_id": "12345",
            "signup_tag_id": "tag-1",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.create.assert_called_once_with(
            "signup_taggings",
            {"signup_id": "12345", "signup_tag_id": "tag-1"},
        )

    def test_tag_signup_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test tagging non-existent signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(tag_signup({
            "signup_id": "99999",
            "signup_tag_id": "tag-1",
        }))

        assert result["is_error"] is True

    def test_tag_signup_invalid_tag(self, patch_get_client: AsyncMock) -> None:
        """Test tagging with non-existent tag fails."""
        patch_get_client.create.side_effect = Exception("Tag not found")

        result = run_async(tag_signup({
            "signup_id": "12345",
            "signup_tag_id": "invalid-tag",
        }))

        assert result["is_error"] is True


class TestUntagSignup:
    """Tests for untag_signup tool."""

    def test_untag_signup_success(self, patch_get_client: AsyncMock) -> None:
        """Test removing a tag from a signup."""
        patch_get_client.delete.return_value = True

        result = run_async(untag_signup({"tagging_id": "tagging-1"}))

        assert "Successfully removed" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with(
            "signup_taggings",
            "tagging-1",
        )

    def test_untag_signup_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test removing non-existent tagging fails."""
        patch_get_client.delete.side_effect = Exception("Tagging not found")

        result = run_async(untag_signup({"tagging_id": "invalid"}))

        assert result["is_error"] is True


class TestListSignupTaggings:
    """Tests for list_signup_taggings tool."""

    def test_list_taggings_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all taggings."""
        patch_get_client.list.return_value = create_list_response(
            "signup_taggings",
            [
                {"id": "tagging-1", "signup_id": "12345", "signup_tag_id": "tag-1"},
                {"id": "tagging-2", "signup_id": "12345", "signup_tag_id": "tag-2"},
            ],
        )

        result = run_async(list_signup_taggings({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_taggings_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing taggings for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "signup_taggings",
            [{"id": "tagging-1", "signup_id": "12345", "signup_tag_id": "tag-1"}],
        )

        result = run_async(list_signup_taggings({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "signup_taggings",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_taggings_by_tag(self, patch_get_client: AsyncMock) -> None:
        """Test listing taggings for a specific tag."""
        patch_get_client.list.return_value = create_list_response(
            "signup_taggings",
            [
                {"id": "tagging-1", "signup_id": "12345", "signup_tag_id": "tag-1"},
                {"id": "tagging-3", "signup_id": "12346", "signup_tag_id": "tag-1"},
            ],
        )

        result = run_async(list_signup_taggings({
            "filter": {"signup_tag_id": "tag-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "signup_taggings",
            filter={"signup_tag_id": "tag-1"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_taggings_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing taggings with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "signup_taggings",
            [{"id": "tagging-1", "signup_id": "12345", "signup_tag_id": "tag-1"}],
        )

        result = run_async(list_signup_taggings({
            "include": ["signup", "signup_tag"],
        }))

        patch_get_client.list.assert_called_once_with(
            "signup_taggings",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "signup_tag"],
        )

    def test_list_taggings_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing taggings handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_signup_taggings({}))

        assert result["is_error"] is True
