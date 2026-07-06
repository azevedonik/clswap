"""Unit tests for the ``security`` CLI wrappers, with subprocess stubbed out."""

import subprocess

import pytest

from clswap import keychain


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def spawns(monkeypatch):
    """Capture security invocations; scripted results via .queue."""
    calls = []

    class Recorder:
        queue: list[Result] = []

        def __call__(self, argv, input=None, capture_output=True, text=True, timeout=None):
            calls.append({"argv": argv, "stdin": input})
            return self.queue.pop(0) if self.queue else Result()

    recorder = Recorder()
    recorder.calls = calls
    monkeypatch.setattr(subprocess, "run", recorder)
    return recorder


def test_get_password_strips_exactly_one_newline(spawns):
    spawns.queue = [Result(0, "secret value\n")]
    assert keychain.get_password("svc", "acct") == "secret value"
    argv = spawns.calls[0]["argv"]
    assert argv[0] == keychain.SECURITY_BIN and "-w" in argv


def test_get_password_rc44_means_absent(spawns):
    spawns.queue = [Result(44)]
    assert keychain.get_password("svc", "acct") is None


def test_get_password_other_rc_raises(spawns):
    spawns.queue = [Result(36, stderr="keychain locked")]
    with pytest.raises(keychain.KeychainError, match="rc=36"):
        keychain.get_password("svc", "acct")


def test_set_password_uses_stdin_and_hex(spawns):
    keychain.set_password("Claude Code-credentials", "nikolas", "s3cret")
    call = spawns.calls[0]
    assert call["argv"] == [keychain.SECURITY_BIN, "-i"]
    assert "s3cret" not in " ".join(call["argv"])  # secret never in argv
    assert f"-X {'s3cret'.encode().hex()}" in call["stdin"]
    assert '"Claude Code-credentials"' in call["stdin"]  # space-safe quoting
    assert "-U" in call["stdin"]


def test_set_password_oversized_falls_back_to_argv(spawns):
    big = "x" * 4096
    keychain.set_password("svc", "acct", big)
    argv = spawns.calls[0]["argv"]
    assert "add-generic-password" in argv and big.encode().hex() in argv


def test_set_password_failure_raises(spawns):
    spawns.queue = [Result(1, stderr="nope")]
    with pytest.raises(keychain.KeychainError):
        keychain.set_password("svc", "acct", "v")


def test_delete_password_rc44_is_success(spawns):
    spawns.queue = [Result(44)]
    keychain.delete_password("svc", "acct")  # no raise
    spawns.queue = [Result(51, stderr="denied")]
    with pytest.raises(keychain.KeychainError):
        keychain.delete_password("svc", "acct")


def test_capability_cache_is_sticky(monkeypatch):
    keychain.reset_capability_cache()
    monkeypatch.setattr(keychain, "is_macos", lambda: True)
    assert keychain.use_keychain()  # optimistic before first op

    def boom():
        raise keychain.KeychainError("locked")

    with pytest.raises(keychain.KeychainError):
        keychain.call(boom)
    assert not keychain.use_keychain()
    keychain.call(lambda: "ok")  # a later success must NOT flip False -> True
    assert not keychain.use_keychain()
    keychain.reset_capability_cache()


def test_use_keychain_false_off_macos(monkeypatch):
    keychain.reset_capability_cache()
    monkeypatch.setattr(keychain, "is_macos", lambda: False)
    assert not keychain.use_keychain()
