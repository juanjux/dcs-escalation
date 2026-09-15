"""Failed/cancelled saves must leave the campaign open and recoverable."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox

from game import persistency
from game.agent import service
from qt_ui import liberation_install
from qt_ui.windows.QLiberationWindow import QLiberationWindow
from tests.test_unsaved_changes import Campaign


def window_for(game: Any) -> Any:
    window: Any = SimpleNamespace(game=game, updateWindowTitle=Mock())
    window._save_game_to_path = lambda path: QLiberationWindow._save_game_to_path(
        window, path
    )
    window.saveGameAs = lambda: QLiberationWindow.saveGameAs(window)
    window.saveGame = lambda: QLiberationWindow.saveGame(window)
    window._shut_down = Mock(side_effect=lambda event: event.accept())
    return window


@pytest.mark.parametrize("save_ok", [True, False])
def test_save_result_reaches_close(monkeypatch: Any, save_ok: bool) -> None:
    window = window_for(SimpleNamespace(savepath="original.retribution"))
    save = Mock(return_value=save_ok)
    monkeypatch.setattr(persistency, "save_game", save)
    monkeypatch.setattr(persistency, "has_unsaved_changes", lambda game: True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: int(QMessageBox.StandardButton.Yes)
    )
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    remember = Mock()
    monkeypatch.setattr(liberation_install, "setup_last_save_file", remember)
    monkeypatch.setattr(liberation_install, "save_config", Mock())
    event = QCloseEvent()
    QLiberationWindow.closeEvent(window, event)
    assert event.isAccepted() is save_ok
    assert window._shut_down.called is save_ok
    assert error.called is not save_ok
    assert remember.called is save_ok
    assert window.updateWindowTitle.called is save_ok
    save.assert_called_once_with(window.game)


def test_cancel_save_as_keeps_untitled_campaign_open(monkeypatch: Any) -> None:
    window = window_for(SimpleNamespace(savepath=""))
    monkeypatch.setattr(persistency, "has_unsaved_changes", lambda game: True)
    monkeypatch.setattr(persistency, "save_dir", lambda: "saves")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", "")
    )
    save = Mock()
    monkeypatch.setattr(persistency, "save_game", save)
    event = QCloseEvent()
    QLiberationWindow.closeEvent(window, event)
    assert not event.isAccepted()
    window._shut_down.assert_not_called()
    save.assert_not_called()
    assert window.game.savepath == ""


def test_failed_save_as_preserves_previous_path(monkeypatch: Any) -> None:
    window = window_for(SimpleNamespace(savepath="original.retribution"))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("new.retribution", "")
    )
    attempted_paths = []

    def fail(game: Any) -> bool:
        attempted_paths.append(game.savepath)
        return False

    monkeypatch.setattr(persistency, "save_game", fail)
    monkeypatch.setattr(QMessageBox, "critical", Mock())
    remember = Mock()
    monkeypatch.setattr(liberation_install, "setup_last_save_file", remember)
    assert not window.saveGameAs()
    assert attempted_paths == ["new.retribution"]
    assert window.game.savepath == "original.retribution"
    remember.assert_not_called()
    window.updateWindowTitle.assert_not_called()


@pytest.mark.parametrize("plain_int", [True, False])
@pytest.mark.parametrize(
    "answer", [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.No]
)
def test_close_respects_answer(monkeypatch: Any, plain_int: bool, answer: Any) -> None:
    window = window_for(None)
    window.saveGame = Mock()
    monkeypatch.setattr(persistency, "has_unsaved_changes", lambda game: True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: int(answer) if plain_int else answer
    )
    event = QCloseEvent()
    QLiberationWindow.closeEvent(window, event)
    assert event.isAccepted() is (answer == QMessageBox.StandardButton.No)
    window.saveGame.assert_not_called()


def test_unchanged_campaign_closes_without_prompt(monkeypatch: Any) -> None:
    window = window_for(None)
    question = Mock()
    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(persistency, "has_unsaved_changes", lambda game: False)
    event = QCloseEvent()
    QLiberationWindow.closeEvent(window, event)
    assert event.isAccepted()
    question.assert_not_called()


def test_api_change_prompts_without_ui_signals(monkeypatch: Any) -> None:
    campaign: Any = Campaign()
    campaign.stored_context = {}
    monkeypatch.setattr(persistency, "_saved_signature", None)
    persistency.remember_saved_state(campaign)
    monkeypatch.setattr(service, "_require_game", lambda: campaign)
    service.post_stored_context({"diagnostic": "unsaved API change"})
    window = window_for(campaign)
    question = Mock(return_value=int(QMessageBox.StandardButton.Cancel))
    monkeypatch.setattr(QMessageBox, "question", question)
    event = QCloseEvent()
    QLiberationWindow.closeEvent(window, event)
    question.assert_called_once()
    assert not event.isAccepted()


def test_unexpected_save_exception_does_not_accept_close(monkeypatch: Any) -> None:
    window = window_for(None)
    window.saveGame = Mock(side_effect=RuntimeError("unexpected error"))
    monkeypatch.setattr(persistency, "has_unsaved_changes", lambda game: True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    event = QCloseEvent()
    with pytest.raises(RuntimeError, match="unexpected error"):
        QLiberationWindow.closeEvent(window, event)
    assert not event.isAccepted()
    window._shut_down.assert_not_called()
