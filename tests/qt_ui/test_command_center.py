"""Regression coverage for integrated Intel and aircraft notes."""

from __future__ import annotations

import os
import pickle
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from game.ato.aircraftnotes import notes_for_flight
from game.models.game_stats import FactionTurnMetadata, GameTurnMetadata
from game.squadrons.pilot import Pilot, PilotStatus
from game.theater import Player
from qt_ui.windows.intel.statistics import StatisticsPane, history
from qt_ui.windows.playable.model import Aircraft
from qt_ui.windows.playable.notes import AircraftNotesPane


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


def flight(*pilots: Pilot, kind: str = "FA-18C_hornet") -> Any:
    return SimpleNamespace(
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=kind)),
        iter_members=lambda: iter(
            SimpleNamespace(is_player=True, pilot=p) for p in pilots
        ),
    )


def test_notes_follow_pilot_airframe_and_survive_save(app: Any) -> None:
    first, second = Pilot("One", player=True), Pilot("Two", player=True)
    pane = AircraftNotesPane()
    pane.show_aircraft(Aircraft(flight(first, second)))
    pane.editor.setPlainText("Hornet checklist")
    pane.players.setCurrentIndex(1)
    assert pane.editor.toPlainText() == ""
    pane.editor.setPlainText("Second pilot notes")
    pane.show_aircraft(Aircraft(flight(first, kind="F-16C_50")))
    assert pane.editor.toPlainText() == ""
    pane.editor.setPlainText("Viper checklist")
    restored = pickle.loads(pickle.dumps(first))
    assert notes_for_flight(flight(restored)) == [("One", "Hornet checklist")]
    assert notes_for_flight(flight(restored, kind="F-16C_50")) == [
        ("One", "Viper checklist")
    ]
    assert second.aircraft_notes == {"FA-18C_hornet": "Second pilot notes"}
    pane.show_aircraft(None)
    assert not pane.editor.isEnabled()
    pane.close()


def test_old_pilot_save_gets_independent_notes() -> None:
    pilot = Pilot("Old")
    state = dict(pilot.__dict__)
    state.pop("aircraft_notes")
    pilot.__setstate__(state)
    assert pilot.aircraft_notes == {}


def test_notes_preserve_pilot_constructor_and_identity() -> None:
    pilot = Pilot("Old", False, PilotStatus.OnLeave)
    assert pilot.status == PilotStatus.OnLeave
    assert pilot.aircraft_notes == {}


def test_financial_and_pilot_statistics_are_recorded(monkeypatch: Any) -> None:
    from game.models.game_stats import GameStats
    from game import income

    monkeypatch.setattr(
        income,
        "Income",
        lambda game, player: SimpleNamespace(total=12 if player.is_blue else 8),
    )

    def coalition(budget: float) -> Any:
        return SimpleNamespace(
            budget=budget,
            air_wing=SimpleNamespace(
                iter_squadrons=lambda: iter(
                    [
                        SimpleNamespace(
                            current_roster=[
                                SimpleNamespace(alive=True),
                                SimpleNamespace(alive=False),
                            ]
                        )
                    ]
                )
            ),
        )

    game: Any = SimpleNamespace(
        turn=0,
        theater=SimpleNamespace(controlpoints=[]),
        blue=coalition(90),
        red=coalition(70),
    )
    stats = GameStats()
    stats.update(game)
    blue = stats.data_per_turn[0].allied_units
    red = stats.data_per_turn[0].enemy_units
    assert (blue.money, blue.income, blue.pilots, blue.bases) == (90, 12, 1, 0)
    assert (red.money, red.income) == (70, 8)


def test_statistics_preserve_missing_history_and_toggle(app: Any) -> None:
    old, current = GameTurnMetadata(), GameTurnMetadata()
    current.allied_units.money = 123.5
    current.enemy_units.money = 60
    game: Any = SimpleNamespace(
        game_stats=SimpleNamespace(data_per_turn=[old, current])
    )
    assert history(game, Player.BLUE, "money") == [(0, None), (1, 123.5)]
    pane = StatisticsPane(game)
    pane.show_side(Player.RED)
    for check in pane.checks.values():
        check.setChecked(False)
    assert game.intel_statistics_metrics == []
    pane.checks["money"].setChecked(True)
    assert game.intel_statistics_metrics == ["money"]
    pane.close()


def test_empty_statistics_are_supported(app: Any) -> None:
    game: Any = SimpleNamespace(game_stats=SimpleNamespace(data_per_turn=[]))
    pane = StatisticsPane(game)
    pane.compare.setChecked(False)
    pane.close()


def test_preferences_are_reachable_under_general(app: Any, monkeypatch: Any) -> None:
    from qt_ui import liberation_install
    from qt_ui import liberation_theme

    liberation_theme.set_theme_index(0)

    for name, value in (
        ("get_dcs_install_directory", ""),
        ("get_saved_game_dir", ""),
        ("prefer_liberation_payloads", False),
        ("setup_preferences_on_every_start", False),
        ("server_port", 16880),
    ):
        monkeypatch.setattr(liberation_install, name, lambda v=value: v)
    from game.settings import Settings
    from qt_ui.windows.settings.QSettingsWindow import AutoSettingsPage
    from qt_ui.windows.preferences.QLiberationPreferences import PreferencesPane

    sc: Any = SimpleNamespace(settings=Settings())
    page = AutoSettingsPage("General", sc, lambda: None)
    assert page.sections is not None
    page.sections.setCurrentRow(page.stack.count() - 1)
    assert isinstance(page.stack.currentWidget(), PreferencesPane)
    page.refresh_page()
    assert isinstance(page.stack.currentWidget(), PreferencesPane)
    page.close()


def test_transfers_filter_and_cancel_the_source_row(app: Any) -> None:
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from qt_ui.models import TransferModel
    from qt_ui.windows.intel.transfers import TransfersPane

    class Model(QStandardItemModel):
        def cancel_transfer_at_index(self, index: Any) -> None:
            self.removeRow(index.row())

    model: Any = Model()
    for name, side in (("Red", Player.RED), ("Blue", Player.BLUE)):
        item = QStandardItem(name)
        item.setData(
            SimpleNamespace(player=side, description="To base"),
            TransferModel.TransferRole,
        )
        model.appendRow(item)
    pane = TransfersPane(model)
    assert pane.proxy.rowCount() == 1
    pane.view.setCurrentIndex(pane.proxy.index(0, 0))
    assert pane.cancel.isEnabled()
    pane.cancel_selected()
    assert model.rowCount() == 1
    assert model.item(0).text() == "Red"
    pane.show_side(Player.RED)
    pane.view.setCurrentIndex(pane.proxy.index(0, 0))
    assert not pane.cancel.isEnabled()
    pane.close()
