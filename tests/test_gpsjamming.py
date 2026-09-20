"""GPS jamming: which units deny GPS, how far, and which weapons care.

The mechanism itself lives in the Lua plugin; what is testable here is the campaign
side -- that a unit becomes a jammer by declaring a block and by nothing else, that the
bubble falls back to the campaign setting, and that only satellite-guided stores are on
the list.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.dcs.groundunittype import GpsJammingProperties
from game.gpsjamming import GPS_GUIDED_WEAPON_PATTERNS


def test_declaring_no_block_is_not_a_jammer() -> None:
    """The overwhelmingly common case: every other ground unit in the game."""
    assert GpsJammingProperties.from_data(None) is None
    assert GpsJammingProperties.from_data(False) is None


def test_a_bare_block_rides_the_campaign_defaults() -> None:
    """`gps_jamming: true` must be enough -- tuning is optional."""
    props = GpsJammingProperties.from_data(True)
    assert props == GpsJammingProperties(radius_nm=None, miss_radius_m=None)


def test_the_block_carries_its_own_reach_and_miss() -> None:
    props = GpsJammingProperties.from_data({"radius_nm": 15, "miss_radius_m": 250})
    assert props is not None
    assert props.radius_nm == 15.0
    assert props.miss_radius_m == 250.0


def test_a_malformed_value_falls_back_rather_than_raising() -> None:
    """A typo in a unit yaml must not take the whole unit registry down."""
    props = GpsJammingProperties.from_data({"radius_nm": "fifteen"})
    assert props is not None
    assert props.radius_nm is None


def test_only_satellite_guided_weapons_are_degraded() -> None:
    """A Paveway that mysteriously misses is a bug report, not a feature: laser, TV,
    IR and anti-radiation weapons must never be on this list."""
    patterns = [p.upper() for p in GPS_GUIDED_WEAPON_PATTERNS]
    assert any("GBU-31" in p for p in patterns), "JDAM must be covered"
    for never in ("GBU-12", "AGM-65", "AGM-88", "AGM-114", "GBU-16", "GBU-10"):
        assert not any(never in p for p in patterns), f"{never} is not GPS-guided"


def test_a_weapon_somebody_flies_is_left_alone() -> None:
    """The exclusion is a pilot in the loop, human or AI. The SLAM family's terminal
    leg is TV flown onto the target by whoever launched it; degrading the navigation
    of a weapon being steered by hand punishes the wrong thing."""
    patterns = [p.upper() for p in GPS_GUIDED_WEAPON_PATTERNS]
    for never in ("AGM-84E", "AGM-84H", "SLAM"):
        assert not any(never in p for p in patterns), f"{never} is flown by its pilot"


def test_an_automatic_terminal_seeker_is_no_excuse() -> None:
    """A seeker that comes up on its own has to find the target by itself, and a
    weapon already tens of miles off track is unlikely to have anything in its field
    of view. The KD-20 is the case: BeiDou midcourse, automatic IIR terminal leg, and
    an AI bomber carrying it."""
    assert "KD_20" in GPS_GUIDED_WEAPON_PATTERNS


def test_the_declared_jammers_carry_a_bubble() -> None:
    """The two DCS GPS spoofer vehicles are what the fork ships as jammers."""
    from game.dcs.groundunittype import GroundUnitType

    for name in ("GPS Jammer (Red)", "GPS Jammer (Blue)"):
        unit = GroundUnitType.named(name)
        assert unit.gps_jamming is not None, f"{name} should be a jammer"
        assert unit.gps_jamming.radius_nm == 15.0


# ---------------------------------------------------------------- power


class _Site:
    """A site carrying one live jammer truck, and nothing else the code reads.

    A class rather than a SimpleNamespace because the state map is keyed by the
    objective, and SimpleNamespace defines __eq__ and so is unhashable.
    """

    def __init__(self, name: str) -> None:
        unit = SimpleNamespace(
            alive=True,
            unit_name=f"{name} unit",
            unit_type=SimpleNamespace(gps_jamming=GpsJammingProperties(15.0, 250.0)),
        )
        self.name = name
        self.position = SimpleNamespace(x=1.0, y=2.0)
        self.groups = [SimpleNamespace(units=[unit])]
        self.control_point = SimpleNamespace(captured=False)


def _game(states: dict[Any, Any], *, nodes: bool = True, plugin: bool = True) -> Any:
    network = SimpleNamespace(
        nodes=[object()] if nodes else [],
        state_map=SimpleNamespace(status_for=states.get),
    )
    return SimpleNamespace(
        settings=SimpleNamespace(
            plugin_option_or=lambda _name, default: plugin,
            plugin_option=lambda _name: True,
        ),
        theater=SimpleNamespace(iads_network=network, controlpoints=[]),
    )


def _status(state: Any) -> Any:
    from game.theater.iadsnetwork.iadsstate import IadsStatus

    return IadsStatus(state, "", False)


def test_a_jammer_with_no_power_is_switched_off() -> None:
    """Skynet will not bring an unpowered site up, so its bubble is not there."""
    from game.gpsjamming import switched_off
    from game.theater.iadsnetwork.iadsstate import IadsState

    tgo = _Site("CUTTLEFISH")
    assert switched_off(_game({tgo: _status(IadsState.DARK)}), tgo)


def test_a_powered_jammer_keeps_jamming() -> None:
    from game.gpsjamming import switched_off
    from game.theater.iadsnetwork.iadsstate import IadsState

    tgo = _Site("CUTTLEFISH")
    assert not switched_off(_game({tgo: _status(IadsState.NETWORKED)}), tgo)


def test_a_campaign_with_no_network_keeps_jamming() -> None:
    """No network means no answer to read, not an answer of "no power"."""
    from game.gpsjamming import switched_off

    tgo = _Site("CUTTLEFISH")
    assert not switched_off(_game({}, nodes=False), tgo)


def test_skynet_switched_off_keeps_jamming() -> None:
    from game.gpsjamming import switched_off
    from game.theater.iadsnetwork.iadsstate import IadsState

    tgo = _Site("CUTTLEFISH")
    game = _game({tgo: _status(IadsState.DARK)}, plugin=False)
    assert not switched_off(game, tgo)


def test_a_dark_site_reaches_neither_the_mission_nor_the_map() -> None:
    """The one that matters: the runtime record and the map ring come from here."""
    from game.gpsjamming import gps_jammer_sites, jamming_reach_for
    from game.theater.iadsnetwork.iadsstate import IadsState

    dark = _Site("CUTTLEFISH")
    live = _Site("SPIDER")
    game = _game({dark: _status(IadsState.DARK), live: _status(IadsState.NETWORKED)})
    game.theater.controlpoints = [
        SimpleNamespace(captured=False, ground_objects=[dark, live])
    ]

    assert [site.name for site in gps_jammer_sites(game)] == ["SPIDER"]
    assert jamming_reach_for(game, dark) is None
    assert jamming_reach_for(game, live) is not None
