"""
Unit tests for the OAuth state (CSRF) protection module.

Covers the acceptance criteria for nat#11:
  - single-use server-side nonce, validated then deleted
  - created_at expiry enforcement
  - redirect_uri allowlist
  - rejection of tampered / replayed / expired / forged state
"""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from src.lambdas.shared.oauth_state import (
    OAuthStateError,
    issue_oauth_state,
    validate_oauth_state,
    validate_redirect_uri,
)

TEST_USER_ID = "user-123"
TEST_NB_SLUG = "testnation"
TEST_REDIRECT_URI = "https://api.example.com/auth/nationbuilder/callback"
ALLOWLIST = TEST_REDIRECT_URI


class MockOAuthStateTable:
    """In-memory stand-in for the DynamoDB OAuth state table."""

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
            # Mirror the conditional-delete failure on a missing item.
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}},
                "DeleteItem",
            )
        old = self.items.pop(nonce)
        if ReturnValues == "ALL_OLD":
            return {"Attributes": old}
        return {}


class MockOAuthStateResource:
    def __init__(self, table: MockOAuthStateTable) -> None:
        self._table = table

    def Table(self, name: str) -> MockOAuthStateTable:
        return self._table


def _patches(table: MockOAuthStateTable, allowlist: str = ALLOWLIST) -> list[Any]:
    return [
        patch(
            "src.lambdas.shared.oauth_state.get_dynamodb_resource",
            return_value=MockOAuthStateResource(table),
        ),
        patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
            allowlist,
        ),
    ]


def _decode(state: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(state).decode("utf-8"))


class TestValidateRedirectUri:
    def test_exact_match_allowed(self) -> None:
        with patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
            ALLOWLIST,
        ):
            assert validate_redirect_uri(TEST_REDIRECT_URI) is True

    def test_unknown_rejected(self) -> None:
        with patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
            ALLOWLIST,
        ):
            assert validate_redirect_uri("https://evil.example.com/callback") is False

    def test_prefix_not_accepted(self) -> None:
        """A URI that only shares a prefix must be rejected (no open redirect)."""
        with patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST",
            ALLOWLIST,
        ):
            assert validate_redirect_uri(TEST_REDIRECT_URI + ".evil.com") is False

    def test_empty_allowlist_denies_all(self) -> None:
        with patch(
            "src.lambdas.shared.oauth_state.OAUTH_REDIRECT_URI_ALLOWLIST", ""
        ):
            assert validate_redirect_uri(TEST_REDIRECT_URI) is False


class TestIssueOAuthState:
    def test_round_trip(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
            result = validate_oauth_state(state)
        assert result == {
            "user_id": TEST_USER_ID,
            "nb_slug": TEST_NB_SLUG,
            "redirect_uri": TEST_REDIRECT_URI,
        }

    def test_state_carries_created_at_and_nonce(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(
                TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI, now=1000.0
            )
        payload = _decode(state)
        assert payload["created_at"] == 1000
        assert isinstance(payload["nonce"], str) and len(payload["nonce"]) > 20

    def test_nonce_stored_server_side(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
        nonce = _decode(state)["nonce"]
        assert nonce in table.items
        assert table.items[nonce]["user_id"] == TEST_USER_ID
        assert "expires_at" in table.items[nonce]

    def test_disallowed_redirect_uri_rejected_at_issuance(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            with pytest.raises(OAuthStateError) as exc:
                issue_oauth_state(
                    TEST_USER_ID, TEST_NB_SLUG, "https://evil.example.com/cb"
                )
        assert exc.value.error_slug == "invalid_redirect_uri"
        assert table.items == {}

    def test_missing_fields_rejected(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            with pytest.raises(OAuthStateError):
                issue_oauth_state("", TEST_NB_SLUG, TEST_REDIRECT_URI)


class TestValidateOAuthState:
    def test_single_use_replay_rejected(self) -> None:
        """A state validated once cannot be validated again (single-use)."""
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
            validate_oauth_state(state)  # consumes it
            with pytest.raises(OAuthStateError):
                validate_oauth_state(state)

    def test_deleted_after_use(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
            validate_oauth_state(state)
        assert table.items == {}

    def test_expired_state_rejected(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(
                TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI, now=1000.0
            )
            with pytest.raises(OAuthStateError) as exc:
                # 601s later, past the 600s TTL
                validate_oauth_state(state, now=1601.0)
        assert exc.value.error_slug == "expired_state"

    def test_not_yet_expired_accepted(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(
                TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI, now=1000.0
            )
            result = validate_oauth_state(state, now=1500.0)
        assert result["user_id"] == TEST_USER_ID

    def test_tampered_user_id_rejected(self) -> None:
        """Changing user_id in the client copy must not change the result."""
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
            payload = _decode(state)
            payload["user_id"] = "attacker-999"
            tampered = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).decode()
            with pytest.raises(OAuthStateError):
                validate_oauth_state(tampered)

    def test_tampered_nb_slug_rejected(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            state = issue_oauth_state(TEST_USER_ID, TEST_NB_SLUG, TEST_REDIRECT_URI)
            payload = _decode(state)
            payload["nb_slug"] = "othernation"
            tampered = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).decode()
            with pytest.raises(OAuthStateError):
                validate_oauth_state(tampered)

    def test_forged_nonce_rejected(self) -> None:
        """A state with a nonce that was never issued is rejected."""
        table = MockOAuthStateTable()
        forged = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "user_id": "attacker-999",
                    "nb_slug": TEST_NB_SLUG,
                    "redirect_uri": TEST_REDIRECT_URI,
                    "nonce": "totally-made-up-nonce",
                    "created_at": 1000,
                }
            ).encode()
        ).decode()
        with _patches(table)[0], _patches(table)[1]:
            with pytest.raises(OAuthStateError):
                validate_oauth_state(forged)

    def test_disallowed_redirect_uri_rejected_at_callback(self) -> None:
        table = MockOAuthStateTable()
        # Issue with a permissive allowlist, then validate under a strict one.
        with _patches(table, allowlist="https://evil.example.com/cb")[0], _patches(
            table, allowlist="https://evil.example.com/cb"
        )[1]:
            state = issue_oauth_state(
                TEST_USER_ID, TEST_NB_SLUG, "https://evil.example.com/cb"
            )
        with _patches(table)[0], _patches(table)[1]:
            with pytest.raises(OAuthStateError) as exc:
                validate_oauth_state(state)
        assert exc.value.error_slug == "invalid_redirect_uri"

    def test_missing_state_rejected(self) -> None:
        with pytest.raises(OAuthStateError) as exc:
            validate_oauth_state("")
        assert exc.value.error_slug == "missing_state"

    def test_malformed_state_rejected(self) -> None:
        table = MockOAuthStateTable()
        with _patches(table)[0], _patches(table)[1]:
            with pytest.raises(OAuthStateError):
                validate_oauth_state("not-valid-base64-json!!!")

    def test_state_without_nonce_rejected(self) -> None:
        no_nonce = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "user_id": TEST_USER_ID,
                    "nb_slug": TEST_NB_SLUG,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            ).encode()
        ).decode()
        with pytest.raises(OAuthStateError):
            validate_oauth_state(no_nonce)
