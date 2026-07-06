"""The account store: one JSON snapshot per account under ``~/.clman/accounts``.

Emails are the stable identifier; list numbers are 1-based positions ordered
by ``addedAt`` (then email), recomputed on every load.

The metadata JSON always lives in a file. The credential *secret* lives inline
in that file on Windows/Linux/WSL; on macOS it goes to the Keychain (service
``clman``) when usable, with ``"credentials": null`` marking the placement,
and falls back inline when the Keychain isn't. Reads are **file-wins**: inline
credentials (written while the Keychain was down, hence fresher) beat a
possibly-stale Keychain copy — which is why a successful Keychain write must
null the inline copy, and an inline write must best-effort delete the
Keychain item.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from clman import keychain
from clman.errors import ClmanError, UnknownAccountError
from clman.fsio import atomic_write_text
from clman.paths import accounts_dir

# Conservative: covers real emails while guaranteeing a valid Windows filename.
_SAFE_EMAIL = re.compile(r"^[A-Za-z0-9._%+@-]+$")


@dataclass
class Account:
    email: str
    credentials: str | None  # raw credential JSON inline, None = in the Keychain
    oauth_account: dict
    added_at: str
    updated_at: str

    @property
    def path(self) -> Path:
        return account_path(self.email)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_email(email: str) -> str:
    email = email.strip()
    if not email or "@" not in email or not _SAFE_EMAIL.match(email):
        raise ClmanError(f"Not a usable account email: {email!r}")
    return email


def account_path(email: str) -> Path:
    return accounts_dir() / f"{email.lower()}.json"


def _load_file(path: Path) -> Account | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("email"):
        return None
    credentials = data.get("credentials")
    # Inline string, or an explicit null meaning "in the Keychain" (macOS).
    if not (isinstance(credentials, str) and credentials) and credentials is not None:
        return None
    return Account(
        email=data["email"],
        credentials=credentials,
        oauth_account=data.get("oauthAccount") or {},
        added_at=data.get("addedAt", ""),
        updated_at=data.get("updatedAt", ""),
    )


def load_accounts() -> list[Account]:
    directory = accounts_dir()
    if not directory.is_dir():
        return []
    accounts = []
    for path in directory.glob("*.json"):
        account = _load_file(path)
        if account is not None:
            accounts.append(account)
    accounts.sort(key=lambda a: (a.added_at, a.email.lower()))
    return accounts


def get(email: str) -> Account | None:
    path = account_path(email)
    return _load_file(path) if path.is_file() else None


def _kc_account(email: str) -> str:
    return f"account-{email.lower()}"


def upsert(email: str, credentials: str, oauth_account: dict) -> tuple[Account, bool]:
    """Create or update a snapshot. Returns ``(account, created)``.

    macOS: secret to the Keychain when usable (inline copy nulled by the same
    file write); inline fallback when it isn't, with the stale Keychain item
    best-effort deleted so a recovered Keychain can't shadow the fresher file.
    """
    email = validate_email(email)
    existing = get(email)
    inline: str | None = credentials
    if keychain.use_keychain():
        try:
            keychain.call(
                keychain.set_password, keychain.SNAPSHOT_SERVICE, _kc_account(email), credentials
            )
            inline = None
        except keychain.KEYCHAIN_ERRORS as e:
            print(
                f"clswap: warning: Keychain write failed, storing in file: {e}",
                file=sys.stderr,
            )
    account = Account(
        email=email,
        credentials=inline,
        oauth_account=oauth_account,
        added_at=existing.added_at if existing else _now(),
        updated_at=_now(),
    )
    payload = {
        "version": 1,
        "email": account.email,
        "credentials": account.credentials,
        "oauthAccount": account.oauth_account,
        "addedAt": account.added_at,
        "updatedAt": account.updated_at,
    }
    atomic_write_text(account.path, json.dumps(payload, indent=2))
    if inline is not None and keychain.is_macos():
        _delete_keychain_snapshot_quiet(email)
    return account, existing is None


def load_credentials(account: Account) -> str:
    """Resolve a snapshot's secret: inline (file-wins) or macOS Keychain."""
    if account.credentials:
        return account.credentials
    if keychain.is_macos():
        try:
            return (
                keychain.call(
                    keychain.get_password,
                    keychain.SNAPSHOT_SERVICE,
                    _kc_account(account.email),
                )
                or ""
            )
        except keychain.KEYCHAIN_ERRORS as e:
            print(f"clswap: warning: Keychain read failed: {e}", file=sys.stderr)
    return ""


def _delete_keychain_snapshot_quiet(email: str) -> None:
    try:
        keychain.delete_password(keychain.SNAPSHOT_SERVICE, _kc_account(email))
    except Exception:
        pass  # best-effort: a down Keychain can't be cleaned now


def remove(email: str) -> None:
    account_path(email).unlink()
    if keychain.is_macos():
        _delete_keychain_snapshot_quiet(email)


def resolve(selector: str, accounts: list[Account] | None = None) -> Account:
    """Find an account by email (case-insensitive) or 1-based list number."""
    if accounts is None:
        accounts = load_accounts()
    if not accounts:
        raise UnknownAccountError("No accounts stored yet - run `clswap add` first.")
    selector = selector.strip()
    if selector.isdigit():
        n = int(selector)
        if 1 <= n <= len(accounts):
            return accounts[n - 1]
        raise UnknownAccountError(
            f"No account #{n} (have 1..{len(accounts)} - see `clswap list`)."
        )
    for account in accounts:
        if account.email.lower() == selector.lower():
            return account
    raise UnknownAccountError(
        f"No stored account {selector!r} - see `clswap list`, or add it with `clswap add`."
    )
