"""Mission results notify the UI when the campaign ends."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from game.game import TurnState
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows import QWaitingForMissionResultWindow as waiting
from qt_ui.windows import QLiberationWindow as main


@pytest.fixture
def signals(monkeypatch: pytest.MonkeyPatch) -> GameUpdateSignal:
    monkeypatch.setattr(GameUpdateSignal, "instance", None)
    return GameUpdateSignal()


def _processing(
    monkeypatch: pytest.MonkeyPatch, signals: GameUpdateSignal, outcome: TurnState
) -> Any:
    order: list[str] = []
    progress = Mock()
    progress.close.side_effect = lambda: order.append("progress closed")
    monkeypatch.setattr(waiting, "QProgressDialog", Mock(return_value=progress))
    monkeypatch.setattr(waiting, "QApplication", SimpleNamespace(processEvents=Mock()))
    game: Any = SimpleNamespace(state=TurnState.CONTINUE)

    def advance() -> None:
        order.append("turn processed")
        game.state = outcome

    def check() -> TurnState:
        order.append("outcome checked")
        return game.state

    game.pass_turn = Mock(side_effect=advance)
    game.check_win_loss = Mock(side_effect=check)
    window: Any = SimpleNamespace(
        game=game,
        sim_controller=SimpleNamespace(
            process_results=Mock(
                side_effect=lambda _: order.append("results committed")
            )
        ),
        debriefing=SimpleNamespace(),
        close=Mock(side_effect=lambda: order.append("waiting closed")),
    )
    signals.debriefingReceived.connect(lambda _: order.append("debriefing"))
    signals.gameupdated.connect(lambda _: order.append("game updated"))
    signals.game_state_changed.connect(lambda _: order.append("campaign ended"))
    return SimpleNamespace(window=window, progress=progress, order=order)


@pytest.mark.parametrize("outcome", list(TurnState))
def test_results_notify_outcome_after_processing_and_dialog_cleanup(
    monkeypatch: pytest.MonkeyPatch, signals: GameUpdateSignal, outcome: TurnState
) -> None:
    context = _processing(monkeypatch, signals, outcome)
    received: list[TurnState] = []
    signals.game_state_changed.connect(received.append)

    waiting.QWaitingForMissionResultWindow.process_debriefing(context.window)

    terminal = outcome in (TurnState.WIN, TurnState.LOSS)
    assert received == ([outcome] if terminal else [])
    assert context.order == [
        "results committed",
        "turn processed",
        "outcome checked",
        "debriefing",
        "game updated",
        "progress closed",
        "waiting closed",
    ] + (["campaign ended"] if terminal else [])
    context.window.game.pass_turn.assert_called_once_with()
    context.window.sim_controller.process_results.assert_called_once_with(
        context.window.debriefing
    )


@pytest.mark.parametrize("step", ["commit", "turn"])
def test_processing_failure_does_not_report_a_campaign_outcome(
    monkeypatch: pytest.MonkeyPatch, signals: GameUpdateSignal, step: str
) -> None:
    context = _processing(monkeypatch, signals, TurnState.WIN)
    failed = (
        context.window.sim_controller.process_results
        if step == "commit"
        else context.window.game.pass_turn
    )
    failed.side_effect = RuntimeError("Processing failed")

    with pytest.raises(RuntimeError, match="Processing failed"):
        waiting.QWaitingForMissionResultWindow.process_debriefing(context.window)

    context.progress.close.assert_called_once_with()
    context.window.close.assert_not_called()
    context.window.game.check_win_loss.assert_not_called()
    assert "campaign ended" not in context.order
    assert "game updated" not in context.order
    assert "debriefing" not in context.order


@pytest.mark.parametrize("outcome", list(TurnState))
@pytest.mark.parametrize("new_campaign", [False, True])
def test_end_game_prompt_matches_the_actual_outcome(
    monkeypatch: pytest.MonkeyPatch,
    signals: GameUpdateSignal,
    outcome: TurnState,
    new_campaign: bool,
) -> None:
    window: Any = SimpleNamespace(top_panel=Mock(), newGame=Mock())
    other_window = Mock()
    monkeypatch.setattr(
        main,
        "QApplication",
        SimpleNamespace(
            topLevelWidgets=lambda: [window, other_window], focusWidget=lambda: None
        ),
    )
    reply = (
        main.QMessageBox.StandardButton.Yes
        if new_campaign
        else main.QMessageBox.StandardButton.No
    )
    prompt = Mock(return_value=reply)
    monkeypatch.setattr(main.QMessageBox, "information", prompt)
    updates: list[Any] = []
    signals.gameupdated.connect(updates.append)

    main.QLiberationWindow.onEndGame(window, outcome)

    if outcome is TurnState.CONTINUE:
        prompt.assert_not_called()
        other_window.close.assert_not_called()
        window.top_panel.setControls.assert_not_called()
        window.newGame.assert_not_called()
        assert updates == []
        return

    victory = outcome is TurnState.WIN
    assert prompt.call_count == 1
    assert prompt.call_args.args[1] == ("Victory!" if victory else "Defeat!")
    assert prompt.call_args.args[2] == (
        f"You have {'won' if victory else 'lost'} the campaign, "
        "do you wish to start a new one?"
    )
    other_window.close.assert_called_once_with()
    window.top_panel.setControls.assert_called_once_with(False)
    assert window.newGame.call_count == int(new_campaign)
    assert updates == [None]
