"""Commander status, animation lifecycle and cancellation."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from game.agent.session import _AiSession
from qt_ui.windows import opforai


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


def test_animation_runs_only_when_visible_and_active(app: Any) -> None:
    button = opforai.CommanderButton()
    snap = {"active": True, "cancelled": False, "status": "Planning packages"}
    button.set_snapshot(snap)
    assert not button._animation.isActive()
    button.show()
    app.processEvents()
    assert button._animation.isActive()
    button._advance()
    assert button._angle > 0
    button.hide()
    assert not button._animation.isActive()
    button.show()
    snap["active"] = False
    button.set_snapshot(snap)
    assert not button._animation.isActive()
    assert "Idle" in button.text()
    button.close()


def test_live_status_cancel_and_connections(app: Any, monkeypatch: Any) -> None:
    from game.agent import service

    session = _AiSession()
    monkeypatch.setattr(opforai, "AI_SESSION", session)
    monkeypatch.setattr(
        service, "connect_url", lambda: "http://localhost/start?token=test"
    )
    monkeypatch.setattr(service, "mcp_url", lambda: "http://localhost/mcp?token=test")
    dialog = opforai.OpforAiDialog()
    assert not dialog.cancel.isEnabled()
    assert dialog.fields[0].echoMode() == QLineEdit.EchoMode.Password
    session.touch()
    session.set_status("Planning <CAP> packages")
    dialog.refresh()
    assert dialog.status.toPlainText() == "Planning <CAP> packages"
    assert dialog.cancel.isEnabled()
    count = dialog.activity.count()
    dialog.refresh()
    assert dialog.activity.count() == count
    dialog._cancel()
    assert session.snapshot()["cancelled"]
    assert dialog.state.text() == "CANCEL REQUESTED"
    assert not dialog.cancel.isEnabled()
    dialog._show_urls(True)
    assert dialog.fields[0].echoMode() == QLineEdit.EchoMode.Normal
    dialog.close()


def test_unavailable_connections_disable_copy(app: Any, monkeypatch: Any) -> None:
    from game.agent import service

    def unavailable() -> str:
        raise RuntimeError("Server is not ready")

    monkeypatch.setattr(service, "connect_url", unavailable)
    dialog = opforai.OpforAiDialog()
    assert all(not button.isEnabled() for button in dialog.copy_buttons)
    assert all(not field.text() for field in dialog.fields)
    dialog.close()
