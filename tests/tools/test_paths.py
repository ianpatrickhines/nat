"""
Unit tests for Path and Path Journey tools.

Tools tested:
- list_paths
- get_path
- list_path_journeys
- assign_to_path
- update_path_journey
- delete_path_journey
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_paths,
    get_path,
    list_path_journeys,
    assign_to_path,
    update_path_journey,
    delete_path_journey,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_PATH,
    SAMPLE_PATH_JOURNEY,
)


class TestListPaths:
    """Tests for list_paths tool."""

    def test_list_paths_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all paths."""
        patch_get_client.list.return_value = create_list_response(
            "paths",
            [
                SAMPLE_PATH,
                {"id": "path-2", "name": "Donor Cultivation"},
            ],
        )

        result = run_async(list_paths({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_paths_with_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing paths with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "paths",
            [SAMPLE_PATH],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_paths({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "paths",
            page_size=10,
            page_number=2,
            include=None,
        )

    def test_list_paths_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing paths with sideloaded steps."""
        patch_get_client.list.return_value = create_list_response(
            "paths",
            [SAMPLE_PATH],
        )

        result = run_async(list_paths({
            "include": ["path_steps"],
        }))

        patch_get_client.list.assert_called_once_with(
            "paths",
            page_size=20,
            page_number=1,
            include=["path_steps"],
        )

    def test_list_paths_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing paths when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "paths",
            [],
        )

        result = run_async(list_paths({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_paths_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing paths handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_paths({}))

        assert result["is_error"] is True


class TestGetPath:
    """Tests for get_path tool."""

    def test_get_path_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single path."""
        patch_get_client.get.return_value = create_single_response(
            "paths",
            SAMPLE_PATH,
        )

        result = run_async(get_path({"id": "path-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "path-1"

    def test_get_path_with_steps(self, patch_get_client: AsyncMock) -> None:
        """Test getting a path with steps by default."""
        patch_get_client.get.return_value = create_single_response(
            "paths",
            SAMPLE_PATH,
        )

        result = run_async(get_path({"id": "path-1"}))

        # Default include is path_steps
        patch_get_client.get.assert_called_once_with(
            "paths",
            "path-1",
            include=["path_steps"],
        )

    def test_get_path_custom_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting a path with custom include."""
        patch_get_client.get.return_value = create_single_response(
            "paths",
            SAMPLE_PATH,
        )

        result = run_async(get_path({
            "id": "path-1",
            "include": ["path_journeys"],
        }))

        patch_get_client.get.assert_called_once_with(
            "paths",
            "path-1",
            include=["path_journeys"],
        )

    def test_get_path_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent path."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_path({"id": "invalid"}))

        assert result["is_error"] is True


class TestListPathJourneys:
    """Tests for list_path_journeys tool."""

    def test_list_journeys_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all path journeys."""
        patch_get_client.list.return_value = create_list_response(
            "path_journeys",
            [
                SAMPLE_PATH_JOURNEY,
                {**SAMPLE_PATH_JOURNEY, "id": "journey-2", "signup_id": "12346"},
            ],
        )

        result = run_async(list_path_journeys({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_journeys_by_path(self, patch_get_client: AsyncMock) -> None:
        """Test listing journeys for a specific path."""
        patch_get_client.list.return_value = create_list_response(
            "path_journeys",
            [SAMPLE_PATH_JOURNEY],
        )

        result = run_async(list_path_journeys({
            "filter": {"path_id": "path-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "path_journeys",
            filter={"path_id": "path-1"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_journeys_by_signup(self, patch_get_client: AsyncMock) -> None:
        """Test listing journeys for a specific signup."""
        patch_get_client.list.return_value = create_list_response(
            "path_journeys",
            [SAMPLE_PATH_JOURNEY],
        )

        result = run_async(list_path_journeys({
            "filter": {"signup_id": "12345"},
        }))

        patch_get_client.list.assert_called_once_with(
            "path_journeys",
            filter={"signup_id": "12345"},
            page_size=20,
            page_number=1,
            include=None,
        )

    def test_list_journeys_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing journeys with sideloaded data."""
        patch_get_client.list.return_value = create_list_response(
            "path_journeys",
            [SAMPLE_PATH_JOURNEY],
        )

        result = run_async(list_path_journeys({
            "include": ["signup", "path", "path_step"],
        }))

        patch_get_client.list.assert_called_once_with(
            "path_journeys",
            filter=None,
            page_size=20,
            page_number=1,
            include=["signup", "path", "path_step"],
        )

    def test_list_journeys_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing journeys handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_path_journeys({}))

        assert result["is_error"] is True


class TestAssignToPath:
    """Tests for assign_to_path tool."""

    def test_assign_success(self, patch_get_client: AsyncMock) -> None:
        """Test assigning a signup to a path."""
        patch_get_client.create.return_value = create_single_response(
            "path_journeys",
            SAMPLE_PATH_JOURNEY,
        )

        result = run_async(assign_to_path({
            "signup_id": "12345",
            "path_id": "path-1",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_assign_with_point_person(self, patch_get_client: AsyncMock) -> None:
        """Test assigning with a point person."""
        patch_get_client.create.return_value = create_single_response(
            "path_journeys",
            {**SAMPLE_PATH_JOURNEY, "point_person_id": "admin-1"},
        )

        result = run_async(assign_to_path({
            "signup_id": "12345",
            "path_id": "path-1",
            "point_person_id": "admin-1",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["point_person_id"] == "admin-1"

    def test_assign_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test assigning invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(assign_to_path({
            "signup_id": "invalid",
            "path_id": "path-1",
        }))

        assert result["is_error"] is True

    def test_assign_invalid_path(self, patch_get_client: AsyncMock) -> None:
        """Test assigning to invalid path fails."""
        patch_get_client.create.side_effect = Exception("Path not found")

        result = run_async(assign_to_path({
            "signup_id": "12345",
            "path_id": "invalid",
        }))

        assert result["is_error"] is True


class TestUpdatePathJourney:
    """Tests for update_path_journey tool."""

    def test_update_journey_success(self, patch_get_client: AsyncMock) -> None:
        """Test updating a path journey."""
        patch_get_client.update.return_value = create_single_response(
            "path_journeys",
            {**SAMPLE_PATH_JOURNEY, "path_step_id": "step-2"},
        )

        result = run_async(update_path_journey({
            "id": "journey-1",
            "path_step_id": "step-2",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data
        patch_get_client.update.assert_called_once_with(
            "path_journeys",
            "journey-1",
            {"path_step_id": "step-2"},
        )

    def test_update_journey_point_person(self, patch_get_client: AsyncMock) -> None:
        """Test updating journey point person."""
        patch_get_client.update.return_value = create_single_response(
            "path_journeys",
            {**SAMPLE_PATH_JOURNEY, "point_person_id": "admin-2"},
        )

        result = run_async(update_path_journey({
            "id": "journey-1",
            "point_person_id": "admin-2",
        }))

        call_args = patch_get_client.update.call_args
        assert call_args[0][2]["point_person_id"] == "admin-2"

    def test_update_journey_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test updating a non-existent journey."""
        patch_get_client.update.side_effect = Exception("Not Found")

        result = run_async(update_path_journey({
            "id": "invalid",
            "path_step_id": "step-2",
        }))

        assert result["is_error"] is True


class TestDeletePathJourney:
    """Tests for delete_path_journey tool."""

    def test_delete_journey_success(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a path journey."""
        patch_get_client.delete.return_value = True

        result = run_async(delete_path_journey({"id": "journey-1"}))

        assert "Successfully removed" in result["content"][0]["text"]
        patch_get_client.delete.assert_called_once_with("path_journeys", "journey-1")

    def test_delete_journey_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test deleting a non-existent journey."""
        patch_get_client.delete.side_effect = Exception("Not Found")

        result = run_async(delete_path_journey({"id": "invalid"}))

        assert result["is_error"] is True
