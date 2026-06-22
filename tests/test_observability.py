"""
Tests for the optional Sentry error-tracking helper.

These verify the no-op behaviour (the common case where no DSN is configured)
without requiring a live Sentry project.
"""

from __future__ import annotations

import pytest

from src.lambdas.shared import observability


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level init flags and clear DSN env between tests."""
    monkeypatch.setattr(observability, "_initialized", False)
    monkeypatch.setattr(observability, "_active", False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_DSN_SECRET", raising=False)


class TestInitSentry:
    def test_no_dsn_is_noop(self) -> None:
        assert observability.init_sentry() is False
        assert observability._active is False

    def test_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_resolve() -> None:
            calls["n"] += 1
            return None

        monkeypatch.setattr(observability, "_resolve_dsn", fake_resolve)
        observability.init_sentry()
        observability.init_sentry()
        # _resolve_dsn must only be consulted once (init is cached).
        assert calls["n"] == 1


class TestResolveDsn:
    def test_env_var_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "https://abc@example.com/1")
        assert observability._resolve_dsn() == "https://abc@example.com/1"

    def test_returns_none_when_unconfigured(self) -> None:
        assert observability._resolve_dsn() is None


class TestCaptureException:
    def test_noop_when_inactive(self) -> None:
        # Must not raise even though Sentry was never initialised.
        observability.capture_exception(ValueError("boom"), nation_slug="acme")
