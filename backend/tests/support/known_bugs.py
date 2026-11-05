"""Confirmed app bugs that are not fixed yet. Each has exactly one test, a strict xfail.

Mark the test with `@known_bug(reason)` and put the one check that the bug breaks inside
`with fails_until_fixed():`. Only that check failing counts as the expected failure; a
failure anywhere else (a step before the check, a fixture, a request no test registered)
is reported as a normal failure, so it can never pass for the bug and hide a fix. Once the
bug is fixed the check passes, and pytest reports the test as XPASS(strict), a failure:
then remove the marker and the `with` line, and keep the test.
"""

import contextlib
from collections.abc import Iterator

import pytest


class StillBroken(Exception):
    """The check that a known bug breaks failed, as it does while the bug is there."""


def known_bug(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, raises=StillBroken, reason=reason)


@contextlib.contextmanager
def fails_until_fixed() -> Iterator[None]:
    """The check of the correct behavior that the bug breaks."""
    try:
        yield
    except (AssertionError, pytest.fail.Exception) as failure:  # an assert, or pytest.raises
        raise StillBroken(str(failure)) from failure
