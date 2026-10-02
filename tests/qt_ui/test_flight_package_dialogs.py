"""UI state and roster regression checks for mission planning dialogs."""

import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def environment(tmp_path: Path, monkeypatch: Any) -> Iterator[None]:
    from game import persistency
    from PySide6.QtGui import QIcon
    from qt_ui.uiconstants import EVENT_ICONS

    persistency.setup(str(tmp_path), False, 16897)
    monkeypatch.setitem(EVENT_ICONS, "strike", QIcon())
    errors: list[Any] = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: errors.append(args))
    yield
    assert not errors, errors


class Named(SimpleNamespace):
    def __str__(self) -> str:
        return str(self.name)


def make_creator(monkeypatch: Any, available: bool = True) -> Any:
    from game.ato.flighttype import FlightType
    from game.ato.loadouts import Loadout
    from game.ato.starttype import StartType
    from game.dcs.aircrafttype import AircraftType
    from game.settings import Settings
    from game.squadrons.pilot import Pilot
    from game.theater import Player
    from qt_ui.windows.mission.flight.QFlightCreator import QFlightCreator

    aircraft = AircraftType.named("F/A-18C Hornet (Lot 20)")
    settings = Settings()
    settings.default_start_type = StartType.COLD
    settings.default_start_type_client = StartType.COLD
    base = Named(
        name="Home base",
        captured=Player.BLUE,
        required_aircraft_start_type=None,
        runway_is_operational=lambda: True,
        can_operate=lambda _: True,
        distance_to=lambda _: 10000,
    )
    squadron = Named(
        name="Squadron 001",
        location=base,
        aircraft=aircraft,
        primary_task=FlightType.STRIKE,
        untasked_aircraft=4,
        capable_of=lambda _: True,
        can_auto_assign=lambda _: True,
        player=Player.BLUE,
        morale_in_play=False,
        friendship_in_play=False,
        pilot_rank=lambda _: None,
        pilot_skill=lambda _: "Excellent",
        rank_order=lambda _: (),
        settings=settings,
        available_pilots=[Pilot(f"Pilot {i + 1}") for i in range(4)],
    )
    squadron.claim_available_pilot = lambda alongside=(): (
        squadron.available_pilots.pop(0) if squadron.available_pilots else None
    )
    squadron.claim_pilot = lambda pilot: squadron.available_pilots.remove(pilot)
    squadron.return_pilot = lambda pilot: squadron.available_pilots.append(pilot)
    squadron.return_pilots = lambda pilots: squadron.available_pilots.extend(pilots)
    wing = SimpleNamespace(
        best_available_aircrafts_for=lambda _: [aircraft] if available else [],
        squadrons_for=lambda _: [squadron] if available else [],
    )
    game: Any = SimpleNamespace(
        theater=SimpleNamespace(controlpoints=[base]),
        settings=settings,
        blue=SimpleNamespace(air_wing=wing),
        red=SimpleNamespace(air_wing=wing),
    )
    package: Any = SimpleNamespace(
        target=Named(
            name="Training target",
            mission_types=lambda **_: [FlightType.STRIKE, FlightType.ANTISHIP],
        )
    )
    first = Loadout.empty_loadout()
    second = Loadout.empty_loadout()
    first.name, second.name = "Strike preset", "Alternative preset"
    monkeypatch.setattr(Loadout, "iter_for_aircraft", lambda _: iter([first, second]))
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.QFlightCreator.get_default_loadout_override",
        lambda *_: None,
    )
    return QFlightCreator(game, package, True)


@pytest.fixture
def creator(qt_app: Any, monkeypatch: Any) -> Iterator[Any]:
    dialog = make_creator(monkeypatch)
    yield dialog
    dialog.reject()
    dialog.deleteLater()
    qt_app.processEvents()


def test_creator_roster_resize_player_and_cancel(creator: Any) -> None:
    squadron = creator.squadron_selector.currentData()
    assert not squadron.available_pilots
    creator.flight_size_spinner.setValue(2)
    assert len(squadron.available_pilots) == 2
    assert "2/2 pilots assigned" in creator.crew_summary.text()
    creator.roster_editor.pilot_controls[0].player_checkbox.click()
    assert "1 player slot" in creator.crew_summary.text()
    creator.cancel_button.click()
    assert len(squadron.available_pilots) == 4


def test_loadout_search_and_task_changes_preserve_roster(creator: Any) -> None:
    from qt_ui.widgets.searchablecombo import SearchableComboBox

    assert isinstance(creator.loadout_selector, SearchableComboBox)
    assert creator.loadout_selector.threshold == 2
    creator.loadout_selector.setCurrentIndex(1)
    assert creator.current_loadout().name == "Alternative preset"
    creator.task_selector.setCurrentIndex(1)
    assert len(list(creator.roster_editor.roster.iter_pilots())) == 4
    assert creator.verify_form() is None


@pytest.mark.parametrize("is_ownfor", [True, False])
def test_creator_only_uses_player_default_for_own_side(
    creator: Any, monkeypatch: Any, is_ownfor: bool
) -> None:
    from game.ato.loadouts import Loadout

    creator.is_ownfor = is_ownfor
    lookup = Mock(return_value="Alternative preset")
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.QFlightCreator.get_default_loadout_override",
        lookup,
    )
    monkeypatch.setattr(
        Loadout,
        "default_loadout_names_for",
        classmethod(lambda cls, task: iter(["Strike preset"])),
    )
    creator._init_loadout_selector()
    assert creator.current_loadout().name == (
        "Alternative preset" if is_ownfor else "Strike preset"
    )
    assert lookup.call_count == int(is_ownfor)


@pytest.mark.parametrize("method", ["save_as_task_default", "clear_task_default"])
def test_enemy_payload_editor_cannot_change_player_defaults(method: str) -> None:
    from game.theater import Player
    from qt_ui.windows.mission.flight.payload.QLoadoutEditor import QLoadoutEditor

    # Only the coalition is available: accessing dialogs or persistence would fail.
    editor: Any = SimpleNamespace(flight=SimpleNamespace(blue=Player.RED))
    getattr(QLoadoutEditor, method)(editor)


def test_creator_required_start_and_empty_air_wing(
    creator: Any, qt_app: Any, monkeypatch: Any
) -> None:
    from game.ato.starttype import StartType

    creator.squadron_selector.currentData().location.required_aircraft_start_type = (
        StartType.IN_FLIGHT
    )
    creator.roster_editor.pilots_changed.emit()
    assert creator.start_type.currentData() == StartType.IN_FLIGHT
    assert not creator.start_type.isEnabled()
    assert "Required" in creator.start_hint.text()
    empty = make_creator(monkeypatch, available=False)
    assert not empty.create_button.isEnabled()
    assert "no compatible aircraft" in empty.selection_summary.text()
    empty.reject()
    empty.deleteLater()


def make_package_dialog() -> Any:
    from game.ato.package import Package
    from game.db import Database
    from qt_ui.models import PackageModel
    from qt_ui.windows.mission.QPackageDialog import QEditPackageDialog

    target: Any = Named(name="Training target")
    package: Any = Package(target, Database(), auto_asap=True)
    package.time_over_target = datetime(2026, 1, 1, 12, 30)
    package.set_tot_asap = lambda _: None
    gm: Any = SimpleNamespace(
        sim_controller=Mock(), allocated_freqs=[], is_ownfor=True, ato_model=Mock()
    )
    return QEditPackageDialog(gm, PackageModel(package, gm))


@pytest.fixture
def package_dialog(qt_app: Any) -> Iterator[Any]:
    dialog = make_package_dialog()
    yield dialog
    dialog.deleteLater()
    qt_app.processEvents()


def insert_flight(dialog: Any) -> Any:
    from PySide6.QtCore import QModelIndex
    from game.ato.flighttype import FlightType

    flight = SimpleNamespace(
        count=4,
        client_count=1,
        missing_pilots=0,
        departure=Named(name="Home base"),
        squadron=Named(name="Squadron 001"),
        unit_type=SimpleNamespace(
            display_name="F/A-18C Hornet (Lot 20)", dcs_id="FA-18C_hornet"
        ),
        flight_type=FlightType.STRIKE,
        flight_plan=SimpleNamespace(
            takeoff_time=lambda: datetime(2026, 1, 1, 12),
            ingress_time=datetime(2026, 1, 1, 12, 25),
            landing_time=datetime(2026, 1, 1, 13, 10),
        ),
        state=SimpleNamespace(is_waiting_for_start=True),
    )
    model = dialog.package_model
    model.beginInsertRows(QModelIndex(), 0, 0)
    model.package.flights.append(flight)
    model.endInsertRows()
    return flight


def test_package_empty_population_and_edit_action(
    package_dialog: Any, monkeypatch: Any
) -> None:
    from PySide6.QtCore import QModelIndex

    dialog = package_dialog
    assert dialog.flight_stack.currentIndex() == 1
    assert dialog.auto_create_button.isEnabled()
    assert not dialog.edit_flight_button.isEnabled()
    insert_flight(dialog)
    assert dialog.flight_stack.currentIndex() == 0
    assert not dialog.auto_create_button.isEnabled()
    assert "4 aircraft" in dialog.package_context.text()
    dialog.package_view.setCurrentIndex(dialog.package_model.index(0))
    edit = Mock()
    monkeypatch.setattr(dialog.package_view, "edit_flight", edit)
    dialog.edit_flight_button.click()
    edit.assert_called_once()
    model = dialog.package_model
    model.beginRemoveRows(QModelIndex(), 0, 0)
    model.package.flights.clear()
    model.endRemoveRows()
    assert dialog.flight_stack.currentIndex() == 1
    assert not dialog.delete_flight_button.isEnabled()


def test_package_timing_and_name_controls(package_dialog: Any) -> None:
    from PySide6.QtCore import QTime

    dialog = package_dialog
    assert not dialog.tot_spinner.isEnabled()
    dialog.auto_asap.click()
    assert dialog.tot_spinner.isEnabled()
    dialog.tot_spinner.setTime(QTime(14, 15, 16))
    assert dialog.package_model.package.time_over_target.hour == 14
    dialog.package_name_text.setText("Custom package")
    assert dialog.package_model.package.custom_name == "Custom package"
    flight = insert_flight(dialog)
    flight.state.is_waiting_for_start = False
    dialog.package_model.dataChanged.emit(
        dialog.package_model.index(0), dialog.package_model.index(0)
    )
    assert not dialog.auto_asap.isEnabled()
    assert not dialog.tot_spinner.isEnabled()
    assert "locked" in dialog.timing_hint.text()


@pytest.mark.parametrize("save", [False, True])
def test_new_package_save_and_cancel(
    package_dialog: Any, qt_app: Any, monkeypatch: Any, save: bool
) -> None:
    from game.db import Database
    from qt_ui.windows.mission.QPackageDialog import QNewPackageDialog

    gm = package_dialog.game_model
    gm.game = SimpleNamespace(db=SimpleNamespace(flights=Database()))
    dialog = QNewPackageDialog(gm, package_dialog.package_model.mission_target)
    monkeypatch.setattr(dialog.package_model.package, "set_tot_asap", lambda _: None)
    if save:
        dialog.save_button.click()
        gm.ato_model.add_package.assert_called_once_with(dialog.package_model.package)
    else:
        dialog.cancel_button.click()
        gm.ato_model.add_package.assert_not_called()
    dialog.deleteLater()
    qt_app.processEvents()
