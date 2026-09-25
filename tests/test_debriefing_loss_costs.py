"""What each side's losses cost it, as the debriefing totals them.

Aircraft and ground units at what buying them back costs, a building at what repairing
it costs plus the income it does not earn while the repair takes, and ships left out
because nothing can buy one back.
"""

from __future__ import annotations

import pickle
from types import SimpleNamespace
from typing import Any

from game.debriefingreport import DebriefingReport, LossCosts, loss_costs
from game.theater.player import Player
from game.theater.theatergroundobject import BuildingGroundObject


class _Type:
    """A unit type stand-in. A plain class, because cargo ships key their load by
    unit type and a SimpleNamespace cannot be a dict key."""

    def __init__(self, price: float) -> None:
        self.price = price


def _settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = dict(
        ignore_non_combat_air_losses=False,
        player_income_multiplier=1.0,
        enemy_income_multiplier=1.0,
        building_repair_turns=4,
        building_repair_income_multiplier=4.0,
        building_repair_ammo_bonus=10.0,
        building_repair_factory_bonus=12.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _building(category: str, settings: SimpleNamespace) -> BuildingGroundObject:
    """A building site with only what repair_cost() reads."""
    site = BuildingGroundObject.__new__(BuildingGroundObject)
    site.category = category
    site.control_point = SimpleNamespace(  # type: ignore[assignment]
        coalition=SimpleNamespace(game=SimpleNamespace(settings=settings))
    )
    return site


def _static(site: Any) -> SimpleNamespace:
    return SimpleNamespace(is_ship=False, unit_type=None, ground_object=site)


def _site_loss(site: Any) -> SimpleNamespace:
    """A destroyed building, the way the unit map hands it over."""
    return SimpleNamespace(theater_unit=_static(site))


def _unit(price: float) -> SimpleNamespace:
    return SimpleNamespace(
        is_ship=False, unit_type=SimpleNamespace(price=price), ground_object=None
    )


def _ship() -> SimpleNamespace:
    return SimpleNamespace(is_ship=True, unit_type=None, ground_object=None)


def _losses(**enemy: list[Any]) -> SimpleNamespace:
    """The enemy side's losses; the player's side lost nothing."""
    kinds = (
        "front_line",
        "motorpool",
        "convoy",
        "cargo_ships",
        "airlifts",
        "ground_objects",
        "scenery",
    )
    fields: dict[str, list[Any]] = {}
    for kind in kinds:
        fields[f"player_{kind}"] = []
        fields[f"enemy_{kind}"] = enemy.get(kind, [])
    return SimpleNamespace(**fields)


def _debriefing(
    settings: SimpleNamespace, air: tuple[Any, ...] = (), **ground: list[Any]
) -> Any:
    return SimpleNamespace(
        game=SimpleNamespace(settings=settings),
        air_losses=SimpleNamespace(player=[], enemy=list(air)),
        is_non_combat_loss=lambda loss: getattr(loss, "crashed", False),
        ground_losses=_losses(**ground),
    )


def _aircraft(price: float, crashed: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        flight=SimpleNamespace(unit_type=SimpleNamespace(price=price)),
        crashed=crashed,
    )


def test_aircraft_cost_what_buying_them_back_costs() -> None:
    debriefing = _debriefing(_settings(), air=(_aircraft(22), _aircraft(22)))
    assert loss_costs(debriefing, Player.RED).aircraft == 44


def test_a_crash_that_does_not_count_costs_nothing_either() -> None:
    """Left out of the count under crashed-do-not-count, so left out of the cost."""
    settings = _settings(ignore_non_combat_air_losses=True)
    debriefing = _debriefing(settings, air=(_aircraft(22), _aircraft(22, True)))
    assert loss_costs(debriefing, Player.RED).aircraft == 22


def test_ground_units_cost_their_price_wherever_they_were_going() -> None:
    tank = _Type(10)
    truck = _Type(1)
    debriefing = _debriefing(
        _settings(),
        front_line=[SimpleNamespace(unit_type=tank)],
        motorpool=[SimpleNamespace(unit_type=tank)],
        convoy=[SimpleNamespace(unit_type=truck)],
        cargo_ships=[SimpleNamespace(units={tank: 2})],
        airlifts=[SimpleNamespace(cargo=[truck, truck])],
    )
    assert loss_costs(debriefing, Player.RED).ground == 10 + 10 + 1 + 20 + 2


def test_a_building_costs_its_repair_and_the_income_the_repair_takes() -> None:
    """Oil earns 10 a turn a building and repairs at four times that; with the
    default four turns of repair, each costs 40 to rebuild and 40 in lost income."""
    settings = _settings()
    oil = _building("oil", settings)
    debriefing = _debriefing(settings, ground_objects=[_site_loss(oil)] * 4)

    costs = loss_costs(debriefing, Player.RED)

    assert costs.ground == 160
    assert costs.income == 160


def test_the_lost_income_follows_the_side_s_income_multiplier() -> None:
    settings = _settings(enemy_income_multiplier=0.5)
    oil = _building("oil", settings)
    debriefing = _debriefing(settings, ground_objects=[_site_loss(oil)])
    assert loss_costs(debriefing, Player.RED).income == 20


def test_instant_repairs_lose_no_income() -> None:
    settings = _settings(building_repair_turns=0)
    oil = _building("oil", settings)
    debriefing = _debriefing(settings, ground_objects=[_site_loss(oil)])
    assert loss_costs(debriefing, Player.RED).income == 0


def test_a_destroyed_scenery_building_counts_like_any_other() -> None:
    settings = _settings()
    factory = _building("factory", settings)
    debriefing = _debriefing(
        settings, scenery=[SimpleNamespace(ground_unit=_static(factory))]
    )
    costs = loss_costs(debriefing, Player.RED)
    assert costs.ground == 2.5 * 4 + 12
    assert costs.income == 2.5 * 4


def test_a_site_s_units_cost_their_price_and_ships_are_left_out() -> None:
    debriefing = _debriefing(
        _settings(),
        ground_objects=[
            SimpleNamespace(theater_unit=_unit(95)),
            SimpleNamespace(theater_unit=_ship()),
        ],
    )
    costs = loss_costs(debriefing, Player.RED)
    assert costs.ground == 95
    assert costs.ships == 1


def test_a_report_saved_before_the_costs_has_none_to_show() -> None:
    """An older save carries no costs: the window shows no totals rather than
    breaking or showing zeroes."""
    report = DebriefingReport(turn=3)
    state = report.__getstate__()
    del state["costs"]
    restored = DebriefingReport.__new__(DebriefingReport)
    restored.__setstate__(state)

    assert restored.loss_costs(Player.BLUE) is None


def test_the_costs_survive_the_save() -> None:
    report = DebriefingReport(turn=3)
    report.costs[False] = LossCosts(aircraft=44, ground=160, income=160, ships=1)

    restored = pickle.loads(pickle.dumps(report))

    assert restored.loss_costs(Player.RED) == LossCosts(44, 160, 160, 1)
