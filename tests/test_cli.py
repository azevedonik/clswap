import json

from clswap import store, switcher
from clswap.cli import main
from clswap.paths import credentials_path
from clswap.session import SESSION_FILENAME
from conftest import fake_credentials, fake_login


def _setup_two_accounts():
    fake_login("a@x.com")
    switcher.snapshot_current()
    fake_login("b@x.com")
    switcher.snapshot_current()


def test_bare_clswap_switches_from_session_file(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    project = tmp_path / "project"
    project.mkdir()
    (project / SESSION_FILENAME).write_text("a@x.com\n")
    monkeypatch.chdir(project)

    assert main([]) == 0
    assert credentials_path().read_text(encoding="utf-8") == fake_credentials("a@x.com")
    assert "switched to a@x.com" in capsys.readouterr().out

    # second run: already active -> reports which account is in use
    assert main([]) == 0
    assert "using Claude credentials for a@x.com" in capsys.readouterr().out


def test_bare_clswap_without_session_file_reports_active_account(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "using Claude credentials for" in out
    assert "no .claude-session here" in out


def test_default_command_sets_default_to_active_account(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    monkeypatch.chdir(tmp_path)

    assert main(["default"]) == 0
    assert "Default account: b@x.com" in capsys.readouterr().out

    assert main(["status"]) == 0
    assert "Default account: b@x.com" in capsys.readouterr().out


def test_default_command_sets_default_by_selector(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    monkeypatch.chdir(tmp_path)

    assert main(["default", "a@x.com"]) == 0
    assert "Default account: a@x.com" in capsys.readouterr().out


def test_bare_clswap_uses_default_when_no_session_file(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    assert main(["default", "a@x.com"]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)

    assert main([]) == 0
    assert credentials_path().read_text(encoding="utf-8") == fake_credentials("a@x.com")
    assert "switched to a@x.com" in capsys.readouterr().out


def test_session_file_takes_precedence_over_default(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    assert main(["default", "a@x.com"]) == 0
    capsys.readouterr()
    project = tmp_path / "project"
    project.mkdir()
    (project / SESSION_FILENAME).write_text("b@x.com\n")
    monkeypatch.chdir(project)

    assert main([]) == 0
    assert credentials_path().read_text(encoding="utf-8") == fake_credentials("b@x.com")
    assert "using Claude credentials for b@x.com" in capsys.readouterr().out


def test_remove_clears_matching_default_account(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    monkeypatch.chdir(tmp_path)

    assert main(["default", "a@x.com"]) == 0
    assert main(["remove", "a@x.com"]) == 0
    capsys.readouterr()

    assert main(["status"]) == 0
    assert "Default account: none" in capsys.readouterr().out


def test_bare_clswap_without_login_hints_at_login(env, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert "not logged in" in capsys.readouterr().out


def test_bare_clswap_unknown_account_errors(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    (tmp_path / SESSION_FILENAME).write_text("nobody@x.com\n")
    monkeypatch.chdir(tmp_path)
    assert main([]) == 1
    assert "nobody@x.com" in capsys.readouterr().err


def test_switch_shorthand_by_email_and_number(env, capsys):
    _setup_two_accounts()
    assert main(["a@x.com"]) == 0
    assert "Switched to a@x.com" in capsys.readouterr().out
    accounts = store.load_accounts()
    number = str(accounts.index(store.resolve("b@x.com", accounts)) + 1)
    assert main([number]) == 0
    assert "Switched to b@x.com" in capsys.readouterr().out


def test_list_marks_active_account(env, capsys):
    _setup_two_accounts()
    assert main(["list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any("*" in line and "b@x.com" in line for line in lines)
    assert any("a@x.com" in line and "*" not in line for line in lines)


def test_status_reports_account_and_session(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    (tmp_path / SESSION_FILENAME).write_text("a@x.com\n")
    monkeypatch.chdir(tmp_path)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "b@x.com (stored)" in out
    assert "-> a@x.com" in out


def test_session_command_writes_file(env, tmp_path, monkeypatch, capsys):
    _setup_two_accounts()
    monkeypatch.chdir(tmp_path)
    assert main(["session"]) == 0  # defaults to active account
    assert (tmp_path / SESSION_FILENAME).read_text(encoding="utf-8") == "b@x.com\n"

    assert main(["session", "unknown@x.com"]) == 0
    captured = capsys.readouterr()
    assert "not in the store" in captured.err
    assert (tmp_path / SESSION_FILENAME).read_text(encoding="utf-8") == "unknown@x.com\n"


def test_remove(env, capsys):
    _setup_two_accounts()
    assert main(["remove", "a@x.com"]) == 0
    assert store.get("a@x.com") is None


def test_unknown_command_with_args_errors(env, capsys):
    assert main(["frobnicate", "now"]) == 1
    assert "unknown command" in capsys.readouterr().err


def test_add_without_login_errors(env, capsys):
    assert main(["add"]) == 1
    assert "log into Claude Code" in capsys.readouterr().err
