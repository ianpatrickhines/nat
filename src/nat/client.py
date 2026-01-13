"""
NationBuilder V2 API Client

A JSON:API compliant client for the NationBuilder V2 API.
Handles authentication, pagination, filtering, sideloading, and sideposting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Dict, cast
import httpx


@dataclass
class NationBuilderV2Client:
    """
    JSON:API client for NationBuilder V2 API.

    Usage:
        client = NationBuilderV2Client(slug="your-nation", token="your-token")

        # List people
        people = await client.list("signups", filter={"email": "test@example.com"})

        # Get a single person with related data
        person = await client.get("signups", "123", include=["donations", "signup_tags"])

        # Create a person
        new_person = await client.create("signups", {
            "email": "new@example.com",
            "first_name": "John",
            "last_name": "Doe"
        })
    """

    slug: str
    token: str
    timeout: float = 30.0
    _client: httpx.AsyncClient | None = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"https://{self.slug}.nationbuilder.com/api/v2",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/vnd.api+json",
                "Accept": "application/vnd.api+json"
            },
            timeout=self.timeout
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not initialized."""
        if self._client is None:
            raise RuntimeError("Client not initialized")
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> "NationBuilderV2Client":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def list(
        self,
        resource: str,
        filter: dict[str, Any] | None = None,
        page_size: int = 20,
        page_number: int = 1,
        include: List[str] | None = None,
        fields: dict[str, List[str]] | None = None,
        extra_fields: dict[str, List[str]] | None = None,
        sort: str | None = None
    ) -> dict[str, Any]:
        """
        List resources with optional filtering, pagination, and sideloading.

        Args:
            resource: The resource type (e.g., "signups", "donations")
            filter: Filter criteria as key-value pairs
            page_size: Number of results per page (max 100)
            page_number: Page number to retrieve
            include: Related resources to sideload
            fields: Sparse fieldsets per resource type
            extra_fields: Extra fields to include per resource type
            sort: Sort field (prefix with - for descending)

        Returns:
            JSON:API response with data, included, links, and meta
        """
        params: dict[str, Any] = {
            "page[size]": min(page_size, 100),
            "page[number]": page_number
        }

        if filter:
            for key, value in filter.items():
                params[f"filter[{key}]"] = value

        if include:
            params["include"] = ",".join(include)

        if fields:
            for resource_type, field_list in fields.items():
                params[f"fields[{resource_type}]"] = ",".join(field_list)

        if extra_fields:
            for resource_type, field_list in extra_fields.items():
                params[f"extra_fields[{resource_type}]"] = ",".join(field_list)

        if sort:
            params["sort"] = sort

        response = await self.client.get(f"/{resource}", params=params)
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def get(
        self,
        resource: str,
        id: str,
        include: List[str] | None = None,
        fields: dict[str, List[str]] | None = None,
        extra_fields: dict[str, List[str]] | None = None
    ) -> dict[str, Any]:
        """
        Get a single resource by ID.

        Args:
            resource: The resource type
            id: The resource ID
            include: Related resources to sideload
            fields: Sparse fieldsets per resource type
            extra_fields: Extra fields to include

        Returns:
            JSON:API response with data and optionally included
        """
        params: dict[str, Any] = {}

        if include:
            params["include"] = ",".join(include)

        if fields:
            for resource_type, field_list in fields.items():
                params[f"fields[{resource_type}]"] = ",".join(field_list)

        if extra_fields:
            for resource_type, field_list in extra_fields.items():
                params[f"extra_fields[{resource_type}]"] = ",".join(field_list)

        response = await self.client.get(f"/{resource}/{id}", params=params)
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def create(
        self,
        resource: str,
        attributes: dict[str, Any],
        relationships: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Create a new resource.

        Args:
            resource: The resource type
            attributes: Resource attributes
            relationships: Optional relationships for sideposting

        Returns:
            JSON:API response with the created resource
        """
        payload: dict[str, Any] = {
            "data": {
                "type": resource,
                "attributes": attributes
            }
        }

        if relationships:
            payload["data"]["relationships"] = relationships

        response = await self.client.post(f"/{resource}", json=payload)
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def update(
        self,
        resource: str,
        id: str,
        attributes: dict[str, Any],
        relationships: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Update an existing resource.

        Args:
            resource: The resource type
            id: The resource ID
            attributes: Attributes to update
            relationships: Optional relationships to update

        Returns:
            JSON:API response with the updated resource
        """
        payload: dict[str, Any] = {
            "data": {
                "type": resource,
                "id": id,
                "attributes": attributes
            }
        }

        if relationships:
            payload["data"]["relationships"] = relationships

        response = await self.client.patch(f"/{resource}/{id}", json=payload)
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def delete(self, resource: str, id: str) -> bool:
        """
        Delete a resource.

        Args:
            resource: The resource type
            id: The resource ID

        Returns:
            True if deletion was successful
        """
        response = await self.client.delete(f"/{resource}/{id}")
        response.raise_for_status()
        return True

    async def list_related(
        self,
        resource: str,
        id: str,
        relationship: str,
        page_size: int = 20,
        page_number: int = 1
    ) -> dict[str, Any]:
        """
        List related resources (e.g., list members of a list).

        Args:
            resource: The parent resource type
            id: The parent resource ID
            relationship: The relationship name
            page_size: Number of results per page
            page_number: Page number to retrieve

        Returns:
            JSON:API response with related resources
        """
        params = {
            "page[size]": min(page_size, 100),
            "page[number]": page_number
        }

        response = await self.client.get(
            f"/{resource}/{id}/{relationship}",
            params=params
        )
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def add_related(
        self,
        resource: str,
        id: str,
        relationship: str,
        related_ids: List[str]
    ) -> dict[str, Any]:
        """
        Add related resources to a relationship.

        Args:
            resource: The parent resource type
            id: The parent resource ID
            relationship: The relationship name
            related_ids: IDs of resources to add

        Returns:
            JSON:API response
        """
        payload = {
            "data": [{"type": relationship, "id": rid} for rid in related_ids]
        }

        response = await self.client.post(
            f"/{resource}/{id}/relationships/{relationship}",
            json=payload
        )
        response.raise_for_status()
        return cast(Dict[str, Any], response.json())

    async def remove_related(
        self,
        resource: str,
        id: str,
        relationship: str,
        related_ids: List[str]
    ) -> bool:
        """
        Remove related resources from a relationship.

        Args:
            resource: The parent resource type
            id: The parent resource ID
            relationship: The relationship name
            related_ids: IDs of resources to remove

        Returns:
            True if removal was successful
        """
        payload = {
            "data": [{"type": relationship, "id": rid} for rid in related_ids]
        }

        response = await self.client.request(
            "DELETE",
            f"/{resource}/{id}/relationships/{relationship}",
            json=payload
        )
        response.raise_for_status()
        return True


# Singleton instance for tool functions
_client: NationBuilderV2Client | None = None


def get_client() -> NationBuilderV2Client:
    """Get the global NationBuilder client instance."""
    if _client is None:
        raise RuntimeError(
            "NationBuilder client not initialized. "
            "Call init_client(slug, token) first."
        )
    return _client


def init_client(slug: str, token: str) -> NationBuilderV2Client:
    """Initialize the global NationBuilder client."""
    global _client
    _client = NationBuilderV2Client(slug=slug, token=token)
    return _client
