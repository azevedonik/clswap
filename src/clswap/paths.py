"""Path resolution for Claude Code's files and clswap's own store.

Mirrors Claude Code's resolution (as reverse-engineered by claude-swap) so we
read and write the same files it does:

- Config home: ``CLAUDE_CONFIG_DIR`` if set, else ``~/.claude``.
- Global config: ``<config_home>/.config.json`` if it exists (legacy), else
  ``(CLAUDE_CONFIG_DIR || $HOME)/.claude.json``.
- Credentials: ``<config_home>/.credentials.json``.
"""

from __future__ import annotations

import os
from pathlib import Path


def claude_config_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def global_config_path() -> Path:
    legacy = claude_config_home() / ".config.json"
    if legacy.exists():
        return legacy
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home()
    return base / ".claude.json"


def credentials_path() -> Path:
    return claude_config_home() / ".credentials.json"


def clswap_home() -> Path:
    env = os.environ.get("CLSWAP_HOME") or os.environ.get("CLMAN_HOME")
    return Path(env) if env else Path.home() / ".clswap"


def clman_home() -> Path:
    """Backward-compatible alias for integrations still importing this helper."""
    return clswap_home()


def accounts_dir() -> Path:
    return clswap_home() / "accounts"


def default_account_path() -> Path:
    return clswap_home() / "default"
