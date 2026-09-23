"""What every High Command objective is measured against."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.highcommand.campaign import RING_WEIGHT, releases
from game.mfd import Band
from game.theater import Player
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStatus
from game.utils import nautical_miles
from tests.highcommand.stubs import NM, campaign, launcher, sam


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
