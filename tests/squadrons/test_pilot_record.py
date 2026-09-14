"""What a campaign remembers about one pilot.

Two integers, until now: missions flown and experience. What he shot down, what he
destroyed, how often he was shot down himself and who finally got him were all worked
out during a debriefing and then thrown away, so the only place any of it existed was
the turn's own report.
"""

from __future__ import annotations

import pickle
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from game.sim.missionresultsprocessor import (
    AIR,
    BUILDING,
    SHIP,
    VEHICLE,
    KilledBy,
    MissionResultsProcessor,
    killer_sentence,
)
from game.squadrons.pilot import Pilot, PilotRecord


def _processor() -> MissionResultsProcessor:
    return MissionResultsProcessor(MagicMock())


# --- the record itself ------------------------------------------------------


def test_a_new_pilot_has_done_nothing() -> None:
    record = PilotRecord()
    assert record.air_kills == {}
    assert record.ground_kills == {}
    assert record.missions_completed == 0
    assert record.aircraft_lost == 0
    assert record.killed_by is None


def test_kills_are_counted_by_what_they_were() -> None:
    """A campaign runs to hundreds of them, and the dialog asks for counts."""
    record = PilotRecord()
    record.note_kill(air=True, what="Su-27")
    record.note_kill(air=True, what="Su-27")
    record.note_kill(air=True, what="MiG-29S")
    record.note_kill(air=False, what="T-72B")

    assert record.air_kills == {"Su-27": 2, "MiG-29S": 1}
    assert record.ground_kills == {"T-72B": 1}
    assert record.total_air_kills == 3
    assert record.total_ground_kills == 1


def test_something_that_cannot_be_named_is_not_counted() -> None:
    """ "One of something unrecognised" is not a row worth having."""
    record = PilotRecord()
    record.note_kill(air=False, what="")
    assert record.ground_kills == {}


def test_a_pilot_from_an_older_save_reads_the_new_fields() -> None:
    """The one that matters: a campaign under way must load."""
    old = {"missions_flown": 7, "xp": 120}
    record = PilotRecord.__new__(PilotRecord)
    record.__setstate__(dict(old))

    assert record.missions_flown == 7
    assert record.xp == 120
    assert record.air_kills == {}
    assert record.ground_kills == {}
    assert record.missions_completed == 0
    assert record.killed_by is None


def test_two_pilots_from_an_older_save_do_not_share_a_tally() -> None:
    """A mutable default is the classic way to give every pilot the same dict."""
    first, second = PilotRecord.__new__(PilotRecord), PilotRecord.__new__(PilotRecord)
    first.__setstate__({"missions_flown": 1})
    second.__setstate__({"missions_flown": 1})

    first.note_kill(air=True, what="Su-27")
    assert second.air_kills == {}


def test_the_record_survives_a_save() -> None:
    pilot = Pilot("Ortega")
    pilot.record.note_kill(air=True, what="Su-27")
    pilot.record.missions_completed = 4
    pilot.record.killed_by = KilledBy("Ivanov", "1st", "MiG-29S", "R-27R", False, 12)

    restored = pickle.loads(pickle.dumps(pilot))
    assert restored.record.air_kills == {"Su-27": 1}
    assert restored.record.missions_completed == 4
    assert restored.record.killed_by == pilot.record.killed_by


# --- what was destroyed -----------------------------------------------------


def _victim_flight(aircraft: str = "Su-27") -> Any:
    return SimpleNamespace(
        flight=SimpleNamespace(unit_type=SimpleNamespace(display_name=aircraft)),
        pilot=MagicMock(),
    )


class _Tgo:
    """A class rather than a SimpleNamespace: a building is named by str()ing it."""

    def __init__(self, category: str) -> None:
        self.category = category
        self.control_point = MagicMock()

    def __str__(self) -> str:
        return "Refinery"


def _victim_unit(unit_type: Any, category: str = "oil") -> Any:
    return SimpleNamespace(
        theater_unit=SimpleNamespace(unit_type=unit_type, ground_object=_Tgo(category))
    )


def test_an_aircraft_is_recognised_and_named() -> None:
    kind = _processor()._victim_kind(_victim_flight("MiG-29S"))
    assert kind.kind == AIR
    assert kind.name == "MiG-29S"


def test_a_vehicle_is_recognised_and_named() -> None:
    from game.dcs.groundunittype import GroundUnitType

    vehicle = MagicMock(spec=GroundUnitType)
    vehicle.display_name = "T-72B"
    kind = _processor()._victim_kind(_victim_unit(vehicle))
    assert kind.kind == VEHICLE
    assert kind.name == "T-72B"


def test_a_hull_is_recognised() -> None:
    from game.dcs.shipunittype import ShipUnitType

    ship = MagicMock(spec=ShipUnitType)
    ship.display_name = "Type 052C"
    assert _processor()._victim_kind(_victim_unit(ship)).kind == SHIP


def test_a_building_keeps_the_category_it_is_paid_by() -> None:
    """The XP table reads it, so the walk has to carry it rather than look again."""
    kind = _processor()._victim_kind(_victim_unit(None, "oil"))
    assert kind.kind == BUILDING
    assert kind.building_category == "oil"


def test_nothing_destroyed_is_recognised_as_nothing() -> None:
    assert _processor()._victim_kind(None).name == ""


# --- who did it -------------------------------------------------------------


class _Squadron:
    def __init__(self, is_blue: bool) -> None:
        self.player = SimpleNamespace(is_blue=is_blue)

    def __str__(self) -> str:
        return "1st FS"


def _killing_flight(pilot: str, is_blue: bool) -> Any:
    return SimpleNamespace(
        pilot=SimpleNamespace(name=pilot),
        flight=SimpleNamespace(squadron=_Squadron(is_blue)),
    )


def _debriefing(killer: Any = None) -> Any:
    return SimpleNamespace(unit_map=SimpleNamespace(flight=lambda name: killer))


def test_the_weapon_is_kept_as_a_weapon() -> None:
    """It was folded into a sentence and the sentence was all that survived, so a
    record could say who but never with what."""
    detail = {
        "initiator": "1",
        "initiator_type": "F-15C",
        "weapon": "AIM-120C",
    }
    parts = _processor()._killer_parts(detail, _debriefing(), True, turn=12)

    assert parts is not None
    assert parts.aircraft == "F-15C"
    assert parts.weapon == "AIM-120C"
    assert parts.turn == 12


def test_the_pilot_behind_the_aircraft_is_preferred_to_the_airframe() -> None:
    killer = _killing_flight("Capt Ortega", is_blue=False)
    detail = {"initiator": "1", "initiator_type": "F-15C", "weapon": "AIM-120C"}

    parts = _processor()._killer_parts(detail, _debriefing(killer), True)
    assert parts is not None
    assert parts.pilot_name == "Capt Ortega"
    assert parts.squadron == "1st FS"


def test_a_kill_by_his_own_side_is_marked_as_one() -> None:
    killer = _killing_flight("Capt Ortega", is_blue=True)
    detail = {"initiator": "1", "initiator_type": "F-15C"}
    parts = _processor()._killer_parts(detail, _debriefing(killer), True)
    assert parts is not None and parts.friendly_fire


def test_nobody_shot_him_down_is_nobody() -> None:
    assert _processor()._killer_parts(None, _debriefing(), True) is None


def test_the_debriefing_sentence_is_built_from_the_pieces() -> None:
    """One place, so the line the debriefing prints and the record a dialog reads
    can never say different things."""
    parts = KilledBy("Capt Ortega", "1st FS", "F-15C", "AIM-120C", False, 12)
    assert killer_sentence(parts) == "Capt Ortega (F-15C) with AIM-120C"


def test_a_weapon_that_is_the_aircraft_is_not_said_twice() -> None:
    """A vehicle kills with itself, and "a T-72B with a T-72B" reads as a bug."""
    parts = KilledBy("T-72B", "", "T-72B", "T-72B", False, 3)
    assert killer_sentence(parts) == "T-72B"


# --- the kill log -----------------------------------------------------------


def test_a_kill_is_written_down_as_well_as_counted() -> None:
    """The count is read at a glance; the entry is what the row opens into."""
    record = PilotRecord()
    record.note_kill(
        air=False, what="SA-15 Tor", kill_class="Air defence", turn=11, weapon="AGM-88C"
    )

    assert record.ground_kills == {"SA-15 Tor": 1}
    assert len(record.kills) == 1
    kill = record.kills[0]
    assert (kill.what, kill.kill_class, kill.turn, kill.weapon) == (
        "SA-15 Tor",
        "Air defence",
        11,
        "AGM-88C",
    )


def test_the_log_is_capped_and_the_counts_are_not() -> None:
    """A year of a good pilot would carry every shot of it into every save."""
    from game.squadrons.pilot import KILL_HISTORY_LIMIT

    record = PilotRecord()
    for turn in range(KILL_HISTORY_LIMIT + 40):
        record.note_kill(air=True, what="Su-27", turn=turn)

    assert len(record.kills) == KILL_HISTORY_LIMIT
    assert record.air_kills["Su-27"] == KILL_HISTORY_LIMIT + 40
    # The oldest go, so what is left is the recent story.
    assert record.kills[-1].turn == KILL_HISTORY_LIMIT + 39


def test_the_kills_behind_one_row_can_be_asked_for() -> None:
    record = PilotRecord()
    record.note_kill(air=False, what="SA-15 Tor", kill_class="Air defence", turn=8)
    record.note_kill(air=False, what="T-72B", kill_class="Armour", turn=8)
    record.note_kill(air=False, what="SA-15 Tor", kill_class="Air defence", turn=11)

    assert len(record.kills_of("SA-15 Tor")) == 2
    assert len(record.kills_in("Armour")) == 1


def test_ground_kills_are_grouped_the_way_a_pilot_would_tell_it() -> None:
    """ "Five air defence" reads at a glance; five separate launcher names do not."""
    record = PilotRecord()
    record.note_kill(air=False, what="SA-15 Tor", kill_class="Air defence", turn=8)
    record.note_kill(air=False, what="ZU-23", kill_class="Air defence", turn=8)
    record.note_kill(air=False, what="T-72B", kill_class="Armour", turn=9)
    record.note_kill(air=True, what="Su-27", turn=9)

    assert record.ground_kills_by_class() == {"Air defence": 2, "Armour": 1}


def test_an_older_save_reads_an_empty_kill_log() -> None:
    record = PilotRecord.__new__(PilotRecord)
    record.__setstate__({"missions_flown": 7, "xp": 120})
    assert record.kills == []


def test_two_pilots_from_an_older_save_do_not_share_a_kill_log() -> None:
    first, second = PilotRecord.__new__(PilotRecord), PilotRecord.__new__(PilotRecord)
    first.__setstate__({})
    second.__setstate__({})
    first.note_kill(air=True, what="Su-27")
    assert second.kills == []


# --- the classes ------------------------------------------------------------


def test_a_launcher_and_its_radar_are_both_air_defence() -> None:
    """What a pilot would say, not what the unit table splits them into."""
    from game.data.units import UnitClass
    from game.sim.missionresultsprocessor import AIR_DEFENCE, ground_class_of

    assert ground_class_of(UnitClass.SHORAD) == AIR_DEFENCE
    assert ground_class_of(UnitClass.SEARCH_RADAR) == AIR_DEFENCE
    assert ground_class_of(UnitClass.MANPAD) == AIR_DEFENCE


def test_tanks_and_carriers_of_infantry_are_both_armour() -> None:
    from game.data.units import UnitClass
    from game.sim.missionresultsprocessor import ARMOUR, ground_class_of

    assert ground_class_of(UnitClass.TANK) == ARMOUR
    assert ground_class_of(UnitClass.APC) == ARMOUR
    assert ground_class_of(UnitClass.IFV) == ARMOUR


def test_anything_else_on_wheels_is_soft() -> None:
    from game.data.units import UnitClass
    from game.sim.missionresultsprocessor import SOFT_VEHICLES, ground_class_of

    assert ground_class_of(UnitClass.LOGISTICS) == SOFT_VEHICLES
    assert ground_class_of(UnitClass.INFANTRY) == SOFT_VEHICLES
    assert ground_class_of(UnitClass.UNKNOWN) == SOFT_VEHICLES


def test_a_building_is_a_structure_and_a_hull_is_a_ship() -> None:
    from game.dcs.shipunittype import ShipUnitType
    from game.sim.missionresultsprocessor import SHIPS, STRUCTURES

    assert (
        _processor()._victim_kind(_victim_unit(None, "oil")).ground_class == STRUCTURES
    )

    ship = MagicMock(spec=ShipUnitType)
    ship.display_name = "Type 052C"
    assert _processor()._victim_kind(_victim_unit(ship)).ground_class == SHIPS
