"""
Unit tests for shared nation_slug validation.
"""

from __future__ import annotations

import pytest

from src.lambdas.shared.validation import (
    InvalidNationSlugError,
    is_valid_nation_slug,
    validate_nation_slug,
)


VALID_SLUGS = [
    "testnation",
    "my-nation",
    "nation123",
    "a",
    "a" * 63,
    "0-9-abc",
]

INVALID_SLUGS = [
    "",  # empty
    "UPPER",  # uppercase
    "Mixed-Case",
    "has space",
    "under_score",
    "dots.here",
    "slash/here",
    "../../etc/passwd",  # path traversal
    "nation!",  # punctuation
    "a" * 64,  # too long (DNS label ceiling is 63)
    "naïve",  # non-ascii
    "legit-slug\n",  # trailing newline ($ anchor bypass — must use \Z)
    "legit\nslug",  # embedded newline
    "legit-slug\r\n",  # CRLF
]


@pytest.mark.parametrize("slug", VALID_SLUGS)
def test_is_valid_accepts(slug: str) -> None:
    assert is_valid_nation_slug(slug) is True


@pytest.mark.parametrize("slug", INVALID_SLUGS)
def test_is_valid_rejects(slug: str) -> None:
    assert is_valid_nation_slug(slug) is False


def test_is_valid_rejects_non_str() -> None:
    assert is_valid_nation_slug(None) is False  # type: ignore[arg-type]
    assert is_valid_nation_slug(123) is False  # type: ignore[arg-type]
    assert is_valid_nation_slug(["testnation"]) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("slug", VALID_SLUGS)
def test_validate_returns_slug(slug: str) -> None:
    assert validate_nation_slug(slug) == slug


@pytest.mark.parametrize("slug", INVALID_SLUGS)
def test_validate_raises(slug: str) -> None:
    with pytest.raises(InvalidNationSlugError):
        validate_nation_slug(slug)


def test_invalid_error_is_value_error() -> None:
    """InvalidNationSlugError is a ValueError so handlers can catch broadly."""
    assert issubclass(InvalidNationSlugError, ValueError)
