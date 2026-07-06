import pytest

from clman import store
from clman.errors import ClmanError, UnknownAccountError


def test_upsert_and_get(env):
    account, created = store.upsert("a@x.com", "creds-a", {"emailAddress": "a@x.com"})
    assert created
    loaded = store.get("A@X.com")  # case-insensitive path
    assert loaded is not None
    assert loaded.credentials == "creds-a"
    assert loaded.oauth_account == {"emailAddress": "a@x.com"}


def test_upsert_updates_preserving_added_at(env):
    first, _ = store.upsert("a@x.com", "v1", {})
    second, created = store.upsert("a@x.com", "v2", {})
    assert not created
    assert second.added_at == first.added_at
    assert store.get("a@x.com").credentials == "v2"
    assert len(store.load_accounts()) == 1


def test_resolve_by_number_and_email(env):
    store.upsert("a@x.com", "creds-a", {})
    store.upsert("b@x.com", "creds-b", {})
    accounts = store.load_accounts()
    assert store.resolve("1", accounts).email in ("a@x.com", "b@x.com")
    assert store.resolve("B@X.COM", accounts).email == "b@x.com"
    with pytest.raises(UnknownAccountError):
        store.resolve("3", accounts)
    with pytest.raises(UnknownAccountError):
        store.resolve("nobody@x.com", accounts)


def test_resolve_with_empty_store(env):
    with pytest.raises(UnknownAccountError, match="clswap add"):
        store.resolve("a@x.com")


def test_remove(env):
    store.upsert("a@x.com", "creds-a", {})
    store.remove("a@x.com")
    assert store.get("a@x.com") is None


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a/b@x.com", "a b@x.com"])
def test_validate_email_rejects(bad):
    with pytest.raises(ClmanError):
        store.validate_email(bad)
