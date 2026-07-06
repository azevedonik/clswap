"""Cooperate with Claude Code's advisory locks while mutating its files.

Claude Code guards its OAuth token refresh with the npm ``proper-lockfile``
package on the config home directory, and its ``~/.claude.json`` writes with
the same mechanism on the config file (protocol documented by claude-swap):

- The lock artifact is a **directory** at ``<target>.lock``; mkdir atomicity
  is the mutex.
- A lock is stale when its mtime is older than 10 s; live holders touch the
  mtime every 5 s, and a stale lock may be removed and taken over.

Holding these locks while swapping closes the one real race with a running
Claude Code: its refresh reads credentials, refreshes over the network, and
saves - all under ``~/.claude.lock`` - so a swap landing inside that window
would be overwritten by the refreshed old-account token.
"""

from __future__ import annotations

import os
import random
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from clman.errors import LockTimeoutError
from clman.paths import claude_config_home, global_config_path

STALENESS_S = 10.0
TOUCH_INTERVAL_S = 3.0
DEFAULT_TIMEOUT_S = 9.0


def credentials_lock_dir() -> Path:
    home = claude_config_home()
    return home.parent / (home.name + ".lock")


def config_lock_dir() -> Path:
    path = global_config_path()
    return path.parent / (path.name + ".lock")


@contextmanager
def proper_lockfile(
    lock_dir: Path,
    *,
    timeout: float | None = None,
    staleness: float = STALENESS_S,
):
    """Acquire a proper-lockfile-compatible directory lock.

    Blocks up to ``timeout`` seconds, taking over locks whose mtime is older
    than ``staleness``; touches the directory mtime while held; removes it on
    exit. Raises LockTimeoutError when the lock stays held past ``timeout``.
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT_S
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            pass
        if time.monotonic() - start > timeout:
            raise LockTimeoutError(
                f"Could not acquire {lock_dir.name} - Claude Code appears to be "
                "refreshing credentials. Retry in a few seconds."
            )
        try:
            held_mtime = os.stat(lock_dir).st_mtime
        except FileNotFoundError:
            continue  # holder released between mkdir and stat; retry now
        if time.time() - held_mtime > staleness:
            try:
                os.rmdir(lock_dir)
            except OSError:
                time.sleep(0.05)
            continue
        time.sleep(0.1 + random.random() * 0.15)

    stop = threading.Event()

    def _touch() -> None:
        while not stop.wait(TOUCH_INTERVAL_S):
            try:
                os.utime(lock_dir)
            except OSError:
                return

    toucher = threading.Thread(target=_touch, daemon=True)
    toucher.start()
    try:
        yield
    finally:
        stop.set()
        toucher.join(timeout=1.0)
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


@contextmanager
def claude_credentials_lock(*, timeout: float | None = None):
    with proper_lockfile(credentials_lock_dir(), timeout=timeout):
        yield


@contextmanager
def claude_config_lock(*, timeout: float | None = None):
    with proper_lockfile(config_lock_dir(), timeout=timeout):
        yield
