"""The ``clswap`` command-line interface.

Grammar (see README for the contract):

    clswap                      auto-swap from .claude-session (silent no-op)
    clswap <email|N>            switch (shorthand)
    clswap switch <email|N>
    clswap add | login | list | status | remove <email|N> | session [email] | help
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from clman import __version__, session, store, switcher
from clman.errors import ClmanError

USAGE = """\
clswap - per-project Claude Code account switching

usage:
  clswap                     auto-swap from the nearest .claude-session (silent no-op)
  clswap <email|N>           switch to a stored account (also: clswap switch <email|N>)
  clswap add                 snapshot the currently logged-in account
  clswap login               run `claude /login`, then snapshot the new account
  clswap list                stored accounts (active one marked)
  clswap status              active account + applicable .claude-session
  clswap session [email]     write .claude-session here (default: active account)
  clswap remove <email|N>    delete an account snapshot
  clswap help                this text (--version prints the version)
"""


def _err(message: str) -> int:
    print(f"clswap: {message}", file=sys.stderr)
    return 1


def cmd_auto() -> int:
    session_file = session.find_session_file(Path.cwd())
    if session_file is None:
        return 0
    email = session.read_session_email(session_file)
    if email is None:
        return _err(f"{session_file} contains no account email")
    active = switcher.read_active()
    if active.email and active.email.lower() == email.lower():
        return 0
    target = store.resolve(email)
    result = switcher.switch_to(target)
    if result.switched:
        print(f"clswap: switched to {result.to_email} ({session_file})")
    return 0


def cmd_switch(selector: str) -> int:
    target = store.resolve(selector)
    result = switcher.switch_to(target)
    if result.switched:
        origin = f" (was {result.from_email})" if result.from_email else ""
        print(f"Switched to {result.to_email}{origin}")
    else:
        print(f"Already on {result.to_email}")
    return 0


def cmd_add() -> int:
    account, created = switcher.snapshot_current()
    print(f"{'Added' if created else 'Updated'} {account.email}")
    return 0


def cmd_login() -> int:
    claude = shutil.which("claude")
    if claude is None:
        return _err("`claude` not found on PATH - install Claude Code first")
    print("Complete the login in Claude Code, then exit it (/exit) to continue...")
    subprocess.run([claude, "/login"])
    return cmd_add()


def cmd_list() -> int:
    accounts = store.load_accounts()
    if not accounts:
        print("No accounts stored yet - run `clswap add`.")
        return 0
    active_email = (switcher.read_active().email or "").lower()
    for n, account in enumerate(accounts, start=1):
        marker = "*" if account.email.lower() == active_email else " "
        print(f" {marker} {n}. {account.email}  (updated {account.updated_at})")
    return 0


def cmd_status() -> int:
    active = switcher.read_active()
    if active.email:
        stored = "stored" if store.get(active.email) else "not stored - run `clswap add`"
        print(f"Active account: {active.email} ({stored})")
    else:
        print("Active account: none (not logged in)")
    session_file = session.find_session_file(Path.cwd())
    if session_file:
        print(f"Session file:   {session_file} -> {session.read_session_email(session_file)}")
    else:
        print("Session file:   none found")
    return 0


def cmd_session(email: str | None) -> int:
    if email is None:
        email = switcher.read_active().email
        if not email:
            return _err("not logged in and no email given")
    email = store.validate_email(email)
    if store.get(email) is None:
        print(f"clswap: warning: {email} is not in the store yet", file=sys.stderr)
    target = Path.cwd() / session.SESSION_FILENAME
    target.write_text(email + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


def cmd_remove(selector: str) -> int:
    account = store.resolve(selector)
    store.remove(account.email)
    print(f"Removed {account.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        if not args:
            return cmd_auto()
        cmd, rest = args[0], args[1:]
        match cmd:
            case "help" | "-h" | "--help":
                print(USAGE, end="")
                return 0
            case "--version":
                print(f"clswap {__version__}")
                return 0
            case "switch":
                if len(rest) != 1:
                    return _err("usage: clswap switch <email|N>")
                return cmd_switch(rest[0])
            case "add":
                return cmd_add()
            case "login":
                return cmd_login()
            case "list":
                return cmd_list()
            case "status":
                return cmd_status()
            case "session":
                if len(rest) > 1:
                    return _err("usage: clswap session [email]")
                return cmd_session(rest[0] if rest else None)
            case "remove":
                if len(rest) != 1:
                    return _err("usage: clswap remove <email|N>")
                return cmd_remove(rest[0])
            case _:
                if rest:
                    return _err(f"unknown command {cmd!r} (see `clswap help`)")
                return cmd_switch(cmd)
    except ClmanError as e:
        return _err(str(e))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
