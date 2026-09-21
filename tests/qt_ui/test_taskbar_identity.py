"""Which icon Windows puts on the taskbar.

It does not come from setWindowIcon. Windows groups a window by the application id
of the process that owns it, and a process that never claims one inherits whatever
launched it -- which is why running from source showed Python's icon while the built
executable showed its own.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

from qt_ui.main import APP_ID, claim_taskbar_identity


class _Shell:
    def __init__(self) -> None:
        self.claimed: list[str] = []

    def SetCurrentProcessExplicitAppUserModelID(self, app_id: str) -> None:
        self.claimed.append(app_id)


def _windows(monkeypatch: Any, shell: Any) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("ctypes.windll", SimpleNamespace(shell32=shell), raising=False)


def test_the_id_is_claimed_on_windows(monkeypatch: Any) -> None:
    shell = _Shell()
    _windows(monkeypatch, shell)

    assert claim_taskbar_identity() is True
    assert shell.claimed == [APP_ID]


def test_nothing_happens_anywhere_else(monkeypatch: Any) -> None:
    """Everything it does is Windows' own shell."""
    monkeypatch.setattr(sys, "platform", "linux")

    assert claim_taskbar_identity() is False


def test_a_shell_that_refuses_does_not_stop_the_application(monkeypatch: Any) -> None:
    """An older Windows or a locked-down host: an icon is not worth failing to
    start over."""

    class Refuses:
        def SetCurrentProcessExplicitAppUserModelID(self, app_id: str) -> None:
            raise OSError("no")

    _windows(monkeypatch, Refuses())

    assert claim_taskbar_identity() is False


def test_the_id_is_one_nothing_else_will_claim() -> None:
    assert APP_ID.count(".") >= 2
    assert APP_ID.islower()
