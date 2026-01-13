"""
Unit tests for Automation tools.

Tools tested:
- list_automations
- get_automation
- enroll_in_automation
- list_automation_enrollments
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_automations,
    get_automation,
    enroll_in_automation,
    list_automation_enrollments,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_AUTOMATION,
)


class TestListAutomations:
    """Tests for list_automations tool."""

    def test_list_automations_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all automations."""
        patch_get_client.list.return_value = create_list_response(
            "automations",
            [
                SAMPLE_AUTOMATION,
                {"id": "auto-2", "name": "Follow-up Series"},
            ],
        )

        result = run_async(list_automations({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_automations_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing automations with filter."""
        patch_get_client.list.return_value = create_list_response(
            "automations",
            [SAMPLE_AUTOMATION],
        )

        result = run_async(list_automations({
            "filter": {"status": "active"},
        }))

        patch_get_client.list.assert_called_once_with(
            "automations",
            filter={"status": "active"},
            page_size=20,
            page_number=1,
        )

    def test_list_automations_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing automations with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "automations",
            [SAMPLE_AUTOMATION],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_automations({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "automations",
            filter=None,
            page_size=10,
            page_number=2,
        )

    def test_list_automations_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing automations when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "automations",
            [],
        )

        result = run_async(list_automations({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_automations_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing automations handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_automations({}))

        assert result["is_error"] is True


class TestGetAutomation:
    """Tests for get_automation tool."""

    def test_get_automation_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single automation."""
        patch_get_client.get.return_value = create_single_response(
            "automations",
            SAMPLE_AUTOMATION,
        )

        result = run_async(get_automation({"id": "auto-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "auto-1"
        assert data["data"]["attributes"]["name"] == "Welcome Email Series"

    def test_get_automation_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent automation."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_automation({"id": "invalid"}))

        assert result["is_error"] is True


class TestEnrollInAutomation:
    """Tests for enroll_in_automation tool."""

    def test_enroll_success(self, patch_get_client: AsyncMock) -> None:
        """Test enrolling a signup in an automation."""
        patch_get_client.create.return_value = create_single_response(
            "automation_enrollments",
            {
                "id": "enrollment-1",
                "signup_id": "12345",
                "automation_id": "auto-1",
            },
        )

        result = run_async(enroll_in_automation({
            "signup_id": "12345",
            "automation_id": "auto-1",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_enroll_with_campaign_source(self, patch_get_client: AsyncMock) -> None:
        """Test enrolling with campaign source."""
        patch_get_client.create.return_value = create_single_response(
            "automation_enrollments",
            {
                "id": "enrollment-1",
                "signup_id": "12345",
                "automation_id": "auto-1",
                "campaign_source": "website",
            },
        )

        result = run_async(enroll_in_automation({
            "signup_id": "12345",
            "automation_id": "auto-1",
            "campaign_source": "website",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["campaign_source"] == "website"

    def test_enroll_with_campaign_url(self, patch_get_client: AsyncMock) -> None:
        """Test enrolling with campaign URL."""
        patch_get_client.create.return_value = create_single_response(
            "automation_enrollments",
            {
                "id": "enrollment-1",
                "signup_id": "12345",
                "automation_id": "auto-1",
                "campaign_url": "https://example.com/signup",
            },
        )

        result = run_async(enroll_in_automation({
            "signup_id": "12345",
            "automation_id": "auto-1",
            "campaign_url": "https://example.com/signup",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["campaign_url"] == "https://example.com/signup"

    def test_enroll_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test enrolling invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(enroll_in_automation({
            "signup_id": "invalid",
            "automation_id": "auto-1",
        }))

        assert result["is_error"] is True

    def test_enroll_invalid_automation(self, patch_get_client: AsyncMock) -> None:
        """Test enrolling in invalid automation fails."""
        patch_get_client.create.side_effect = Exception("Automation not found")

        result = run_async(enroll_in_automation({
            "signup_id": "12345",
            "automation_id": "invalid",
        }))

        assert result["is_error"] is True


class TestListAutomationEnrollments:
    """Tests for list_automation_enrollments tool."""

    def test_list_enrollments_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all enrollments."""
        patch_get_client.list.return_value = create_list_response(
            "automation_enrollments",
            [
                {"id": "enrollment-1", "signup_id": "12345", "automation_id": "auto-1"},
                {"id": "enrollment-2", "signup_id": "12346", "automation_id": "auto-1"},
            ],
        )

        result = run_async(list_automation_enrollments({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_enrollments_by_automation(self, patch_get_client: AsyncMock) -> None:
        """Test listing enrollments for a specific automation."""
        patch_get_client.list.return_value = create_list_response(
            "automation_enrollments",
            [{"id": "enrollment-1", "signup_id": "12345", "automation_id": "auto-1"}],
        )

        result = run_async(list_automation_enrollments({
            "filter": {"automation_id": "auto-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "automation_enrollments",
            filter={"automation_id": "auto-1"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_enrollments_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing enrollments for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "automation_enrollments",
            [{"id": "enrollment-1", "signup_id": "12345", "automation_id": "auto-1"}],
        )

        result = run_async(list_automation_enrollments({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "automation_enrollments",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_enrollments_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing enrollments with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "automation_enrollments",
            [{"id": "enrollment-1", "signup_id": "12345", "automation_id": "auto-1"}],
        )

        result = run_async(list_automation_enrollments({
            "include": ["signup", "automation"],
        }))

        patch_get_client.list.assert_called_once_with(
            "automation_enrollments",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "automation"],
        )

    def test_list_enrollments_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing enrollments handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_automation_enrollments({}))

        assert result["is_error"] is True
