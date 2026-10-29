"""AFAC cannot allocate human slots or change a pilot's global player flag."""

import os
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from dcs.unit import Skill

from game.ato import Flight, FlightType
from game.ato.flightmembers import FlightMembers
from game.ato.flightroster import FlightRoster
from game.ato.loadouts import Loadout
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)
from game.squadrons import Squadron
from game.squadrons.pilot import Pilot


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    from game import persistency

    persistency.setup(str(tmp_path), False, 0)


def squadron_with(*pilots: Pilot) -> Any:
    squadron = Squadron.__new__(Squadron)
    squadron.available_pilots = list(pilots)
    squadron.aircraft = NS(variant_id="test", flyable=True)  # type: ignore[assignment]
    squadron.claim_new_pilot_if_allowed = MagicMock(return_value=None)  # type: ignore[method-assign]
    return squadron


def test_ai_only_allocation_ignores_player_preference_without_changing_flags() -> None:
    human, ai = Pilot("Human", player=True), Pilot("AI")
    squadron = squadron_with(ai, human)
    assert squadron.claim_available_pilot(ai_only=True) is ai
    assert squadron.available_pilots == [human]
    assert squadron.claim_available_pilot(ai_only=True) is None
    assert human.player


def test_recruitment_cannot_introduce_a_player_from_an_old_pool() -> None:
    human = Pilot("Human", player=True)
    squadron = squadron_with()
    squadron.claim_new_pilot_if_allowed.return_value = human
    assert squadron.claim_available_pilot(ai_only=True) is None
    assert squadron.available_pilots == [human] and human.player


def test_creator_roster_rejects_player_before_claiming_or_releasing_pilots() -> None:
    human, ai = Pilot("Human", player=True), Pilot("AI")
    squadron = squadron_with(ai, human)
    roster = FlightRoster(squadron, 1, allow_players=False)
    assert roster.pilot_at(0) is ai
    with pytest.raises(ValueError, match="AI pilots only"):
        roster.set_pilot(0, human)
    assert roster.pilot_at(0) is ai and squadron.available_pilots == [human]
    roster.resize(2)
    assert roster.pilot_at(1) is None
    assert human.player


@pytest.mark.parametrize("task", [FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE])
def test_flight_members_allocate_ai_and_reject_manual_player_assignment(
    task: FlightType,
) -> None:
    human, ai = Pilot("Human", player=True), Pilot("AI")
    squadron = squadron_with(ai, human)
    flight: Any = NS(flight_type=task, squadron=squadron)
    with patch.object(Loadout, "default_for", return_value=Loadout.empty_loadout()):
        members = FlightMembers(flight, 1)
    assert not members.allow_players and members.pilot_at(0) is ai
    with pytest.raises(ValueError, match="AI pilots only"):
        members.set_pilot(0, human)
    assert members.player_count == 0 and human.player


def test_flight_creation_rejects_player_roster_before_claiming_inventory() -> None:
    settings = NS(plugins={"realisticcas": True, "realisticcas.afacEnabled": True})
    squadron = MagicMock(settings=settings)
    roster: Any = NS(player_count=1)
    with pytest.raises(ValueError, match="AI pilots only"):
        Flight(
            MagicMock(),
            squadron,
            1,
            FlightType.AFAC_AREA,
            MagicMock(),
            None,
            roster=roster,
        )
    squadron.claim_inventory.assert_not_called()


def test_old_flight_with_player_is_rejected_before_mission_configuration() -> None:
    configurator: Any = NS(
        flight=NS(flight_type=FlightType.AFAC_FRONTLINE, client_count=1),
        setup_radios=MagicMock(),
    )
    with pytest.raises(ValueError, match="Replace player pilots"):
        FlightGroupConfigurator.configure(configurator)
    configurator.setup_radios.assert_not_called()


def test_player_flight_cannot_be_converted_to_afac() -> None:
    flight: Any = NS(flight_type=FlightType.CAS, client_count=1)
    with pytest.raises(ValueError, match="AI pilots only"):
        Flight.set_flight_type(flight, FlightType.AFAC_AREA)
    assert flight.flight_type is FlightType.CAS


def test_editor_explains_why_a_player_flight_cannot_be_converted() -> None:
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab import (
        QFlightWaypointTab,
    )

    editor: Any = NS(flight=NS(client_count=1))
    module = "qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab.QMessageBox"
    with patch(module) as message:
        QFlightWaypointTab.confirm_recreate(editor, FlightType.AFAC_FRONTLINE)
    message.information.assert_called_once()
    message.question.assert_not_called()


@pytest.mark.parametrize("skill", [Skill.Client, Skill.Player])
def test_registry_rejects_human_afac_aircraft(skill: Skill) -> None:
    from game.missiongenerator.realisticcasluadata import collect_registry
    from tests.missiongenerator.test_afac_missions import scenario

    s = scenario()
    s.group.units[0].skill = skill
    data: Any = NS(
        jtacs=[],
        flights=[NS(flight_type=FlightType.AFAC_AREA, units=s.group.units)],
    )
    mapping: Any = NS()
    with pytest.raises(ValueError, match="AI aircraft only"):
        collect_registry(s.mission, data, enabled=True, unit_map=mapping)


def test_ai_roster_controls_remain_locked_after_refresh_and_resize() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from qt_ui.windows.mission.flight.settings.QFlightSlotEditor import (
        FlightRosterEditor,
    )

    app = QApplication.instance() or QApplication([])
    human, ai = Pilot("Human", player=True), Pilot("AI")
    squadron = squadron_with(ai, human)
    squadron.aircraft = NS(flyable=True)
    squadron.settings = NS(live_pilots_enabled=False)
    squadron.pilot_rank = lambda _: None
    squadron.rank_order = lambda _: ()

    roster = FlightRoster(squadron, 1, allow_players=False)
    editor = FlightRosterEditor(squadron, roster)
    controls = editor.pilot_controls[0]
    assert not controls.player_checkbox.isEnabled()
    assert all(
        controls.selector.itemData(i) is not human
        for i in range(controls.selector.count())
    )
    controls.update_available_pilots()
    editor.resize(1)
    assert not controls.player_checkbox.isEnabled()
    controls.player_checkbox.setChecked(True)
    assert not controls.player_checkbox.isChecked() and not ai.player and human.player
    assert app is not None
