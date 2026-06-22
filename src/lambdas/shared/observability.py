"""
Optional Sentry error tracking for Lambda handlers.

Every handler calls :func:`init_sentry` at entry and :func:`capture_exception`
in its top-level ``except`` block. Both functions are **no-ops** unless:

1. the ``sentry-sdk`` package is importable, and
2. a DSN is configured (``SENTRY_DSN`` env var, or the name of a Secrets
   Manager secret in ``SENTRY_DSN_SECRET``).

This keeps the wiring inert in tests/local and in any environment where Sentry
has not been provisioned, while making it a one-secret change to turn on in
production. Nothing here can raise into a request path.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger()

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
SENTRY_DSN_ENV = "SENTRY_DSN"
SENTRY_DSN_SECRET_ENV = "SENTRY_DSN_SECRET"
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

# Tracks whether init has run so we only initialise once per warm container.
_initialized = False
_active = False


def _resolve_dsn() -> str | None:
    """Resolve the Sentry DSN from env var or a Secrets Manager secret name."""
    dsn = os.environ.get(SENTRY_DSN_ENV, "").strip()
    if dsn:
        return dsn

    secret_name = os.environ.get(SENTRY_DSN_SECRET_ENV, "").strip()
    if not secret_name:
        return None

    try:
        import boto3  # imported lazily; available in the Lambda runtime

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        secret = response.get("SecretString", "") or ""
        try:
            data = json.loads(secret)
            return str(data.get("dsn") or data.get("sentry_dsn") or secret) or None
        except json.JSONDecodeError:
            return secret or None
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning(f"Could not resolve Sentry DSN from secret: {exc}")
        return None


def init_sentry() -> bool:
    """
    Initialise Sentry if a DSN is configured and the SDK is installed.

    Idempotent and safe to call on every invocation. Returns ``True`` when Sentry
    is active, ``False`` otherwise (which is the normal case when no DSN is set).
    """
    global _initialized, _active
    if _initialized:
        return _active

    _initialized = True

    dsn = _resolve_dsn()
    if not dsn:
        logger.debug("Sentry DSN not configured; error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=ENVIRONMENT,
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            integrations=[AwsLambdaIntegration(timeout_warning=True)],
        )
        _active = True
        logger.info("Sentry error tracking initialised")
    except ImportError:
        logger.warning("sentry-sdk not installed; error tracking disabled")
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning(f"Failed to initialise Sentry: {exc}")

    return _active


def capture_exception(exc: BaseException, **context: Any) -> None:
    """
    Report an exception to Sentry when active; otherwise a no-op.

    Extra keyword arguments are attached as Sentry tags (e.g. ``nation_slug=...``)
    to aid triage. Never raises.
    """
    if not _active:
        return
    try:
        import sentry_sdk

        if context:
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_tag(key, str(value))
                sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_exception(exc)
    except Exception as report_exc:  # pragma: no cover - defensive only
        logger.warning(f"Failed to report exception to Sentry: {report_exc}")
