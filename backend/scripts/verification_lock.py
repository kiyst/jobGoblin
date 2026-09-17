"""Cross-platform, non-blocking exclusive advisory file locking.

Used by `verification_coordinator.py` to prove ownership of its own run
directory for the *entire* duration of a receipt-eligible verification
run: the coordinator acquires this lock immediately after creating its
run directory and holds it open until that run directory is removed.
Stale-directory cleanup (`cleanup_stale_coordinator_dirs`) uses a
non-blocking acquire attempt as its provable-abandonment test -- a
directory whose lock can be acquired has no live owner and is safe to
remove; one whose lock is still held by another process is never
touched, regardless of age. This is deliberately not a PID-liveness
check (unreliable across platforms, and racy against PID reuse) -- an OS
advisory lock is released automatically if the owning process exits or
crashes, by the kernel itself, which is exactly the "provable
abandonment" signal required.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import BinaryIO


class LockHandle:
    """An acquired exclusive lock. Call `release()` exactly once, when
    the owning run is completely finished with the locked directory."""

    def __init__(self, file: BinaryIO, path: Path) -> None:
        self._file = file
        self.path = path
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        _unlock(self._file)
        self._file.close()
        self._released = True


def _unlock(file: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        file.seek(0)
        with contextlib.suppress(OSError):
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def try_acquire_exclusive_lock(path: Path) -> LockHandle | None:
    """Attempts to acquire an exclusive, non-blocking lock on `path`
    (created if it does not exist). Returns a `LockHandle` on success, or
    `None` if another process already holds it -- never blocks, never
    raises for the "already locked" case."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file = open(path, "a+b")  # noqa: SIM115 -- lifetime is the returned LockHandle's, not this scope's
    try:
        if file.seek(0, 2) == 0:  # empty -- give it one byte to lock
            file.write(b"L")
            file.flush()
        if sys.platform == "win32":
            import msvcrt

            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                file.close()
                return None
        else:
            import fcntl

            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                file.close()
                return None
        return LockHandle(file, path)
    except Exception:
        file.close()
        raise
