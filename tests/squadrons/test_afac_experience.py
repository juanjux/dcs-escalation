"""Discovery experience is paid once per verified enemy group and coalition."""

from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock

import pytest

from game.ato import FlightType
from game.debriefing import StateData
from game.settings import Settings
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons.experience import XP_AFAC_DISCOVERY, XP_RECON
from game.squadrons.pilot import Pilot


def scenario(*, blue: bool = True) -> Any:
    settings = Settings()
    settings.plugins.update({"realisticcas": True, "realisticcas.afacEnabled": True})
    pilot = Pilot("Observer")
    flight = NS(flight_type=FlightType.AFAC_AREA, squadron=NS(player=NS(is_blue=blue)))
    flying = NS(pilot=pilot, flight=flight)
    mapping = NS(
        afac_targets={
            "T1": ("GROUP", 1 if blue else 2),
            "T2": ("GROUP", 1 if blue else 2),
        },
        flight=lambda name: flying if name == "OBS" else None,
    )
    detail = {
        "observer": "OBS",
        "target": "T1",
        "group": "GROUP",
        "coalition": 2 if blue else 1,
    }
    debriefing = NS(unit_map=mapping, state_data=NS(afac_discoveries=[detail]))
    processor = MissionResultsProcessor(MagicMock(settings=settings))
    return NS(
        settings=settings,
        pilot=pilot,
        flying=flying,
        mapping=mapping,
        detail=detail,
        debriefing=debriefing,
        processor=processor,
    )


@pytest.mark.parametrize("blue", [False, True])
def test_discovery_credits_both_coalitions_without_recording_a_kill(blue: bool) -> None:
    s = scenario(blue=blue)
    assert s.processor._experience_from_afac(s.debriefing) == {
        id(s.pilot): XP_AFAC_DISCOVERY
    }
    assert s.processor._xp_reasons[id(s.pilot)] == {XP_RECON: XP_AFAC_DISCOVERY}
    assert s.pilot.record.aircraft_lost == 0


def test_duplicate_reports_and_multiple_vehicles_pay_once() -> None:
    s = scenario()
    s.debriefing.state_data.afac_discoveries += [s.detail, dict(s.detail, target="T2")]
    assert s.processor._experience_from_afac(s.debriefing) == {
        id(s.pilot): XP_AFAC_DISCOVERY
    }


@pytest.mark.parametrize(
    "replacement",
    [
        None,
        1,
        "text",
        {},
        {"observer": [], "target": "T1"},
        {"observer": "UNKNOWN", "target": "T1"},
        {"observer": "OBS", "target": "UNKNOWN"},
        {"observer": "OBS", "target": "T1", "group": "FORGED", "coalition": 2},
    ],
)
def test_malformed_or_unverified_records_pay_nothing(replacement: Any) -> None:
    s = scenario()
    s.debriefing.state_data.afac_discoveries = [replacement]
    assert s.processor._experience_from_afac(s.debriefing) == {}


def test_friendly_targets_non_afac_flights_and_disabled_feature_pay_nothing() -> None:
    for kind in ("friendly", "role", "disabled", "old_map", "old_state"):
        s = scenario()
        if kind == "friendly":
            s.mapping.afac_targets["T1"] = ("GROUP", 2)
        elif kind == "role":
            s.flying.flight.flight_type = FlightType.CAS
        elif kind == "disabled":
            s.settings.plugins["realisticcas.afacEnabled"] = False
        elif kind == "old_map":
            del s.mapping.afac_targets
        else:
            del s.debriefing.state_data.afac_discoveries
        assert s.processor._experience_from_afac(s.debriefing) == {}


def test_old_and_malformed_state_files_keep_an_empty_discovery_list() -> None:
    for data in ({}, {"afac_discoveries": None}, {"afac_discoveries": "invalid"}):
        assert StateData.from_json(data, MagicMock()).afac_discoveries == []


def test_old_pickled_state_migrates_discovery_list() -> None:
    state = StateData.__new__(StateData)
    state.__setstate__({})
    assert state.afac_discoveries == []
