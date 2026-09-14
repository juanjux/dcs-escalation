"""What the base menu says before you do anything: what is here, and does it work.

The window used to open with a 300 px photograph, then the base name in bold beside
four radio editors, then a paragraph of rich text holding the aircraft, the ground
units and the runway state, then a repair button. Everything weighed the same and
the three facts a player checks before fragging a strike -- is the runway up, is
there ammo, how much parking is left -- were the tail of the paragraph.

Here the name is the only large text, the kind and the owner are stated rather than
inferred from which tabs turned up, and the paragraph becomes figures.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from dcs.planes import B_1B
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.dcs.aircrafttype import AircraftType
from game.theater import (
    AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION,
    FREE_FRONTLINE_UNIT_SUPPLY,
    ControlPoint,
    Fob,
    NavalControlPoint,
    ParkingType,
)
from game.theater.theatergroundobject import TheaterGroundObject
from qt_ui.widgets.cards import CAPTION, card, make_transparent, shrinkable
from qt_ui.widgets.controls import KEY, VALUE, mono, wrapped_tooltip

#: The status of a thing that works, does not, or is being seen to.
GOOD = "#86C39A"
BAD = "#D9645E"
PENDING = "#E0A86B"
QUIET = "#8FA3BD"

#: Blue and red as the rest of the app paints them.
OWNER_BLUE = "#8FC3F0"
OWNER_RED = "#D9645E"

BANNER_HEIGHT = 132

#: How many kinds of air defence the figure names before it says "and n more".
NAMED_DEFENCES = 3

#: Every kind of parking, because a base's figure counts every kind of aircraft.
EVERY_PARKING = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)


def chip(text: str, colour: str, filled: bool = False) -> QLabel:
    """A word with a box around it: a state, not a control."""
    label = QLabel(text)
    if filled:
        style = (
            f"background: {colour}; color: #0F1922; font-weight: bold;"
            " border: none; border-radius: 3px; padding: 2px 8px; font-size: 11px;"
            " letter-spacing: 1px;"
        )
    else:
        style = (
            f"background: transparent; color: {colour}; border: 1px solid {colour};"
            " border-radius: 3px; padding: 2px 8px; font-size: 11px;"
        )
    label.setStyleSheet(style)
    return label


def figure(value: str, label: str, note: str = "", warn: bool = False) -> QWidget:
    """One cell of the figures strip: a number to read, and the breakdown under it."""
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(2)

    name = QLabel(label.upper())
    name.setStyleSheet(
        f"font-size: 11px; font-weight: bold; letter-spacing: 1px; color: {CAPTION};"
        " background: transparent; border: none;"
    )
    column.addWidget(name)

    number = QLabel(value)
    number.setFont(mono(20))
    number.setStyleSheet(
        f"color: {PENDING if warn else VALUE}; background: transparent; border: none;"
    )
    column.addWidget(number)

    if note:
        detail = QLabel(note)
        detail.setStyleSheet(
            f"font-size: 11px; color: {QUIET}; background: transparent; border: none;"
        )
        # "M48 Chaparral x4 · M6 Linebacker x4 · M163 Vulcan Air Defense System x3"
        # is a sentence, and a sentence must not decide how wide a window opens.
        column.addWidget(shrinkable(detail))

    holder = QWidget()
    make_transparent(holder)
    holder.setLayout(column)
    return holder


def kind_of(cp: ControlPoint) -> str:
    """What this base is, in the words the header states rather than implies."""
    if cp.is_carrier:
        return "CARRIER"
    if cp.is_lha:
        return "LHA"
    if isinstance(cp, Fob):
        return "HELIPORT" if cp.has_helipads and not cp.has_ground_spawns else "FOB"
    if isinstance(cp, NavalControlPoint):
        return "SHIP"
    return "AIRBASE"


#: The last estimate worked out for each base, against the inputs it was worked out
#: from. Simulating the placement deep-copies the airport and walks every slot, which
#: is affordable once and is not affordable on every click: ordering a tank refreshes
#: the strip, and the strip asks for this.
_PARKING_CACHE: dict[
    int, tuple[tuple[Any, ...], Optional[dict[str, dict[str, int]]]]
] = {}


def parking_inputs(cp: ControlPoint) -> tuple[Any, ...]:
    """Everything the estimate is derived from, so a hit cannot be a stale answer."""
    squadrons = [
        (id(squadron), squadron.owned_aircraft, squadron.pending_deliveries)
        for squadron in cp.coalition.air_wing.iter_squadrons()
        if squadron.location == cp or squadron.destination == cp
    ]
    squadrons.sort()
    return (
        tuple(squadrons),
        cp.coalition.game.settings.ground_start_ai_planes,
        cp.total_aircraft_parking(EVERY_PARKING),
    )


def parking_breakdown(cp: ControlPoint) -> Optional[dict[str, dict[str, int]]]:
    inputs = parking_inputs(cp)
    cached = _PARKING_CACHE.get(id(cp))
    if cached is not None and cached[0] == inputs:
        return cached[1]
    answer = estimate_parking(cp)
    _PARKING_CACHE[id(cp)] = (inputs, answer)
    return answer


def estimate_parking(cp: ControlPoint) -> Optional[dict[str, dict[str, int]]]:
    """Estimate per-category parking usage by simulating slot allocation.

    The data model only tracks aircraft counts, not which slot each one
    occupies, so this replicates the placement priority used elsewhere to
    attribute aircraft to slot categories. The split is an estimate.
    """
    airport = cp.dcs_airport
    if airport is None:
        return None

    pt_rotary = ParkingType(rotary_wing=True)
    pt_stol = ParkingType(fixed_wing_stol=True)
    slots = list(cp.parking_slots)
    totals = {
        "shared": len([s for s in slots if s.helicopter and s.airplanes]),
        "fixed": len([s for s in slots if s.airplanes and not s.helicopter]),
        "rotary": len([s for s in slots if s.helicopter and not s.airplanes])
        + cp.total_aircraft_parking(pt_rotary),
        "ground": cp.total_aircraft_parking(pt_stol),
    }
    counts: dict[str, dict[str, int]] = {
        c: {"present": 0, "transferring": 0, "ordered": 0}
        for c in ("shared", "fixed", "rotary", "ground")
    }

    ap = deepcopy(airport)
    free_helipads = cp.total_aircraft_parking(pt_rotary)
    free_ground = cp.total_aircraft_parking(pt_stol)
    ground_start = cp.coalition.game.settings.ground_start_ai_planes

    def place(aircraft: AircraftType, phase: str) -> None:
        nonlocal free_helipads, free_ground
        is_heli = aircraft.helicopter
        is_vtol = not is_heli and aircraft.lha_capable
        ground_ok = aircraft.flyable or ground_start
        if free_helipads > 0 and is_heli:
            free_helipads -= 1
            counts["rotary"][phase] += 1
        elif free_ground > 0 and (is_heli or is_vtol or ground_ok):
            free_ground -= 1
            counts["ground"][phase] += 1
        else:
            slot = ap.free_parking_slot(aircraft.dcs_unit_type)
            if slot is None:
                return
            slot.unit_id = 1
            if slot.helicopter and slot.airplanes:
                counts["shared"][phase] += 1
            elif slot.airplanes:
                counts["fixed"][phase] += 1
            else:
                counts["rotary"][phase] += 1

    staying = [s for s in cp.squadrons if s.destination is None]
    incoming = [
        s for s in cp.coalition.air_wing.iter_squadrons() if s.destination == cp
    ]
    for s in staying:
        for _ in range(s.owned_aircraft):
            place(s.aircraft, "present")
    for s in incoming:
        for _ in range(s.owned_aircraft):
            place(s.aircraft, "transferring")
    for s in staying + incoming:
        for _ in range(max(s.pending_deliveries, 0)):
            place(s.aircraft, "ordered")

    # Fixed-wing slots split by size. "Big" slots are those that can host a
    # heavy aircraft (C-130, B-1B, tankers, AWACS...). DCS uses two slot
    # schemes: v1 maps flag big slots with .large, while v2 maps decide
    # purely by physical dimensions, so we mirror pydcs' own v2 fit test
    # against a representative heavy (the B-1B). Free counts come from the
    # placement sim above, so they match what a transfer would actually find.
    fw_slots = [s for s in ap.parking_slots if s.airplanes]
    if ap.slot_version == 1:
        big_flags = [s.large for s in fw_slots]
    else:
        big_flags = [
            s.width is not None
            and s.length is not None
            and B_1B.width < s.width
            and B_1B.height < (s.height or 1000)
            and B_1B.length < s.length
            for s in fw_slots
        ]
    big_total = sum(big_flags)
    small_total = len(fw_slots) - big_total
    free_big = sum(
        1 for s, big in zip(fw_slots, big_flags) if big and s.unit_id is None
    )
    free_small = sum(
        1 for s, big in zip(fw_slots, big_flags) if not big and s.unit_id is None
    )

    result: dict[str, dict[str, int]] = {}
    for c, total in totals.items():
        occ = counts[c]["present"]
        tr = counts[c]["transferring"]
        od = counts[c]["ordered"]
        result[c] = {
            "total": total,
            "occupied": occ,
            "transferring": tr,
            "ordered": od,
            "free": max(total - occ - tr - od, 0),
        }
    result["fixed_size"] = {
        "small_total": small_total,
        "free_small": free_small,
        "big_total": big_total,
        "free_big": free_big,
    }
    return result


def air_defences(cp: ControlPoint) -> list[TheaterGroundObject]:
    """The live air-defence sites this base is covered by, strongest first.

    Dead sites are left out: a site whose launchers are gone is not a reason to send
    SEAD, and counting it would overstate what a strike has to get through.
    """
    sites = [
        objective
        for objective in cp.connected_objectives
        if objective.category == "aa" and not objective.is_dead
    ]
    return sorted(sites, key=lambda site: (-site.alive_unit_count, site.obj_name))


def site_name(site: TheaterGroundObject) -> str:
    """What the site is, from what is in it: its most numerous live launcher.

    The objective's own name is a code word -- ALBATROSS, PYTHON -- which says where
    it is on the map but nothing about what it can shoot at you.
    """
    counts: dict[str, int] = {}
    for unit in site.units:
        # unit.type is the pydcs class; unit_type is the campaign's own model of it,
        # and the only one of the two with a name meant for a player to read.
        if unit.alive and unit.unit_type is not None:
            name = unit.unit_type.display_name
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return site.obj_name
    return max(counts.items(), key=lambda pair: pair[1])[0]


class BaseHeader(QWidget):
    """The banner, the name, what it is, who holds it, and whether it works."""

    def __init__(self, cp: ControlPoint, game_model) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.cp = cp
        self.game_model = game_model

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._banner())
        layout.addWidget(self._identity())
        self.setLayout(layout)

    # -- the pieces ----------------------------------------------------------

    def _banner(self, image: Optional[str] = None) -> QWidget:
        """The photograph, cropped to a strip.

        It only ever said "this is an airbase" or "this is a carrier", which the chip
        beside the name now says in words -- but it says it faster, so it stays, at a
        height that does not cost the fold every time the window opens.
        """
        banner = QLabel()
        banner.setFixedHeight(BANNER_HEIGHT)
        banner.setScaledContents(False)
        if image is not None:
            pixmap = QPixmap(image)
            if not pixmap.isNull():
                banner.setPixmap(pixmap)
        banner.setStyleSheet("background: #0F1922; border: none;")
        return banner

    def _identity(self) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(16)
        row.addLayout(self._name_and_state(), 1)
        comms = self._comms()
        if comms is not None:
            row.addWidget(comms)

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(row)
        return holder

    def _name_and_state(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)

        name = QLabel(self.cp.name)
        name.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #E8F0FB;"
            " background: transparent; border: none;"
        )
        title_row.addWidget(name)

        blue = self.cp.captured.is_blue
        owner = "BLUE" if blue else "RED"
        title_row.addWidget(
            chip(
                f"{kind_of(self.cp)} · {owner}",
                OWNER_BLUE if blue else OWNER_RED,
                filled=True,
            )
        )
        title_row.addStretch()
        column.addLayout(title_row)

        pills = QHBoxLayout()
        pills.setContentsMargins(0, 0, 0, 0)
        pills.setSpacing(8)
        for pill in self.status_pills():
            pills.addWidget(pill)
        pills.addStretch()
        column.addLayout(pills)
        return column

    def status_pills(self) -> list[QLabel]:
        """Where it flies from, its ammunition and its industry.

        Every pill is always here, including the ones that say no: a base with no
        depots looked exactly like a base whose depots the window had forgotten to
        mention, and the three of them are what a player checks before fragging.
        """
        pills = [self._surface_pill(), self._depots_pill(), self._factory_pill()]
        return [pill for pill in pills if pill is not None]

    def _surface_pill(self) -> Optional[QLabel]:
        """The runway, or the helipads, depending on what the base actually has.

        A FARP reports a runway status because every control point does, but it has
        no runway: nothing can crater it and nothing repairs it, so saying "runway
        operational" there says nothing and invites the player to believe a Hornet
        could use it.
        """
        if not self.cp.runway_is_destroyable:
            pads = self.cp.total_aircraft_parking(ParkingType(rotary_wing=True))
            if not pads:
                return None
            pill = chip(f"{pads} helipad{'' if pads == 1 else 's'}", GOOD)
            pill.setToolTip(
                wrapped_tooltip(
                    "Helicopters and anything that can land vertically. There is no "
                    "runway here, so nothing can crater it and nothing needs "
                    "repairing."
                )
            )
            return pill

        status = self.cp.runway_status
        if status is None:
            return None
        if status.damaged and status.repair_turns_remaining is not None:
            pill = chip(
                f"Runway damaged · repairs in {status.repair_turns_remaining}", PENDING
            )
        elif status.damaged:
            pill = chip("Runway damaged", BAD)
        else:
            pill = chip("Runway operational", GOOD)
        if status.damaged:
            pill.setToolTip(
                wrapped_tooltip(
                    "Nothing takes off or lands here while the runway is cratered. "
                    "Helicopters and anything with a ground start are unaffected."
                )
            )
        return pill

    def _depots_pill(self) -> QLabel:
        """How many units the front can be fed from here, and by what.

        The figure alone is meaningless without the arithmetic behind it, which is
        why it carries it: each live depot is worth twelve more units at the front.
        """
        alive, total = self._ammo_depots()
        if not total:
            pill = chip("No ammo depots", QUIET)
        elif alive == total:
            pill = chip(f"Ammo depots {alive}/{total}", GOOD)
        elif alive:
            pill = chip(f"Ammo depots {alive}/{total} · low", PENDING)
        else:
            pill = chip(f"Ammo depots 0/{total}", BAD)

        pill.setToolTip(wrapped_tooltip(self.deployable_explained(alive, total)))
        return pill

    def deployable_explained(self, alive: int, total: int) -> str:
        """Where the front-line limit comes from, in the terms that set it.

        The campaign has a ceiling of its own, and above it the depots stop counting.
        Reciting the arithmetic there would be quoting a sum that does not equal the
        figure beside it, so the cap says so instead.
        """
        limit = self.cp.frontline_unit_count_limit
        depots = f"{alive} live depot{'' if alive == 1 else 's'}"
        supplied = (
            FREE_FRONTLINE_UNIT_SUPPLY + AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION * alive
        )

        if supplied > limit:
            return (
                f"{limit} units can be deployed to the front from here, which is the "
                "campaign's own ceiling. The base and its "
                f"{depots} would otherwise supply {supplied}, so another depot would "
                "buy nothing."
            )

        text = (
            f"{limit} units can be deployed to the front from here: "
            f"{FREE_FRONTLINE_UNIT_SUPPLY} for the base itself and "
            f"{AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION} for each of its {depots}."
        )
        if alive < total:
            repaired = self.cp.front_line_capacity_with(total)
            if repaired > limit:
                text += (
                    f" Repairing the other {total - alive} would take that to "
                    f"{repaired}."
                )
        return text

    def _factory_pill(self) -> QLabel:
        """Whether this base builds its own ground units or waits for someone else's.

        Not whether it can order them: a base with no factory still can, as long as
        somewhere friendly has one. What the factory decides is where they are built
        and how they get here.
        """
        if self._has_factory():
            pill = chip("Factory producing", GOOD)
            pill.setToolTip(
                wrapped_tooltip(
                    "Ground units ordered here are built here, and are on the base "
                    "next turn."
                )
            )
        else:
            pill = chip("No factory", QUIET)
            pill.setToolTip(
                wrapped_tooltip(
                    "Ground units can still be ordered here. With no factory of its "
                    "own, the base is supplied by the nearest friendly base that has "
                    "one and can reach it, and the units arrive by road -- which "
                    "takes longer and can be attacked on the way. An order that no "
                    "factory can reach is not filled at all."
                )
            )
        return pill

    def _ammo_depots(self) -> tuple[int, int]:
        """Alive and total, counted the way the front-line limit counts them.

        The limit is driven by the warehouses inside the objectives rather than by
        the objectives themselves, and one objective can hold several. Counting the
        objectives here gave a figure whose own tooltip could not add up.
        """
        return self.cp.active_ammo_depots_count, self.cp.total_ammo_depots_count

    def _has_factory(self) -> bool:
        return self.cp.has_factory

    def _comms(self) -> Optional[QWidget]:
        """Radio, TACAN, ICLS and Link 4, one row each, and only the ones it has.

        Built by whoever owns those widgets and handed here, so this module does not
        learn what a TACAN channel is.
        """
        rows = getattr(self, "comms_rows", None)
        if not rows:
            return None
        grid = QGridLayout()
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(8)
        for index, (label, widget) in enumerate(rows):
            key = QLabel(label)
            key.setStyleSheet(
                f"font-size: 12px; color: {KEY}; background: transparent;"
                " border: none;"
            )
            grid.addWidget(key, index, 0)
            grid.addWidget(widget, index, 1)
        holder = card()
        holder.setLayout(grid)
        return holder


class FiguresStrip(QWidget):
    """Aircraft, ground units and money: the paragraph as three numbers.

    Budget belongs here rather than in the footer. It is a figure you read, not a
    button, and it sits beside the two numbers it constrains. The detail line under
    each number is what the paragraph said in fifteen lines of indented rich text;
    the rest of it -- how the deployable limit is arrived at, what is free where --
    is the tooltip, where a figure you only sometimes want belongs.
    """

    def __init__(self, cp: ControlPoint, game_model) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.cp = cp
        self.game_model = game_model

        self._row = QHBoxLayout()
        self._row.setContentsMargins(16, 10, 16, 10)
        self._row.setSpacing(28)

        holder = card()
        holder.setLayout(self._row)
        outer = QVBoxLayout()
        outer.setContentsMargins(16, 0, 16, 12)
        outer.addWidget(holder)
        self.setLayout(outer)
        self._pending = False
        self.repaint_cells()

    def refresh(self) -> None:
        """Repaint after the current burst of signals rather than once per signal.

        One purchase emits three -- the motorpool update, the inventory change and the
        budget -- and each of them used to rebuild these cells in full.
        """
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self.repaint_cells)

    def repaint_cells(self) -> None:
        self._pending = False
        while self._row.count():
            taken = self._row.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.deleteLater()
        for cell in self.cells():
            self._row.addWidget(cell)
        self._row.addStretch()

    def cells(self) -> list[QWidget]:
        if self.cp.captured.is_blue:
            return [self._aircraft(), self._ground(), self._budget()]
        # An enemy base's third figure is not money you cannot spend: it is what a
        # strike on this base would have to get through.
        return [self._aircraft(), self._ground(), self._air_defence()]

    def _air_defence(self) -> QWidget:
        sites = air_defences(self.cp)
        kinds: dict[str, int] = {}
        for site in sites:
            name = site_name(site)
            kinds[name] = kinds.get(name, 0) + 1
        # The heaviest few, not all sixteen: this is a line under a figure, and the
        # full list is what the Intel tab is for.
        ordered = sorted(kinds.items(), key=lambda pair: (-pair[1], pair[0]))
        shown = ordered[:NAMED_DEFENCES]
        parts = [name if count == 1 else f"{name} x{count}" for name, count in shown]
        if len(ordered) > NAMED_DEFENCES:
            parts.append(f"+{len(ordered) - NAMED_DEFENCES} more")

        cell = figure(
            str(len(sites)),
            "Air defence",
            " · ".join(parts) or "nothing covering this base",
        )
        if len(ordered) > NAMED_DEFENCES:
            cell.setToolTip(
                wrapped_tooltip(
                    "Covering this base: "
                    + ", ".join(
                        name if count == 1 else f"{name} x{count}"
                        for name, count in ordered
                    )
                    + ". The Intel tab lists them in full."
                )
            )
        return cell

    def _aircraft(self) -> QWidget:
        allocation = self.cp.allocated_aircraft(EVERY_PARKING)
        parking = self.cp.total_aircraft_parking(EVERY_PARKING)
        present = allocation.total_present

        parts = []
        tooltip = ""
        breakdown = parking_breakdown(self.cp)
        if breakdown is not None:
            sizes = breakdown["fixed_size"]
            small, big = sizes["small_total"], sizes["big_total"]
            rotary = breakdown["rotary"]
            ground = breakdown["ground"]
            if small:
                parts.append(f"{small - sizes['free_small']}/{small} small")
            if big:
                parts.append(f"{big - sizes['free_big']}/{big} big")
            if rotary["total"]:
                parts.append(
                    f"{rotary['total'] - rotary['free']}/{rotary['total']} rotary"
                )
            if ground["total"]:
                parts.append(
                    f"{ground['total'] - ground['free']}/{ground['total']} ground start"
                )
            tooltip = wrapped_tooltip(
                "Which parking is taken is an estimate: the campaign counts aircraft, "
                "not which slot each one sits in, so this places them the way the "
                "mission generator would. A big slot is one a B-1B would fit in."
            )
        else:
            free = max(parking - allocation.total, 0)
            parts.append(f"{free} free")

        if allocation.total_transferring:
            parts.append(f"{allocation.total_transferring} transferring")
        if allocation.total_ordered:
            parts.append(f"{allocation.total_ordered} ordered")

        cell = figure(f"{present} / {parking}", "Aircraft", " · ".join(parts))
        if tooltip:
            cell.setToolTip(tooltip)
        return cell

    def _ground(self) -> QWidget:
        transfers = self.game_model.game.coalition_for(self.cp.captured).transfers
        allocation = self.cp.allocated_ground_units(transfers)
        limit = self.cp.frontline_unit_count_limit
        reserve = max(allocation.total_present - limit, 0)

        parts = [f"{min(allocation.total_present, limit)}/{limit} deployable"]
        if reserve:
            parts.append(f"{reserve} reserve")
        if allocation.total_transferring_out:
            parts.append(f"{allocation.total_transferring_out} transferring out")
        if allocation.total_transferring:
            parts.append(f"{allocation.total_transferring} en route")
        if allocation.total_ordered:
            parts.append(f"{allocation.total_ordered} ordered")

        cell = figure(f"{allocation.total_present}", "Ground units", " · ".join(parts))
        cell.setToolTip(wrapped_tooltip(self.deployable_limit_explained()))
        return cell

    def deployable_limit_explained(self) -> str:
        """Why the limit is what it is, which is not derivable from the number."""
        text = (
            f"{self.cp.frontline_unit_count_limit} deployable = "
            f"{FREE_FRONTLINE_UNIT_SUPPLY} for the base + "
            f"{AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION} for each of its "
            f"{self.cp.total_ammo_depots_count} ammo depots."
        )
        if self.cp.has_active_frontline:
            reserve = max(
                self.cp.base.total_armor - self.cp.frontline_unit_count_limit, 0
            )
            if reserve:
                text += (
                    f" The {reserve} over that stay here in reserve rather than going "
                    "to the front this turn."
                )
        return text

    def _budget(self) -> QWidget:
        budget = self.game_model.game.blue.budget
        return figure(f"${budget:.2f}M", "Budget", "available to spend")
