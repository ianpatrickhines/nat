"""
Unit tests for the stdlib HS256 session-token (JWT) helper.

Covers minting, verification, expiry, signature tampering, forged secrets,
malformed input, bearer extraction, and the request-authentication convenience.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.shared.session_token import (
    SessionContext,
    SessionTokenError,
    authenticate_request,
    extract_bearer_token,
    get_session_secret,
    mint_session_token,
    reset_secret_cache,
    verify_session_token,
)

SECRET = "unit-test-secret"
USER_ID = "user-abc"
NATION = "acme"


class TestMintAndVerify:
    def test_roundtrip_returns_claims(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET)
        claims = verify_session_token(token, SECRET)
        assert claims["user_id"] == USER_ID
        assert claims["nation_slug"] == NATION
        assert claims["exp"] > claims["iat"]

    def test_token_has_three_segments(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET)
        assert len(token.split(".")) == 3

    def test_mint_requires_identity(self) -> None:
        with pytest.raises(ValueError):
            mint_session_token("", NATION, SECRET)
        with pytest.raises(ValueError):
            mint_session_token(USER_ID, "", SECRET)

    def test_ttl_controls_expiry(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET, ttl_seconds=100, now=1000)
        claims = verify_session_token(token, SECRET, now=1050)
        assert claims["exp"] == 1100


class TestVerifyFailures:
    def test_wrong_secret_rejected(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET)
        with pytest.raises(SessionTokenError) as exc:
            verify_session_token(token, "different-secret")
        assert exc.value.http_status == 401

    def test_expired_token_rejected(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET, ttl_seconds=100, now=1000)
        with pytest.raises(SessionTokenError) as exc:
            verify_session_token(token, SECRET, now=2000)
        assert exc.value.code == "TOKEN_EXPIRED"

    def test_exactly_at_expiry_rejected(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET, ttl_seconds=100, now=1000)
        with pytest.raises(SessionTokenError):
            verify_session_token(token, SECRET, now=1100)

    def test_tampered_payload_rejected(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET)
        header, payload, sig = token.split(".")
        flipped = "A" if payload[-1] != "A" else "B"
        tampered = f"{header}.{payload[:-1]}{flipped}.{sig}"
        with pytest.raises(SessionTokenError):
            verify_session_token(tampered, SECRET)

    def test_alg_none_attack_rejected(self) -> None:
        # An attacker-crafted unsigned token must not be accepted.
        import base64

        def seg(data: dict[str, object]) -> str:
            raw = json.dumps(data).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        forged = (
            seg({"alg": "none", "typ": "JWT"})
            + "."
            + seg({"user_id": USER_ID, "nation_slug": NATION, "exp": 9999999999})
            + "."
        )
        with pytest.raises(SessionTokenError):
            verify_session_token(forged, SECRET)

    def test_malformed_token_rejected(self) -> None:
        with pytest.raises(SessionTokenError):
            verify_session_token("not-a-jwt", SECRET)

    def test_empty_token_rejected(self) -> None:
        with pytest.raises(SessionTokenError) as exc:
            verify_session_token("", SECRET)
        assert exc.value.code == "MISSING_TOKEN"


class TestExtractBearer:
    def test_extracts_token(self) -> None:
        assert extract_bearer_token({"Authorization": "Bearer abc.def.ghi"}) == "abc.def.ghi"

    def test_case_insensitive_header_and_scheme(self) -> None:
        assert extract_bearer_token({"authorization": "bearer xyz"}) == "xyz"

    def test_missing_header_rejected(self) -> None:
        with pytest.raises(SessionTokenError) as exc:
            extract_bearer_token({})
        assert exc.value.code == "MISSING_TOKEN"

    def test_non_bearer_rejected(self) -> None:
        with pytest.raises(SessionTokenError):
            extract_bearer_token({"Authorization": "Basic abc"})

    def test_empty_bearer_rejected(self) -> None:
        with pytest.raises(SessionTokenError):
            extract_bearer_token({"Authorization": "Bearer "})


class TestAuthenticateRequest:
    def test_returns_identity_from_claims(self) -> None:
        token = mint_session_token(USER_ID, NATION, SECRET)
        event = {"headers": {"Authorization": f"Bearer {token}"}}
        ctx = authenticate_request(event, secret=SECRET)
        assert isinstance(ctx, SessionContext)
        assert ctx.user_id == USER_ID
        assert ctx.nation_slug == NATION

    def test_cross_nation_token_cannot_claim_another_nation(self) -> None:
        # A token for nation A yields nation A regardless of any other input.
        token = mint_session_token(USER_ID, "nation-a", SECRET)
        event = {
            "headers": {
                "Authorization": f"Bearer {token}",
                "X-Nat-Nation-Slug": "nation-b",
            }
        }
        ctx = authenticate_request(event, secret=SECRET)
        assert ctx.nation_slug == "nation-a"

    def test_missing_token_raises(self) -> None:
        with pytest.raises(SessionTokenError):
            authenticate_request({"headers": {}}, secret=SECRET)


class TestGetSessionSecret:
    def setup_method(self) -> None:
        reset_secret_cache()

    def teardown_method(self) -> None:
        reset_secret_cache()

    def test_plain_string_secret(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "plain-secret"}
        with patch(
            "src.lambdas.shared.session_token.get_secrets_manager_client",
            return_value=client,
        ):
            assert get_session_secret() == "plain-secret"

    def test_json_secret_field(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {
            "SecretString": json.dumps({"secret": "json-secret"})
        }
        with patch(
            "src.lambdas.shared.session_token.get_secrets_manager_client",
            return_value=client,
        ):
            assert get_session_secret() == "json-secret"

    def test_secret_is_cached(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "cached"}
        with patch(
            "src.lambdas.shared.session_token.get_secrets_manager_client",
            return_value=client,
        ):
            get_session_secret()
            get_session_secret()
        # Only the first call hits Secrets Manager.
        assert client.get_secret_value.call_count == 1
