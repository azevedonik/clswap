"""Reading the active Claude Code login and switching it to a stored account.

A switch, under Claude Code's own locks (see ``locks``):

1. Re-snapshot the *current* account's live credentials into the store, so a
   token Claude Code refreshed since the last snapshot is never lost.
2. Atomically replace ``.credentials.json`` with the target's snapshot.
3. Splice ``oauthAccount`` into the global config, preserving every other key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from clman import credstore, locks, store
from clman.errors import ClmanError, NotLoggedInError
from clman.fsio import atomic_write_text
from clman.paths import global_config_path


@dataclass
class ActiveLogin:
    credentials: str  # raw .credentials.json content, "" when absent
    oauth_account: dict  # {} when absent

    @property
    def email(self) -> str | None:
        email = self.oauth_account.get("emailAddress")
        return email if isinstance(email, str) and email else None


@dataclass
class SwitchResult:
    switched: bool
    from_email: str | None
    to_email: str


def _read_global_config() -> dict:
    path = global_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ClmanError(f"Cannot read {path}: {e}")
    return data if isinstance(data, dict) else {}


def read_active() -> ActiveLogin:
    credentials = credstore.read_active_credentials()
    config = _read_global_config()
    oauth = config.get("oauthAccount")
    return ActiveLogin(credentials, oauth if isinstance(oauth, dict) else {})


def snapshot_current() -> tuple[store.Account, bool]:
    """``clswap add``: store the currently logged-in account. Returns (account, created)."""
    active = read_active()
    if not active.credentials.strip() or "claudeAiOauth" not in active.credentials:
        raise NotLoggedInError(
            "No OAuth credentials found - log into Claude Code first (clswap login)."
        )
    if not active.email:
        raise NotLoggedInError(
            "No oauthAccount in the Claude config - log into Claude Code first."
        )
    return store.upsert(active.email, active.credentials, active.oauth_account)


def _splice_oauth_account(oauth_account: dict) -> None:
    """Rewrite the global config with a new ``oauthAccount``, under its lock."""
    with locks.claude_config_lock():
        config = _read_global_config()
        config["oauthAccount"] = oauth_account
        atomic_write_text(global_config_path(), json.dumps(config, indent=2))


def switch_to(target: store.Account) -> SwitchResult:
    target_credentials = store.load_credentials(target)
    if not target_credentials:
        raise ClmanError(
            f"Snapshot for {target.email} has no readable credentials - "
            "log in with that account and re-run `clswap add`."
        )
    with locks.claude_credentials_lock():
        active = read_active()
        if active.email and active.email.lower() == target.email.lower():
            return SwitchResult(False, active.email, target.email)
        # Keep the departing account's freshest tokens (refresh rotates them).
        if active.email and active.credentials.strip() and store.get(active.email):
            store.upsert(active.email, active.credentials, active.oauth_account)
        credstore.write_active_credentials(target_credentials)
        _splice_oauth_account(target.oauth_account)
    return SwitchResult(True, active.email, target.email)
