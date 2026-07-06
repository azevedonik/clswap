import json

import pytest

from clman import store, switcher
from clman.errors import NotLoggedInError
from clman.paths import credentials_path, global_config_path
from conftest import fake_credentials, fake_login


def test_add_requires_login(env):
    with pytest.raises(NotLoggedInError):
        switcher.snapshot_current()


def test_add_snapshots_active_account(env):
    fake_login("a@x.com")
    account, created = switcher.snapshot_current()
    assert created
    assert account.email == "a@x.com"
    assert account.credentials == fake_credentials("a@x.com")
    assert account.oauth_account["organizationName"] == "a@x.com-org"


def test_switch_swaps_credentials_and_splices_config(env):
    fake_login("a@x.com", extra_config={"projects": {"D:/x": {}}, "theme": "dark"})
    switcher.snapshot_current()
    fake_login("b@x.com")
    switcher.snapshot_current()

    result = switcher.switch_to(store.get("a@x.com"))
    assert result.switched and result.from_email == "b@x.com" and result.to_email == "a@x.com"

    assert credentials_path().read_text(encoding="utf-8") == fake_credentials("a@x.com")
    config = json.loads(global_config_path().read_text(encoding="utf-8"))
    assert config["oauthAccount"]["emailAddress"] == "a@x.com"
    # everything else in the config is preserved
    assert config["projects"] == {"D:/x": {}}
    assert config["theme"] == "dark"


def test_switch_to_active_account_is_noop(env):
    fake_login("a@x.com")
    switcher.snapshot_current()
    result = switcher.switch_to(store.get("a@x.com"))
    assert not result.switched


def test_switch_resnapshots_departing_account(env):
    fake_login("a@x.com")
    switcher.snapshot_current()
    fake_login("b@x.com", token="old")
    switcher.snapshot_current()
    # Claude Code refreshes b's token after the snapshot was taken.
    credentials_path().write_text(fake_credentials("b@x.com", token="fresh"), encoding="utf-8")

    switcher.switch_to(store.get("a@x.com"))
    assert store.get("b@x.com").credentials == fake_credentials("b@x.com", token="fresh")


def test_switch_from_unknown_account_does_not_snapshot_it(env):
    fake_login("a@x.com")
    switcher.snapshot_current()
    fake_login("stranger@x.com")  # active but never added

    switcher.switch_to(store.get("a@x.com"))
    assert store.get("stranger@x.com") is None
    assert json.loads(global_config_path().read_text(encoding="utf-8"))["oauthAccount"][
        "emailAddress"
    ] == "a@x.com"
