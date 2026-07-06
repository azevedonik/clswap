import os
import time

import pytest

from clman.errors import LockTimeoutError
from clman.locks import proper_lockfile


def test_acquire_creates_and_releases_dir(tmp_path):
    lock = tmp_path / "x.lock"
    with proper_lockfile(lock):
        assert lock.is_dir()
    assert not lock.exists()


def test_held_lock_times_out(tmp_path):
    lock = tmp_path / "x.lock"
    lock.mkdir()  # fresh mtime -> a live holder
    with pytest.raises(LockTimeoutError):
        with proper_lockfile(lock, timeout=0.5):
            pass
    lock.rmdir()


def test_stale_lock_is_taken_over(tmp_path):
    lock = tmp_path / "x.lock"
    lock.mkdir()
    stale = time.time() - 60
    os.utime(lock, (stale, stale))
    with proper_lockfile(lock, timeout=2.0, staleness=10.0):
        assert lock.is_dir()
    assert not lock.exists()
