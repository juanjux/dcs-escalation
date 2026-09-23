"""The High Command's list of enemy objectives: how hard each is, and why go."""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any

from dcs import Point
from dcs.terrain import Caucasus

from game.data.units import UnitClass
from game.highcommand import objectives
from game.highcommand.objectives import (
    COMICAL,
    RING_WEIGHT,
    Effort,
    Objective,
    ranked,
    system_name,
)
from game.mfd import Band
from game.theater import Player
from game.utils import meters, nautical_miles

TERRAIN = Caucasus()
NM = nautical_miles(1).meters


def _at(x_nm: float, y_nm: float = 0.0) -> Point:
    return Point(x_nm * NM, y_nm * NM, TERRAIN)


class _Type:
    """A unit type as much as the labels read it: a name and a class."""

    def __init__(self, label: str, unit_class: Any = None) -> None:
        self.label = label
        self.unit_class = unit_class

    def __str__(self) -> str:
        return self.label


def _shooter(label: str, reach_nm: float, unit_class: Any = UnitClass.LAUNCHER) -> Any:
    return SimpleNamespace(
        alive=True,
        is_anti_air=True,
        threat_range=meters(reach_nm * NM),
        type=SimpleNamespace(id=label),
        unit_type=_Type(label, unit_class),
    )


class _Base:
    """A control point, hashable like the real one, since the counters key on it."""

    def __init__(
        self, name: str, x_nm: float, side: Player = Player.RED, fleet: bool = False
    ) -> None:
        self.name = name
        self.position = _at(x_nm)
        self.captured = side
        self.is_fleet = fleet
        self.front_lines: dict[Any, Any] = {}


def _base(
    name: str, x_nm: float, side: Player = Player.RED, fleet: bool = False
) -> Any:
    return _Base(name, x_nm, side, fleet)


def _site(
    name: str, x_nm: float, units: list[Any], base: Any = None, category: str = "aa"
) -> Any:
    reach = max((u.threat_range.meters for u in units), default=0.0)
    return SimpleNamespace(
        name=name,
        category=category,
        position=_at(x_nm),
        control_point=base or _base("Somewhere", x_nm),
        units=units,
        statics=[],
        is_dead=False,
        max_threat_range=lambda: meters(reach),
    )


def _campaign(**parts: Any) -> Any:
    """The measuring context without a game behind it."""
    campaign: Any = objectives._Campaign.__new__(objectives._Campaign)
    bases = parts.pop("enemy_bases", [])
    campaign.game = SimpleNamespace(theater=SimpleNamespace(controlpoints=bases))
    campaign.player = Player.BLUE
    campaign.enemy = Player.RED
    campaign.groups = parts.pop("groups", {})
    campaign.defences = parts.pop("defences", [])
    campaign.bases = parts.pop("our_bases", [])
    campaign.aircraft = Counter(parts.pop("aircraft", {}))
    campaign.fighters = Counter(parts.pop("fighters", {}))
    campaign.enemy_income = parts.pop("enemy_income", 100.0)
    campaign.income_multiplier = 1.0
    campaign.skynet = True
    campaign.advanced = True
    assert not parts, parts
    return campaign


def _objective(name: str, total: float) -> Objective:
    return Objective(
        name=name,
        kind="Factory",
        targets=(),
        effort=Effort(air_defence=total, fighters=0, distance=0, size=0),
        justification="",
        hazards=(),
    )


# ------------------------------------------------------------------ difficulty


def test_difficulty_is_the_fifth_the_effort_falls_in() -> None:
    objectives_ = ranked([_objective(str(n), float(n)) for n in range(10)])

    assert [o.difficulty for o in objectives_] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_equal_efforts_share_a_difficulty() -> None:
    efforts = [1.0, 2.0, 2.0, 2.0, 2.0, 9.0]

    difficulties = [o.difficulty for o in ranked([_objective("x", e) for e in efforts])]

    assert difficulties[1] == difficulties[2] == difficulties[3] == difficulties[4]
    assert difficulties[0] == 1
    assert difficulties[-1] == 5


def test_a_ring_weighs_most_over_its_site_and_nothing_past_its_edge() -> None:
    sam = _site("GRUMBLE", 0, [_shooter("SAM SA-10 LN", 40)])
    ring = objectives._Defence(sam, reach=40 * NM, band=Band.LONG)

    assert ring.weight_at(_at(0)) == RING_WEIGHT[Band.LONG]
    assert abs(ring.weight_at(_at(20)) - RING_WEIGHT[Band.LONG] / 2) < 1e-9
    assert ring.weight_at(_at(41)) == 0


def test_effort_adds_the_rings_the_fighters_the_distance_and_the_size() -> None:
    sam = _site("GRUMBLE", 0, [_shooter("SAM SA-10 LN", 40)])
    enemy_field = _base("Kutaisi", 50)
    campaign = _campaign(
        defences=[objectives._Defence(sam, 40 * NM, Band.LONG)],
        our_bases=[_base("Batumi", 300, Player.BLUE)],
        fighters={enemy_field: 24},
    )

    effort, hazards = campaign._effort("FACTORY", _at(10), units=12)

    assert effort.air_defence == RING_WEIGHT[Band.LONG] * 30 / 40
    assert effort.fighters == 2.0
    # 290 nm out: a point for each hundred past the first.
    assert abs(effort.distance - 1.9) < 1e-9
    assert effort.size == 1.0
    assert hazards == (
        "SA-10 at GRUMBLE",
        "24 fighters within 150 nm",
        "290 nm from Batumi",
        "12 units to destroy",
    )


# --------------------------------------------------------------- the reasons


def test_a_site_is_named_after_its_system() -> None:
    assert (
        system_name(_site("A", 0, [_shooter('SAM SA-10 S-300 "Grumble" LN', 40)]))
        == "SA-10"
    )
    assert system_name(_site("B", 0, [_shooter("HQ-7 Launcher", 8)])) == "HQ-7"
    assert system_name(_site("C", 0, [_shooter("Patriot ln", 60)])) == "Patriot"
    guns = [_shooter("AAA KS-19", 3, UnitClass.AAA)]
    assert system_name(_site("D", 0, guns)) == "guns"


def test_a_battery_reaching_one_of_our_bases_says_so() -> None:
    sam = _site("GRUMBLE", 0, [_shooter("SAM SA-10 LN", 40)])
    campaign = _campaign(
        our_bases=[_base("Batumi", 30, Player.BLUE), _base("Stennis", 20, fleet=True)]
    )

    assert campaign._battery(sam) == "Its SA-10 reaches the Stennis."


def test_a_battery_covers_the_bases_and_objectives_in_its_ring() -> None:
    field = _base("Kutaisi", 5)
    sam = _site("GRUMBLE", 0, [_shooter("SAM SA-10 LN", 40)])
    campaign = _campaign(
        enemy_bases=[field],
        groups={
            "GRUMBLE": [sam],
            "FACTORY": [_site("FACTORY", 10, [])],
            "DEPOT": [_site("DEPOT", 20, [])],
            "FAR": [_site("FAR", 80, [])],
        },
    )

    assert campaign._battery(sam) == "Its SA-10 covers Kutaisi, DEPOT and FACTORY."


def test_a_battery_with_nothing_to_cover_is_left_to_the_comedians() -> None:
    guns = _site("LONELY", 0, [_shooter("AAA ZU-23", 1, UnitClass.AAA)])
    campaign = _campaign(groups={"LONELY": [guns], "FAR": [_site("FAR", 50, [])]})

    assert campaign._battery(guns) == COMICAL


def test_a_building_is_worth_its_share_of_the_enemy_income() -> None:
    oil = _site("RIG", 0, [], category="oil")
    oil.statics = [SimpleNamespace(alive=True) for _ in range(4)]
    village = _site("HAMLET", 0, [], category="village")
    village.statics = [SimpleNamespace(alive=True)]
    campaign = _campaign(enemy_income=400.0)

    assert campaign._building([oil]) == (
        "Earns the enemy $40M a turn, 10% of their income."
    )
    assert campaign._building([village]) == COMICAL


def test_an_ammo_depot_on_a_front_supplies_it() -> None:
    base = _base("Kutaisi", 0)
    base.front_lines = {"a front": object()}
    depot = _site("DEPOT", 0, [], base=base, category="ammo")

    assert _campaign()._building([depot]) == (
        "Supplies the front at Kutaisi: 12 more units in the line."
    )


def test_a_base_is_worth_the_aircraft_on_it() -> None:
    field = _base("Kutaisi", 0)
    empty = _base("Sukhumi", 0)
    campaign = _campaign(aircraft={field: 20}, fighters={field: 12})

    assert campaign._aircraft_line("Home to", field) == (
        "Home to 20 enemy aircraft, 12 of them fighters."
    )
    assert campaign._aircraft_line("Home to", empty) == COMICAL
