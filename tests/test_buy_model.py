"""What the buy dialog offers, what it adds up to, and what it thinks is there."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.data.groups import GroupTask
from qt_ui.windows.groundobject.buymodel import Selection, here_now, section_of


class _UnitType:
    def __init__(self, name: str, price: int, dcs_type: Any) -> None:
        self.display_name = name
        self.price = price
        self.dcs_unit_type = dcs_type
        self.unit_class = SimpleNamespace(description="launcher")


def _unit_group(name: str, size: int, max_size: int, optional: bool = False) -> Any:
    return SimpleNamespace(
        name=name,
        group_size=size,
        max_size=max_size,
        optional=optional,
    )


def _layout(name: str, groups: list[tuple[str, list[Any]]]) -> Any:
    return SimpleNamespace(
        name=name,
        groups=[
            SimpleNamespace(group_name=group_name, unit_groups=unit_groups)
            for group_name, unit_groups in groups
        ],
    )


class _ForceGroup:
    def __init__(self, name: str, options: dict[str, list[_UnitType]], layout: Any):
        self.name = name
        self.options = options
        self.layouts = [layout]
        self.tasks = [GroupTask.LORAD]

    def unit_types_for_group(self, unit_group: Any) -> list[_UnitType]:
        return self.options.get(unit_group.name, [])

    def statics_for_group(self, unit_group: Any) -> list[Any]:
        return []


def _battery() -> Any:
    """Duck-typed: the model reads a handful of attributes off a force group."""
    radar = _unit_group("radar", size=1, max_size=1)
    launchers = _unit_group("launchers", size=4, max_size=8)
    guns = _unit_group("guns", size=1, max_size=2, optional=True)
    return _ForceGroup(
        "Patriot",
        {
            "radar": [_UnitType("STR", 22, "str")],
            "launchers": [_UnitType("LN", 15, "ln")],
            "guns": [
                _UnitType("Vulcan", 10, "vulcan"),
                _UnitType("Linebacker", 18, "lb"),
            ],
        },
        _layout("Patriot Battery", [("Battery", [radar, launchers]), ("PD", [guns])]),
    )


def test_a_selection_prices_what_it_holds() -> None:
    selection = Selection(_battery(), _battery().layouts[0])

    assert selection.units == 6
    assert selection.price == 22 + 4 * 15 + 10


def test_a_slot_that_is_switched_off_costs_nothing() -> None:
    selection = Selection(_battery(), _battery().layouts[0])
    guns = selection.slots[-1]
    guns.enabled = False

    assert guns.price == 0
    assert selection.units == 5


def test_a_slot_with_a_choice_charges_for_the_one_chosen() -> None:
    selection = Selection(_battery(), _battery().layouts[0])
    guns = selection.slots[-1]
    guns.chosen = 1

    assert guns.option.name == "Linebacker"
    assert guns.price == 18


def test_the_slots_keep_the_group_they_belong_to() -> None:
    selection = Selection(_battery(), _battery().layouts[0])

    assert [name for name, _ in selection.groups] == ["Battery", "PD"]


def test_a_preset_is_listed_under_what_it_is_for() -> None:
    assert section_of(_battery()) == "Long range SAM"


def test_what_stands_there_is_read_off_the_units_parked() -> None:
    group = _battery()
    site: Any = SimpleNamespace(
        units=[SimpleNamespace(type="str"), SimpleNamespace(type="ln")]
    )

    assert here_now(site, [group]) is group


def test_an_emptied_site_came_from_nowhere() -> None:
    empty: Any = SimpleNamespace(units=[])

    assert here_now(empty, [_battery()]) is None


def test_a_group_that_cannot_field_what_is_there_is_not_it() -> None:
    site: Any = SimpleNamespace(units=[SimpleNamespace(type="something else")])

    assert here_now(site, [_battery()]) is None
