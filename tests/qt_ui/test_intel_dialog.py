"""What the Intelligence tabs say, before anything is painted.

The old dialog built its rows straight into a grid of labels, so the only way to ask
whether the numbers were right was to look at the window. These read the values the
painter is handed: the grouping, the shares, the order, what the filter keeps and what
the totals come to.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.theater import Player
from qt_ui.windows.intel import model as data


class _Type:
    """An airframe or vehicle type. A class, because the real ones are dict keys and
    a SimpleNamespace defines __eq__ and so cannot be hashed."""

    def __init__(self, name: str) -> None:
        self.display_name = name


def _airframe(name: str) -> Any:
    return _Type(name)


def _base(
    name: str,
    aircraft: dict[str, int] | None = None,
    armor: dict[str, int] | None = None,
    *,
    carrier: bool = False,
    fob: bool = False,
    income: int = 0,
    runway: bool = True,
) -> Any:
    present = {_airframe(k): v for k, v in (aircraft or {}).items()}
    held = {_airframe(k): v for k, v in (armor or {}).items()}
    return SimpleNamespace(
        name=name,
        is_carrier=carrier,
        is_lha=False,
        is_fleet=carrier,
        is_fob=fob,
        income_per_turn=income,
        runway_is_operational=lambda: runway,
        allocated_aircraft=lambda _parking: SimpleNamespace(
            present=present, total_present=sum(present.values())
        ),
        base=SimpleNamespace(armor=held, total_armor=sum(held.values())),
    )


def _game(*bases: Any, budget: float = 100.0) -> Any:
    return SimpleNamespace(
        theater=SimpleNamespace(control_points_for=lambda _player: list(bases)),
        coalition_for=lambda _player: SimpleNamespace(
            budget=budget, faction=SimpleNamespace(name="USA")
        ),
        turn=14,
    )


# The real one: the model only asks it which side it is, and everything else it
# touches is a double.
BLUE = Player.BLUE


def test_money_is_whole_and_signed_only_when_it_should_be() -> None:
    assert data.money(260.4) == "$260"
    assert data.money(260.4, signed=True) == "+$260"
    assert data.money(0, signed=True) == "+$0"
    assert data.money(-12, signed=True) == "-$12"


def test_a_variant_comes_off_the_display_name() -> None:
    assert data.split_variant("F/A-18C Hornet (Lot 20)") == (
        "F/A-18C Hornet",
        "Lot 20",
    )
    assert data.split_variant("A-50") == ("A-50", "")


def test_aircraft_are_grouped_by_base_and_share_the_whole() -> None:
    game = _game(
        _base("Groom Lake", {"F-16CM": 8, "KC-135": 2}),
        _base("Nellis AFB", {"F-16CM": 12}),
        _base("Creech", {}),
    )

    tab = data.air_forces(game, BLUE)

    assert [group.name for group in tab.groups] == ["Nellis AFB", "Groom Lake"]
    assert tab.total == 22
    assert [figure.value for figure in tab.figures] == ["22", "2", "2"]
    assert round(sum(group.share for group in tab.groups), 6) == 1.0
    assert tab.total_caption == "TOTAL · 2 BASES"


def test_a_base_with_nothing_is_left_out_but_still_counted_nowhere() -> None:
    """An empty base is not news; a side with nothing at all is."""
    game = _game(_base("Creech", {}))

    tab = data.air_forces(game, BLUE)

    assert tab.groups == ()
    assert tab.empty is not None
    assert "No aircraft in reserve" == tab.empty[0]


def test_base_name_orders_the_groups_and_type_name_the_rows() -> None:
    game = _game(
        _base("Zulu", {"A-10C": 1}),
        _base("Alpha", {"F-16CM": 2, "A-10C": 9}),
    )

    by_name = data.air_forces(game, BLUE, data.Sort.BASE_NAME)
    assert [group.name for group in by_name.groups] == ["Alpha", "Zulu"]

    by_type = data.air_forces(game, BLUE, data.Sort.TYPE_NAME)
    alpha = next(g for g in by_type.groups if g.name == "Alpha")
    assert [row.name for row in alpha.rows] == ["A-10C", "F-16CM"]
    # A row sort leaves the groups where the default put them.
    assert [group.name for group in by_type.groups] == ["Alpha", "Zulu"]


def test_the_filter_keeps_the_matches_and_counts_what_it_hid() -> None:
    game = _game(
        _base("Rio Gallegos", armor={"BM-30 Smerch": 3, "BMP-1": 2, "PLZ-05": 1}),
        _base("Mount Pleasant", armor={"BMP-1": 4}),
    )

    tab = data.ground_forces(game, BLUE, needle="smerch")

    gallegos = next(g for g in tab.groups if g.name == "Rio Gallegos")
    assert [row.name for row in gallegos.rows] == ["BM-30 Smerch"]
    assert gallegos.hidden == 2
    assert not gallegos.no_match

    pleasant = next(g for g in tab.groups if g.name == "Mount Pleasant")
    assert pleasant.no_match
    assert pleasant.rows == ()
    # The base stays in the list: knowing it has none is an answer too.
    assert tab.total_caption == "MATCHING 3 OF 10 · 2 BASES"


def test_matching_a_base_name_keeps_everything_it_holds() -> None:
    game = _game(_base("Rio Gallegos", armor={"BMP-1": 4, "PLZ-05": 1}))

    tab = data.ground_forces(game, BLUE, needle="gallegos")

    assert [row.name for row in tab.groups[0].rows] == ["BMP-1", "PLZ-05"]
    assert tab.groups[0].hidden == 0


def test_a_carrier_is_marked_as_one() -> None:
    game = _game(_base("CVN-72 Abraham Lincoln", {"F/A-18E": 7}, carrier=True))

    group = data.air_forces(game, BLUE).groups[0]

    assert group.afloat
    assert group.kind == "carrier"


def _income(monkeypatch: pytest.MonkeyPatch, **fields: Any) -> None:
    monkeypatch.setattr(
        data, "Income", lambda _game, _player: SimpleNamespace(**fields)
    )


def test_economy_splits_into_two_sections_with_their_share(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.income import BuildingIncome

    _income(
        monkeypatch,
        multiplier=1.0,
        control_points=[_base("Mount Pleasant", income=20)],
        buildings=[BuildingIncome("PIKE", "oil", 4, 10, 4)],
        from_bases=20,
        total_buildings=40,
        total=60,
    )

    tab = data.economy(_game(budget=261), BLUE)

    points, buildings = tab.sections
    assert (points.caption, points.subtotal) == ("CONTROL POINTS", 20)
    assert (buildings.caption, buildings.subtotal) == ("BUILDINGS", 40)
    assert round(buildings.share, 4) == round(40 / 60, 4)
    assert [figure.value for figure in tab.figures] == ["+$60", "$261", "2"]


def test_a_half_bombed_building_says_so_in_its_own_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Damage is the only coloured text in a row, so it is carried on its own."""
    from game.income import BuildingIncome

    _income(
        monkeypatch,
        multiplier=1.0,
        control_points=[],
        buildings=[BuildingIncome("CHAMELEON", "oil", 2, 10, 4)],
        from_bases=0,
        total_buildings=20,
        total=20,
    )

    row = data.economy(_game(), BLUE).sections[1].rows[0]

    assert row.name == "Oil platform"
    assert row.damage == "2 of 4 standing"
    assert row.detail == "CHAMELEON · 2 of 4 standing · $10 each"
    assert row.income == 20


def test_a_cut_runway_is_the_damaged_fragment_of_a_control_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _income(
        monkeypatch,
        multiplier=1.0,
        control_points=[_base("Rio Grande", income=0, runway=False)],
        buildings=[],
        from_bases=0,
        total_buildings=0,
        total=0,
    )

    row = data.economy(_game(), BLUE).sections[0].rows[0]

    assert row.damage == "runway destroyed"
    assert row.income == 0


# ------------------------------------------------------------------- the window


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_folding_a_group_takes_its_rows_off_the_list(qt_app: Any) -> None:
    from qt_ui.windows.intel.rows import HeaderLine, TypeLine, force_lines

    groups = data.air_forces(
        _game(_base("Groom Lake", {"F-16CM": 8, "KC-135": 2})), BLUE
    ).groups

    opened = force_lines(groups, set())
    shut = force_lines(groups, {"Groom Lake"})

    assert [type(line) for line in opened] == [HeaderLine, TypeLine, TypeLine]
    assert [type(line) for line in shut] == [HeaderLine]
    header = shut[0]
    assert isinstance(header, HeaderLine)
    assert header.folded


def test_the_fold_state_is_kept_per_side(qt_app: Any) -> None:
    """Switching sides and coming back should find the window as it was left."""
    from game.theater import Player
    from qt_ui.windows.intel.dialog import AIR, IntelWindow

    window = IntelWindow.__new__(IntelWindow)
    window.folded = {}
    window.player = Player.BLUE

    window.fold_state(AIR).add("Groom Lake")
    window.player = Player.RED
    assert window.fold_state(AIR) == set()

    window.player = Player.BLUE
    assert window.fold_state(AIR) == {"Groom Lake"}
