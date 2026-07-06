""".claude-session discovery and parsing.

The file holds one account email on the first non-empty, non-``#`` line, and
is discovered by walking up from a start directory to the drive root; the
nearest file wins.
"""

from __future__ import annotations

from pathlib import Path

SESSION_FILENAME = ".claude-session"


def find_session_file(start: Path) -> Path | None:
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / SESSION_FILENAME
        if candidate.is_file():
            return candidate
    return None


def read_session_email(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None
