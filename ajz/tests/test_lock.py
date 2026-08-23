"""Tests for the one-refresh-at-a-time lock.

Jeff double-clicks a shortcut. When something takes a few seconds without obviously
working, clicking again is the normal human response — so concurrent runs are expected
input, not an exotic edge case.
"""

from __future__ import annotations

import pytest

from ajz.lock import AlreadyRunningError, single_instance


def test_a_second_refresh_is_refused_while_the_first_holds_the_lock(tmp_path):
    lock_path = tmp_path / "refresh.lock"
    with single_instance(lock_path):
        with pytest.raises(AlreadyRunningError):
            with single_instance(lock_path):
                pass


def test_the_lock_is_released_when_the_first_refresh_finishes(tmp_path):
    lock_path = tmp_path / "refresh.lock"
    with single_instance(lock_path):
        pass
    with single_instance(lock_path):  # must not raise
        pass


def test_the_lock_is_released_even_when_the_refresh_raises(tmp_path):
    """A failed run must not poison every later one.

    This is why the lock is an OS file lock rather than a lockfile holding a PID: the
    kernel drops it however the process ends, so there is no stale-lock state to reason
    about and no liveness check to get wrong.
    """
    lock_path = tmp_path / "refresh.lock"
    with pytest.raises(RuntimeError):
        with single_instance(lock_path):
            raise RuntimeError("network down")

    with single_instance(lock_path):  # must not raise
        pass


def test_an_unusable_lock_location_does_not_block_the_refresh(tmp_path):
    """Failing to refresh because we could not create a lock would be the worse outcome.

    The lock exists to stop a duplicate run wasting quota. It is not worth trading the
    entire feature for, so an unwritable location degrades to running unlocked.
    """
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("this is a file, so it cannot contain the lock")

    with single_instance(blocked / "refresh.lock"):
        pass  # reaching here at all is the assertion
