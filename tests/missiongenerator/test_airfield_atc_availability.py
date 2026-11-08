"""A field without a DCS ATC station must not look like a missing preset."""

from types import SimpleNamespace as NS
from typing import Any

from dcs.terrain.nevada import Nevada

from game.atcdata import AtcData
from game.missiongenerator.kneeboard import BriefingPage
from game.radio.channels import CommonRadioChannelAllocator
from game.radio.radios import MHz
from game.runways import RunwayData
from tests.test_radio_channel_allocation import scenario


def _tonopah_runway() -> RunwayData:
    terrain = Nevada()
    airport = terrain.airports["Tonopah"]
    theater: Any = NS(terrain=terrain)
    return RunwayData.for_pydcs_runway_runway(
        theater, airport, airport.runways[0].opposite
    )


def test_tonopah_and_tonopah_test_range_have_distinct_atc_data() -> None:
    terrain = Nevada()
    assert AtcData.from_pydcs(terrain.airports["Tonopah"]) is None
    controlled = AtcData.from_pydcs(terrain.airports["Tonopah Test Range"])
    assert controlled is not None
    assert controlled.uhf == MHz(257, 950)
    assert controlled.vhf_am == MHz(124, 750)


def test_no_atc_is_explicit_in_departure_and_arrival_rows() -> None:
    page = object.__new__(BriefingPage)
    runway = _tonopah_runway()
    for title in ("Departure", "Arrival"):
        row = page.airfield_info_row(title, runway)
        assert row[:3] == [title, "Tonopah", "No ATC"]
        assert row[-1] == "15"


def test_an_absent_divert_does_not_claim_to_be_an_uncontrolled_airfield() -> None:
    page = object.__new__(BriefingPage)
    assert page.airfield_info_row("Divert", None) == ["Divert", "", "", "", "", ""]


def test_a_real_frequency_keeps_its_automatic_channel_annotation() -> None:
    s = scenario()
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    page = object.__new__(BriefingPage)
    page.flight = s.flight
    row = page.airfield_info_row("Departure", s.flight.departure)
    assert "250 MHz AM" in row[2]
    assert "COMM1" in row[2]
    assert "No ATC" not in row[2]


def test_an_uncontrolled_departure_does_not_receive_an_invented_atc_preset() -> None:
    s = scenario()
    s.flight.departure = s.flight.arrival = _tonopah_runway()
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    assert not s.flight.channels_for(MHz(250))
    assert not s.flight.channels_for(MHz(257, 950))
    assert s.flight.channels_for(s.flight.package.frequency)
