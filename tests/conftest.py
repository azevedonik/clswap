import json

import pytest

from clswap import keychain
from clswap.paths import claude_config_home, credentials_path, global_config_path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point clswap and the Claude Code paths at an isolated temp layout."""
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("CLSWAP_HOME", str(tmp_path / "clswap-home"))
    return tmp_path


class FakeKeychain:
    """In-memory stand-in for the ``security`` CLI wrappers."""

    def __init__(self):
        self.items: dict[tuple[str, str], str] = {}
        self.broken = False  # when True every op raises KeychainError

    def _check(self):
        if self.broken:
            raise keychain.KeychainError("keychain is locked (simulated)")

    def get(self, service, account):
        self._check()
        return self.items.get((service, account))

    def set(self, service, account, value):
        self._check()
        self.items[(service, account)] = value

    def delete(self, service, account):
        self._check()
        self.items.pop((service, account), None)


@pytest.fixture
def mac(env, monkeypatch):
    """Simulate macOS with a working in-memory Keychain."""
    fake = FakeKeychain()
    monkeypatch.setattr(keychain, "is_macos", lambda: True)
    monkeypatch.setattr(keychain, "get_password", fake.get)
    monkeypatch.setattr(keychain, "set_password", fake.set)
    monkeypatch.setattr(keychain, "delete_password", fake.delete)
    monkeypatch.setattr(keychain, "account_name", lambda: "nikolas")
    keychain.reset_capability_cache()
    yield fake
    keychain.reset_capability_cache()


def fake_credentials(email: str, token: str = "tok") -> str:
    return json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": f"at-{email}-{token}",
                "refreshToken": f"rt-{email}-{token}",
                "expiresAt": 4102444800000,
                "scopes": ["user:inference"],
                "subscriptionType": "max",
            }
        }
    )


def fake_login(email: str, token: str = "tok", extra_config: dict | None = None) -> None:
    """Simulate `claude /login`: write live credentials + config for `email`."""
    claude_config_home().mkdir(parents=True, exist_ok=True)
    credentials_path().write_text(fake_credentials(email, token), encoding="utf-8")
    config_file = global_config_path()
    config = {}
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    config.update(extra_config or {})
    config["oauthAccount"] = {"emailAddress": email, "organizationName": f"{email}-org"}
    config_file.write_text(json.dumps(config), encoding="utf-8")
