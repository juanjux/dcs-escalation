"""The pilot dialog's record column: kills, what he survived, and how he died.

Kills are grouped by what was destroyed for ground targets and by what shot it down for
air targets. Each row opens in place to the individual kills rather than to a second
dialog.

The counts come from the tallies, which are never trimmed; the rows they open into come
from the kill log, which is capped, so the remainder is shown as "and n earlier".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from PySide6.QtWidgets import QVBoxLayout, QWidget

from game.squadrons.pilot import Kill, Pilot, PilotRecord, PilotStatus
from game.sim.missionresultsprocessor import (
    AIR_DEFENCE,
    ARMOUR,
    ARTILLERY,
    SHIPS,
    SOFT_VEHICLES,
    STRUCTURES,
)
from qt_ui.widgets.cards import shrinkable
from qt_ui.windows.pilot.common import (
    AIR_FAMILY,
    GREEN,
    GROUND_FAMILY,
    HEADING_BG,
    RED,
    ROW_OPEN,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    Row,
    Stack,
    captioned,
    empty_row,
    label,
    rich,
)

#: The order the classes are shown in: what shoots back first, then what was being
#: shot at. Any class the game grows that is not in here sorts after them by count.
CLASS_ORDER = (
    AIR_DEFENCE,
    ARMOUR,
    ARTILLERY,
    SHIPS,
    STRUCTURES,
    SOFT_VEHICLES,
)

#: How many unit types a closed ground row names before it gives up and says "…".
TYPES_IN_SUMMARY = 3

#: Where the second column of an open row starts.
CHILD_NAME_WIDTH = 200

EARLIER = "earlier, before these were kept"


@dataclass
class KillGroup:
    """One row of the record: a heading, a count, and what it opens into."""

    name: str
    count: int
    children: list["KillGroup"] = field(default_factory=list)
    #: The turn or turns, and the weapons -- the right-hand half of a child row.
    detail: str = ""
    #: What a closed row says after its name: the unit types inside it.
    summary: str = ""


def turns_phrase(kills: Sequence[Kill]) -> str:
    """ "T8", or "T8-T11" when they were not all on the same day."""
    turns = sorted({kill.turn for kill in kills if kill.turn})
    if not turns:
        return ""
    if len(turns) == 1:
        return f"T{turns[0]}"
    return f"T{turns[0]}-T{turns[-1]}"


def weapons_phrase(kills: Sequence[Kill]) -> str:
    """The weapons, most used first, each with its count when it is more than one."""
    counted: dict[str, int] = {}
    for kill in kills:
        if kill.weapon:
            counted[kill.weapon] = counted.get(kill.weapon, 0) + 1
    ordered = sorted(counted.items(), key=lambda item: (-item[1], item[0]))
    return " · ".join(
        name if count == 1 else f"{name} x{count}" for name, count in ordered
    )


def _detail_of(kills: Sequence[Kill]) -> str:
    return " · ".join(
        part for part in (turns_phrase(kills), weapons_phrase(kills)) if part
    )


def _grouped(kills: Sequence[Kill], key: str) -> list[KillGroup]:
    """The kills under one row, grouped by unit type or by weapon.

    A ground row groups by what was destroyed, since the row itself is the class. An air
    row groups by the weapon used.

    """
    buckets: dict[str, list[Kill]] = {}
    for kill in kills:
        name = kill.what if key == "what" else (kill.weapon or "no weapon recorded")
        buckets.setdefault(name, []).append(kill)
    groups = [
        KillGroup(
            name,
            len(inner),
            detail=_detail_of(inner) if key == "what" else turns_phrase(inner),
        )
        for name, inner in buckets.items()
    ]
    groups.sort(key=lambda group: (-group.count, group.name))
    return groups


def air_groups(record: PilotRecord) -> list[KillGroup]:
    """One row per aircraft type, opening into the weapons he used on them."""
    groups = []
    for what, count in sorted(
        record.air_kills.items(), key=lambda item: (-item[1], item[0])
    ):
        kills = record.kills_of(what)
        children = _grouped([kill for kill in kills if kill.air], "weapon")
        _note_the_missing(children, count)
        groups.append(KillGroup(what, count, children))
    return groups


def ground_groups(record: PilotRecord) -> list[KillGroup]:
    """One row per class of target, opening into the types inside it."""
    by_class = record.ground_kills_by_class()
    groups = []
    for name in sorted(
        by_class, key=lambda name: (_class_rank(name), -by_class[name], name)
    ):
        kills = record.kills_in(name)
        children = _grouped(kills, "what")
        groups.append(
            KillGroup(
                name,
                by_class[name],
                children,
                summary=_summary_of(children),
            )
        )

    # Whatever the log no longer holds: kills from before it existed, and the tail of a
    # campaign long enough to have pushed some out of it.
    missing = record.total_ground_kills - sum(by_class.values())
    if missing > 0:
        groups.append(KillGroup(EARLIER, missing))
    return groups


def _class_rank(name: str) -> int:
    return CLASS_ORDER.index(name) if name in CLASS_ORDER else len(CLASS_ORDER)


def _summary_of(children: Sequence[KillGroup]) -> str:
    """The types inside a closed row, so "5 air defence" is not all it says."""
    named = [
        child.name if child.count == 1 else f"{child.name} x{child.count}"
        for child in children[:TYPES_IN_SUMMARY]
    ]
    if len(children) > TYPES_IN_SUMMARY:
        named.append("…")
    return " · ".join(named)


def _note_the_missing(children: list[KillGroup], count: int) -> None:
    """Say so when the tally is ahead of what the log can account for."""
    missing = count - sum(child.count for child in children)
    if missing > 0:
        children.append(KillGroup(EARLIER, missing))


class GroupRow(Row):
    """A summary row and the kills it opens into.

    A Row with three attributes stapled on would do the same job; a class says what
    they are and lets the card be read without guessing.
    """

    def __init__(self, group: KillGroup, openable: bool) -> None:
        super().__init__(height=30, interactive=openable)
        self.group = group
        self.body.setSpacing(0)

        self.arrow = label("▸" if openable else "", 10, TEXT_LABEL)
        self.arrow.setFixedWidth(16)
        self.add(self.arrow)

        self.name_label = rich("", 12.5)
        self.add(shrinkable(self.name_label))
        self.body.setStretchFactor(self.name_label, 1)
        self.add(label(str(group.count), 13, TEXT_PRIMARY, True, monospace=True))
        self._say(False)

    def set_open(self, opening: bool) -> None:
        self.arrow.setText("▾" if opening else "▸")
        self.fill = ROW_OPEN if opening else ""
        self._restyle()
        self._say(opening)

    def _say(self, opening: bool) -> None:
        """The summary names the types inside, so with them on the screen it would be
        the same thing said twice."""
        if opening or not self.group.summary:
            weight = ";font-weight:600" if opening else ""
            ink = TEXT_PRIMARY if opening else TEXT_BASE
            self.name_label.setText(
                f"<span style='color:{ink}{weight}'>{self.group.name}</span>"
            )
            return
        self.name_label.setText(
            f"<span style='color:{TEXT_BASE}'>{self.group.name}</span>"
            f" <span style='color:{TEXT_LABEL}'>{self.group.summary}</span>"
        )


class KillRows(QWidget):
    """The combat record: two families of rows, one of them open at a time."""

    def __init__(self, pilot: Pilot) -> None:
        super().__init__()
        record = pilot.record
        self.open_row: Optional[Row] = None
        self.stack = Stack()

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.stack)
        self.setLayout(column)

        self._family("AIR-TO-AIR", AIR_FAMILY, record.total_air_kills)
        self._groups(air_groups(record))
        self._family("AIR-TO-GROUND", GROUND_FAMILY, record.total_ground_kills)
        self._groups(ground_groups(record))
        self.stack.refresh()

    def _family(self, name: str, ink: str, count: int) -> None:
        row = Row(height=22, fill=HEADING_BG)
        heading = label(name, 10, ink, bold=True)
        heading.setStyleSheet(heading.styleSheet() + " letter-spacing: 1px;")
        row.add(heading)
        row.stretch()
        row.add(label(str(count), 11, TEXT_LABEL, monospace=True))
        self.stack.append(row)

    def _groups(self, groups: Sequence[KillGroup]) -> None:
        if not groups:
            self.stack.append(empty_row("none"))
            return
        for group in groups:
            children = [self._child(child) for child in group.children]
            parent = GroupRow(group, bool(children))
            self.stack.append(parent)
            for child in children:
                child.setVisible(False)
                self.stack.append(child)
            if children:
                parent.clicked.connect(
                    lambda parent=parent, children=children: self._toggle(
                        parent, children
                    )
                )

    @staticmethod
    def _child(group: KillGroup) -> Row:
        row = Row(height=26)
        row.body.setContentsMargins(30, 0, 14, 0)
        row.body.setSpacing(0)
        name = label(group.name, 12, TEXT_SECONDARY)
        name.setFixedWidth(CHILD_NAME_WIDTH)
        row.add(name)
        detail = label(group.detail, 11, TEXT_LABEL)
        row.add(shrinkable(detail))
        row.body.setStretchFactor(detail, 1)
        row.add(label(str(group.count), 12, TEXT_BASE, monospace=True))
        return row

    def _toggle(self, parent: GroupRow, children: Sequence[Row]) -> None:
        """Open this one, and shut whatever was open: two open rows at once turn the
        card into a list of everything, which is what the grouping was for."""
        opening = parent is not self.open_row
        if self.open_row is not None and self.open_row is not parent:
            self._set_open(self.open_row, False)
        self._set_open(parent, opening)
        self.open_row = parent if opening else None
        self.stack.refresh()

    def _set_open(self, parent: GroupRow, opening: bool) -> None:
        index = self.stack.rows.index(parent)
        for row in self.stack.rows[index + 1 : index + 1 + len(parent.group.children)]:
            row.setVisible(opening)
        parent.set_open(opening)


def survival_rows(pilot: Pilot) -> Stack:
    """What he has walked away from, and what it cost him."""
    record = pilot.record
    stack = Stack()

    lost = record.aircraft_lost
    walked = record.survived_losses
    ink = GREEN if walked else RED
    stack.append(
        _key_value(
            "Ejected",
            f"<span style='color:{TEXT_PRIMARY};font-weight:600'>{lost}</span>"
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'>"
            f" {'time' if lost == 1 else 'times'}</span>"
            + (
                f"<span style='color:#4F6070;font-size:11.5px'> · </span>"
                f"<span style='color:{ink}'>{walked}</span>"
                f"<span style='color:{'#5F8A6C' if walked else '#8A6C5C'};"
                "font-size:11.5px'> walked away</span>"
                if lost
                else ""
            ),
        )
    )

    wounds = record.wounds
    text = (
        f"<span style='color:{TEXT_PRIMARY};font-weight:600'>{wounds}</span>"
        f"<span style='color:{TEXT_LABEL};font-size:11.5px'>"
        f" {'time' if wounds == 1 else 'times'}</span>"
    )
    if wounds and record.last_wound_turn:
        turns = record.last_wound_turns
        text += (
            f"<span style='color:#4F6070;font-size:11.5px'> · </span>"
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'>last on turn "
            f"{record.last_wound_turn}, {turns} "
            f"{'turn' if turns == 1 else 'turns'} out</span>"
        )
    stack.append(_key_value("Wounded", text))

    taken = record.leaves_taken
    leave = (
        f"<span style='color:{TEXT_PRIMARY};font-weight:600'>{taken}</span>"
        f"<span style='color:{TEXT_LABEL};font-size:11.5px'>"
        f" {'time' if taken == 1 else 'times'}</span>"
    )
    if record.leave_turns_total:
        leave += (
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'>"
            f", {record.leave_turns_total} turns</span>"
        )
    stack.append(_key_value("Leave taken", leave))
    stack.refresh()
    return stack


def _key_value(key: str, value_html: str, height: int = 36) -> Row:
    row = Row(height=height)
    row.add(label(key, 12.5, TEXT_SECONDARY))
    row.stretch()
    row.add(rich(value_html, 14))
    return row


def killed_in_action(pilot: Pilot) -> Optional[Stack]:
    """How it ended, for the man it ended for."""
    if pilot.status is not PilotStatus.Dead:
        return None
    stack = Stack()
    killed_by = pilot.record.killed_by
    if killed_by is None or not killed_by.pilot_name:
        stack.append(
            _fact(
                "Killed by",
                f"<span style='color:{TEXT_LABEL}'>"
                "Unknown — lost with the aircraft</span>",
            )
        )
        stack.refresh()
        return stack

    who = (
        f"<span style='color:{TEXT_PRIMARY};font-weight:600'>"
        f"{killed_by.pilot_name}</span>"
    )
    trailing = " · ".join(
        part
        for part in (killed_by.aircraft, killed_by.squadron)
        if part and part != killed_by.pilot_name
    )
    if trailing:
        who += f" <span style='color:{TEXT_LABEL}'>· {trailing}</span>"
    if killed_by.friendly_fire:
        who += f" <span style='color:{RED}'>· friendly fire</span>"
    stack.append(_fact("Killed by", who))

    if killed_by.weapon:
        stack.append(
            _fact(
                "Weapon", f"<span style='color:{TEXT_BASE}'>{killed_by.weapon}</span>"
            )
        )
    stack.refresh()
    return stack


def _fact(key: str, value_html: str) -> Row:
    row = Row(height=36)
    name = label(key, 12.5, TEXT_SECONDARY)
    name.setFixedWidth(116)
    row.add(name)
    answer = shrinkable(rich(value_html, 12.5))
    row.add(answer)
    row.body.setStretchFactor(answer, 1)
    return row


KILLS_TOOLTIP = (
    "Everything he has destroyed. Air kills are listed by aircraft type, ground"
    " kills by what sort of target it was."
    "\n\n"
    "Click a row to see the individual kills: what it was, the turn, and the"
    " weapon used."
)

SURVIVAL_TOOLTIP = (
    "How often he has been shot down, and how often he survived it. Rank,"
    " hardening and friends in the same flight all improve those odds."
    "\n\n"
    "A wound keeps him off the roster for 1 to 4 turns. Leave is granted by you"
    " and raises morale quickly."
)


def record_column(pilot: Pilot, also: Optional[QWidget] = None) -> QVBoxLayout:
    """The left-hand half of the dialog, top to bottom.

    ``also`` is whatever else wants the elastic column rather than the fixed one --
    the relationships, whose rows are sentences and need the room.
    """
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(22)

    fallen = killed_in_action(pilot)
    if fallen is not None:
        where = pilot.record.killed_by
        hint = f"turn {where.turn}" if where is not None and where.turn else ""
        column.addWidget(captioned("Killed in action", fallen, hint, ink=RED))

    column.addWidget(captioned("Combat record", KillRows(pilot), tooltip=KILLS_TOOLTIP))
    column.addWidget(
        captioned("Survival", survival_rows(pilot), tooltip=SURVIVAL_TOOLTIP)
    )
    if also is not None:
        column.addWidget(also)
    column.addStretch()
    return column
