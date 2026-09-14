"""Genuine (non-mocked) tests, including a real subprocess holding the
lock to prove cross-process exclusion -- not merely in-process
simulation."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from scripts import verification_lock as lock


def test_acquire_and_release_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    handle = lock.try_acquire_exclusive_lock(path)
    assert handle is not None
    handle.release()


def test_second_in_process_acquire_fails_while_first_holds_it(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    first = lock.try_acquire_exclusive_lock(path)
    assert first is not None
    try:
        second = lock.try_acquire_exclusive_lock(path)
        assert second is None
    finally:
        first.release()


def test_acquire_succeeds_again_after_release(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    first = lock.try_acquire_exclusive_lock(path)
    assert first is not None
    first.release()

    second = lock.try_acquire_exclusive_lock(path)
    assert second is not None
    second.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    handle = lock.try_acquire_exclusive_lock(path)
    assert handle is not None
    handle.release()
    handle.release()  # must not raise


_HOLDER_SCRIPT = """
import sys
import time
from pathlib import Path
sys.path.insert(0, {backend_dir!r})
from scripts import verification_lock as lock

handle = lock.try_acquire_exclusive_lock(Path(sys.argv[1]))
if handle is None:
    print("FAILED_TO_ACQUIRE")
    sys.exit(1)
print("ACQUIRED", flush=True)
time.sleep(float(sys.argv[2]))
handle.release()
print("RELEASED", flush=True)
"""


def test_genuine_concurrent_process_holds_the_lock(tmp_path: Path) -> None:
    """Spawns a real second Python process that acquires and holds the
    lock for a short, fixed duration -- proving this module's exclusion
    is a genuine OS-level, cross-process guarantee, not merely an
    in-process Python object comparison."""
    backend_dir = str(Path(__file__).resolve().parent.parent)
    path = tmp_path / "run.lock"
    script = _HOLDER_SCRIPT.format(backend_dir=backend_dir)

    holder = subprocess.Popen(
        [sys.executable, "-c", script, str(path), "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Wait for the holder to genuinely acquire the lock before probing.
        deadline = time.monotonic() + 5.0
        acquired = False
        while time.monotonic() < deadline:
            line = holder.stdout.readline() if holder.stdout else ""
            if "ACQUIRED" in line:
                acquired = True
                break
        assert acquired, "holder subprocess never reported acquiring the lock"

        # While the real subprocess holds it, our own acquire must fail.
        blocked = lock.try_acquire_exclusive_lock(path)
        assert blocked is None

        holder.wait(timeout=10)
        assert holder.returncode == 0

        # Now that the holder process has exited (and the kernel released
        # its lock), acquisition must succeed.
        released = lock.try_acquire_exclusive_lock(path)
        assert released is not None
        released.release()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()
