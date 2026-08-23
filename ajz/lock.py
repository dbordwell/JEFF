"""One refresh at a time.

Jeff double-clicks a shortcut to refresh. When something takes a few seconds and does
not immediately look like it is working, the natural human response is to click it
again — so two refreshes running at once is an expected input, not an exotic one.

Two of them are not catastrophic on their own (the workbook write is atomic, and each
run writes to its own temp file), but they burn double the API quota, race on the
history snapshot, and put two windows on screen, which is exactly the sort of thing
that makes a person believe the tool is broken.

The lock is an OS file lock rather than a lockfile-with-a-PID-in-it, deliberately. The
kernel releases it when the process dies, however it dies — so a crash or a force-quit
cannot leave behind a stale lock that blocks every future run. A PID file would need
liveness checks and a stale-entry policy, and that machinery would then be the thing
most likely to be wrong.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

from .config import app_dir

log = logging.getLogger(__name__)

LOCK_NAME = "refresh.lock"


class AlreadyRunningError(RuntimeError):
    """Another refresh holds the lock. Message is written to be read by Jeff."""


def _acquire(handle) -> bool:
    """Take an exclusive, non-blocking lock on an open file. False if someone has it."""
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def single_instance(lock_path: Path | None = None) -> Iterator[Path]:
    """Hold the refresh lock for the duration of the block.

    Raises AlreadyRunningError if another refresh is in progress. If the lock file
    cannot be created at all — an unwritable directory, say — we log and proceed rather
    than refusing to run: failing to refresh because we could not create a lock would be
    a worse outcome than the concurrency it prevents.
    """
    path = lock_path or (app_dir() / LOCK_NAME)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
    except OSError as exc:
        log.warning("could not open the lock file (%s); continuing without it", exc)
        yield path
        return

    try:
        if not _acquire(handle):
            raise AlreadyRunningError(
                "A refresh is already running. Give it a moment to finish."
            )
        yield path
    finally:
        handle.close()  # closing releases the lock on both platforms
