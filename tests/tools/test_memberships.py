"""
Unit tests for Membership tools.

Tools tested:
- list_memberships
- create_membership
- list_membership_types
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_memberships,
    create_membership,
    list_membership_types,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_MEMBERSHIP,
)


class TestListMemberships:
    """Tests for list_memberships tool."""

    def test_list_memberships_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all memberships."""
        patch_get_client.list.return_value = create_list_response(
            "memberships",
            [
                SAMPLE_MEMBERSHIP,
                {**SAMPLE_MEMBERSHIP, "id": "membership-2", "signup_id": "12346"},
            ],
        )

        result = run_async(list_memberships({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_memberships_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing memberships for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "memberships",
            [SAMPLE_MEMBERSHIP],
        )

        result = run_async(list_memberships({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "memberships",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_memberships_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing memberships with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "memberships",
            [SAMPLE_MEMBERSHIP],
        )

        result = run_async(list_memberships({
            "include": ["signup", "membership_type"],
        }))

        patch_get_client.list.assert_called_once_with(
            "memberships",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "membership_type"],
        )

    def test_list_memberships_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing memberships with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "memberships",
            [SAMPLE_MEMBERSHIP],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_memberships({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "memberships",
            filter=None,
            page_size=10,
            page_number=2,
            include=None,
        )

    def test_list_memberships_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing memberships when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "memberships",
            [],
        )

        result = run_async(list_memberships({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_memberships_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing memberships handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_memberships({}))

        assert result["is_error"] is True


class TestCreateMembership:
    """Tests for create_membership tool."""

    def test_create_membership_success(self, patch_get_client: AsyncMock) -> None:
        """Test creating a membership."""
        patch_get_client.create.return_value = create_single_response(
            "memberships",
            SAMPLE_MEMBERSHIP,
        )

        result = run_async(create_membership({
            "signup_id": "12345",
            "membership_type_id": "type-1",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_create_membership_with_dates(self, patch_get_client: AsyncMock) -> None:
        """Test creating a membership with start and end dates."""
        patch_get_client.create.return_value = create_single_response(
            "memberships",
            {
                **SAMPLE_MEMBERSHIP,
                "started_at": "2024-01-01T00:00:00Z",
                "expires_at": "2025-01-01T00:00:00Z",
            },
        )

        result = run_async(create_membership({
            "signup_id": "12345",
            "membership_type_id": "type-1",
            "started_at": "2024-01-01T00:00:00Z",
            "expires_at": "2025-01-01T00:00:00Z",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["started_at"] == "2024-01-01T00:00:00Z"
        assert call_args[0][1]["expires_at"] == "2025-01-01T00:00:00Z"

    def test_create_membership_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test creating membership for invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(create_membership({
            "signup_id": "invalid",
            "membership_type_id": "type-1",
        }))

        assert result["is_error"] is True

    def test_create_membership_invalid_type(self, patch_get_client: AsyncMock) -> None:
        """Test creating membership with invalid type fails."""
        patch_get_client.create.side_effect = Exception("Membership type not found")

        result = run_async(create_membership({
            "signup_id": "12345",
            "membership_type_id": "invalid",
        }))

        assert result["is_error"] is True


class TestListMembershipTypes:
    """Tests for list_membership_types tool."""

    def test_list_types_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all membership types."""
        patch_get_client.list.return_value = create_list_response(
            "membership_types",
            [
                {"id": "type-1", "name": "Basic Member"},
                {"id": "type-2", "name": "Premium Member"},
            ],
        )

        result = run_async(list_membership_types({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_types_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing types with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "membership_types",
            [{"id": "type-1", "name": "Basic Member"}],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_membership_types({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "membership_types",
            page_size=10,
            page_number=2,
        )

    def test_list_types_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing types when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "membership_types",
            [],
        )

        result = run_async(list_membership_types({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_types_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing types handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_membership_types({}))

        assert result["is_error"] is True
