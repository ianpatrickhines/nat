"""
Unit tests for Petition tools.

Tools tested:
- list_petitions
- get_petition
- sign_petition
- list_petition_signatures
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_petitions,
    get_petition,
    sign_petition,
    list_petition_signatures,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_PETITION,
)


class TestListPetitions:
    """Tests for list_petitions tool."""

    def test_list_petitions_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all petitions."""
        patch_get_client.list.return_value = create_list_response(
            "petitions",
            [
                SAMPLE_PETITION,
                {"id": "petition-2", "name": "Save the Library"},
            ],
        )

        result = run_async(list_petitions({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_petitions_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing petitions with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "petitions",
            [SAMPLE_PETITION],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_petitions({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "petitions",
            page_size=10,
            page_number=2,
        )

    def test_list_petitions_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing petitions when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "petitions",
            [],
        )

        result = run_async(list_petitions({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_petitions_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing petitions handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_petitions({}))

        assert result["is_error"] is True


class TestGetPetition:
    """Tests for get_petition tool."""

    def test_get_petition_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single petition."""
        patch_get_client.get.return_value = create_single_response(
            "petitions",
            SAMPLE_PETITION,
        )

        result = run_async(get_petition({"id": "petition-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "petition-1"
        assert data["data"]["attributes"]["name"] == "Support Local Parks"

    def test_get_petition_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent petition."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_petition({"id": "invalid"}))

        assert result["is_error"] is True


class TestSignPetition:
    """Tests for sign_petition tool."""

    def test_sign_petition_success(self, patch_get_client: AsyncMock) -> None:
        """Test signing a petition."""
        patch_get_client.create.return_value = create_single_response(
            "petition_signatures",
            {
                "id": "signature-1",
                "petition_id": "petition-1",
                "signup_id": "12345",
            },
        )

        result = run_async(sign_petition({
            "petition_id": "petition-1",
            "signup_id": "12345",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_sign_petition_invalid_petition(self, patch_get_client: AsyncMock) -> None:
        """Test signing invalid petition fails."""
        patch_get_client.create.side_effect = Exception("Petition not found")

        result = run_async(sign_petition({
            "petition_id": "invalid",
            "signup_id": "12345",
        }))

        assert result["is_error"] is True

    def test_sign_petition_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test signing with invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(sign_petition({
            "petition_id": "petition-1",
            "signup_id": "invalid",
        }))

        assert result["is_error"] is True

    def test_sign_petition_already_signed(self, patch_get_client: AsyncMock) -> None:
        """Test signing a petition already signed fails."""
        patch_get_client.create.side_effect = Exception("Already signed")

        result = run_async(sign_petition({
            "petition_id": "petition-1",
            "signup_id": "12345",
        }))

        assert result["is_error"] is True


class TestListPetitionSignatures:
    """Tests for list_petition_signatures tool."""

    def test_list_signatures_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all signatures."""
        patch_get_client.list.return_value = create_list_response(
            "petition_signatures",
            [
                {"id": "signature-1", "petition_id": "petition-1", "signup_id": "12345"},
                {"id": "signature-2", "petition_id": "petition-1", "signup_id": "12346"},
            ],
        )

        result = run_async(list_petition_signatures({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_signatures_by_petition(self, patch_get_client: AsyncMock) -> None:
        """Test listing signatures for a specific petition."""
        patch_get_client.list.return_value = create_list_response(
            "petition_signatures",
            [{"id": "signature-1", "petition_id": "petition-1", "signup_id": "12345"}],
        )

        result = run_async(list_petition_signatures({
            "filter": {"petition_id": "petition-1"},
        }))

        patch_get_client.list.assert_called_once_with(
            "petition_signatures",
            filter={"petition_id": "petition-1"},
            page_size=20,
            page_number=1,
        )

    def test_list_signatures_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing signatures with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "petition_signatures",
            [{"id": "signature-1", "petition_id": "petition-1", "signup_id": "12345"}],
            total_pages=5,
            current_page=3,
        )

        result = run_async(list_petition_signatures({
            "page_size": 50,
            "page_number": 3,
        }))

        patch_get_client.list.assert_called_once_with(
            "petition_signatures",
            filter=None,
            page_size=50,
            page_number=3,
        )

    def test_list_signatures_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing signatures handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_petition_signatures({}))

        assert result["is_error"] is True
