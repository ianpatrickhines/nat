"""
Tests for the EMF-based CloudWatch metrics helper.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.lambdas.shared import metrics


@pytest.fixture(autouse=True)
def _enable_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure metrics are enabled for these tests regardless of the environment."""
    monkeypatch.delenv("NAT_DISABLE_METRICS", raising=False)


def _capture(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the module logger so we can inspect emitted EMF lines."""
    fake_logger = MagicMock()
    monkeypatch.setattr(metrics, "logger", fake_logger)
    return fake_logger


def _emf_payloads(fake_logger: MagicMock) -> list[dict[str, Any]]:
    """Return parsed EMF dicts, ignoring non-JSON (human-readable) log lines."""
    payloads: list[dict[str, Any]] = []
    for call in fake_logger.info.call_args_list:
        # EMF lines are emitted as a single positional JSON string with no
        # logging format args; the human-readable summary uses %s args.
        if len(call.args) != 1:
            continue
        try:
            payloads.append(json.loads(call.args[0]))
        except (TypeError, ValueError):
            continue
    return payloads


class TestEmitMetric:
    def test_emits_valid_emf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)
        monkeypatch.setattr(metrics, "ENVIRONMENT", "prod")
        monkeypatch.setattr(metrics, "METRICS_NAMESPACE", "Nat")

        metrics.emit_metric("AgentError", 1.0)

        fake_logger.info.assert_called_once()
        payload = json.loads(fake_logger.info.call_args[0][0])
        assert payload["Environment"] == "prod"
        assert payload["AgentError"] == 1.0
        cw = payload["_aws"]["CloudWatchMetrics"][0]
        assert cw["Namespace"] == "Nat"
        assert cw["Dimensions"] == [["Environment"]]
        assert cw["Metrics"][0] == {"Name": "AgentError", "Unit": "Count"}
        assert isinstance(payload["_aws"]["Timestamp"], int)

    def test_properties_are_attached_but_not_dimensions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_logger = _capture(monkeypatch)

        metrics.emit_metric(
            "NationNotFound", 1.0, properties={"nation_slug": "acme"}
        )

        payload = json.loads(fake_logger.info.call_args[0][0])
        assert payload["nation_slug"] == "acme"
        # nation_slug must NOT become a metric dimension
        assert payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [["Environment"]]

    def test_property_cannot_clobber_reserved_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_logger = _capture(monkeypatch)

        metrics.emit_metric(
            "AgentError", 7.0, properties={"AgentError": 999, "Environment": "x"}
        )

        payload = json.loads(fake_logger.info.call_args[0][0])
        assert payload["AgentError"] == 7.0  # not clobbered by property

    def test_disabled_emits_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)
        monkeypatch.setenv("NAT_DISABLE_METRICS", "true")

        metrics.emit_metric("AgentError")

        fake_logger.info.assert_not_called()

    def test_custom_unit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)

        metrics.emit_metric(
            metrics.AGENT_LATENCY_MS, 1234.0, metrics.UNIT_MILLISECONDS
        )

        payload = json.loads(fake_logger.info.call_args[0][0])
        assert payload["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Unit"] == "Milliseconds"


class TestRecordCacheUsage:
    def test_cache_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)

        metrics.record_cache_usage(
            {"cache_read_input_tokens": 19000, "cache_creation_input_tokens": 0},
            "acme",
        )

        emitted = _emf_payloads(fake_logger)
        names = {k for p in emitted for k in p if k not in ("_aws", "Environment", "nation_slug")}
        assert metrics.CACHE_READ_TOKENS in names
        assert metrics.CACHE_HIT in names
        assert metrics.CACHE_MISS not in names

    def test_cache_miss(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)

        metrics.record_cache_usage(
            {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 19000}
        )

        emitted = _emf_payloads(fake_logger)
        names = {k for p in emitted for k in p if k not in ("_aws", "Environment")}
        assert metrics.CACHE_MISS in names
        assert metrics.CACHE_HIT not in names

    def test_none_usage_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_logger = _capture(monkeypatch)
        metrics.record_cache_usage(None)
        fake_logger.info.assert_not_called()

    def test_unparseable_usage_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _capture(monkeypatch)
        # Should swallow the bad value and not raise.
        metrics.record_cache_usage({"cache_read_input_tokens": object()})  # type: ignore[dict-item]
