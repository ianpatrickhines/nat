"""Shared utilities for Lambda functions."""

# Lambda packages are built by flattening ``src/lambdas/shared`` to a top-level
# ``shared`` package, so the absolute ``src.lambdas.shared`` path does not
# resolve at runtime. Fall back to a relative import so this package imports
# cleanly in both the repo (pytest) layout and the flattened Lambda layout.
try:
    from src.lambdas.shared.subscription_middleware import (
        SubscriptionError,
        SubscriptionMiddleware,
        SubscriptionStatus,
        verify_subscription,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised only in Lambda
    from .subscription_middleware import (
        SubscriptionError,
        SubscriptionMiddleware,
        SubscriptionStatus,
        verify_subscription,
    )

__all__ = [
    "SubscriptionError",
    "SubscriptionMiddleware",
    "SubscriptionStatus",
    "verify_subscription",
]
