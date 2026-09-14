"""What kind of building a target is, and what a base's factories are doing.

Every fixed target that is not a SAM came back as `kind: "building"`, so the planner
could not tell a factory from a warehouse -- and a base's own factories appeared
nowhere at all, which is the one thing that says whether it can build ground units.

Fakes rather than a campaign: these are two small view fields, and building a theater
to read them would test the theater.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.agent import views


class _Tgo:
    """As much of a TheaterGroundObject as the views touch."""

    def __init__(
        self,
        name: str,
        category: str,
        dead: bool = False,
        repairing: bool = False,
    ) -> None:
        self.id = name
        self.name = name
        self.category = category
        self.is_dead = dead
        self.has_pending_repairs = repairing
        self.position = SimpleNamespace(x=0.0, y=0.0)
        self.control_point = SimpleNamespace(name="Groom Lake")

    @property
    def is_factory(self) -> bool:
        return self.category == "factory"


def _game() -> Any:
    # latlng() is all _build_target asks the terrain for.
    return SimpleNamespace(
        theater=SimpleNamespace(terrain=None),
        settings=SimpleNamespace(),
    )


def _target(tgo: _Tgo, monkeypatch: Any) -> views.TargetView:
    monkeypatch.setattr(
        views, "DcsPoint", lambda x, y, terrain: SimpleNamespace(latlng=_latlng)
    )
    monkeypatch.setattr(views, "_iads_status", lambda game, tgo: None)
    return views._build_target(_game(), tgo, "building", "STRIKE")


def _latlng() -> Any:
    return SimpleNamespace(lat=37.0, lng=-115.0)


def test_a_building_target_says_which_kind_it_is(monkeypatch: Any) -> None:
    view = _target(_Tgo("SILKWORM", "factory"), monkeypatch)
    assert view.category == "factory"


def test_a_warehouse_is_not_a_factory(monkeypatch: Any) -> None:
    view = _target(_Tgo("ARAPAIMA", "ware"), monkeypatch)
    assert view.category == "ware"


def test_a_target_names_the_base_it_sits_at(monkeypatch: Any) -> None:
    view = _target(_Tgo("BELUGA", "factory"), monkeypatch)
    assert view.base == "Groom Lake"


def test_a_sam_is_not_given_a_category(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        views, "DcsPoint", lambda x, y, terrain: SimpleNamespace(latlng=_latlng)
    )
    monkeypatch.setattr(views, "_iads_status", lambda game, tgo: None)
    view = views._build_target(_game(), _Tgo("MINK", "aa"), "sam", "DEAD")
    assert view.category is None
    assert view.base == "Groom Lake"


def test_a_base_says_what_each_of_its_factories_is_doing() -> None:
    cp = SimpleNamespace(
        connected_objectives=[
            _Tgo("SILKWORM", "factory"),
            _Tgo("BELUGA", "factory", dead=True),
            _Tgo("BEAR", "factory", dead=True, repairing=True),
            _Tgo("ARAPAIMA", "ware"),
        ]
    )

    assert views._factories(cp) == {  # type: ignore[arg-type]
        "SILKWORM": "alive",
        "BELUGA": "destroyed",
        "BEAR": "repairing",
    }


def test_a_base_with_no_factory_carries_nothing() -> None:
    cp = SimpleNamespace(connected_objectives=[_Tgo("GORILLA", "ware")])

    assert views._factories(cp) is None  # type: ignore[arg-type]
