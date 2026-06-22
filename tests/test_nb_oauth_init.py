"""
Unit tests for the NationBuilder OAuth Init Lambda Handler.

The init endpoint is the issuance side of the CSRF protection: it mints a
single-use, server-side ``state`` nonce and redirects to NationBuilder's
authorize endpoint.
"""

from __future__ import annotations

import base64
import json
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from botocore.exceptions import ClientError

from src.lambdas.nb_oauth_init.handler import handler

TEST_CLIENT_ID = "client_id_123"
TEST_NB_SLUG = "testnation"
TEST_CALLBACK_URL = "https://api.example.com/auth/nationbuilder/callback"


class MockOAuthStateTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def put_item(self, Item: dict[str, Any]) -> None:
        self.items[Item["nonce"]] = dict(Item)

    def delete_item(
        self,
        Key: dict[str, Any],
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        nonce = Key["nonce"]
        if nonce not in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}},
                "DeleteItem",
            )
        old = self.items.pop(nonce)
        return {"Attributes": old} if ReturnValues == "ALL_OLD" else {}


class MockOAuthStateResource:
    def __init__(self, table: MockOAuthStateTable) -> None:
        self._table = table

    def Table(self, name: str) -> MockOAuthStateTable:
        return self._table


def _patches(
    table: MockOAuthStateTable, callback_url: str = TEST_CALLBACK_URL
) -> list[Any]:
    return [
        patch(
            "src.lambdas.shared.oauth_state.get_dynamodb_resource",
            return_value=MockOAuthStateResource(table),
        ),
        patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
            TEST_CALLBACK_URL,
        ),
        patch("src.lambdas.nb_oauth_init.handler.OAUTH_CALLBACK_URL", callback_url),
        patch(
            "src.lambdas.nb_oauth_init.handler.get_secret",
            return_value=TEST_CLIENT_ID,
        ),
    ]


class TestInitHandler:
    def test_missing_nb_slug_redirects_to_error(self) -> None:
        event = {"queryStringParameters": {}}
        response = handler(event, None)
        assert response["statusCode"] == 302
        assert "error=missing_nb_slug" in response["headers"]["Location"]

    def test_null_query_params_handled(self) -> None:
        response = handler({"queryStringParameters": None}, None)
        assert response["statusCode"] == 302
        assert "error=missing_nb_slug" in response["headers"]["Location"]

    def test_malformed_nb_slug_rejected(self) -> None:
        """A slug that would distort the authorize host is rejected."""
        table = MockOAuthStateTable()
        for bad in ["evil.com/x", "Foo Bar", "slug?x=1", "-leading", "UPPER"]:
            with ExitStack() as stack:
                for p in _patches(table):
                    stack.enter_context(p)
                response = handler(
                    {"queryStringParameters": {"nb_slug": bad}}, None
                )
            assert response["statusCode"] == 302
            assert "error=invalid_nb_slug" in response["headers"]["Location"]
        assert table.items == {}

    def test_missing_callback_url_misconfigured(self) -> None:
        table = MockOAuthStateTable()
        with ExitStack() as stack:
            for p in _patches(table, callback_url=""):
                stack.enter_context(p)
            response = handler(
                {"queryStringParameters": {"nb_slug": TEST_NB_SLUG}}, None
            )
        assert response["statusCode"] == 302
        assert "error=server_misconfigured" in response["headers"]["Location"]

    def test_successful_init_redirects_to_authorize(self) -> None:
        table = MockOAuthStateTable()
        with ExitStack() as stack:
            for p in _patches(table):
                stack.enter_context(p)
            response = handler(
                {"queryStringParameters": {"nb_slug": TEST_NB_SLUG}}, None
            )

        assert response["statusCode"] == 302
        location = response["headers"]["Location"]
        parsed = urlparse(location)
        assert parsed.scheme == "https"
        assert parsed.netloc == f"{TEST_NB_SLUG}.nationbuilder.com"
        assert parsed.path == "/oauth/authorize"

        params = parse_qs(parsed.query)
        assert params["client_id"] == [TEST_CLIENT_ID]
        assert params["redirect_uri"] == [TEST_CALLBACK_URL]
        assert params["response_type"] == ["code"]
        assert "state" in params

        # The state nonce was persisted server-side, bound to a generated user.
        assert len(table.items) == 1
        stored = next(iter(table.items.values()))
        assert stored["nb_slug"] == TEST_NB_SLUG
        assert stored["redirect_uri"] == TEST_CALLBACK_URL
        assert stored["user_id"].startswith("user-")

    def test_state_matches_stored_nonce(self) -> None:
        table = MockOAuthStateTable()
        with ExitStack() as stack:
            for p in _patches(table):
                stack.enter_context(p)
            response = handler(
                {"queryStringParameters": {"nb_slug": TEST_NB_SLUG}}, None
            )

        location = response["headers"]["Location"]
        state = parse_qs(urlparse(location).query)["state"][0]
        payload = json.loads(base64.urlsafe_b64decode(state).decode())
        assert payload["nonce"] in table.items

    def test_supplied_user_id_is_ignored(self) -> None:
        """A caller-supplied user_id must NOT be trusted (session-fixation
        defense): the issued state binds to a server-generated identity."""
        table = MockOAuthStateTable()
        with ExitStack() as stack:
            for p in _patches(table):
                stack.enter_context(p)
            response = handler(
                {
                    "queryStringParameters": {
                        "nb_slug": TEST_NB_SLUG,
                        "user_id": "attacker-controlled-7",
                    }
                },
                None,
            )
        assert response["statusCode"] == 302
        stored = next(iter(table.items.values()))
        assert stored["user_id"] != "attacker-controlled-7"
        assert stored["user_id"].startswith("user-")

    def test_callback_url_off_allowlist_rejected(self) -> None:
        """If the configured callback URL is not allowlisted, issuance fails."""
        table = MockOAuthStateTable()
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.lambdas.shared.oauth_state.get_dynamodb_resource",
                    return_value=MockOAuthStateResource(table),
                )
            )
            stack.enter_context(
                patch(
                    "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
                    "https://other.example.com/cb",
                )
            )
            stack.enter_context(
                patch(
                    "src.lambdas.nb_oauth_init.handler.OAUTH_CALLBACK_URL",
                    TEST_CALLBACK_URL,
                )
            )
            stack.enter_context(
                patch(
                    "src.lambdas.nb_oauth_init.handler.get_secret",
                    return_value=TEST_CLIENT_ID,
                )
            )
            response = handler(
                {"queryStringParameters": {"nb_slug": TEST_NB_SLUG}}, None
            )

        assert response["statusCode"] == 302
        assert "error=invalid_redirect_uri" in response["headers"]["Location"]
        assert table.items == {}
