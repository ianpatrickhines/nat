"""
Shared test fixtures for NationBuilder API tool tests.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx


def run_async(coro: Any) -> Any:
    """Helper to run async coroutines in sync tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def create_list_response(
    resource_type: str,
    data: list[dict[str, Any]],
    total_pages: int = 1,
    current_page: int = 1,
) -> dict[str, Any]:
    """Create a JSON:API list response."""
    return {
        "data": [
            {
                "type": resource_type,
                "id": str(item.get("id", i)),
                "attributes": item,
            }
            for i, item in enumerate(data)
        ],
        "meta": {
            "pagination": {
                "total_pages": total_pages,
                "current_page": current_page,
            }
        },
        "links": {
            "self": f"https://test.nationbuilder.com/api/v2/{resource_type}",
        },
    }


def create_single_response(
    resource_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create a JSON:API single resource response."""
    return {
        "data": {
            "type": resource_type,
            "id": str(data.get("id", "1")),
            "attributes": data,
        },
    }


def create_error_response(
    status_code: int,
    title: str,
    detail: str,
) -> dict[str, Any]:
    """Create a JSON:API error response."""
    return {
        "errors": [
            {
                "status": str(status_code),
                "title": title,
                "detail": detail,
            }
        ]
    }


class MockResponse:
    """Mock HTTP response for httpx."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self) -> dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=MagicMock(),
            )


class MockAsyncClient:
    """Mock httpx.AsyncClient for testing."""

    def __init__(self) -> None:
        self.get = AsyncMock()
        self.post = AsyncMock()
        self.patch = AsyncMock()
        self.delete = AsyncMock()
        self.request = AsyncMock()

    async def aclose(self) -> None:
        pass


@pytest.fixture
def mock_client() -> MockAsyncClient:
    """Provide a mock async HTTP client."""
    return MockAsyncClient()


@pytest.fixture
def patch_get_client(mock_client: MockAsyncClient) -> Any:
    """Patch the get_client function to return a mock client."""
    from src.nat.client import NationBuilderV2Client

    mock_nb_client = MagicMock(spec=NationBuilderV2Client)
    mock_nb_client._client = mock_client
    mock_nb_client.list = AsyncMock()
    mock_nb_client.get = AsyncMock()
    mock_nb_client.create = AsyncMock()
    mock_nb_client.update = AsyncMock()
    mock_nb_client.delete = AsyncMock()
    mock_nb_client.list_related = AsyncMock()
    mock_nb_client.add_related = AsyncMock()
    mock_nb_client.remove_related = AsyncMock()

    with patch("src.nat.tools.get_client", return_value=mock_nb_client):
        yield mock_nb_client


# Sample test data

SAMPLE_SIGNUP = {
    "id": "12345",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Smith",
    "phone_number": "555-1234",
    "is_volunteer": True,
    "email_opt_in": True,
}

SAMPLE_SIGNUP_TAG = {
    "id": "tag-1",
    "name": "Volunteer",
}

SAMPLE_CONTACT = {
    "id": "contact-1",
    "signup_id": "12345",
    "author_id": "admin-1",
    "contact_method": "phone",
    "contact_status": "completed",
    "content": "Discussed volunteer opportunities",
}

SAMPLE_DONATION = {
    "id": "donation-1",
    "signup_id": "12345",
    "amount_in_cents": 10000,
    "payment_type_name": "Credit Card",
    "succeeded_at": "2024-01-15T12:00:00Z",
}

SAMPLE_EVENT = {
    "id": "event-1",
    "name": "Campaign Rally",
    "status": "published",
    "start_time": "2024-03-01T18:00:00Z",
    "end_time": "2024-03-01T21:00:00Z",
    "venue_name": "Community Center",
}

SAMPLE_EVENT_RSVP = {
    "id": "rsvp-1",
    "event_id": "event-1",
    "signup_id": "12345",
    "guests_count": 2,
    "canceled": False,
}

SAMPLE_PATH = {
    "id": "path-1",
    "name": "New Volunteer Onboarding",
}

SAMPLE_PATH_JOURNEY = {
    "id": "journey-1",
    "signup_id": "12345",
    "path_id": "path-1",
}

SAMPLE_AUTOMATION = {
    "id": "auto-1",
    "name": "Welcome Email Series",
}

SAMPLE_LIST = {
    "id": "list-1",
    "name": "Active Volunteers",
}

SAMPLE_SURVEY = {
    "id": "survey-1",
    "name": "Volunteer Interest Survey",
}

SAMPLE_PETITION = {
    "id": "petition-1",
    "name": "Support Local Parks",
}

SAMPLE_MEMBERSHIP = {
    "id": "membership-1",
    "signup_id": "12345",
    "membership_type_id": "type-1",
}

SAMPLE_MAILING = {
    "id": "mailing-1",
    "name": "Monthly Newsletter",
}

SAMPLE_PLEDGE = {
    "id": "pledge-1",
    "signup_id": "12345",
    "amount_in_cents": 50000,
}

SAMPLE_BROADCASTER = {
    "id": "broadcaster-1",
    "name": "Campaign Updates",
}

SAMPLE_ELECTION = {
    "id": "election-1",
    "name": "2024 General Election",
}

SAMPLE_PAGE = {
    "id": "page-1",
    "name": "Donate Now",
}
