"""Shared support frequencies need one automatic preset per radio, not per unit."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zipfile import ZipFile

from dcs import Mission, Point, lua
from dcs.planes import FA_18C_hornet

from game.ato import FlightType
from game.ato.starttype import StartType
from game.missiongenerator.aircraft.flightdata import ChannelAssignment, FlightData
from game.missiongenerator.kneeboard import SupportPage
from game.missiongenerator.missiondata import AwacsInfo, MissionData, TankerInfo
from game.radio.channels import ChannelNamer, CommonRadioChannelAllocator
from game.radio.radios import MHz
from game.runways import RunwayData
from game.theater.player import Player
from game.utils import Heading


class AircraftLabel:
    channel_name = staticmethod(ChannelNamer.channel_name)

    def __str__(self) -> str:
        return "F/A-18C"


def scenario() -> Any:
    mission = Mission()
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "Player Hornets",
        FA_18C_hornet,
        Point(-200000, 600000, mission.terrain),
        5000,
        group_size=2,
    )
    for unit in group.units:
        unit.set_client()
    package: Any = NS(
        frequency=MHz(257),
        custom_name="",
        package_description="STRIKE",
        time_over_target=None,
    )
    squadron: Any = NS(radio_presets={})
    aircraft: Any = AircraftLabel()
    runway = RunwayData("Departure", Heading(90), "09", atc=MHz(250))
    flight = FlightData(
        package=package,
        flight_type=FlightType.STRIKE,
        aircraft_type=aircraft,
        squadron=squadron,
        units=[u for u in group.units],
        size=2,
        friendly=Player.BLUE,
        departure_delay=timedelta(),
        arrival=runway,
        departure=runway,
        divert=RunwayData("Divert", Heading(90), "09", atc=MHz(260)),
        waypoints=[],
        intra_flight_channel=MHz(305),
        bingo_fuel=None,
        joker_fuel=None,
        laser_codes=[],
        custom_name=None,
        start_type=StartType.IN_FLIGHT,
    )
    now = datetime(2026, 1, 1, 10)
    data = MissionData(
        awacs=[
            AwacsInfo(
                "AWACS",
                "Magic 1",
                MHz(253),
                Player.BLUE,
                "Base",
                now,
                now + timedelta(hours=2),
                group.units[0],
            )
        ],
        tankers=[
            TankerInfo(
                name,
                name,
                MHz(311),
                Player.BLUE,
                "KC-135",
                None,
                now,
                now + timedelta(hours=2),
            )
            for name in ("Texaco 9", "Shell 5")
        ],
    )
    return NS(mission=mission, flight=flight, data=data)


def test_shared_tankers_use_one_preset_on_each_radio() -> None:
    s = scenario()
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    assert s.flight.channels_for(MHz(311)) == [
        ChannelAssignment(1, 4),
        ChannelAssignment(2, 5),
    ]
    for unit in s.flight.client_units:
        for radio, channel in ((1, 4), (2, 5)):
            assert unit.radio[radio]["channels"][channel] == 311
            assert list(unit.radio[radio]["channels"].values()).count(311) == 1
    assert SupportPage._format_frequency(s.flight, MHz(311), stack=True) == (
        "COMM1 Ch 4\nCOMM2 Ch 5\n311 MHz AM"
    )


def test_shared_frequencies_keep_their_first_priority_order() -> None:
    s = scenario()
    s.flight.package.frequency = MHz(253)
    s.flight.arrival = RunwayData("Arrival", Heading(90), "09", atc=MHz(311))
    s.flight.divert = RunwayData("Divert", Heading(90), "09", atc=MHz(253))
    assert CommonRadioChannelAllocator._inter_flight_frequencies(s.flight, s.data) == [
        MHz(250),
        MHz(253),
        MHz(311),
    ]


def test_intra_flight_frequency_is_not_assigned_twice_on_its_radio() -> None:
    s = scenario()
    s.flight.intra_flight_channel = MHz(311)
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    assert s.flight.channels_for(MHz(311)) == [
        ChannelAssignment(2, 1),
        ChannelAssignment(1, 4),
    ]
    assert s.flight.channels_for(MHz(260)) == [
        ChannelAssignment(1, 5),
        ChannelAssignment(2, 5),
    ]


def test_duplicate_support_does_not_consume_limited_channel_capacity() -> None:
    s = scenario()
    s.flight.num_radio_channels = lambda radio: 5
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    assert s.flight.channels_for(MHz(260)) == [ChannelAssignment(1, 5)]
    assert all(
        ch.channel <= 5
        for channels in s.flight.frequency_to_channel_map.values()
        for ch in channels
    )


def test_shared_radio_bank_reserves_intra_flight_without_a_second_mirror() -> None:
    s = scenario()
    s.flight.intra_flight_channel = MHz(311)
    CommonRadioChannelAllocator(1, 1).assign_channels_for_flight(s.flight, s.data)
    assert s.flight.channels_for(MHz(311)) == [ChannelAssignment(1, 1)]
    assert s.flight.channels_for(MHz(250)) == [ChannelAssignment(1, 2)]


def test_explicit_squadron_presets_are_not_deduplicated() -> None:
    s = scenario()
    s.flight.squadron.radio_presets = {1: [MHz(311), MHz(311)], 2: [MHz(311)]}
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    assert s.flight.channels_for(MHz(311)) == [
        ChannelAssignment(1, 1),
        ChannelAssignment(1, 2),
        ChannelAssignment(2, 1),
    ]


def test_native_mission_and_support_page_agree_on_shared_tanker_channels(
    tmp_path: Path,
) -> None:
    s = scenario()
    CommonRadioChannelAllocator(1, 2).assign_channels_for_flight(s.flight, s.data)
    path = tmp_path / "radio-presets.miz"
    s.mission.save(path)
    with ZipFile(path) as archive:
        mission = lua.loads(archive.read("mission").decode())["mission"]
    units = [
        unit
        for country in mission["coalition"]["blue"]["country"].values()
        for group in country.get("plane", {}).get("group", {}).values()
        for unit in group["units"].values()
    ]
    for unit in units:
        for radio, channel in ((1, 4), (2, 5)):
            channels = unit["Radio"][radio]["channels"]
            assert channels[channel] == 311
            assert list(channels.values()).count(311) == 1
    pages = SupportPage.paginate(
        s.flight,
        [],
        [],
        s.data.awacs,
        s.data.tankers,
        datetime(2026, 1, 1, 10),
        dark_kneeboard=False,
    )
    text = ""
    for i, page in enumerate(pages):
        page_path = tmp_path / f"support-{i}.png"
        page.write(page_path)
        text += page_path.with_suffix(".txt").read_text(encoding="utf-8")
    assert text.count("COMM1 Ch 4") == 2
    assert text.count("COMM2 Ch 5") == 2
    assert "COMM1 Ch 5" not in text
    assert "COMM2 Ch 6" not in text
