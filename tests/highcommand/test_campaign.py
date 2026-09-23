"""What every High Command objective is measured against."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.highcommand.campaign import RING_WEIGHT, Task, releases
from game.mfd import Band
from game.theater import Airfield, Fob, Player
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStatus
from game.utils import nautical_miles
from tests.highcommand.stubs import (
    NM,
    armour,
    building,
    campaign,
    launcher,
    sam,
    unit,
)


def test_a_switched_off_or_destroyed_site_has_no_ring() -> None:
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40)])
    measured = campaign()
    status: dict[str, Any] = {"now": None}
    measured.network = SimpleNamespace(
        state_map=SimpleNamespace(status_for=lambda tgo: status["now"])
    )

    ring = measured.ring(battery)
    assert ring is not None and ring.weight == RING_WEIGHT[Band.LONG]
    for state in (IadsState.DARK, IadsState.DESTROYED):
        status["now"] = IadsStatus(state, "", False)
        assert measured.ring(battery) is None
    status["now"] = IadsStatus(IadsState.AUTONOMOUS, "", False)
    assert measured.ring(battery) is not None


def _weapon(name: str, reach_nm: float) -> Any:
    return SimpleNamespace(
        launch_range=nautical_miles(reach_nm),
        weapon_group=SimpleNamespace(name=name),
    )


def test_anti_ship_missiles_only_reach_ships(monkeypatch: pytest.MonkeyPatch) -> None:
    from game.data.weapons import Pylon

    pylon = SimpleNamespace(
        allowed=[_weapon("AGM-84D Harpoon", 60), _weapon("AGM-154C JSOW", 40)]
    )
    monkeypatch.setattr(Pylon, "iter_pylons", staticmethod(lambda aircraft: [pylon]))
    squadron = SimpleNamespace(aircraft="Hornet", owned_aircraft=4)
    coalition = SimpleNamespace(
        air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron]), faction=None
    )
    game: Any = SimpleNamespace(
        coalition_for=lambda player: coalition,
        settings=SimpleNamespace(restrict_weapons_by_date=False),
        date=None,
    )

    land, sea = releases(game, Player.BLUE)

    assert [r.radius / NM for r in land] == pytest.approx([10, 40])
    assert [r.radius / NM for r in sea] == pytest.approx([10, 60])


def _airfield(name: str, runway: bool = True, front: bool = False) -> Any:
    field: Any = Airfield.__new__(Airfield)
    field.name = name
    field._runway_status = SimpleNamespace(damaged=not runway)
    field.front_lines = {"a front": object()} if front else {}
    return field


def test_a_base_is_asked_for_what_it_has() -> None:
    busy = _airfield("Kutaisi", front=True)
    empty = _airfield("Sukhumi")
    cratered = _airfield("Senaki", runway=False)
    helipads: Any = Fob.__new__(Fob)
    helipads.front_lines = {}
    measured = campaign(
        aircraft={busy: 10, cratered: 4, helipads: 2},
        squadrons={busy: 2, cratered: 1, helipads: 1},
    )

    assert measured.tasks_at(busy) == [Task.AIRCRAFT, Task.RUNWAY, Task.CAPTURE]
    assert measured.tasks_at(empty) == []
    assert measured.tasks_at(cratered) == [Task.AIRCRAFT]
    assert measured.tasks_at(helipads) == [Task.AIRCRAFT]


def test_taking_a_base_means_beating_its_armour() -> None:
    garrison = armour("BABOON", 1, [unit("T-72B"), unit("T-72B")])
    depot = building("DEPOT", "ammo", 0, standing=1)
    field: Any = SimpleNamespace(
        base=SimpleNamespace(total_armor=6), ground_objects=[garrison, depot]
    )

    assert campaign().defenders(field, Task.CAPTURE) == 8
    assert campaign().defenders(field, Task.AIRCRAFT) == 0
