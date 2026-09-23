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

from qt_ui.main import (
    APP_ID,
    GCLP_HICON,
    GCLP_HICONSM,
    claim_class_icon,
    claim_taskbar_identity,
)


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


def _window() -> Any:
    return SimpleNamespace(winId=lambda: 1234)


def _user32(handle: int) -> Any:
    loaded: list[str] = []
    set_on_class: list[tuple[int, int, int]] = []

    def load_image(
        instance: Any, path: str, kind: int, width: int, height: int, flags: int
    ) -> int:
        loaded.append(path)
        return handle

    def set_class(hwnd: int, index: int, value: int) -> int:
        set_on_class.append((hwnd, index, value))
        return 0

    return SimpleNamespace(
        LoadImageW=load_image,
        GetSystemMetrics=lambda index: 32,
        SetClassLongPtrW=set_class,
        loaded=loaded,
        set_on_class=set_on_class,
    )


def test_the_class_gets_the_application_icon(monkeypatch: Any) -> None:
    """Both of the class's icons, big and small, on the window's own class."""
    user32 = _user32(handle=77)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("ctypes.windll", SimpleNamespace(user32=user32), raising=False)

    assert claim_class_icon(_window()) is True
    assert user32.set_on_class == [(1234, GCLP_HICON, 77), (1234, GCLP_HICONSM, 77)]
    assert all(path.endswith("icon.ico") for path in user32.loaded)


def test_an_icon_that_does_not_load_leaves_the_class_alone(monkeypatch: Any) -> None:
    user32 = _user32(handle=0)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("ctypes.windll", SimpleNamespace(user32=user32), raising=False)

    assert claim_class_icon(_window()) is False
    assert user32.set_on_class == []


def test_the_class_icon_is_left_alone_anywhere_else(monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert claim_class_icon(_window()) is False
