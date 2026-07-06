"""macOS Keychain access via the ``security`` CLI, plus the platform gate.

Same approach as Claude Code itself (and claude-swap): shell out to the stable
system ``security`` binary rather than linking Security.framework in-process,
so the Keychain item's creator never changes across tool upgrades and macOS
never shows a "wants to use your keychain" prompt.

Contract notes (mirroring ``security``'s actual behavior):

- ``find-generic-password -w`` prints the value plus one trailing newline;
  exit code 44 (errSecItemNotFound) means "no such item".
- Writes go through ``security -i`` (stdin) with the value hex-encoded via
  ``-X``, so the secret never appears in process argv. ``security -i`` reads
  lines with a 4096-byte buffer; anything longer would truncate mid-argument
  and corrupt the entry, so oversized payloads fall back to argv.
- Values must be printable text (``-w`` hex-encodes binary on read, breaking
  round-trips). Fine here: credentials are ASCII JSON.
- ``/usr/bin/security`` is pinned absolutely: a credential tool must not let
  an attacker-controlled ``security`` earlier on PATH intercept secrets.

This module also owns the per-process capability cache: the first Keychain
failure flips the process to file mode and it sticks, so one invocation can
never split-brain between backends. Import-safe everywhere; only meaningful
on macOS.
"""

from __future__ import annotations

import os
import subprocess
import sys

SECURITY_BIN = "/usr/bin/security"
_NOT_FOUND_RC = 44
_TIMEOUT_S = 5.0
# security -i uses a 4096-byte line buffer; keep headroom for the terminator.
_STDIN_LINE_LIMIT = 4096 - 64

# Keychain service of Claude Code's active OAuth credential (its own name).
ACTIVE_SERVICE = "Claude Code-credentials"
# Keychain service for clman's per-account snapshots.
SNAPSHOT_SERVICE = "clman"


class KeychainError(Exception):
    """A ``security`` invocation failed for a reason other than "not found"."""


# What callers may treat as "Keychain unusable -> use files": wrapper failures,
# raw timeouts, and a missing binary. Never catch bare Exception around these —
# a programming error should stay loud, not silently reroute to file mode.
KEYCHAIN_ERRORS = (KeychainError, subprocess.TimeoutExpired, OSError)


def is_macos() -> bool:
    return sys.platform == "darwin"


def account_name() -> str:
    """Keychain account for the active credential, matching Claude Code's
    ``getUsername()``: ``$USER``, then the OS user, then a stable fallback.

    Matching exactly matters — a divergent name would key a different item
    than Claude Code and the two could never see each other's login.
    """
    user = os.environ.get("USER")
    if user:
        return user
    try:
        import pwd  # POSIX-only; call sites are macOS-only

        return pwd.getpwuid(os.geteuid()).pw_name
    except Exception:
        return "claude-code-user"


def _run(argv: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv, input=stdin, capture_output=True, text=True, timeout=_TIMEOUT_S
        )
    except subprocess.TimeoutExpired as e:
        raise KeychainError(f"{argv[0]} timed out after {_TIMEOUT_S}s") from e


def get_password(service: str, account: str) -> str | None:
    """The stored value, or None when the item doesn't exist (rc 44).

    Raises KeychainError on any other failure (locked/denied/timeout) so a
    genuine miss is never confused with an unusable Keychain.
    """
    result = _run(
        [SECURITY_BIN, "find-generic-password", "-a", account, "-w", "-s", service]
    )
    if result.returncode == 0:
        # -w appends exactly one newline; strip only that.
        return result.stdout.removesuffix("\n")
    if result.returncode == _NOT_FOUND_RC:
        return None
    raise KeychainError(
        f"find-generic-password failed (rc={result.returncode}): {result.stderr.strip()}"
    )


def _stdin_quote(value: str) -> str:
    """Quote for a ``security -i`` command line (it re-parses shell-style)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_password(service: str, account: str, value: str) -> None:
    """Create or update an item (``-U``), keeping the secret out of argv.

    The value goes hex-encoded (``-X``) through ``security -i`` stdin; only a
    payload that would overflow the 4 KB stdin line buffer (and thus corrupt
    the write) falls back to argv.
    """
    hex_value = value.encode("utf-8").hex()
    line = (
        f"add-generic-password -U -a {_stdin_quote(account)} "
        f"-s {_stdin_quote(service)} -X {hex_value}\n"
    )
    if len(line.encode("utf-8")) <= _STDIN_LINE_LIMIT:
        result = _run([SECURITY_BIN, "-i"], stdin=line)
    else:
        result = _run(
            [SECURITY_BIN, "add-generic-password", "-U",
             "-a", account, "-s", service, "-X", hex_value]
        )
    if result.returncode != 0:
        raise KeychainError(
            f"add-generic-password failed (rc={result.returncode}): {result.stderr.strip()}"
        )


def delete_password(service: str, account: str) -> None:
    """Delete an item; already-absent (rc 44) counts as success."""
    result = _run(
        [SECURITY_BIN, "delete-generic-password", "-a", account, "-s", service]
    )
    if result.returncode in (0, _NOT_FOUND_RC):
        return
    raise KeychainError(
        f"delete-generic-password failed (rc={result.returncode}): {result.stderr.strip()}"
    )


# --- per-process capability cache -----------------------------------------
# None = not yet probed; True once an op succeeded; False (sticky) after the
# first failure. get_password returning None (rc 44) is a *success* — the
# Keychain answered.

_usable: bool | None = None


def use_keychain() -> bool:
    """Whether Keychain *writes* (and active reads) should be attempted."""
    return is_macos() and _usable is not False


def call(fn, *args):
    """Run a wrapper call through the capability cache.

    Success flips None -> True (never False -> True: once failed, file mode
    sticks for the process). A KEYCHAIN_ERRORS failure marks the Keychain
    unusable and re-raises so the caller can fall back.
    """
    global _usable
    try:
        result = fn(*args)
    except KEYCHAIN_ERRORS:
        _usable = False
        raise
    if _usable is None:
        _usable = True
    return result


def reset_capability_cache() -> None:
    """Test hook: forget what this process learned about the Keychain."""
    global _usable
    _usable = None
