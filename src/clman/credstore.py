"""Backend for Claude Code's *active* credential: Keychain-first on macOS,
plaintext ``.credentials.json`` everywhere else (and as the macOS fallback).

Behaviors mirrored from how Claude Code itself operates (via claude-swap's
findings):

- Reads try the Keychain item first (when usable), then the plaintext file —
  a macOS login whose credential only exists in the file is still found.
- A successful Keychain write also rewrites an **already-present**
  ``.credentials.json`` with the same content — never creating one — so a
  running session's file-mtime cache invalidation fires and it hot-reloads
  the new account. Keychain-only setups keep their fileless posture (their
  absent-file path hot-reloads via Claude Code's ~30s Keychain cache).
- A file-mode write best-effort deletes any stale Keychain item, because
  Claude Code reads the Keychain first and would resurrect the old account.
"""

from __future__ import annotations

import sys

from clman import keychain
from clman.errors import ClmanError
from clman.fsio import atomic_write_text
from clman.paths import credentials_path


def _warn(message: str) -> None:
    print(f"clswap: warning: {message}", file=sys.stderr)


def read_active_credentials() -> str:
    """The active credential string, ```` "" ```` when logged out everywhere."""
    if keychain.use_keychain():
        try:
            value = keychain.call(
                keychain.get_password, keychain.ACTIVE_SERVICE, keychain.account_name()
            )
            if value:
                return value
        except keychain.KEYCHAIN_ERRORS as e:
            _warn(f"Keychain read failed, trying file: {e}")
    creds_file = credentials_path()
    if not creds_file.exists():
        return ""
    try:
        return creds_file.read_text(encoding="utf-8")
    except OSError as e:
        raise ClmanError(f"Cannot read {creds_file}: {e}")


def write_active_credentials(credentials: str) -> None:
    if keychain.use_keychain():
        try:
            keychain.call(
                keychain.set_password,
                keychain.ACTIVE_SERVICE,
                keychain.account_name(),
                credentials,
            )
        except keychain.KEYCHAIN_ERRORS as e:
            _warn(f"Keychain write failed, falling back to file: {e}")
        else:
            _refresh_credentials_file_mtime(credentials)
            return
    try:
        atomic_write_text(credentials_path(), credentials)
    except OSError as e:
        raise ClmanError(f"Cannot write {credentials_path()}: {e}")
    if keychain.is_macos():
        # Claude Code reads the Keychain before the file; a stale item there
        # would shadow the file we just wrote.
        try:
            keychain.delete_password(keychain.ACTIVE_SERVICE, keychain.account_name())
        except Exception:
            pass  # best-effort: a down Keychain can't be cleaned now


def _refresh_credentials_file_mtime(credentials: str) -> None:
    """Rewrite an already-present credentials file after a Keychain write.

    Never creates the file. Best-effort: the Keychain write is authoritative
    and already succeeded — failure here only delays a running session's
    hot-reload until restart.
    """
    creds_file = credentials_path()
    if not creds_file.exists():
        return
    try:
        atomic_write_text(creds_file, credentials)
    except OSError as e:
        _warn(f"could not refresh {creds_file.name} after Keychain write: {e}")
