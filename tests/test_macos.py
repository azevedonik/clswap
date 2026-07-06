"""macOS behavior against a fake in-memory Keychain (see conftest.mac)."""

import json

from clswap import credstore, keychain, store, switcher
from clswap.cli import main
from clswap.paths import credentials_path, global_config_path
from clswap.session import SESSION_FILENAME
from conftest import fake_credentials


def kc_login(fake, email, token="tok"):
    """Simulate `claude /login` on macOS: credential in the Keychain, not the file."""
    fake.items[(keychain.ACTIVE_SERVICE, "nikolas")] = fake_credentials(email, token)
    config_file = global_config_path()
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    config["oauthAccount"] = {"emailAddress": email}
    config_file.write_text(json.dumps(config), encoding="utf-8")


def test_read_active_prefers_keychain_over_file(mac):
    kc_login(mac, "a@x.com")
    credentials_path().write_text(fake_credentials("stale@x.com"), encoding="utf-8")
    assert credstore.read_active_credentials() == fake_credentials("a@x.com")


def test_read_active_falls_back_to_file(mac):
    credentials_path().write_text(fake_credentials("filed@x.com"), encoding="utf-8")
    assert credstore.read_active_credentials() == fake_credentials("filed@x.com")


def test_write_active_goes_to_keychain_never_creating_file(mac):
    credstore.write_active_credentials("secret")
    assert mac.items[(keychain.ACTIVE_SERVICE, "nikolas")] == "secret"
    assert not credentials_path().exists()


def test_write_active_bumps_existing_file_for_hot_reload(mac):
    credentials_path().write_text("old", encoding="utf-8")
    credstore.write_active_credentials("secret")
    assert credentials_path().read_text(encoding="utf-8") == "secret"


def test_write_active_broken_keychain_uses_file_and_clears_stale_item(mac):
    mac.items[(keychain.ACTIVE_SERVICE, "nikolas")] = "stale"
    mac.broken = True
    credstore.write_active_credentials("secret")
    assert credentials_path().read_text(encoding="utf-8") == "secret"
    mac.broken = False
    credstore.write_active_credentials("secret2")  # cache is sticky: still file mode
    assert credentials_path().read_text(encoding="utf-8") == "secret2"
    assert (keychain.ACTIVE_SERVICE, "nikolas") not in mac.items


def test_snapshot_secret_lives_in_keychain_not_file(mac):
    store.upsert("a@x.com", "creds-a", {"emailAddress": "a@x.com"})
    account = store.get("a@x.com")
    assert account.credentials is None  # nulled inline copy
    raw = json.loads(account.path.read_text(encoding="utf-8"))
    assert raw["credentials"] is None
    assert "creds-a" not in account.path.read_text(encoding="utf-8")
    assert (keychain.SNAPSHOT_SERVICE, "account-a@x.com") in mac.items
    assert keychain.SNAPSHOT_SERVICE == "clswap"
    assert store.load_credentials(account) == "creds-a"


def test_snapshot_secret_reads_legacy_clman_keychain_item(mac):
    account = store.Account("a@x.com", None, {}, "", "")
    mac.items[("clman", "account-a@x.com")] = "legacy-creds"

    assert store.load_credentials(account) == "legacy-creds"


def test_snapshot_broken_keychain_falls_back_inline(mac, capsys):
    mac.broken = True
    store.upsert("a@x.com", "creds-a", {})
    account = store.get("a@x.com")
    assert account.credentials == "creds-a"
    assert store.load_credentials(account) == "creds-a"
    assert "Keychain write failed" in capsys.readouterr().err


def test_inline_file_credentials_win_over_stale_keychain_copy(mac):
    # A Keychain copy exists, but a fresher inline copy was written while the
    # Keychain was down -> the file wins.
    mac.items[(keychain.SNAPSHOT_SERVICE, "account-a@x.com")] = "stale"
    store.upsert("a@x.com", "fresh", {})  # keychain usable: overwrites item
    assert store.load_credentials(store.get("a@x.com")) == "fresh"

    mac.items[(keychain.SNAPSHOT_SERVICE, "account-a@x.com")] = "stale"
    account = store.get("a@x.com")
    account.credentials = "inline-fresh"
    assert store.load_credentials(account) == "inline-fresh"


def test_remove_deletes_keychain_item(mac):
    store.upsert("a@x.com", "creds-a", {})
    assert (keychain.SNAPSHOT_SERVICE, "account-a@x.com") in mac.items
    store.remove("a@x.com")
    assert (keychain.SNAPSHOT_SERVICE, "account-a@x.com") not in mac.items


def test_full_switch_on_macos(mac, tmp_path, monkeypatch, capsys):
    kc_login(mac, "a@x.com")
    switcher.snapshot_current()
    kc_login(mac, "b@x.com")
    switcher.snapshot_current()

    (tmp_path / SESSION_FILENAME).write_text("a@x.com\n")
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert "switched to a@x.com" in capsys.readouterr().out

    # Active credential now lives in the Keychain; no plaintext file appeared.
    assert mac.items[(keychain.ACTIVE_SERVICE, "nikolas")] == fake_credentials("a@x.com")
    assert not credentials_path().exists()
    config = json.loads(global_config_path().read_text(encoding="utf-8"))
    assert config["oauthAccount"]["emailAddress"] == "a@x.com"
    # Departing account b was re-snapshotted into the Keychain.
    assert store.load_credentials(store.get("b@x.com")) == fake_credentials("b@x.com")
