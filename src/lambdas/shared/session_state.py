"""
Server-side session state: destructive-action confirmations and undo history.

Confirmation state and undo history are *authoritative server-side*. Both were
previously trusted from the streaming request body (``confirmed_tools`` and
``undo_stack``), which are forgeable: a malicious client could pre-confirm a
destructive tool it was never prompted for (bypassing the confirmation gate),
or spoof undo instructions so an "undo" deletes the wrong record.

This module persists that state in DynamoDB keyed by an opaque ``session_id``
derived from the verified ``(user_id, nation_slug)`` identity claims (never from
client-supplied fields). State expires automatically via a DynamoDB TTL.

Security posture
----------------
Confirmation checks **fail closed**: if the store is unavailable, an action is
treated as *not* confirmed, so the worst case is an extra confirmation
round-trip — never a silent destructive execution. Undo helpers **fail open**:
undo is a convenience, so a store error simply yields no undo context.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB table holding per-session confirmation + undo state.
SESSION_STATE_TABLE = os.environ.get("SESSION_STATE_TABLE", "nat-session-state-dev")

# How long session state lives before the DynamoDB TTL reaps it (seconds).
SESSION_STATE_TTL_SECONDS = int(
    os.environ.get("SESSION_STATE_TTL_SECONDS", "3600")
)

# Cap the server-side undo stack so the item stays small.
MAX_UNDO_ENTRIES = 20


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (allows mocking in tests)."""
    return boto3.resource("dynamodb")


def get_current_timestamp() -> int:
    """Get current Unix timestamp (allows mocking in tests)."""
    return int(time.time())


def make_session_id(user_id: str, nation_slug: str) -> str:
    """
    Build the opaque session id for confirmation/undo state.

    Derived solely from the verified identity claims so it cannot be forged or
    aimed at another user's session. The nation slug is length-prefixed so the
    encoding is unambiguous even if a field were ever to contain the delimiter
    (no two distinct (user, nation) pairs can collide on the same session id).
    """
    return f"v1:{len(nation_slug)}:{nation_slug}#{user_id}"


def compute_tool_id(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Compute a stable, deterministic id for a (tool, input) pair.

    Uses SHA-256 over the canonicalised input rather than the builtin ``hash()``,
    which is salted per process (``PYTHONHASHSEED``) and would therefore differ
    between the request that prompts for confirmation and the follow-up request
    that confirms it — breaking the round-trip and the server-side record match.
    """
    canonical = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(f"{tool_name}:{canonical}".encode("utf-8")).hexdigest()
    return f"{tool_name}_{digest[:16]}"


def _table() -> Any:
    return get_dynamodb_resource().Table(SESSION_STATE_TABLE)


def record_pending_confirmation(session_id: str, tool_id: str) -> None:
    """
    Record that the server legitimately prompted ``session_id`` to confirm
    ``tool_id``.

    Only a tool_id recorded here may later be honoured as confirmed. Best-effort:
    on failure the confirmation simply will not be authorised on resubmission
    (the user is re-prompted), so the gate fails closed.
    """
    expires_at = get_current_timestamp() + SESSION_STATE_TTL_SECONDS
    try:
        _table().update_item(
            Key={"session_id": session_id},
            UpdateExpression="ADD pending_tool_ids :tid SET expires_at = :ttl",
            ExpressionAttributeValues={
                ":tid": {tool_id},
                ":ttl": expires_at,
            },
        )
    except ClientError as e:
        logger.error(
            f"Failed to record pending confirmation for session {session_id}: {e}"
        )


def filter_authorized_confirmations(
    session_id: str, tool_ids: list[str] | set[str]
) -> set[str]:
    """
    Return the subset of client-supplied ``tool_ids`` that the server actually
    prompted for in this session.

    This is the authoritative check that closes the bypass: a forged tool_id the
    server never issued a ``confirmation_required`` for is dropped here, so it
    cannot execute a destructive tool without a real confirmation round-trip.
    Fails closed (returns empty) on any error.
    """
    requested = {t for t in tool_ids if t}
    if not requested:
        return set()

    try:
        response = _table().get_item(
            Key={"session_id": session_id},
            ProjectionExpression="pending_tool_ids",
        )
    except ClientError as e:
        logger.error(
            f"Failed to read pending confirmations for session {session_id}: {e}"
        )
        return set()

    item = response.get("Item") or {}
    pending = item.get("pending_tool_ids") or set()
    # DynamoDB returns string sets as Python sets; be defensive about lists too.
    pending_set = set(pending)
    return requested & pending_set


def consume_confirmation(session_id: str, tool_id: str) -> None:
    """
    Remove a confirmation once it has been honoured so it cannot be replayed for
    a different agent turn. Best-effort.
    """
    try:
        _table().update_item(
            Key={"session_id": session_id},
            UpdateExpression="DELETE pending_tool_ids :tid",
            ExpressionAttributeValues={":tid": {tool_id}},
        )
    except ClientError as e:
        logger.error(
            f"Failed to consume confirmation {tool_id} for session {session_id}: {e}"
        )


def append_undo_entry(session_id: str, entry: dict[str, Any]) -> None:
    """
    Append a server-observed undoable action to the session's undo stack.

    The stack is stored as a JSON string (preserving exact id types) and capped
    to the most recent ``MAX_UNDO_ENTRIES``. Best-effort / fails open.
    """
    try:
        stack = get_undo_stack(session_id)
        stack.append(entry)
        stack = stack[-MAX_UNDO_ENTRIES:]
        expires_at = get_current_timestamp() + SESSION_STATE_TTL_SECONDS
        _table().update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET undo_stack_json = :stack, expires_at = :ttl",
            ExpressionAttributeValues={
                ":stack": json.dumps(stack, ensure_ascii=False),
                ":ttl": expires_at,
            },
        )
    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to append undo entry for session {session_id}: {e}")


def get_undo_stack(session_id: str) -> list[dict[str, Any]]:
    """
    Return the server-maintained undo stack for a session (never the client's).

    Fails open: returns an empty list on any error so undo simply offers no
    history rather than blocking the request.
    """
    try:
        response = _table().get_item(
            Key={"session_id": session_id},
            ProjectionExpression="undo_stack_json",
        )
    except ClientError as e:
        logger.error(f"Failed to read undo stack for session {session_id}: {e}")
        return []

    item = response.get("Item") or {}
    raw = item.get("undo_stack_json")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [e for e in parsed if isinstance(e, dict)]
