"""
Unit tests for the server-side session state store (confirmations + undo).

These cover the authoritative-confirmation invariant that closes the bypass in
issue #12: a tool_id is only honoured as confirmed if the *server* recorded that
it prompted for it; client claims alone carry no authority.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.lambdas.shared import session_state
from src.lambdas.shared.session_state import (
    append_undo_entry,
    compute_tool_id,
    consume_confirmation,
    filter_authorized_confirmations,
    get_undo_stack,
    make_session_id,
    record_pending_confirmation,
)


class FakeTable:
    """Minimal in-memory stand-in for a boto3 DynamoDB Table resource.

    Supports the narrow slice of update_item/get_item semantics this module
    uses: ADD/DELETE on a string-set attribute and SET on scalar attributes.
    """

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def _key(self, key: dict[str, Any]) -> str:
        return key["session_id"]

    def update_item(
        self,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
    ) -> None:
        item = self.items.setdefault(self._key(Key), {})
        expr = UpdateExpression
        if "ADD pending_tool_ids :tid" in expr:
            current = set(item.get("pending_tool_ids", set()))
            current |= set(ExpressionAttributeValues[":tid"])
            item["pending_tool_ids"] = current
        if "DELETE pending_tool_ids :tid" in expr:
            current = set(item.get("pending_tool_ids", set()))
            current -= set(ExpressionAttributeValues[":tid"])
            if current:
                item["pending_tool_ids"] = current
            else:
                item.pop("pending_tool_ids", None)
        if "SET undo_stack_json = :stack" in expr:
            item["undo_stack_json"] = ExpressionAttributeValues[":stack"]
        if ":ttl" in ExpressionAttributeValues:
            item["expires_at"] = ExpressionAttributeValues[":ttl"]

    def get_item(
        self, Key: dict[str, Any], ProjectionExpression: str | None = None
    ) -> dict[str, Any]:
        item = self.items.get(self._key(Key))
        if item is None:
            return {}
        return {"Item": dict(item)}


def _patch_table(table: Any) -> Any:
    resource = MagicMock()
    resource.Table.return_value = table
    return patch.object(
        session_state, "get_dynamodb_resource", return_value=resource
    )


class TestComputeToolId:
    def test_is_deterministic(self) -> None:
        a = compute_tool_id("delete_contact", {"id": "5"})
        b = compute_tool_id("delete_contact", {"id": "5"})
        assert a == b

    def test_key_order_independent(self) -> None:
        a = compute_tool_id("update_signup", {"a": 1, "b": 2})
        b = compute_tool_id("update_signup", {"b": 2, "a": 1})
        assert a == b

    def test_differs_by_input(self) -> None:
        a = compute_tool_id("delete_contact", {"id": "5"})
        b = compute_tool_id("delete_contact", {"id": "6"})
        assert a != b

    def test_differs_by_tool(self) -> None:
        a = compute_tool_id("delete_contact", {"id": "5"})
        b = compute_tool_id("delete_signup", {"id": "5"})
        assert a != b

    def test_prefixed_with_tool_name(self) -> None:
        tid = compute_tool_id("delete_event", {"id": "9"})
        assert tid.startswith("delete_event_")


class TestSessionId:
    def test_derived_from_identity(self) -> None:
        assert make_session_id("user-1", "nation-a") == "v1:8:nation-a#user-1"

    def test_distinct_per_user(self) -> None:
        assert make_session_id("u1", "n") != make_session_id("u2", "n")

    def test_distinct_per_nation(self) -> None:
        assert make_session_id("u", "n1") != make_session_id("u", "n2")

    def test_no_collision_with_delimiter_in_fields(self) -> None:
        # Length-prefixing makes the encoding unambiguous even with '#'/':'.
        assert make_session_id("b#c", "a") != make_session_id("c", "a#b")


class TestConfirmations:
    def test_recorded_confirmation_is_authorized(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            tid = compute_tool_id("delete_contact", {"id": "5"})
            record_pending_confirmation("sess", tid)
            assert filter_authorized_confirmations("sess", [tid]) == {tid}

    def test_unprompted_tool_id_is_rejected(self) -> None:
        """The bypass: a forged tool_id the server never prompted for is dropped."""
        table = FakeTable()
        with _patch_table(table):
            forged = compute_tool_id("delete_contact", {"id": "999"})
            assert filter_authorized_confirmations("sess", [forged]) == set()

    def test_only_matching_subset_authorized(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            real = compute_tool_id("delete_contact", {"id": "5"})
            forged = compute_tool_id("delete_signup", {"person_id": "7"})
            record_pending_confirmation("sess", real)
            result = filter_authorized_confirmations("sess", [real, forged])
            assert result == {real}

    def test_confirmation_is_session_scoped(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            tid = compute_tool_id("delete_contact", {"id": "5"})
            record_pending_confirmation("session-a", tid)
            # A different session cannot use session-a's confirmation.
            assert filter_authorized_confirmations("session-b", [tid]) == set()

    def test_consume_removes_authorization(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            tid = compute_tool_id("delete_contact", {"id": "5"})
            record_pending_confirmation("sess", tid)
            consume_confirmation("sess", tid)
            assert filter_authorized_confirmations("sess", [tid]) == set()

    def test_empty_request_returns_empty(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            assert filter_authorized_confirmations("sess", []) == set()

    def test_record_sets_ttl(self) -> None:
        table = FakeTable()
        with _patch_table(table), patch.object(
            session_state, "get_current_timestamp", return_value=1000
        ):
            tid = compute_tool_id("delete_contact", {"id": "5"})
            record_pending_confirmation("sess", tid)
            assert table.items["sess"]["expires_at"] == (
                1000 + session_state.SESSION_STATE_TTL_SECONDS
            )

    def test_filter_fails_closed_on_dynamo_error(self) -> None:
        """A store outage must not authorize an action (fail closed)."""
        resource = MagicMock()
        bad_table = MagicMock()
        bad_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "boom"}},
            "GetItem",
        )
        resource.Table.return_value = bad_table
        with patch.object(
            session_state, "get_dynamodb_resource", return_value=resource
        ):
            assert filter_authorized_confirmations("sess", ["anything"]) == set()


class TestUndoStack:
    def test_append_and_read_roundtrip(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            entry = {
                "description": "Add person 1 to list 2",
                "toolName": "add_to_list",
                "undoType": "remove_from_list",
                "undoData": {"person_id": "1", "list_id": "2"},
            }
            append_undo_entry("sess", entry)
            stack = get_undo_stack("sess")
            assert stack == [entry]

    def test_get_empty_when_missing(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            assert get_undo_stack("sess") == []

    def test_append_caps_history(self) -> None:
        table = FakeTable()
        with _patch_table(table):
            for i in range(session_state.MAX_UNDO_ENTRIES + 5):
                append_undo_entry("sess", {"i": i})
            stack = get_undo_stack("sess")
            assert len(stack) == session_state.MAX_UNDO_ENTRIES
            # Oldest entries dropped; newest retained.
            assert stack[-1] == {"i": session_state.MAX_UNDO_ENTRIES + 4}

    def test_get_handles_malformed_json(self) -> None:
        table = FakeTable()
        table.items["sess"] = {"undo_stack_json": "not json{"}
        with _patch_table(table):
            assert get_undo_stack("sess") == []

    def test_get_fails_open_on_dynamo_error(self) -> None:
        resource = MagicMock()
        bad_table = MagicMock()
        bad_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "boom"}},
            "GetItem",
        )
        resource.Table.return_value = bad_table
        with patch.object(
            session_state, "get_dynamodb_resource", return_value=resource
        ):
            assert get_undo_stack("sess") == []
