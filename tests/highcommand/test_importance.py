"""What losing an objective costs the enemy, and the line that says why."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.data.units import UnitClass
from game.highcommand.approach import Ring
from game.config import RUNWAY_REPAIR_COST
from game.highcommand.campaign import RING_WEIGHT, Task
from game.highcommand.importance import (
    AIRCRAFT_SHARE,
    COVER_SHARE,
    DARK_SHARE,
    FRONT_FACTOR,
    GARRISON_SHARE,
    INCOME_TURNS,
    OTHER_SHIP_WORTH,
    SQUADRON_WORTH,
    THREAT_SHARE,
    WARSHIP_WORTH,
    Reason,
    Worth,
    rebuild_worth,
)
from game.highcommand.objectives import Effort, Objective
from game.mfd import Band
from game.theater import Player
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsStateMap
from game.theater.theatergroundobject import BuildingGroundObject
from tests.highcommand.stubs import (
    NM,
    Base,
    armour,
    building,
    campaign,
    launcher,
    sam,
    ships,
    unit,
)


def _objective(target: Any, worth: float) -> Objective:
    return Objective(
        name=target.name,
        kind="",
        targets=(target,),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        reasons=(Reason("rebuild", worth, ""),) if worth else (),
    )


def _ring(site: Any, reach_nm: float, band: Band = Band.LONG) -> Ring:
    return Ring(
        site, site.position.x, site.position.y, reach_nm * NM, RING_WEIGHT[band]
    )


def test_ground_units_count_at_their_price_and_warships_by_class() -> None:
    battery = sam(
        "GRUMBLE", 0, [launcher("SAM SA-10 LN", 40, price=30), launcher("SR", 0, 38)]
    )
    fleet = ships(
        "SHARK",
        0,
        [
            unit("Type 052C Destroyer", unit_class=UnitClass.DESTROYER, ship=True),
            unit("Type 054A Frigate", unit_class=UnitClass.FRIGATE, ship=True),
            unit("Tanker", unit_class=None, ship=True),
        ],
    )

    assert rebuild_worth([battery]) == 68
    assert rebuild_worth([fleet]) == (
        WARSHIP_WORTH[UnitClass.DESTROYER]
        + WARSHIP_WORTH[UnitClass.FRIGATE]
        + OTHER_SHIP_WORTH
    )
    (reason,) = Worth(campaign()).own([fleet])
    assert reason.line == "3 warships (Type 052C Destroyer) the enemy cannot replace."


def test_an_income_building_is_worth_its_income_and_its_rebuilding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BuildingGroundObject, "repair_cost", lambda self: 40.0)
    rig = building("RIG", "oil", 0, standing=3, fallen=1)

    (reason,) = Worth(campaign(enemy_income=300.0)).own([rig])

    # $10M a turn for each of the three still standing, and $40M to rebuild each.
    assert reason.kind == "income"
    assert reason.worth == 30 * INCOME_TURNS + 3 * 40
    assert reason.line == "Earns the enemy $30M a turn, 10% of their income."


def test_a_garrison_counts_for_more_close_to_its_base_and_on_a_front() -> None:
    home = Base("Kutaisi")
    vehicles = [
        unit("T-72B", price=20),
        unit("T-72B", price=20),
        unit(
            "ZU-23 Emplacement",
            price=5,
            unit_class=UnitClass.AAA,
            reach_nm=1.5,
            anti_air=True,
        ),
    ]
    near = armour("NEAR", 2, vehicles, base=home)
    far = armour("FAR", 20, vehicles, base=home)
    worth = Worth(campaign())

    (close_in,) = worth.own([near])
    (out_there,) = worth.own([far])
    home.front_lines = {"a front": object()}
    (on_a_front,) = worth.own([near])

    assert out_there.worth == 45
    assert close_in.worth == 45 * (1 + GARRISON_SHARE)
    assert on_a_front.worth == 45 * (1 + GARRISON_SHARE * FRONT_FACTOR)
    assert close_in.line == (
        "3 vehicles (T-72B, ZU-23) garrisoning Kutaisi, in the way of any assault on "
        "it."
    )


def test_a_bases_aircraft_are_worth_part_of_what_they_cost() -> None:
    field: Any = Base("Kutaisi")
    worth = Worth(
        campaign(
            aircraft={field: 12},
            fighters={field: 8},
            squadrons={field: 2},
            aircraft_worth={field: 240.0},
        )
    )

    assert worth.own_base(field, Task.AIRCRAFT) == (
        Reason(
            "aircraft",
            AIRCRAFT_SHARE * 240,
            "Home to 2 squadrons: 12 aircraft, 8 of them fighters.",
        ),
    )


def test_a_runway_is_worth_its_repair_and_the_squadrons_it_grounds() -> None:
    field: Any = Base("Kutaisi")
    worth = Worth(campaign(squadrons={field: 2}))

    assert worth.own_base(field, Task.RUNWAY) == (
        Reason(
            "runway",
            RUNWAY_REPAIR_COST + 2 * SQUADRON_WORTH,
            "Cratering its runway grounds 2 squadrons until the enemy pays $100M to "
            "repair it.",
        ),
    )


def test_taking_a_base_costs_the_enemy_its_income_and_the_sites_around_it() -> None:
    works = building("DRAGON", "factory", 0, standing=2)
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40, price=30)])
    field: Any = SimpleNamespace(ground_objects=[works, battery], income_per_turn=20)

    (reason,) = Worth(campaign()).own_base(field, Task.CAPTURE)

    # The base earns 20 and the factory's two buildings 2.5 each; the battery is
    # cleared when the base falls, the factory changes hands.
    assert reason.worth == 25 * INCOME_TURNS + 30
    assert reason.line == "Taking it costs the enemy $25M a turn and 1 site around it."


def test_a_sam_reaching_one_of_our_bases_counts_part_of_what_is_there() -> None:
    ours = Base("Batumi", 30, Player.BLUE)
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40, price=0)])
    worth = Worth(campaign(our_bases=[ours], our_aircraft_worth={ours: 400.0}))

    assert worth.own([battery]) == (
        Reason("threat", THREAT_SHARE * 400, "Its SA-10 reaches our base at Batumi."),
    )


def test_two_rings_over_an_objective_share_its_cover() -> None:
    depot = building("DEPOT", "ammo", 0, standing=1)
    north = sam("NORTH", 0, [launcher("SAM SA-10 LN", 40, price=0)], y_nm=5)
    south = sam("SOUTH", 0, [launcher("SAM SA-10 LN", 40, price=0)], y_nm=-5)
    objectives = [_objective(depot, 100), _objective(north, 0), _objective(south, 0)]
    worth = Worth(campaign(rings=[_ring(north, 40), _ring(south, 40)]))

    shared = worth.shared(objectives)

    # Well past what one long-range ring weighs: half of the depot's worth, split.
    assert shared["NORTH"] == [
        Reason("cover", COVER_SHARE * 100 / 2, "Its SA-10 covers DEPOT.")
    ]
    assert shared["SOUTH"][0].worth == COVER_SHARE * 100 / 2


def test_a_lone_short_range_ring_covers_less_than_a_long_range_one() -> None:
    depot = building("DEPOT", "ammo", 0, standing=1)
    guns = sam(
        "GUNS",
        0,
        [unit("ZU-23", unit_class=UnitClass.AAA, reach_nm=2, anti_air=True, price=0)],
    )
    objectives = [_objective(depot, 100), _objective(guns, 0)]
    worth = Worth(campaign(rings=[_ring(guns, 2, Band.SHORT)]))

    (reason,) = worth.shared(objectives)["GUNS"]

    assert reason.worth == COVER_SHARE * 100 * RING_WEIGHT[Band.SHORT] / 4


def test_what_a_substation_powers_goes_dark_without_it() -> None:
    power = building("SUBSTATION", "power", 0, standing=1, role=IadsRole.POWER_SOURCE)
    battery = sam(
        "BADGER", 20, [launcher("SAM SA-10 LN", 40, price=0)], role=IadsRole.SAM
    )
    network: Any = SimpleNamespace(
        nodes=[
            SimpleNamespace(group=battery.groups[0], connections={0: power.groups[0]})
        ]
    )
    network.state_map = IadsStateMap(network)
    objectives = [_objective(power, 15), _objective(battery, 300)]

    shared = Worth(campaign(network=network)).shared(objectives)

    assert shared["SUBSTATION"] == [
        Reason(
            "network",
            DARK_SHARE * 300,
            "Powers the air defence site BADGER, which goes dark without it.",
        )
    ]
    # Losing the battery switches nothing else off.
    assert shared["BADGER"] == []
