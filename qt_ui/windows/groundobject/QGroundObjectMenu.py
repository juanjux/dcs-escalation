"""The location dialog: what stands at an objective, and what the site depends on.

One shape for every location: a header that says what it is and how much of it is
left, a card of units under their groups, and -- for an air-defence site -- the IADS
chain behind it. Buildings keep their own card until that half is redrawn.
"""

from __future__ import annotations

import logging
import math
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from dcs import Point

from game import Game
from game.ato import FlightType
from game.config import REWARDS
from game.cruise_raids import tgo_magazines
from game.data.building_data import FORTIFICATION_BUILDINGS
from game.server import EventStream
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater import ControlPoint, Player, TheaterGroundObject
from game.mfd import band_of, is_manpads, is_mobile, shows_on_mfd
from game.theater.iadsnetwork.iadsexplain import IadsPicture, describe
from game.theater.theatergroundobject import BuildingGroundObject
from game.theater.theatergroup import TheaterUnit
from game.utils import Heading
from qt_ui.models import GameModel
from qt_ui.uiconstants import EVENT_ICONS
from qt_ui.widgets.cards import card, make_transparent
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.groundobject.QBuildingInfo import QBuildingInfo
from qt_ui.windows.groundobject.QGroundObjectBuyMenu import QGroundObjectBuyMenu
from qt_ui.widgets.controls import button
from qt_ui.windows.groundobject.buildingcard import (
    BuildingCard,
    buildings_of,
    repairable_buildings,
    reward_for,
)
from qt_ui.windows.groundobject.common import Compass, two_tone_button
from qt_ui.windows.groundobject.header import LocationHeader
from qt_ui.windows.groundobject.iadscard import IadsCard
from qt_ui.windows.groundobject.unitcard import UnitCard, price_of, repairable_units
from qt_ui.windows.pilot.common import (
    ACCENT,
    Clickable,
    EMPTY,
    GREEN,
    PANEL,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    captioned,
    heading,
    label,
)

WIDTH = 760
MIN_WIDTH = 640

#: Above this many rows the unit card scrolls rather than the dialog growing past the
#: screen. A flattened Patriot battery is twenty-two rows.
ROWS_BEFORE_SCROLLING = 12


class QGroundObjectMenu(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        ground_object: TheaterGroundObject,
        cp: ControlPoint,
        gm: GameModel,
    ) -> None:
        super().__init__(parent)
        self.ground_object = ground_object
        self.cp = cp
        self.game_model = gm
        self.total_value = 0
        self.cruise_missile_rows: list[tuple[str, int]] = []
        self.heading_selector: Optional[QSpinBox] = None
        self.compass: Optional[Compass] = None

        self.setWindowTitle(f"Location — {ground_object.obj_name} ({cp.name})")
        self.setWindowIcon(EVENT_ICONS["capture"])
        self.setMinimumWidth(MIN_WIDTH)
        self.resize(WIDTH, self.height())
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; }}")

        self.column = QVBoxLayout()
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(0)
        self.setLayout(self.column)
        self._build()

    @property
    def game(self) -> Game:
        """There is no location dialog without a campaign behind it."""
        game = self.game_model.game
        assert game is not None
        return game

    # ------------------------------------------------------------------ building

    def _build(self) -> None:
        self._update_total_value()
        self.cruise_missile_rows = self._magazines()
        iads = self._iads()
        self.column.addWidget(LocationHeader(self.ground_object, self.cp, iads))

        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(14)
        if isinstance(self.ground_object, BuildingGroundObject):
            body.addWidget(self._buildings())
            if iads is not None:
                body.addWidget(self._iads_card(iads))
            income = self._income()
            if income is not None:
                body.addWidget(income)
        else:
            body.addWidget(self._units())
            if iads is not None:
                body.addWidget(self._iads_card(iads))
            if self.cruise_missile_rows:
                body.addWidget(self._cruise_missiles())
            body.addWidget(self._heading())
            if self.ground_object.is_iads and not self._friendly:
                body.addWidget(self._mfd_switch())
        body.addStretch()

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(body)
        self.column.addWidget(holder, 1)
        self.column.addWidget(self._footer())
        # Asked for after the content is in: a row of long unit names would otherwise
        # set the width, and the names elide happily.
        self.resize(WIDTH, self.sizeHint().height())

    def _rebuild(self) -> None:
        while self.column.count():
            item = self.column.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
        self._build()

    # --------------------------------------------------------------------- cards

    def _units(self) -> QWidget:
        units = UnitCard(
            self.ground_object,
            self.game.settings,
            self._repair_unit if self._can_repair else None,
        )
        caption = heading("Units")
        if units.folds:
            fold = Clickable("Collapse all" if units.any_open else "Expand all", 11)
            fold.clicked.connect(partial(self._toggle_folds, units, fold))
            _right_of(caption, fold)
        wrecks = repairable_units(self.ground_object) if self._can_repair else []
        if wrecks:
            price = sum(price_of(unit) for unit in wrecks)
            shortcut = Clickable(f"Repair all destroyed · ${price}M", 11, ACCENT)
            shortcut.clicked.connect(self._repair_all)
            # After the stretch the caption ends with, so it sits on the right.
            _right_of(caption, shortcut)

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)
        column.addWidget(caption)
        column.addWidget(self._scrollable(units))
        holder.setLayout(column)
        return holder

    def _iads_card(self, iads: IadsPicture) -> QWidget:
        return captioned("IADS network", IadsCard(iads, self._open_site))

    def _open_site(self, objective: TheaterGroundObject) -> None:
        """Open the location dialog of a site this one is wired to."""
        QGroundObjectMenu(
            self.parentWidget(), objective, objective.control_point, self.game_model
        ).show()

    @staticmethod
    def _toggle_folds(units: UnitCard, control: Clickable) -> None:
        opening = not units.any_open
        units.set_all_open(opening)
        control.setText("Collapse all" if opening else "Expand all")

    def _scrollable(self, inner: QWidget) -> QWidget:
        rows = sum(len(group.units) + 1 for group in self.ground_object.groups)
        if rows <= ROWS_BEFORE_SCROLLING:
            return inner
        area = QScrollArea()
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setFixedHeight(ROWS_BEFORE_SCROLLING * 36)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        make_transparent(area)
        return area

    def _cruise_missiles(self) -> QWidget:
        stack = Stack()
        for name, remaining in self.cruise_missile_rows:
            row = Row(height=36)
            row.add(label(name, 12.5, TEXT_BASE, bold=True))
            row.stretch()
            row.add(label(f"{remaining} left · no rearm", 11.5, TEXT_LABEL))
            stack.append(row)
        stack.refresh()
        return captioned("Cruise missiles", stack)

    def _heading(self) -> QWidget:
        holder = card()
        row = QHBoxLayout()
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        self.compass = Compass(self.ground_object.heading)
        row.addWidget(self.compass)

        self.heading_selector = QSpinBox()
        self.heading_selector.setRange(0, 359)
        self.heading_selector.setWrapping(True)
        self.heading_selector.setSingleStep(5)
        self.heading_selector.setSuffix("°")
        self.heading_selector.setValue(self.ground_object.heading.degrees)
        self.heading_selector.valueChanged.connect(
            lambda degrees: self._rotate(Heading(degrees))
        )
        row.addWidget(self.heading_selector)

        if self._friendly:
            front = (
                self.game.theater.heading_to_conflict_from(self.ground_object.position)
                or self.ground_object.heading
            )
            row.addWidget(
                two_tone_button(
                    "Face the front",
                    f"{front.degrees:03d}°",
                    TEXT_LABEL,
                    handler=partial(self._set_heading, front),
                )
            )
        else:
            self.heading_selector.setEnabled(False)
        row.addWidget(label("steps of 5°", 11, EMPTY))
        row.addStretch()
        holder.setLayout(row)
        return captioned("Heading", holder)

    def _mfd_switch(self) -> QWidget:
        holder = card()
        row = QHBoxLayout()
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        shown = shows_on_mfd(self.ground_object, self.game.settings)
        box = QCheckBox("Shown as a threat in the cockpit")
        box.setChecked(shown)
        box.setEnabled(not is_manpads(self.ground_object))
        box.stateChanged.connect(
            # An explicit answer for this site, which outlives a change to the
            # campaign settings.
            lambda state: setattr(self.ground_object, "hide_on_mfd", not bool(state))
        )
        row.addWidget(box)
        row.addWidget(label(self._mfd_hint(shown), 11, EMPTY))
        row.addStretch()
        holder.setLayout(row)
        return captioned("On the MFD", holder)

    def _mfd_hint(self, shown: bool) -> str:
        """Why the box is where it is, since the campaign settings usually decide."""
        if is_manpads(self.ground_object):
            return "MANPADS are never shown, whatever the campaign asks for"
        if self.ground_object.hide_on_mfd is not None:
            return "set for this site; the campaign setting does not move it"
        band = band_of(self.ground_object).value
        kind = "mobile" if is_mobile(self.ground_object) else "emplaced"
        verb = "shows" if shown else "hides"
        return f"the campaign {verb} {kind} {band} range air defence"

    def _buildings(self) -> QWidget:
        assert isinstance(self.ground_object, BuildingGroundObject)
        card = BuildingCard(
            self.ground_object,
            self.game.settings,
            self._repair_building if self._can_repair else None,
        )
        caption = heading("Buildings")
        wrecks = repairable_buildings(self.ground_object) if self._can_repair else []
        if wrecks:
            price = self.ground_object.repair_cost() * len(wrecks)
            shortcut = Clickable(f"Repair all · ${price:g}M", 11, ACCENT)
            shortcut.clicked.connect(self._repair_all_buildings)
            _right_of(caption, shortcut)

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)
        column.addWidget(caption)
        column.addWidget(card)
        holder.setLayout(column)
        return holder

    def _income(self) -> Optional[QWidget]:  # noqa: D401
        """The two figures the old finances box showed, and what they mean.

        Plus the one a player actually asks: how long a repair takes to pay for itself.
        """
        if not isinstance(self.ground_object, BuildingGroundObject):
            return None
        reward = reward_for(self.ground_object)
        if not reward or not self._friendly:
            return None
        buildings = buildings_of(self.ground_object)
        standing = sum(1 for building in buildings if building.alive)
        price = self.ground_object.repair_cost()

        rows = [
            ("When all standing", f"${len(buildings) * reward:g}M / turn", TEXT_BASE),
            ("Receiving now", f"${standing * reward:g}M / turn", GREEN),
        ]
        if standing < len(buildings) and price > 0:
            turns = math.ceil(price / reward)
            rows.append(
                (
                    "Repair pays back in",
                    f"{turns} turns  (${price:g}M ÷ ${reward:g}M)",
                    TEXT_BASE,
                )
            )

        stack = Stack()
        for name, value, ink in rows:
            row = Row(height=32)
            row.add(label(name, 12, TEXT_LABEL))
            row.stretch()
            row.add(label(value, 12.5, ink, bold=True, monospace=True))
            stack.append(row)
        stack.refresh()
        return captioned("Income", stack)

    def _footer(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName(f"locationFooter{id(self)}")
        holder.setStyleSheet(
            f"#{holder.objectName()} {{ background: {PANEL}; border: none; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(16, 10, 16, 12)
        row.setSpacing(10)

        if self._can_trade and self.total_value > 0:
            row.addWidget(
                two_tone_button(
                    "Disband",
                    f"+${self.total_value}M",
                    "#E8C5C5",
                    kind="danger",
                    handler=self._sell_all,
                )
            )
        row.addStretch()
        row.addWidget(
            label(f"Budget ${self.game.blue.budget:.1f}M", 12, TEXT_LABEL, bold=True)
        )
        if self._can_trade:
            row.addWidget(button("Buy / replace…", handler=self._buy_group))
        row.addWidget(button("Close", "primary", handler=self._close))
        holder.setLayout(row)
        return holder

    # ---------------------------------------------------------------------- data

    def _iads(self) -> Optional[IadsPicture]:
        if not self.ground_object.is_iads:
            return None
        return describe(
            self.ground_object,
            self.game.theater.iads_network,
            awacs=self._awacs_on_station(),
            friendly=self._friendly,
            plugin_enabled=bool(
                self.game.settings.plugin_option_or("skynetiads", True)
            ),
        )

    def _magazines(self) -> list[tuple[str, int]]:
        """What the launchers here have left. Friendly sites only: what the enemy
        holds in its tubes is not intel one click should hand out."""
        if not self._friendly:
            return []
        return tgo_magazines(self.game, self.ground_object)

    def _awacs_on_station(self) -> list[str]:
        """The AEW&C flights the owning side has up, which Skynet counts as radars."""
        names = []
        for package in self.game.ato_for(player=self.cp.captured).packages:
            for flight in package.flights:
                if flight.flight_type is FlightType.AEWC:
                    names.append(f"{flight.unit_type} from {flight.departure.name}")
        return names

    @property
    def _viewer(self) -> Player:
        return Player.BLUE if self.game_model.is_ownfor else Player.RED

    @property
    def _friendly(self) -> bool:
        return self.cp.is_friendly(to_player=self._viewer)

    @property
    def _can_repair(self) -> bool:
        return self.cp.captured.is_blue

    @property
    def _can_trade(self) -> bool:
        """Whether this side's units can be bought and sold at all."""
        if not self.ground_object.purchasable or self.cp.captured.is_neutral:
            return False
        return self.cp.captured.is_blue or self.game.settings.enable_enemy_buy_sell

    def _update_total_value(self) -> None:
        if not self.ground_object.purchasable:
            self.total_value = 0
            return
        self.total_value = self.ground_object.value + self._pending_repair_value()

    def _pending_repair_value(self) -> int:
        return sum(
            price_of(unit)
            for unit in self.ground_object.units
            if not unit.alive and unit.repair_turns_remaining is not None
        )

    # ------------------------------------------------------------------- actions

    def _repair_all_buildings(self) -> None:
        assert isinstance(self.ground_object, BuildingGroundObject)
        price = self.ground_object.repair_cost()
        for building in repairable_buildings(self.ground_object):
            if self.game.blue.budget <= price:
                break
            self._repair_building(building, price, refresh=False)
        self._update_game()

    def _repair_all(self) -> None:
        for unit in repairable_units(self.ground_object):
            price = price_of(unit)
            if self.game.blue.budget <= price:
                break
            self._repair_unit(unit, price, refresh=False)
        self._update_game()

    def _repair_unit(self, unit: TheaterUnit, price: int, refresh: bool = True) -> None:
        if self.game.blue.budget > price:
            self.game.blue.budget -= price
            turns = self.game.settings.ground_object_repair_turns
            if turns == 0:
                self._revive(unit)
                logging.info(f"Repaired unit: {unit.unit_name}")
            else:
                unit.repair_turns_remaining = turns
                logging.info(f"Scheduled unit repair: {unit.unit_name}")
            GameUpdateSignal.get_instance().updateGame(self.game)
        if refresh:
            self._update_game()

    def _repair_building(
        self, unit: TheaterUnit, price: float, refresh: bool = True
    ) -> None:
        if self.game.blue.budget > price:
            self.game.blue.budget -= price
            turns = self.game.settings.building_repair_turns
            if turns == 0:
                self._revive(unit)
                logging.info(f"Repaired building: {unit.unit_name}")
            else:
                unit.repair_turns_remaining = turns
                logging.info(f"Scheduled building repair: {unit.unit_name}")
            GameUpdateSignal.get_instance().updateGame(self.game)
        if refresh:
            self._update_game()

    def _revive(self, unit: TheaterUnit) -> None:
        unit.alive = True
        destroyed = self.game.get_destroyed_units()
        for dead in list(destroyed):
            point = Point(dead["x"], dead["z"], self.game.theater.terrain)
            if point.distance_to_point(unit.position) < 15:
                destroyed.remove(dead)
                logging.info(f"Removed destroyed units {dead}")

    def _set_heading(self, heading: Heading) -> None:  # noqa: D401
        if self.heading_selector is not None:
            self.heading_selector.setValue(heading.degrees)

    def _rotate(self, heading: Heading) -> None:
        self.ground_object.rotate(heading)
        if self.compass is not None:
            self.compass.set_heading(heading)

    def _close(self) -> None:
        self.close()

    def _sell_all(self) -> None:
        self._update_total_value()
        self.ground_object.coalition.budget += self.total_value
        self.ground_object.clear()
        self._update_game()

    def _buy_group(self) -> None:
        self.subwindow = QGroundObjectBuyMenu(
            self, self.ground_object, self.game, self.total_value
        )
        if self.subwindow.exec_():
            self._update_game()

    def _update_game(self) -> None:
        events = GameUpdateEvents()
        events.update_tgo(self.ground_object)
        self.game.theater.iads_network.update_tgo(self.ground_object, events)
        replan_opfor_if_targeted(self.game, self.ground_object, events)
        EventStream.put_nowait(events)
        GameUpdateSignal.get_instance().updateGame(self.game)
        self._rebuild()


def replan_opfor_if_targeted(
    game: Game, ground_object: TheaterGroundObject, events: GameUpdateEvents
) -> None:
    """Replan the enemy if one of its packages was aimed at the site that changed.

    Only the enemy: the player's own plan is theirs to keep, and buying or selling at a
    site is no reason to throw it away. Passing the coalitions themselves here, which
    are always true, replanned both sides and emptied the player's ATO.
    """
    if any(
        package.target == ground_object
        for package in game.ato_for(player=Player.RED).packages
    ):
        game.initialize_turn(events, for_red=True, for_blue=False)


def _right_of(caption: QWidget, widget: QWidget) -> None:
    """Put a control at the right-hand end of a caption row."""
    row = caption.layout()
    assert row is not None
    row.addWidget(widget)
