"""The chain behind a site: who cues it, who directs it, what powers it.

The rows are what a dialog paints, so the tests read them the way a player would: the
chip is the verdict for that link and the note says what breaking it costs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.data.units import UnitClass
from game.theater.iadsnetwork.iadsexplain import LinkTone, NoNetwork, describe
from game.theater.iadsnetwork.iadsrole import IadsRole

BLUE = True


def _unit(alive: bool = True, detection: float = 0.0, power: bool = False) -> Any:
    return SimpleNamespace(
        alive=alive,
        detection_range=SimpleNamespace(meters=detection if alive else 0.0),
        unit_type=SimpleNamespace(
            unit_class=UnitClass.POWER if power else UnitClass.LAUNCHER,
            display_name="EPP-III" if power else "Launcher",
            skynet_properties=SimpleNamespace(autonomous_behaviour=None),
        ),
    )


class _Tgo:
    """A ground object keyed by identity, as the real one is."""

    def __init__(self, name: str, at: tuple[float, float]) -> None:
        self.name = name
        self.control_point = SimpleNamespace(captured=SimpleNamespace(is_blue=BLUE))
        self.position = SimpleNamespace(
            distance_to_point=lambda other, _a=at: (
                (_a[0] - other.x) ** 2 + (_a[1] - other.y) ** 2
            )
            ** 0.5,
            x=at[0],
            y=at[1],
        )
        self.groups: list[Any] = []
        self.carries_gps_jammer = False


def _group(
    name: str, role: IadsRole, *units: Any, at: tuple[float, float] = (0.0, 0.0)
) -> Any:
    units = units or (_unit(),)
    tgo = _Tgo(name, at)
    group = SimpleNamespace(
        name=name,
        iads_role=role,
        units=list(units),
        alive_units=sum(1 for u in units if u.alive),
        ground_object=tgo,
    )
    tgo.groups = [group]
    return group


def _node(group: Any, *connections: Any) -> Any:
    return SimpleNamespace(
        group=group, connections={i: c for i, c in enumerate(connections)}
    )


def _network(*nodes: Any) -> Any:
    return SimpleNamespace(
        nodes=list(nodes),
        state_map=SimpleNamespace(status_for=lambda tgo: None),
    )


def _link(picture: Any, caption: str) -> Any:
    for link in picture.links:
        if link.caption == caption:
            return link
    raise AssertionError(f"no {caption} row in {[l.caption for l in picture.links]}")


def test_the_plugin_being_off_is_the_whole_answer() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    network = _network(_node(sam))

    picture = describe(sam.ground_object, network, plugin_enabled=False)

    assert picture.off is NoNetwork.PLUGIN_OFF
    assert picture.links == ()
    assert "options" in picture.summary


def test_a_campaign_without_an_iads_says_so() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)

    picture = describe(sam.ground_object, _network())

    assert picture.off is NoNetwork.CAMPAIGN
    assert picture.verdict == "NO IADS"


def test_a_site_outside_an_existing_network_is_standalone() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    other = _group("ORIOLE", IadsRole.SAM)

    picture = describe(sam.ground_object, _network(_node(other)))

    assert picture.off is NoNetwork.STANDALONE
    assert picture.verdict == "STANDALONE"


def test_a_live_radar_in_range_is_cueing_the_site() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=100_000), at=(10.0, 0.0))
    network = _network(_node(sam), _node(ewr))

    early_warning = _link(describe(sam.ground_object, network), "EARLY WARNING")

    assert early_warning.chip == "CUEING"
    assert early_warning.tone is LinkTone.GOOD
    assert early_warning.title == "Tonopah"


def test_a_radar_whose_comms_are_cut_is_named_with_the_comms_node() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=100_000), at=(10.0, 0.0))
    comms = _group("Beatty", IadsRole.CONNECTION_NODE, _unit(alive=False))
    network = _network(_node(sam), _node(ewr, comms))

    early_warning = _link(describe(sam.ground_object, network), "EARLY WARNING")

    assert early_warning.chip == "LINK CUT"
    assert early_warning.tone is LinkTone.WARN
    assert "Beatty" in early_warning.note


def test_a_destroyed_radar_stops_covering_the_site() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    ewr = _group(
        "Tonopah", IadsRole.EWR, _unit(alive=False, detection=100_000), at=(10.0, 0.0)
    )
    network = _network(_node(sam), _node(ewr))

    early_warning = _link(describe(sam.ground_object, network), "EARLY WARNING")

    # A dead radar has no range, so it does not even count as covering the site: the
    # row says nothing covers it rather than naming a wreck.
    assert early_warning.chip == "NO COVER"


def test_nothing_in_range_says_nothing_covers_it() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=1.0), at=(10_000.0, 0.0))
    network = _network(_node(sam), _node(ewr))

    early_warning = _link(describe(sam.ground_object, network), "EARLY WARNING")

    assert early_warning.chip == "NO COVER"
    assert early_warning.tone is LinkTone.WARN


def test_an_awacs_on_station_gets_its_own_row() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    network = _network(_node(sam))

    picture = describe(sam.ground_object, network, awacs=["Magic 11"])

    rows = [link for link in picture.links if link.chip == "CUES WHEN AIRBORNE"]
    assert len(rows) == 1
    assert rows[0].title == "Magic 11"


def test_a_standing_command_centre_is_directing() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    centre = _group("Indian Springs", IadsRole.COMMAND_CENTER)
    network = _network(_node(sam), _node(centre))

    command = _link(describe(sam.ground_object, network), "COMMAND")

    assert command.chip == "DIRECTING"
    assert command.title == "Indian Springs"


def test_a_network_without_command_centres_needs_none() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    network = _network(_node(sam))

    command = _link(describe(sam.ground_object, network), "COMMAND")

    assert command.chip == "NOT NEEDED"
    assert command.tone is LinkTone.INFO


def test_a_site_with_no_power_link_is_powered_anyway() -> None:
    """An empty list of power sources is what Skynet reads as powered."""
    sam = _group("KAKAPO", IadsRole.SAM)

    power = _link(describe(sam.ground_object, _network(_node(sam))), "POWER")

    assert power.chip == "POWERED"


def test_a_dead_substation_leaves_the_site_on_its_generator() -> None:
    sam = _group("KAKAPO", IadsRole.SAM, _unit(), _unit(power=True))
    substation = _group("Creech", IadsRole.POWER_SOURCE, _unit(alive=False))
    network = _network(_node(sam, substation))

    picture = describe(sam.ground_object, network)

    assert _link(picture, "POWER").chip == "GRID DOWN"
    assert _link(picture, "OWN POWER").chip == "RUNNING ON IT"


def test_a_site_without_a_generator_stays_switched_off() -> None:
    sam = _group("KAKAPO", IadsRole.SAM)
    substation = _group("Creech", IadsRole.POWER_SOURCE, _unit(alive=False))
    network = _network(_node(sam, substation))

    picture = describe(sam.ground_object, network)

    assert _link(picture, "POWER").tone is LinkTone.BAD
    assert [link for link in picture.links if link.caption == "OWN POWER"] == []


def test_a_radar_lists_what_it_cues_instead_of_who_cues_it() -> None:
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=100_000))
    first = _group("KAKAPO", IadsRole.SAM, at=(10.0, 0.0))
    second = _group("ORIOLE", IadsRole.SAM, at=(20.0, 0.0))
    network = _network(_node(ewr), _node(first), _node(second))

    cues = _link(describe(ewr.ground_object, network), "CUES")

    assert cues.chip == "2 SITES"
    assert cues.title == "KAKAPO · ORIOLE"


def test_a_radar_with_its_comms_cut_reaches_nobody() -> None:
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=100_000))
    comms = _group("Beatty", IadsRole.CONNECTION_NODE, _unit(alive=False))
    sam = _group("KAKAPO", IadsRole.SAM, at=(10.0, 0.0))
    network = _network(_node(ewr, comms), _node(sam))

    cues = _link(describe(ewr.ground_object, network), "CUES")

    assert cues.chip == "REACHES NOBODY"


def test_a_gps_jammer_is_asked_about_power_and_nothing_else() -> None:
    jammer = _group("SCARAB", IadsRole.EWR)
    jammer.ground_object.carries_gps_jammer = True
    network = _network(_node(jammer))

    picture = describe(jammer.ground_object, network)

    assert [link.caption for link in picture.links] == ["POWER"]


def test_an_enemy_site_reads_as_a_target_list() -> None:
    sam = _group("ORIOLE", IadsRole.SAM)
    ewr = _group("Tonopah", IadsRole.EWR, _unit(detection=100_000), at=(10.0, 0.0))
    network = _network(_node(sam), _node(ewr))

    early_warning = _link(
        describe(sam.ground_object, network, friendly=False), "EARLY WARNING"
    )

    assert "kill it" in early_warning.note
