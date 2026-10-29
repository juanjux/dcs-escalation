"""Additional RetLab DTC data without its fog or territory model."""

from types import SimpleNamespace
from typing import Any

from dcs import Point
from dcs.terrain import Caucasus

from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType as W
from game.missiongenerator import dtc
from game.radio.radios import MHz
from game.theater import Player

TERRAIN = Caucasus()


def orbit(callsign: str, task: FlightType, side: Player = Player.BLUE) -> Any:
    return SimpleNamespace(
        callsign=callsign,
        flight_type=task,
        friendly=side,
        waypoints=[
            SimpleNamespace(
                waypoint_type=W.PATROL_TRACK, position=Point(100, 200, TERRAIN)
            ),
            SimpleNamespace(waypoint_type=W.PATROL, position=Point(1100, 200, TERRAIN)),
        ],
    )


def test_hornet_own_track_precedes_support_and_other_caps_are_not_added() -> None:
    own = orbit("Own CAP", FlightType.BARCAP)
    data = SimpleNamespace(
        flights=[
            own,
            orbit("Tanker", FlightType.REFUELING),
            orbit("AWACS", FlightType.AEWC),
            orbit("Other CAP", FlightType.BARCAP),
            orbit("Enemy", FlightType.AEWC, Player.RED),
        ]
    )
    points = dtc.friendly_orbit_points(own, data)
    assert [p["note"] for p in points] == ["Own CAP", "Tanker", "AWACS"]
    assert points[0]["length"] == 3704
    assert (points[0]["x"], points[0]["y"]) == (600, 200)
    assert points[0]["course"] == 0
    assert points[0]["diameter"] == 9260


def test_red_player_gets_no_blue_support_tracks() -> None:
    own = orbit("Red CAP", FlightType.BARCAP, Player.RED)
    data = SimpleNamespace(
        flights=[
            orbit("Blue", FlightType.AEWC),
            orbit("Red tanker", FlightType.REFUELING, Player.RED),
        ]
    )
    assert [p["note"] for p in dtc.friendly_orbit_points(own, data)] == [
        "Red CAP",
        "Red tanker",
    ]


def test_hornet_hold_is_a_readable_point_orbit_and_nine_is_the_limit() -> None:
    own = orbit("Strike", FlightType.STRIKE)
    own.waypoints = [
        SimpleNamespace(waypoint_type=W.LOITER, position=Point(50, 60, TERRAIN))
    ]
    data = SimpleNamespace(
        flights=[orbit(f"Tanker {n}", FlightType.REFUELING) for n in range(12)]
    )
    points = dtc.friendly_orbit_points(own, data)
    assert len(points) == 9
    assert (points[0]["x"], points[0]["y"]) == (50, 60)
    assert [p["num"] for p in points] == list(range(1, 10))


def test_radio_labels_keep_all_assigned_and_unused_frequencies() -> None:
    channels = {n: 300.0 + n * 0.25 for n in range(1, 21)}
    own = SimpleNamespace(
        callsign="Enfield 11",
        friendly=Player.BLUE,
        client_units=[SimpleNamespace(radio={1: {"channels": channels}})],
        intra_flight_channel=MHz(300, 250),
        frequency_to_channel_map={
            MHz(300, 250): [SimpleNamespace(radio_id=1, channel=1)],
            MHz(300, 500): [SimpleNamespace(radio_id=1, channel=2)],
        },
    )
    data = SimpleNamespace(
        awacs=[SimpleNamespace(freq=MHz(300, 500), callsign="Magic", blue=Player.BLUE)]
    )
    result = dtc.hornet_radio_presets(own, data)
    assert result["mirror_COMM1"] is False
    assert result["mirror_COMM2"] is True
    assert result["COMM2"] == {}
    assert result["COMM1"]["Channel_1"]["name"] == "ENFIE"
    assert result["COMM1"]["Channel_2"]["name"] == "MAGIC"
    assert [result["COMM1"][f"Channel_{n}"]["frequency"] for n in range(1, 21)] == list(
        channels.values()
    )


def test_missing_actual_radio_presets_do_not_invent_a_radio_table() -> None:
    own = SimpleNamespace(callsign="Flight", frequency_to_channel_map={MHz(251): []})
    assert dtc.hornet_radio_presets(own, None) == {}


def test_complete_automatic_cmds_table_retains_native_program_choices() -> None:
    programs = dtc.automatic_countermeasure_programs()
    exported = dtc._cmds_threats()
    assert (
        len(programs["CMDS_Avionics_Threat_Table"]) == len(exported["threats"]) == 123
    )
    for source, entry in zip(
        exported["threats"], programs["CMDS_Avionics_Threat_Table"]
    ):
        assert entry["group_name"] == source["group_name"]
        assert entry["program"] == source["program"]
        assert entry["thresholds"] == source["thresholds"]
        assert entry["threats"] == source["threats"]
        if source["category"]:
            assert (
                programs[source["category"]][source["group_name"]]["program"]
                == source["program"]
            )
    assert programs["Ground"]
    assert programs["delayBetweenPrograms"] == 2


def test_cmds_cartridges_do_not_share_mutable_cached_threat_data() -> None:
    first = dtc.automatic_countermeasure_programs()
    first["CMDS_Avionics_Threat_Table"][0]["threats"].clear()
    second = dtc.automatic_countermeasure_programs()
    assert second["CMDS_Avionics_Threat_Table"][0]["threats"]


def test_oversized_viper_route_is_left_mirrored_not_truncated() -> None:
    from tests.test_dtc import _nav

    assert _nav(dtc.ViperCartridge(), route=25, saved=1) == []


def test_hornet_campaign_orbits_do_not_remove_attack_corridor() -> None:
    from tests.test_dtc import _game, _flight_data, _waypoint

    flight = _flight_data()
    flight.waypoints = [
        _waypoint("Hold", 0, 0),
        _waypoint("IP", 1, 1),
        _waypoint("Split", 2, 2),
    ]
    flight.waypoints[0].waypoint_type = W.LOITER
    flight.waypoints[1].waypoint_type = W.INGRESS_STRIKE
    flight.waypoints[2].waypoint_type = W.SPLIT
    for index, waypoint in enumerate(flight.waypoints):
        waypoint.position = Point(index * 1000, 0, TERRAIN)
    data = dtc.HornetCartridge().campaign_sections(_game(), flight)
    assert data["SA"]["Default_CAP_Point"] == 1
    assert data["SA"]["CAP_PTS"]
    assert data["SA"]["CORRIDORS"]
