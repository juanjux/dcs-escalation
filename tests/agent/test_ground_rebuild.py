"""Tests for the OPFOR-AI ground-object rebuild feature (parity with the player's
Buy-ground-object dialog): the request schemas, the role/task mapping, the options
builder, and the rebuild write path.

Kept light with fakes/mocks (no full game load), matching the other agent-adjacent
tests. Real TGO instances are built for the isinstance-based role mapping; the game,
force-group and layout are duck-typed where a real one would need a full campaign.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import pytest
from dcs.mapping import Point

from game.agent import planner, schemas, views
from game.data.groups import GroupRole, GroupTask
from game.layout.layout import TgoLayoutGroup, TgoLayoutUnitGroup, LayoutUnit
from game.theater.controlpoint import OffMapSpawn, Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    CoastalSiteGroundObject,
    EwrGroundObject,
    MissileSiteGroundObject,
    SamGroundObject,
    ShipGroundObject,
    VehicleGroupGroundObject,
)
from game.utils import Heading

# --- helpers -------------------------------------------------------------------------


def _cp(player: Player = Player.RED) -> OffMapSpawn:
    cp = OffMapSpawn(
        name="cp",
        position=Point(0, 0, None),  # type: ignore[arg-type]
        theater=None,  # type: ignore[arg-type]
        starts_blue=player,
    )
    cp._coalition = SimpleNamespace(player=player)  # type: ignore[assignment]
    return cp


def _loc() -> PresetLocation:
    return PresetLocation(
        name="loc", position=Point(0, 0, None), heading=Heading(0)  # type: ignore[arg-type]
    )


def _sam(player: Player = Player.RED) -> SamGroundObject:
    return SamGroundObject(
        name="SAM Site", location=_loc(), control_point=_cp(player), task=None
    )


class _FakeUnitType:
    def __init__(self, name: str, price: int, dcs_unit_type: Any) -> None:
        self.display_name = name
        self.price = price
        self.dcs_unit_type = dcs_unit_type


class _FakeForceGroup:
    """Duck-typed ForceGroup: only the methods the rebuild path calls."""

    def __init__(
        self, name: str, layouts: list[Any], unit_types: list[_FakeUnitType]
    ) -> None:
        self.name = name
        self.layouts = layouts
        self._unit_types = unit_types
        # (group_name, dcs_unit_type, count)
        self.created: list[tuple[Any, Any, Any]] = []

    def unit_types_for_group(self, unit_group: Any) -> Iterator[_FakeUnitType]:
        return iter(self._unit_types)

    def statics_for_group(self, unit_group: Any) -> Iterator[Any]:
        return iter(())

    def create_theater_group_for_tgo(
        self,
        tgo: Any,
        unit_group: Any,
        group_name: Any,
        game: Any,
        dcs_unit_type: Any,
        unit_count: Any = None,
    ) -> None:
        self.created.append((group_name, dcs_unit_type, unit_count))


def _unit_group(
    name: str = "main", size: int = 2, optional: bool = False
) -> TgoLayoutUnitGroup:
    ug = TgoLayoutUnitGroup(
        name=name,
        layout_units=[LayoutUnit(f"u{i}", Point(0, 0, None), 0) for i in range(4)],  # type: ignore[arg-type]
    )
    ug.unit_count = [size]
    ug.optional = optional
    return ug


def _layout(name: str, unit_group: TgoLayoutUnitGroup) -> Any:
    grp = TgoLayoutGroup(group_name="Battery", group_index=0, unit_groups=[unit_group])
    return SimpleNamespace(name=name, groups=[grp])


def _fake_game(
    tgo: Any, *, budget: float = 1000, turn: int = 3, repair_turns: int = 0
) -> Any:
    coalition = SimpleNamespace(budget=budget)
    renewed: list[Any] = []
    theater = SimpleNamespace(
        heading_to_conflict_from=lambda pos: None,
        iads_network=SimpleNamespace(
            update_tgo=lambda tgo, events: renewed.append(tgo), renewed=renewed
        ),
    )
    return SimpleNamespace(
        turn=turn,
        settings=SimpleNamespace(ground_object_repair_turns=repair_turns),
        theater=theater,
        db=SimpleNamespace(tgos=SimpleNamespace(get=lambda _id: tgo)),
        coalition_for=lambda player: coalition,
        next_group_id=lambda: 1,
        next_unit_id=lambda: 1,
    )


# --- schemas -------------------------------------------------------------------------


def test_rebuild_group_spec_defaults() -> None:
    spec = schemas.RebuildGroupSpec(group_name="Battery")
    assert spec.unit_type is None
    assert spec.count is None
    assert spec.enabled is True


def test_rebuild_request_validates() -> None:
    req = schemas.RebuildGroundObjectRequest(
        tgo_id="abc",
        force_group="SA-10",
        layout="Default",
        groups=[{"group_name": "Battery", "unit_type": "S-300", "count": 4}],
    )
    assert req.side == "red"
    assert req.groups[0].count == 4
    assert req.groups[0].enabled is True


# --- role / task mapping -------------------------------------------------------------


def test_role_tasks_for_each_tgo_type() -> None:
    cp = _cp()
    cases = [
        (SamGroundObject("s", _loc(), cp, None), GroupRole.AIR_DEFENSE, None),
        (
            EwrGroundObject("e", _loc(), cp),
            GroupRole.AIR_DEFENSE,
            GroupTask.EARLY_WARNING_RADAR,
        ),
        (VehicleGroupGroundObject("v", _loc(), cp, None), GroupRole.GROUND_FORCE, None),
        (ShipGroundObject("sh", _loc(), cp), GroupRole.NAVAL, GroupTask.NAVY),
        (
            MissileSiteGroundObject("m", _loc(), cp),
            GroupRole.DEFENSES,
            GroupTask.MISSILE,
        ),
        (
            CoastalSiteGroundObject("c", _loc(), cp),
            GroupRole.DEFENSES,
            GroupTask.COASTAL,
        ),
    ]
    for tgo, expected_role, expected_task in cases:
        role, tasks = views._ground_object_role_and_tasks(tgo)
        assert role is expected_role, type(tgo).__name__
        if expected_task is not None:
            assert tasks == [expected_task], type(tgo).__name__
        else:
            # SAM/armor fall back to every task of the role.
            assert tasks == expected_role.tasks, type(tgo).__name__


def test_role_tasks_rejects_unsupported_tgo() -> None:
    with pytest.raises(ValueError):
        views._ground_object_role_and_tasks(SimpleNamespace(name="x"))


# --- options builder: error paths ----------------------------------------------------


def test_options_bogus_tgo_id_raises_valueerror() -> None:
    def _raise(_id: Any) -> Any:
        raise KeyError(_id)

    game = SimpleNamespace(db=SimpleNamespace(tgos=SimpleNamespace(get=_raise)))
    with pytest.raises(ValueError, match="no ground object"):
        views.build_ground_object_options(game, "red", str(uuid4()))  # type: ignore[arg-type]


def test_options_not_owned_raises_valueerror() -> None:
    tgo = _sam(Player.BLUE)  # a blue site — red must not rebuild it
    game = _fake_game(tgo)
    with pytest.raises(ValueError, match="is not yours"):
        views.build_ground_object_options(game, "red", str(uuid4()))


# --- options builder: happy path -----------------------------------------------------


def test_options_lists_layout_and_units() -> None:
    ug = _unit_group(size=2)
    layout = _layout("SA-10 Default", ug)
    ut = _FakeUnitType("S-300 LN", 60, object)
    fg = _FakeForceGroup("SA-10", [layout], [ut])
    tgo = _sam()
    game = _fake_game(tgo, budget=500)
    game.coalition_for = lambda player: SimpleNamespace(
        budget=500, armed_forces=SimpleNamespace(groups_for_tasks=lambda tasks: [fg])
    )

    view = views.build_ground_object_options(game, "red", str(uuid4()))
    assert view.role == "air_defense"
    assert view.budget == 500
    assert len(view.options) == 1
    opt = view.options[0]
    assert opt.force_group == "SA-10"
    assert opt.layout == "SA-10 Default"
    assert opt.price == 120  # 2 * 60
    assert opt.groups[0].group_name == "Battery"
    assert opt.groups[0].default_count == 2
    assert opt.groups[0].max_count == 4
    assert opt.groups[0].unit_types[0].name == "S-300 LN"


# --- rebuild write path --------------------------------------------------------------


def test_rebuild_bogus_tgo_returns_opresult_error() -> None:
    def _raise(_id: Any) -> Any:
        raise KeyError(_id)

    game = SimpleNamespace(
        db=SimpleNamespace(tgos=SimpleNamespace(get=_raise)),
        coalition_for=lambda player: SimpleNamespace(budget=0),
    )
    res = planner.rebuild_ground_object(
        game, "red", str(uuid4()), "SA-10", "Default"  # type: ignore[arg-type]
    )
    assert res.ok is False
    assert res.error and "no ground object" in res.error


def _rebuild_game(tgo: Any, fg: Any, **kw: Any) -> Any:
    game = _fake_game(tgo, **kw)
    game.coalition_for = lambda player: SimpleNamespace(
        budget=kw.get("budget", 1000),
        armed_forces=SimpleNamespace(groups_for_tasks=lambda tasks: [fg]),
    )
    return game


def test_rebuild_happy_path_charges_net_and_creates_group() -> None:
    ug = _unit_group(size=2)
    layout = _layout("Default", ug)
    ut = _FakeUnitType("S-300 LN", 60, object)  # price 60 * 2 = 120
    fg = _FakeForceGroup("SA-10", [layout], [ut])
    tgo = _sam()
    # a fresh SAM has no units -> value 0 -> refund 0 -> net cost = 120
    coalition_budget = {"v": 500.0}
    game = _fake_game(tgo, budget=500, turn=3, repair_turns=0)
    coalition = SimpleNamespace(
        budget=500.0,
        armed_forces=SimpleNamespace(groups_for_tasks=lambda tasks: [fg]),
    )
    game.coalition_for = lambda player: coalition

    res = planner.rebuild_ground_object(game, "red", str(uuid4()), "SA-10", "Default")
    assert res.ok is True, res.error
    assert coalition.budget == 380.0  # 500 - 120
    assert fg.created == [("SAM Site (Battery)", object, 2)]
    assert tgo.groups == []  # cleared before create (fake create doesn't repopulate)
    # Its IADS node is renewed on the new groups.
    assert game.theater.iads_network.renewed == [tgo]


def test_turn_zero_is_not_a_free_shopping_spree() -> None:
    """Ground objects used to cost nothing on turn 0 while the dialog still quoted a
    price, so a campaign could open with an S-300 belt bought for free."""
    ug = _unit_group(size=2)
    layout = _layout("Default", ug)
    ut = _FakeUnitType("S-300 LN", 999, object)
    fg = _FakeForceGroup("SA-10", [layout], [ut])
    tgo = _sam()
    game = _fake_game(tgo, budget=10, turn=0)
    coalition = SimpleNamespace(
        budget=10.0,
        armed_forces=SimpleNamespace(groups_for_tasks=lambda tasks: [fg]),
    )
    game.coalition_for = lambda player: coalition

    res = planner.rebuild_ground_object(game, "red", str(uuid4()), "SA-10", "Default")
    assert res.ok is False
    assert "have 10" in (res.error or "")
    assert coalition.budget == 10.0  # refused, so nothing was spent either


def test_rebuild_unknown_force_group_reports_valid_names() -> None:
    ug = _unit_group()
    layout = _layout("Default", ug)
    fg = _FakeForceGroup("SA-10", [layout], [_FakeUnitType("x", 1, object)])
    tgo = _sam()
    game = _rebuild_game(tgo, fg)
    res = planner.rebuild_ground_object(game, "red", str(uuid4()), "SA-99", "Default")
    assert res.ok is False
    assert res.error and "SA-10" in res.error  # valid names listed


def test_rebuild_count_override_clamped_to_max() -> None:
    ug = _unit_group(size=2)  # max_size = 4 (four layout units)
    layout = _layout("Default", ug)
    ut = _FakeUnitType("S-300 LN", 10, object)
    fg = _FakeForceGroup("SA-10", [layout], [ut])
    tgo = _sam()
    coalition = SimpleNamespace(
        budget=10_000.0,
        armed_forces=SimpleNamespace(groups_for_tasks=lambda tasks: [fg]),
    )
    game = _fake_game(tgo, budget=10_000, turn=3)
    game.coalition_for = lambda player: coalition

    res = planner.rebuild_ground_object(
        game,
        "red",
        str(uuid4()),
        "SA-10",
        "Default",
        groups=[{"group_name": "Battery", "count": 99}],
    )
    assert res.ok is True, res.error
    assert fg.created[0][2] == 4  # clamped to max_size


def test_rebuild_bad_unit_type_override_errors() -> None:
    ug = _unit_group()
    layout = _layout("Default", ug)
    fg = _FakeForceGroup("SA-10", [layout], [_FakeUnitType("S-300 LN", 10, object)])
    tgo = _sam()
    game = _rebuild_game(tgo, fg)
    res = planner.rebuild_ground_object(
        game,
        "red",
        str(uuid4()),
        "SA-10",
        "Default",
        groups=[{"group_name": "Battery", "unit_type": "Nonexistent"}],
    )
    assert res.ok is False
    assert res.error and "not available" in res.error
