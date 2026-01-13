"""
Unit tests for Mailing tools.

Tools tested:
- list_mailings
- get_mailing
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_mailings,
    get_mailing,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_MAILING,
)


class TestListMailings:
    """Tests for list_mailings tool."""

    def test_list_mailings_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all mailings."""
        patch_get_client.list.return_value = create_list_response(
            "mailings",
            [
                SAMPLE_MAILING,
                {"id": "mailing-2", "name": "Welcome Email"},
            ],
        )

        result = run_async(list_mailings({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_mailings_with_filter(self, patch_get_client: AsyncMock) -> None:
        """Test listing mailings with filter."""
        patch_get_client.list.return_value = create_list_response(
            "mailings",
            [SAMPLE_MAILING],
        )

        result = run_async(list_mailings({
            "filter": {"status": "sent"},
        }))

        patch_get_client.list.assert_called_once_with(
            "mailings",
            filter={"status": "sent"},
            page_size=20,
            page_number=1,
        )

    def test_list_mailings_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing mailings with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "mailings",
            [SAMPLE_MAILING],
            total_pages=5,
            current_page=3,
        )

        result = run_async(list_mailings({
            "page_size": 25,
            "page_number": 3,
        }))

        patch_get_client.list.assert_called_once_with(
            "mailings",
            filter=None,
            page_size=25,
            page_number=3,
        )

    def test_list_mailings_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing mailings when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "mailings",
            [],
        )

        result = run_async(list_mailings({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_mailings_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing mailings handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_mailings({}))

        assert result["is_error"] is True


class TestGetMailing:
    """Tests for get_mailing tool."""

    def test_get_mailing_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single mailing."""
        patch_get_client.get.return_value = create_single_response(
            "mailings",
            SAMPLE_MAILING,
        )

        result = run_async(get_mailing({"id": "mailing-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "mailing-1"
        assert data["data"]["attributes"]["name"] == "Monthly Newsletter"

    def test_get_mailing_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent mailing."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_mailing({"id": "invalid"}))

        assert result["is_error"] is True
