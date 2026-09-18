"""What each Intelligence tab has to say, worked out before anything is painted.

The old dialog built its rows straight into a grid of labels, so the only way to ask
whether the numbers were right was to look at the window. These are plain values --
groups, rows, shares, totals -- so the arithmetic is testable and the painter has
nothing to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence

from game.game import Game
from game.income import Income
from game.theater import ControlPoint, ParkingType, Player
from game.theater.theatergroundobject import NAME_BY_CATEGORY


class Sort(Enum):
    """How a force tab is ordered.

    The first two order the groups, the last two the rows inside them: the question
    is either "where is most of it" or "what is at each base", and one control
    answers both without two combo boxes.
    """

    BASE_SIZE = "Base size"
    BASE_NAME = "Base name"
    COUNT = "Count"
    TYPE_NAME = "Type name"

    @property
    def orders_groups(self) -> bool:
        return self in (Sort.BASE_SIZE, Sort.BASE_NAME)


@dataclass(frozen=True)
class Figure:
    """One of the three numbers a tab opens with."""

    caption: str
    value: str
    note: str = ""


@dataclass(frozen=True)
class ForceRow:
    """One airframe or vehicle type at one base."""

    name: str
    #: The bracketed half of a display name -- "Lot 20", "Night Attack" -- carried
    #: separately so it can recede without the brackets.
    variant: str
    count: int
    #: Whether the filter matched this row, for the highlight.
    matched: bool = False

    @property
    def display(self) -> str:
        return f"{self.name} ({self.variant})" if self.variant else self.name


@dataclass(frozen=True)
class ForceGroup:
    """One base and what it holds."""

    name: str
    kind: str
    #: Carriers and LHAs get a diamond: a base that can sail is not a base.
    afloat: bool
    count: int
    share: float
    rows: tuple[ForceRow, ...]
    #: Rows the filter took out of this group.
    hidden: int = 0
    #: The filter is on and nothing here matched.
    no_match: bool = False

    @property
    def biggest_row(self) -> int:
        return max((row.count for row in self.rows), default=0)


@dataclass(frozen=True)
class ForceTab:
    """A whole Air forces or Ground forces tab."""

    figures: tuple[Figure, ...]
    groups: tuple[ForceGroup, ...]
    total: int
    #: Set when the side has none of this at all, and the list is replaced by a line.
    empty: Optional[tuple[str, str]] = None
    #: "MATCHING 7 OF 27 - 5 BASES" when the filter is on, else the plain total line.
    total_caption: str = ""


@dataclass(frozen=True)
class EconomyRow:
    name: str
    #: The grey line under the name, in three parts so the damaged fragment can be
    #: painted rust without the painter having to parse a sentence back apart.
    before: str
    damage: str
    after: str
    income: float
    share: float

    @property
    def detail(self) -> str:
        return f"{self.before}{self.damage}{self.after}"


@dataclass(frozen=True)
class EconomySection:
    caption: str
    subtotal: float
    share: float
    rows: tuple[EconomyRow, ...]


@dataclass(frozen=True)
class EconomyTab:
    figures: tuple[Figure, ...]
    sections: tuple[EconomySection, ...]
    empty: Optional[tuple[str, str]] = None


def money(value: float, signed: bool = False) -> str:
    """``$NM`` or ``+$NM``. The currency is millions, and the M says so.

    Whole millions drop the decimal, because "260.0M" spends two characters saying
    nothing and makes a column of money harder to compare down the page. A site that
    pays a fraction of one -- a village at 0.25 -- keeps its decimal rather than
    rounding away to nothing.
    """
    amount = round(value, 1)
    magnitude = abs(amount)
    body = f"{int(magnitude)}M" if amount == int(amount) else f"{magnitude:.1f}M"
    if signed:
        return f"{'-' if amount < 0 else '+'}${body}"
    return f"{'-' if amount < 0 else ''}${body}"


def base_kind(control_point: ControlPoint) -> str:
    if control_point.is_carrier:
        return "carrier"
    if control_point.is_lha:
        return "LHA"
    if control_point.is_fleet:
        return "fleet"
    if control_point.is_fob:
        return "FOB"
    return "airbase"


def split_variant(display_name: str) -> tuple[str, str]:
    """Take the bracketed half off a display name, if it has one."""
    if display_name.endswith(")") and " (" in display_name:
        head, _, tail = display_name.rpartition(" (")
        if head:
            return head, tail[:-1]
    return display_name, ""


def _share(part: float, whole: float) -> float:
    return part / whole if whole else 0.0


def _matches(text: str, needle: str) -> bool:
    return needle in text.casefold()


def _filtered(
    groups: Sequence[ForceGroup], needle: str
) -> tuple[tuple[ForceGroup, ...], int]:
    """The groups as the filter leaves them, and how many rows survived.

    A base whose own name matches keeps everything -- you asked for that base -- and
    a base that matches on nothing at all stays in the list rather than vanishing:
    knowing a base has none of what you are looking for is an answer too.
    """
    if not needle:
        return tuple(groups), sum(row.count for g in groups for row in g.rows)

    kept: list[ForceGroup] = []
    matching = 0
    for group in groups:
        if _matches(group.name, needle):
            rows = tuple(ForceRow(r.name, r.variant, r.count, True) for r in group.rows)
            matching += sum(r.count for r in rows)
            kept.append(
                ForceGroup(
                    group.name,
                    group.kind,
                    group.afloat,
                    group.count,
                    group.share,
                    rows,
                )
            )
            continue
        hits = tuple(
            ForceRow(r.name, r.variant, r.count, True)
            for r in group.rows
            if _matches(r.display, needle)
        )
        matching += sum(r.count for r in hits)
        kept.append(
            ForceGroup(
                group.name,
                group.kind,
                group.afloat,
                group.count,
                group.share,
                hits,
                hidden=len(group.rows) - len(hits),
                no_match=not hits,
            )
        )
    return tuple(kept), matching


def _sorted(groups: Iterable[ForceGroup], sort: Sort) -> tuple[ForceGroup, ...]:
    ordered = list(groups)
    if sort is Sort.BASE_NAME:
        ordered.sort(key=lambda g: g.name.casefold())
    else:
        # Base size is the default because the question is usually where most of it
        # is; the row sorts leave the groups in that order and reorder inside them.
        ordered.sort(key=lambda g: (-g.count, g.name.casefold()))

    out = []
    for group in ordered:
        rows = list(group.rows)
        if sort is Sort.TYPE_NAME:
            rows.sort(key=lambda r: r.display.casefold())
        else:
            rows.sort(key=lambda r: (-r.count, r.display.casefold()))
        out.append(
            ForceGroup(
                group.name,
                group.kind,
                group.afloat,
                group.count,
                group.share,
                tuple(rows),
                group.hidden,
                group.no_match,
            )
        )
    return tuple(out)


def _force_tab(
    raw: Sequence[ForceGroup],
    total: int,
    figures: tuple[Figure, ...],
    empty: Optional[tuple[str, str]],
    sort: Sort,
    needle: str,
) -> ForceTab:
    groups, matching = _filtered(raw, needle)
    groups = _sorted(groups, sort)
    bases = len(groups)
    plural = "BASES" if bases != 1 else "BASE"
    if needle:
        caption = f"MATCHING {matching} OF {total} · {bases} {plural}"
    else:
        caption = f"TOTAL · {bases} {plural}"
    return ForceTab(figures, groups, total, empty, caption)


def _with_shares(groups: Sequence[ForceGroup], total: int) -> list[ForceGroup]:
    return [
        ForceGroup(g.name, g.kind, g.afloat, g.count, _share(g.count, total), g.rows)
        for g in groups
    ]


def _side(player: Player) -> str:
    return "OWNFOR" if player.is_blue else "OPFOR"


def air_forces(
    game: Game, player: Player, sort: Sort = Sort.BASE_SIZE, needle: str = ""
) -> ForceTab:
    """Every aircraft the side has parked, grouped by where it is parked."""
    parking = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
    raw: list[ForceGroup] = []
    total = 0
    types: set[str] = set()
    for control_point in game.theater.control_points_for(player):
        allocation = control_point.allocated_aircraft(parking)
        count = allocation.total_present
        total += count
        if not count:
            continue
        rows = []
        for airframe, held in allocation.present.items():
            if not held:
                continue
            name, variant = split_variant(airframe.display_name)
            types.add(airframe.display_name)
            rows.append(ForceRow(name, variant, held))
        raw.append(
            ForceGroup(
                control_point.name,
                base_kind(control_point),
                control_point.is_fleet or control_point.is_carrier,
                count,
                0.0,
                tuple(rows),
            )
        )
    groups = _with_shares(raw, total)
    figures = (
        Figure("AIRCRAFT", str(total)),
        Figure("BASES", str(len(groups))),
        Figure("TYPES", str(len(types))),
    )
    empty = (
        None
        if total
        else (
            "No aircraft in reserve",
            f"{_side(player)} holds no airframes at any base this turn.",
        )
    )
    return _force_tab(groups, total, figures, empty, sort, needle.casefold())


def ground_forces(
    game: Game, player: Player, sort: Sort = Sort.BASE_SIZE, needle: str = ""
) -> ForceTab:
    """The vehicles held in reserve at each base, not the ones already deployed."""
    raw: list[ForceGroup] = []
    total = 0
    types: set[str] = set()
    for control_point in game.theater.control_points_for(player):
        base = control_point.base
        count = base.total_armor
        total += count
        if not count:
            continue
        rows = []
        for vehicle, held in base.armor.items():
            if not held:
                continue
            name, variant = split_variant(vehicle.display_name)
            types.add(vehicle.display_name)
            rows.append(ForceRow(name, variant, held))
        raw.append(
            ForceGroup(
                control_point.name,
                base_kind(control_point),
                control_point.is_fleet or control_point.is_carrier,
                count,
                0.0,
                tuple(rows),
            )
        )
    groups = _with_shares(raw, total)
    figures = (
        Figure("VEHICLES IN RESERVE", str(total)),
        Figure("BASES", str(len(groups))),
        Figure("TYPES", str(len(types))),
    )
    empty = (
        None
        if total
        else (
            "No vehicles in reserve",
            f"{_side(player)} keeps no armour at any base this turn.",
        )
    )
    return _force_tab(groups, total, figures, empty, sort, needle.casefold())


def economy(game: Game, player: Player) -> EconomyTab:
    """Where the side's money comes from, in two captioned sections."""
    income = Income(game, player)
    gross = income.from_bases + income.total_buildings

    control_points = []
    for control_point in sorted(
        income.control_points, key=lambda c: (-c.income_per_turn, c.name)
    ):
        operational = control_point.runway_is_operational()
        kind = base_kind(control_point)
        control_points.append(
            EconomyRow(
                name=control_point.name,
                before=f"{kind} · " + ("runway intact" if operational else ""),
                damage="" if operational else "runway destroyed",
                after="",
                income=control_point.income_per_turn,
                share=_share(control_point.income_per_turn, gross),
            )
        )

    buildings = []
    for building in sorted(income.buildings, key=lambda b: (-b.income, b.name)):
        standing = f"{building.number} of {building.total} standing"
        whole = building.number == building.total
        each = f" · {money(building.income_per_building)} each"
        buildings.append(
            EconomyRow(
                name=NAME_BY_CATEGORY.get(building.category, building.category),
                before=f"{building.name} · " + (standing if whole else ""),
                damage="" if whole else standing,
                after=each,
                income=building.income,
                share=_share(building.income, gross),
            )
        )

    sections = (
        EconomySection(
            "CONTROL POINTS",
            income.from_bases,
            _share(income.from_bases, gross),
            tuple(control_points),
        ),
        EconomySection(
            "BUILDINGS",
            income.total_buildings,
            _share(income.total_buildings, gross),
            tuple(buildings),
        ),
    )
    sources = len(control_points) + len(buildings)
    bases_note = f"{len(control_points)} base" + (
        "s" if len(control_points) != 1 else ""
    )
    builds_note = f"{len(buildings)} building" + ("s" if len(buildings) != 1 else "")
    figures = (
        Figure(
            "INCOME PER TURN",
            money(income.total, signed=True),
            f"× {income.multiplier:.1f} multiplier",
        ),
        Figure("BALANCE", money(game.coalition_for(player).budget)),
        Figure("SOURCES", str(sources), f"{bases_note} · {builds_note}"),
    )
    empty = (
        None
        if sources
        else ("No income", f"{_side(player)} holds nothing that pays this turn.")
    )
    return EconomyTab(figures, sections, empty)
