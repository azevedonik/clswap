"""clswap exception hierarchy. The CLI turns any ClmanError into stderr + exit 1."""

from __future__ import annotations


class ClmanError(Exception):
    """Base for user-reportable failures."""


class UnknownAccountError(ClmanError):
    pass


class NotLoggedInError(ClmanError):
    pass


class LockTimeoutError(ClmanError):
    pass
