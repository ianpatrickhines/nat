"""
Input validation helpers shared across Lambda handlers.

The canonical home for ``nation_slug`` format validation. A nation slug flows
directly into DynamoDB keys, Secrets Manager secret names
(``nat/nation/{slug}/nb-tokens``) and NationBuilder API URLs
(``https://{slug}.nationbuilder.com``), so every entry point that accepts one
must reject malformed values before they are used.

Only the Lambdas that bundle ``shared/`` at deploy time (the agent handlers)
import this module. The standalone handlers (stripe_checkout, stripe_webhook,
nb_oauth_callback) are packaged without ``shared/`` and inline an identical
``NATION_SLUG_PATTERN`` instead.
"""

from __future__ import annotations

import re
from typing import Any

# NationBuilder slugs are lowercase alphanumeric plus hyphen. The 63-char ceiling
# matches a DNS label (slugs appear as the subdomain of *.nationbuilder.com).
NATION_SLUG_PATTERN = re.compile(r"^[a-z0-9-]{1,63}\Z")


class InvalidNationSlugError(ValueError):
    """Raised when a nation_slug does not match the required format."""


def is_valid_nation_slug(slug: Any) -> bool:
    """Return True if *slug* is a non-empty, well-formed nation slug."""
    return isinstance(slug, str) and NATION_SLUG_PATTERN.match(slug) is not None


def validate_nation_slug(slug: Any) -> str:
    """Return *slug* unchanged if valid, else raise :class:`InvalidNationSlugError`."""
    if not is_valid_nation_slug(slug):
        raise InvalidNationSlugError(
            f"Invalid nation_slug format: {slug!r} (must match ^[a-z0-9-]{{1,63}}$)"
        )
    # is_valid_nation_slug guarantees a str; assert narrows it for the type checker.
    assert isinstance(slug, str)
    return slug
