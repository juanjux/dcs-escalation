from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest

from game.data.doctrine import GroundUnitProcurementRatios
from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.factions.faction import Faction
from game.game import Game
from game.procurement import ProcurementAi
from game.theater import ControlPoint, Player


@dataclass(frozen=True)
class Unit:
    name: str
    price: int
    unit_class: UnitClass


TANK = Unit("tank", 25, UnitClass.TANK)
MLRS = Unit("rocket artillery", 55, UnitClass.ARTILLERY)
APC = Unit("APC", 6, UnitClass.APC)
ATGM = Unit("ATGM", 8, UnitClass.ATGM)
AAA = Unit("AAA", 10, UnitClass.AAA)
RECON = Unit("recon", 2, UnitClass.RECON)
UNITS = [TANK, MLRS, APC, ATGM, AAA, RECON]
RATIOS = {
    UnitClass.TANK: 3,
    UnitClass.ATGM: 2,
    UnitClass.APC: 2,
    UnitClass.IFV: 3,
    UnitClass.ARTILLERY: 1,
    UnitClass.SHORAD: 2,
    UnitClass.RECON: 1,
}


class Base:
    def __init__(
        self,
        present: dict[Unit, int] | None = None,
        incoming: dict[Unit, int] | None = None,
        capacity: int = 10,
    ) -> None:
        self.present = present or {}
        self.incoming = incoming or {}
        self.capacity = capacity
        self.orders: dict[Unit, int] = defaultdict(int)
        self.ground_unit_orders = SimpleNamespace(order=self.order)

    def order(self, units: dict[Unit, int]) -> None:
        for unit, count in units.items():
            self.orders[unit] += count

    def allocated_ground_units(self, transfers: object) -> SimpleNamespace:
        units: dict[Unit, int] = defaultdict(int)
        for inventory in (self.present, self.incoming, self.orders):
            for unit, count in inventory.items():
                units[unit] += count
        return SimpleNamespace(all=units, total=sum(units.values()))


class Ai(ProcurementAi):
    def __init__(
        self,
        base: Base,
        units: list[Unit] | None = None,
        ratios: dict[UnitClass, int] | None = None,
        weighted: bool = True,
    ) -> None:
        self.base = base
        self.game = cast(
            Game,
            SimpleNamespace(
                settings=SimpleNamespace(weighted_ground_procurement=weighted),
                coalition_for=lambda _: SimpleNamespace(transfers=[]),
            ),
        )
        self.is_player = Player.BLUE
        self.faction = cast(
            Faction,
            SimpleNamespace(
                frontline_units=UNITS if units is None else units,
                artillery_units=[],
                doctrine=SimpleNamespace(
                    ground_unit_procurement_ratios=GroundUnitProcurementRatios(
                        cast(
                            dict[UnitClass, float], RATIOS if ratios is None else ratios
                        )
                    )
                ),
            ),
        )

    def ground_reinforcement_candidate(self) -> ControlPoint | None:
        if self.base.allocated_ground_units([]).total >= self.base.capacity:
            return None
        return cast(ControlPoint, self.base)


def choose(ai: Ai, budget: float) -> GroundUnitType | None:
    return ai.balanced_ground_unit(cast(ControlPoint, ai.base), budget)


@pytest.mark.parametrize("weighted", [True, False])
def test_missing_class_never_falls_back_to_unrelated_expensive_units(
    weighted: bool,
) -> None:
    ai = Ai(Base(), units=[TANK, MLRS], weighted=weighted)
    setattr(ai.faction, "has_access_to_unit_class", lambda unit_class: True)
    assert choose(ai, 200) == TANK


def test_first_purchase_builds_armor_before_expensive_artillery() -> None:
    ai = Ai(Base({APC: 1, ATGM: 1, AAA: 1, RECON: 2}))
    assert choose(ai, 55) == TANK


def test_air_defenses_in_presets_do_not_create_an_unfillable_purchase_quota() -> None:
    ai = Ai(Base({APC: 1, ATGM: 1, RECON: 2}), units=[TANK, MLRS, APC, ATGM, RECON])
    setattr(ai.faction, "has_access_to_unit_class", lambda unit_class: True)
    assert choose(ai, 55) == TANK


def test_aaa_fills_the_available_air_defense_role() -> None:
    ai = Ai(
        Base({TANK: 3}),
        units=[TANK, AAA],
        ratios={UnitClass.TANK: 3, UnitClass.SHORAD: 2},
    )
    assert choose(ai, 100) == AAA


def test_manpads_fill_the_available_air_defense_role() -> None:
    manpad = Unit("MANPADS", 5, UnitClass.MANPAD)
    ai = Ai(
        Base({TANK: 2}),
        units=[TANK, manpad],
        ratios={UnitClass.TANK: 3, UnitClass.SHORAD: 2},
    )
    assert choose(ai, 100) == manpad


def test_unaffordable_role_does_not_stop_other_useful_purchases() -> None:
    ai = Ai(Base(), units=[TANK, APC], ratios={UnitClass.TANK: 3, UnitClass.APC: 2})
    assert choose(ai, 6) == APC
    assert ai.reinforce_front_line(6) == 0
    assert ai.base.orders == {APC: 1}


def test_unaffordable_class_keeps_its_long_term_quota() -> None:
    ai = Ai(
        Base({APC: 10}), units=[TANK, APC], ratios={UnitClass.TANK: 3, UnitClass.APC: 2}
    )
    assert choose(ai, 25) == TANK
    assert choose(ai, 5) is None


def test_compare_models_after_purchase_not_only_before_purchase() -> None:
    howitzer = Unit("howitzer", 10, UnitClass.ARTILLERY)
    ai = Ai(
        Base({TANK: 3}),
        units=[TANK, MLRS, howitzer],
        ratios={UnitClass.TANK: 3, UnitClass.ARTILLERY: 1},
    )
    assert choose(ai, 55) == howitzer


def test_existing_artillery_prevents_more_artillery_spam() -> None:
    ai = Ai(
        Base({MLRS: 2}),
        units=[TANK, MLRS],
        ratios={UnitClass.TANK: 3, UnitClass.ARTILLERY: 1},
    )
    assert choose(ai, 200) == TANK


def test_expensive_artillery_is_bought_when_the_force_can_support_it() -> None:
    ai = Ai(
        Base({TANK: 6}),
        units=[TANK, MLRS],
        ratios={UnitClass.TANK: 3, UnitClass.ARTILLERY: 1},
    )
    assert choose(ai, 55) == MLRS


def test_incoming_and_ordered_units_count_before_they_arrive() -> None:
    base = Base(incoming={MLRS: 2})
    base.order({TANK: 1})
    ai = Ai(
        base, units=[TANK, MLRS], ratios={UnitClass.TANK: 3, UnitClass.ARTILLERY: 1}
    )
    assert choose(ai, 200) == TANK


@pytest.mark.parametrize("weighted", [True, False])
def test_full_purchase_loop_rechecks_balance_after_every_order(weighted: bool) -> None:
    ai = Ai(Base({APC: 1, ATGM: 1, AAA: 1, RECON: 2}), weighted=weighted)
    remaining = ai.reinforce_front_line(200)
    assert ai.base.orders[TANK] >= 1
    assert ai.base.orders[AAA] >= 1
    assert ai.base.orders[MLRS] == 0
    assert ai.base.allocated_ground_units([]).total == 10
    assert remaining == 200 - sum(u.price * n for u, n in ai.base.orders.items())


def test_one_role_faction_can_still_buy_its_units() -> None:
    ai = Ai(Base(), units=[MLRS])
    assert choose(ai, 55) == MLRS


def test_faction_with_no_doctrinal_roles_uses_its_actual_roster() -> None:
    infantry = Unit("infantry", 1, UnitClass.INFANTRY)
    ai = Ai(Base(), units=[infantry])
    assert choose(ai, 1) == infantry


def test_unavailable_doctrinal_roles_are_renormalized() -> None:
    ai = Ai(
        Base({TANK: 2}),
        units=[TANK, APC],
        ratios={UnitClass.TANK: 1, UnitClass.APC: 1, UnitClass.IFV: 100},
    )
    assert choose(ai, 25) == APC


def test_no_available_units_returns_none() -> None:
    ai = Ai(Base(), units=[])
    assert choose(ai, 200) is None


def test_no_affordable_units_returns_none() -> None:
    ai = Ai(Base(), units=[TANK, MLRS])
    assert choose(ai, 24) is None


def test_free_units_do_not_divide_by_zero_or_exceed_capacity() -> None:
    free = Unit("free infantry", 0, UnitClass.INFANTRY)
    ai = Ai(Base(capacity=3), units=[free])
    assert choose(ai, 1) == free
    assert ai.reinforce_front_line(1) == 1
    assert ai.base.orders == {free: 3}


def test_picker_does_not_modify_existing_allocations() -> None:
    base = Base({TANK: 2}, {APC: 1})
    ai = Ai(base)
    choose(ai, 200)
    assert base.present == {TANK: 2}
    assert base.incoming == {APC: 1}
    assert not base.orders


def test_price_weighting_never_competes_between_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai = Ai(
        Base(), units=[TANK, MLRS], ratios={UnitClass.TANK: 1, UnitClass.ARTILLERY: 1}
    )
    offered: list[object] = []

    def weighted_pick(
        units: list[GroundUnitType], weights: list[int], k: int
    ) -> list[GroundUnitType]:
        offered.extend(units)
        assert len({u.unit_class for u in units}) == 1
        return [units[0]]

    monkeypatch.setattr("game.procurement.random.choices", weighted_pick)
    assert choose(ai, 55) in (TANK, MLRS)
    assert len(offered) == 1


def test_weighting_remains_available_for_equally_balanced_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cheap = Unit("old tank", 5, UnitClass.TANK)
    ai = Ai(Base(), units=[cheap, TANK])
    weights_seen: list[int] = []

    def weighted_pick(
        units: list[GroundUnitType], weights: list[int], k: int
    ) -> list[GroundUnitType]:
        weights_seen.extend(weights)
        return [units[-1]]

    monkeypatch.setattr("game.procurement.random.choices", weighted_pick)
    assert choose(ai, 55) == TANK
    assert weights_seen == [5, 25]


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_both_coalitions_use_the_balanced_purchase_loop(owner: Player) -> None:
    ai = Ai(Base({APC: 1, ATGM: 1, AAA: 1, RECON: 2}))
    ai.is_player = owner
    ai.reinforce_front_line(55)
    assert ai.base.orders[TANK] >= 1
    assert ai.base.orders[MLRS] == 0
