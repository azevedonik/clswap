# clman

Per-project Claude Code account switching, driven by a `.claude-session` file.
Works on Windows, Linux/WSL, and macOS.

`clman` installs one command, **`clswap`**. Drop a `.claude-session` file containing an
account email into a project, add one line to your shell profile, and every shell
you open in that project is automatically switched to the right Claude account. You can
also add accounts, switch manually, and log in — inspired by
[claude-swap](https://github.com/realiti4/claude-swap), but file-session-driven.

## Requirements

- Windows, Linux, WSL, or macOS
- [uv](https://docs.astral.sh/uv/) (manages Python 3.12+ for you)
- Claude Code installed and logged in

## Install

```powershell
git clone <this repo> clman
cd clman
uv tool install .            # installs the clswap command onto your PATH (~/.local/bin)
```

Developing locally? Use `uv tool install -e .` so edits apply without reinstalling.

## Quick start

```powershell
# 1. Snapshot the account you are currently logged in with
clswap add

# 2. Log in with another account, snapshot it too
clswap login                 # runs `claude /login`; finish the login, exit claude,
                             # and the new account is snapshotted automatically

# 3. Pin an account to a project
cd D:\Personal\some-project
clswap session work@example.com     # writes .claude-session

# 4. Auto-swap on shell start — add to your $PROFILE
#    (bash/zsh: `command -v clswap >/dev/null && clswap` — see Shell profile integration):
if (Get-Command clswap -ErrorAction SilentlyContinue) { clswap }
```

From then on, opening a terminal in `some-project` (or any subdirectory) switches
Claude Code to `work@example.com`. Opening one elsewhere leaves the account alone.

## The `.claude-session` file

- Contains a single account **email** on the first non-empty line.
- Lines starting with `#` are comments and are skipped.
- Discovered by walking **up** from the current directory to the drive root; the
  nearest file wins.
- Safe to commit if your team shares account emails; add it to `.gitignore` otherwise.

Example:

```
# This project runs on the work account
work@example.com
```

## Commands

| Command | Behavior |
|---|---|
| `clswap` | Auto-swap: find `.claude-session` (walking up from the current directory) and switch to that account. **Silent when there is nothing to do** — no session file, or the account is already active. Prints one line when it actually switches. Designed for your shell profile. |
| `clswap <email\|N>` | Switch to an account by email (case-insensitive) or by its number in `clswap list`. Shorthand for `clswap switch`. |
| `clswap switch <email\|N>` | Same, explicit form. |
| `clswap add` | Snapshot the currently logged-in account into the store. Re-running for an existing email updates it (use after re-login / token refresh). |
| `clswap login` | Launch `claude /login` interactively. After you complete the login and exit Claude, the new account is snapshotted automatically (i.e. `add` is run for you). |
| `clswap list` | All stored accounts, numbered, with the active one marked. |
| `clswap status` | Active account, whether it is stored, and which `.claude-session` (if any) applies to the current directory. |
| `clswap session [email]` | Write `.claude-session` in the current directory. With no email, uses the active account. Warns if the email is not in the store (still writes). |
| `clswap remove <email\|N>` | Delete an account from the store. Does not touch the live Claude login, even when removing the active account. No confirmation prompt. |
| `clswap help` | Usage. `--version` prints the version. |

Exit codes: `0` = success or nothing to do (including bare `clswap` finding no session
file, and switching to the already-active account); `1` = error (unknown account, not
logged in, lock timeout, corrupt files). Errors go to stderr.

## Shell profile integration

Auto-swap when a shell opens (recommended — covers VS Code terminals, which open at the
workspace root). PowerShell (`$PROFILE`):

```powershell
if (Get-Command clswap -ErrorAction SilentlyContinue) { clswap }
```

bash/zsh (`~/.bashrc` / `~/.zshrc`):

```bash
command -v clswap >/dev/null && clswap
```

Optionally also swap right before every `claude` launch, so a long-lived shell that
`cd`-ed into another project still picks the right account. PowerShell:

```powershell
function claude {
    if (Get-Command clswap -ErrorAction SilentlyContinue) { clswap }
    & (Get-Command claude -CommandType Application | Select-Object -First 1) @args
}
```

bash/zsh:

```bash
claude() { command -v clswap >/dev/null && clswap; command claude "$@"; }
```

## How it works

Claude Code keeps its login in two places:

- The OAuth tokens (`claudeAiOauth`): the plaintext `~/.claude/.credentials.json` on
  Windows/Linux/WSL; the **macOS Keychain** (service `Claude Code-credentials`) on
  macOS, with the plaintext file as its fallback.
- `~/.claude.json` — global config; the `oauthAccount` key identifies the account.

A switch:

1. Takes Claude Code's own advisory locks (`~/.claude.lock`, `~/.claude.json.lock` —
   the npm `proper-lockfile` directory protocol: mkdir-as-mutex, 10 s staleness,
   mtime keep-alive) so a swap never interleaves with Claude Code's token refresh.
2. Re-snapshots the **current** account's live credentials into the store first, so a
   token that Claude Code refreshed since the last snapshot is never lost.
3. Atomically replaces the active credential with the target account's snapshot and
   splices `oauthAccount` into `~/.claude.json`, preserving every other key.

Running Claude Code sessions pick up the new account on their next message — on
Windows/Linux Claude Code re-reads the credentials file when its mtime changes; on
macOS its Keychain cache expires after ~30 s (restart Claude to apply instantly).
Note that the login is machine-global: **all** running sessions follow a switch, so
parallel projects on different accounts in simultaneously-active terminals will fight;
the tool switches on shell start, not per process.

Expired tokens are not a problem: Claude Code refreshes them itself on the next message
using the stored refresh token, and step 2 above captures the rotation at the next
switch. If a refresh token has fully died, log in again (`clswap login`).

Honors `CLAUDE_CONFIG_DIR` the same way Claude Code does.

### macOS specifics

Keychain access goes through the system `/usr/bin/security` binary (never a Python
Keychain library), so the item's creator stays stable across upgrades and macOS never
shows a "wants to use your keychain" prompt. Secrets are passed hex-encoded over
`security -i` stdin, never in process argv. Writes prefer the Keychain; the first
Keychain failure in a run (locked/headless/SSH) flips that invocation to plaintext-file
mode and it sticks, with stale Keychain items cleaned up so they can't shadow the file.
After a Keychain write, an already-present `.credentials.json` is rewritten in place
(never created) so running sessions hot-reload. Account snapshots follow the same rule:
secret in the Keychain (service `clman`) when usable, inline in the snapshot file when
not — and an inline copy always wins on read, since it is the fresher one.

## Data locations

| What | Where |
|---|---|
| Account snapshots (metadata) | `~/.clman/accounts/<email>.json` (override root with `CLMAN_HOME`) |
| Account snapshots (secret) | inline in that JSON on Windows/Linux/WSL; macOS Keychain service `clman` on macOS |
| Session pin | `.claude-session` in each project |

Each snapshot file holds `{version, email, credentials, oauthAccount, addedAt,
updatedAt}`; on macOS `credentials` is `null` and the secret lives in the Keychain.
Remove everything with `Remove-Item -Recurse ~/.clman` (POSIX: `rm -rf ~/.clman`) —
plus, on macOS, the `clman` items in Keychain Access.

Account **numbers** shown by `clswap list` are 1-based positions ordered by the date the
account was added; removing an account renumbers the ones after it. Emails are the
stable identifier — use them in `.claude-session`.

## Development

```powershell
uv sync            # create .venv with dev deps
uv run pytest -q   # run the tests
```

Stdlib-only at runtime; `pytest` is the only dev dependency.
