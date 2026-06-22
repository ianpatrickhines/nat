"""
CloudWatch custom metrics via the Embedded Metric Format (EMF).

Emitting a metric here means writing a single structured JSON line to the
Lambda's CloudWatch Logs. CloudWatch automatically extracts those lines into
custom metrics in the ``Nat`` namespace -- no extra IAM permissions, no
synchronous ``PutMetricData`` API call (which would add latency to every
request, including the SSE streaming path), and the raw event is still queryable
in CloudWatch Logs Insights.

See: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html

Design notes
------------
* The only **dimension** is ``Environment`` (dev/staging/prod). Keeping the
  dimension set tiny and low-cardinality means alarms aggregate across all
  nations and stay cheap. Higher-cardinality context (nation_slug, error_type,
  the failing API path) is attached as non-dimension *properties*: it shows up
  in the log event for Logs Insights queries but does not multiply the number
  of billed metric streams.
* This module imports only the standard library, so it is safe to bundle into
  every Lambda package without pulling in extra dependencies.
* Set ``NAT_DISABLE_METRICS=true`` to silence emission (used in tests / local).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger()

# Namespace and dimension values
METRICS_NAMESPACE = os.environ.get("METRICS_NAMESPACE", "Nat")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

# ---------------------------------------------------------------------------
# Metric names. Defined once here so handlers (which emit) and the
# CloudFormation alarms / dashboard (which reference) cannot drift apart on
# spelling. If you rename one of these, update infrastructure/template.yaml.
# ---------------------------------------------------------------------------
SUBSCRIPTION_VERIFICATION = "SubscriptionVerification"
SUBSCRIPTION_VERIFICATION_FAILURE = "SubscriptionVerificationFailure"
QUERY_LIMIT_HIT = "QueryLimitHit"
NATION_NOT_FOUND = "NationNotFound"
NB_API_ERROR = "NBApiError"
TOKEN_REFRESH_FAILURE = "TokenRefreshFailure"
STRIPE_WEBHOOK_FAILURE = "StripeWebhookFailure"
AGENT_LATENCY_MS = "AgentLatencyMs"
AGENT_ERROR = "AgentError"
CACHE_READ_TOKENS = "CacheReadInputTokens"
CACHE_CREATION_TOKENS = "CacheCreationInputTokens"
CACHE_HIT = "CacheHit"
CACHE_MISS = "CacheMiss"

# Units understood by CloudWatch (subset we use)
UNIT_COUNT = "Count"
UNIT_MILLISECONDS = "Milliseconds"


def _metrics_disabled() -> bool:
    """Metrics are emitted unless explicitly disabled (e.g. in tests)."""
    return os.environ.get("NAT_DISABLE_METRICS", "").lower() == "true"


def emit_metric(
    name: str,
    value: float = 1.0,
    unit: str = UNIT_COUNT,
    properties: dict[str, Any] | None = None,
) -> None:
    """
    Emit a single custom metric in EMF format to the Lambda logs.

    Args:
        name: Metric name (use the constants defined in this module).
        value: Metric value. Defaults to 1.0 (a simple "it happened" counter).
        unit: CloudWatch unit, e.g. ``"Count"`` or ``"Milliseconds"``.
        properties: Optional high-cardinality context (nation_slug, error_type,
            …). Attached to the log event for Logs Insights but NOT used as a
            metric dimension.

    Emission never raises: observability must not be able to break a request.
    """
    if _metrics_disabled():
        return

    try:
        emf: dict[str, Any] = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": METRICS_NAMESPACE,
                        "Dimensions": [["Environment"]],
                        "Metrics": [{"Name": name, "Unit": unit}],
                    }
                ],
            },
            "Environment": ENVIRONMENT,
            name: value,
        }
        if properties:
            for key, prop_value in properties.items():
                # Never let a property clobber the reserved keys.
                if key not in ("_aws", "Environment", name):
                    emf[key] = prop_value
        logger.info(json.dumps(emf, default=str))
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning(f"Failed to emit metric {name}: {exc}")


def emit_count(name: str, properties: dict[str, Any] | None = None) -> None:
    """Convenience wrapper: emit a count of 1 for ``name``."""
    emit_metric(name, 1.0, UNIT_COUNT, properties)


def record_cache_usage(usage: dict[str, Any] | None, nation_slug: str | None = None) -> None:
    """
    Record prompt-cache effectiveness from an Anthropic ``usage`` payload.

    The Claude Agent SDK surfaces token usage on ``ResultMessage.usage``. The
    Anthropic API reports cache activity via ``cache_read_input_tokens`` (tokens
    served from cache -- the savings) and ``cache_creation_input_tokens`` (tokens
    written to the cache on a miss). A non-zero ``cache_read_input_tokens`` is the
    ground-truth confirmation that prompt caching is actually active.

    Emits ``CacheReadInputTokens`` / ``CacheCreationInputTokens`` (token counts)
    plus a ``CacheHit`` or ``CacheMiss`` counter, and logs a human-readable
    summary so cache effectiveness is visible in the logs even before the metric
    aggregates.
    """
    if not usage:
        return

    try:
        cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens", 0) or 0)
    except (TypeError, ValueError):
        logger.warning(f"Unparseable usage payload for cache metrics: {usage!r}")
        return

    props = {"nation_slug": nation_slug} if nation_slug else None

    emit_metric(CACHE_READ_TOKENS, float(cache_read), UNIT_COUNT, props)
    emit_metric(CACHE_CREATION_TOKENS, float(cache_creation), UNIT_COUNT, props)

    if cache_read > 0:
        emit_count(CACHE_HIT, props)
    else:
        emit_count(CACHE_MISS, props)

    logger.info(
        "Prompt cache usage: cache_read_input_tokens=%s cache_creation_input_tokens=%s "
        "caching_active=%s",
        cache_read,
        cache_creation,
        cache_read > 0,
    )
