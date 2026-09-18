"""Air Wing Configuration: three panes, one per question.

Types (what do we fly, and how much), squadrons (what is each one allowed to do, and
where), bases (does it fit). The form this replaces answered the first two and hid the
third at the bottom of a group box, so a base going over capacity -- the commonest
mistake made in this window -- was something you found out later.

The same window opens in two situations that were impossible to tell apart: composing
an air force before a campaign starts, and reaching into a running one with the cheat
switched on. The header says which, in words and in colour, and in cheat mode the extra
controls sit in an amber block so it is obvious which fields are the cheat.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import yaml
import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from dcs.mapping import Point

from game import Game
from game.campaignloader.campaignairwingconfig import (
    DEFAULT_SQUADRON_SIZE,
    CampaignAirWingConfig,
)
from game.coalition import Coalition
from game.dcs.aircrafttype import AircraftType
from game.persistency import airwing_dir
from game.squadrons import Squadron
from game.theater import ControlPoint
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import Segmented, style_button
from .card import SquadronCard
from .common import (
    ACCENT,
    AMBER,
    AirWingConfigParkingTracker,
    BG,
    CHEAT_CHIP_BG,
    CHEAT_HEADER,
    CHEAT_HEADER_LINE,
    CHEAT_HINT,
    GREEN,
    HEADER,
    LINE,
    PANEL,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)
from .panes import AircraftTypeList, BasesPane
from .popups import PresetSquadronSelector, SquadronConfigPopup


def _caption(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"font-size: 10.5px; font-weight: 700; letter-spacing: 1px; color: {TEXT_MUTED};"
    )
    return label


def _secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFixedHeight(30)
    button.setStyleSheet(
        f"QPushButton {{ background: {PANEL}; color: {TEXT_SECONDARY};"
        f" border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 14px;"
        f" font-size: 12px; }}"
        f"QPushButton:hover {{ background: #31424F; }}"
    )
    return button


class SquadronsPane(QWidget):
    """The squadrons of the selected type, one card open at a time."""

    def __init__(self, tab: AirWingConfigurationTab) -> None:
        super().__init__()
        self.tab = tab
        make_transparent(self)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        self.setLayout(column)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        self.title = QLabel()
        self.title.setStyleSheet(
            f"font-size: 10.5px; font-weight: 700; letter-spacing: 1px;"
            f" color: {TEXT_MUTED};"
        )
        header.addWidget(self.title)
        header.addStretch()
        self.add_button = _secondary_button("+ Add squadron…")
        self.add_button.clicked.connect(self.tab.add_squadron)
        header.addWidget(self.add_button)
        column.addLayout(header)

        self.cards_holder = QWidget()
        make_transparent(self.cards_holder)
        self.cards_column = QVBoxLayout()
        # Room on the right for the scrollbar: an open card is taller than the pane,
        # and the bar was sitting on top of the Remove button.
        self.cards_column.setContentsMargins(0, 0, 12, 0)
        self.cards_column.setSpacing(8)
        self.cards_holder.setLayout(self.cards_column)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(self.cards_holder)
        column.addWidget(scroll, stretch=1)

        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        column.addWidget(self.empty)
        self.empty.setVisible(False)

    def show_cards(self, cards: list[SquadronCard], title: str, empty: str) -> None:
        while self.cards_column.count():
            item = self.cards_column.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Hidden first. Taking a card out of the column leaves it without a
                # parent, and a widget with no parent that still has its shown flag is
                # a window on the desktop -- one nothing ever closes, because the pane
                # keeps its cards and puts them back. Changing a squadron's pilot limit
                # rebuilds this column, so one click of the spinner scattered the whole
                # list of them across the screen.
                widget.hide()
                widget.setParent(None)
        for card in cards:
            self.cards_column.addWidget(card)
            card.setVisible(True)
        self.cards_column.addStretch()
        self.title.setText(title)
        self.empty.setText(empty)
        self.empty.setVisible(not cards)


@dataclass(frozen=True)
class SquadronState:
    """What this dialog writes into a squadron before anything is applied.

    Max size, the pilot limit and the cheat's aircraft buttons take effect the moment
    they are touched -- the parking counts and the base pane are drawn from them, so
    they cannot wait for Apply. Discarding therefore has to put them back. The rest of
    the form is only read in apply() and needs nothing.
    """

    squadron: Squadron
    max_size: int
    pilot_limit_override: Optional[int]
    owned_aircraft: int
    untasked_aircraft: int

    @classmethod
    def of(cls, squadron: Squadron) -> SquadronState:
        return cls(
            squadron,
            squadron.max_size,
            squadron.pilot_limit_override,
            squadron.owned_aircraft,
            squadron.untasked_aircraft,
        )

    def restore(self) -> None:
        self.squadron.max_size = self.max_size
        self.squadron.pilot_limit_override = self.pilot_limit_override
        self.squadron.owned_aircraft = self.owned_aircraft
        self.squadron.untasked_aircraft = self.untasked_aircraft


class AirWingConfigurationTab(QWidget):
    """One coalition's wing: its types, its squadrons and its bases."""

    def __init__(
        self,
        coalition: Coalition,
        game: Game,
        aircraft_present: bool,
        cheat: bool = False,
    ) -> None:
        super().__init__()
        self.game = game
        self.coalition = coalition
        self.aircraft_present = aircraft_present
        self.cheat = cheat
        self.base_filter: Optional[ControlPoint] = None
        self.cards: dict[AircraftType, list[SquadronCard]] = defaultdict(list)

        #: Gathers a burst of spinner presses into one pass over the counters. 120 ms
        #: is under what a hand notices and over the interval an auto-repeating arrow
        #: fires at.
        self._counters = QTimer(self)
        self._counters.setSingleShot(True)
        self._counters.setInterval(120)
        self._counters.timeout.connect(self._refresh_counters)

        make_transparent(self)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)
        self.setLayout(row)

        self.parking_tracker = AirWingConfigParkingTracker(
            coalition.air_wing.iter_squadrons()
        )

        #: The wing as the dialog found it, for Discard to put back.
        self._at_open = self._snapshot()

        self.type_list = AircraftTypeList(coalition.air_wing)
        self.type_list.type_selected.connect(self.on_type_selected)
        row.addWidget(self.type_list)

        self.squadrons_pane = SquadronsPane(self)
        row.addWidget(self.squadrons_pane, stretch=1)

        self.bases_pane = BasesPane(
            game.theater.control_points_for(coalition.player),
            self.parking_tracker,
            game.settings.ground_start_ai_planes,
        )
        self.bases_pane.base_selected.connect(self.on_base_selected)
        row.addWidget(self.bases_pane)

        self.build_cards()
        self.on_type_selected(self.type_list.selected_type())

    # --- cards ---------------------------------------------------------------

    def build_cards(self) -> None:
        for cards in self.cards.values():
            for card in cards:
                # Hidden first: a visible widget with no parent is a top-level window,
                # and it stays one until deleteLater runs a turn of the event loop
                # later -- long enough for Windows to flash it on screen.
                card.hide()
                card.setParent(None)
                card.deleteLater()
        self.cards = defaultdict(list)
        for aircraft, squadrons in self.coalition.air_wing.squadrons.items():
            for squadron in squadrons:
                self.cards[aircraft].append(self.new_card(squadron))

    def new_card(self, squadron: Squadron) -> SquadronCard:
        card = SquadronCard(
            self.game,
            self.coalition,
            squadron,
            self.parking_tracker,
            self.aircraft_present,
            self.cheat,
        )
        card.setStyleSheet(
            f"#{card.objectName()} {{ background: {PANEL};"
            f" border: 1px solid {LINE}; border-radius: 4px; }}"
        )
        card.remove_squadron_signal.connect(self.remove_squadron)
        card.expanded.connect(self.on_card_expanded)
        card.changed.connect(self.on_values_changed)
        card.structure_changed.connect(self.on_changed)
        return card

    def on_card_expanded(self, opened: SquadronCard) -> None:
        """One open card per type.

        Per type rather than per dialog: opening a Hornet squadron used to close the
        Warthog one you had open, so going to look at something else and coming back
        left you where you had not been.
        """
        for card in self.cards.get(opened.squadron.aircraft, []):
            if card is not opened:
                card.set_open(False)

    def on_changed(self) -> None:
        """A squadron was added, removed or moved: the three panes are rebuilt."""
        self.type_list.refresh()
        self.bases_pane.refresh()
        self.refresh_squadrons_pane()
        dialog = self.window()
        if isinstance(dialog, AirWingConfigurationDialog):
            dialog.refresh_totals()

    def on_values_changed(self) -> None:
        """A number on a card changed: everything is where it was, so nothing moves.

        Rebuilding the column here took the card out from under the cursor, which is
        why a size spinner only answered the first press of its arrow. The counters
        are the only thing that has to catch up, and they wait for the flurry of
        presses to stop.
        """
        self._counters.start()

    def _refresh_counters(self) -> None:
        # Rebuilding the type list moves its selection, and a selection moving takes
        # the keyboard focus with it -- off the spinner whose arrow key is still
        # being held. Put the focus back where the player left it.
        dialog = self.window()
        # The window's own answer as well as the application's: a window that is not
        # the active one has a focus widget of its own and no application focus.
        focused = QApplication.focusWidget() or dialog.focusWidget()
        self.type_list.refresh()
        self.bases_pane.refresh()
        if isinstance(dialog, AirWingConfigurationDialog):
            dialog.refresh_totals()
        if focused is not None and shiboken6.isValid(focused):
            focused.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- panes ---------------------------------------------------------------

    def on_type_selected(self, aircraft: Optional[AircraftType]) -> None:
        self.bases_pane.set_highlight_type(aircraft)
        self.refresh_squadrons_pane()

    def on_base_selected(self, base: Optional[ControlPoint]) -> None:
        # Click the base you are worried about and the middle pane shows only what is
        # parked there; click it again to see the whole type.
        self.base_filter = None if base is self.base_filter else base
        if self.base_filter is None:
            self.bases_pane.clearSelection()
        self.refresh_squadrons_pane()

    def refresh_squadrons_pane(self) -> None:
        aircraft = self.type_list.selected_type()
        cards = list(self.cards.get(aircraft, [])) if aircraft is not None else []
        if self.base_filter is not None:
            cards = [c for c in cards if c.squadron.location == self.base_filter]
        name = aircraft.display_name.upper() if aircraft is not None else "—"
        title = f"SQUADRONS · {name}"
        if self.base_filter is not None:
            title += f" · AT {self.base_filter.name.upper()}"
        empty = (
            f"No {name} squadron at {self.base_filter.name}."
            if self.base_filter is not None
            else "This coalition flies nothing of this type yet."
        )
        self.squadrons_pane.show_cards(cards, title, empty)
        self.squadrons_pane.add_button.setText("+ Add squadron…")
        self.squadrons_pane.add_button.setToolTip(
            "Any aircraft this faction can field, not only " f"{aircraft.display_name}."
            if aircraft is not None
            else "Any aircraft this faction can field."
        )

    # --- squadrons -----------------------------------------------------------

    def remove_squadron(self, squadron: Squadron) -> None:
        self.parking_tracker.remove_squadron(squadron)
        for aircraft, cards in self.cards.items():
            for card in cards:
                if card.squadron is squadron:
                    cards.remove(card)
                    card.hide()
                    card.setParent(None)
                    card.deleteLater()
                    squadron.coalition.air_wing.unclaim_squadron_def(squadron)
                    self.coalition.air_wing.squadrons[aircraft] = [
                        c.squadron for c in cards
                    ]
                    if not cards:
                        self.coalition.air_wing.squadrons.pop(aircraft, None)
                        self.type_list.refresh()
                    self.on_changed()
                    return

    def add_squadron(self) -> None:
        selected = self.type_list.selected_type()
        bases = list(self.game.theater.control_points_for(self.coalition.player))
        offered: Iterable[Any] = self.coalition.faction.all_aircrafts
        if self.cheat:
            # The faction is what the campaign was built with; a cheat menu is for
            # what it was not. Anything a base here can take is on the list.
            offered = AircraftType.iter_all()
        possible_aircrafts = {
            aircraft
            for aircraft in offered
            if isinstance(aircraft, AircraftType)
            and any(base.can_operate(aircraft) for base in bases)
        }
        popup = SquadronConfigPopup(
            selected.display_name if selected is not None else None,
            possible_aircrafts,
            bases,
            self.coalition.air_wing.squadron_defs,
        )
        if popup.exec_() != QDialog.DialogCode.Accepted:
            return

        selected_type = popup.aircraft_type_selector.currentData()
        selected_base = popup.squadron_base_selector.currentData()
        selected_task = popup.primary_task_selector.selected_task
        selected_def = popup.squadron_def_selector.currentData()

        squadron_def = (
            selected_def
            or self.coalition.air_wing.squadron_def_generator.generate_for_aircraft(
                selected_type
            )
        )
        squadron = Squadron.create_from(
            squadron_def,
            selected_task,
            DEFAULT_SQUADRON_SIZE,
            selected_base,
            self.coalition,
            self.game,
        )
        self.coalition.air_wing.squadrons[selected_type].append(squadron)
        card = self.new_card(squadron)
        self.cards[selected_type].append(card)
        self.type_list.refresh(keep=selected_type)
        self.base_filter = None
        self.on_changed()
        card.set_open(True)
        self.on_card_expanded(card)

    # --- totals and state ----------------------------------------------------

    def totals(self) -> dict[str, int]:
        squadrons = [c.squadron for cards in self.cards.values() for c in cards]
        return {
            "types": len({s.aircraft for s in squadrons}),
            "squadrons": len(squadrons),
            "aircraft": sum(
                s.owned_aircraft if self.cheat else s.max_size for s in squadrons
            ),
            "over": self.bases_pane.bases_over_capacity(),
        }

    def apply(self) -> None:
        wing = self.coalition.air_wing
        wing.squadrons = defaultdict(list)
        for aircraft, cards in self.cards.items():
            if not cards:
                continue
            wing.squadrons[aircraft] = [card.apply() for card in cards]

    def _snapshot(
        self,
    ) -> tuple[dict[AircraftType, list[Squadron]], list[SquadronState]]:
        wing = self.coalition.air_wing
        return (
            {
                aircraft: list(squadrons)
                for aircraft, squadrons in wing.squadrons.items()
            },
            [SquadronState.of(squadron) for squadron in wing.iter_squadrons()],
        )

    def rebuild(self) -> None:
        """Draw the panes again from whatever the wing holds now."""
        self.parking_tracker = AirWingConfigParkingTracker(
            self.coalition.air_wing.iter_squadrons()
        )
        self.bases_pane.parking_tracker = self.parking_tracker
        self.parking_tracker.allocation_changed.connect(self.bases_pane.refresh)
        self.build_cards()
        self.type_list.refresh()
        self.on_changed()

    def discard(self) -> None:
        """Put the wing back the way the dialog found it.

        The panes are not drawn again: discarding closes the dialog, and rebuilding
        every card first is the pause between pressing the button and the window
        going away.
        """
        wing = self.coalition.air_wing
        squadrons, states = self._at_open
        # A squadron added or swapped in while the dialog was open holds a preset.
        # Hand it back, or that preset is gone for the rest of the campaign.
        kept = {state.squadron for state in states}
        for squadron in list(wing.iter_squadrons()):
            if squadron not in kept:
                wing.unclaim_squadron_def(squadron)
        wing.squadrons = defaultdict(
            list, {aircraft: list(group) for aircraft, group in squadrons.items()}
        )
        for state in states:
            state.restore()
            wing.claim_squadron_def(state.squadron)


class AirWingConfigurationDialog(QDialog):
    """Dialog window for air wing configuration."""

    def __init__(
        self, game: Game, aircraft_present: bool, parent: Any, cheat: bool = False
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.cheat = cheat
        # Wide enough for an open card: 300 of types, 300 of form and the chips
        # beside it, 300 of bases, and the gaps between them.
        self.setMinimumSize(1300, 780)
        self.resize(1420, 880)
        self.setWindowTitle("Air Wing Configuration")
        # The app stylesheet gives every QWidget -- labels included -- a background
        # colour, so each label painted a blue-grey box of its own over whatever it sat
        # on. Over the cheat header that reads as mud. A label that wants a background
        # (the task chip, the CHEAT chip) sets its own, and its own stylesheet wins.
        self.setStyleSheet(
            f"QDialog {{ background: {BG}; }} QLabel {{ background: transparent; }}"
        )

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.setLayout(column)

        self.tabs: list[AirWingConfigurationTab] = []
        self.by_coalition: dict[Coalition, AirWingConfigurationTab] = {}
        for coalition in game.coalitions:
            tab = AirWingConfigurationTab(coalition, game, aircraft_present, cheat)
            self.tabs.append(tab)
            self.by_coalition[coalition] = tab

        column.addWidget(self._build_header())

        self.body = QWidget()
        make_transparent(self.body)
        body_column = QVBoxLayout()
        body_column.setContentsMargins(20, 18, 20, 0)
        body_column.setSpacing(0)
        self.body.setLayout(body_column)
        for tab in self.tabs:
            body_column.addWidget(tab)
            tab.setVisible(False)
        self.tabs[0].setVisible(True)
        self.current = self.tabs[0]
        column.addWidget(self.body, stretch=1)

        column.addWidget(self._build_footer())
        self.refresh_totals()

    # --- header --------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("awcHeader")
        header.setFixedHeight(72)
        if self.cheat:
            header.setStyleSheet(
                f"#awcHeader {{ background: {CHEAT_HEADER};"
                f" border-bottom: 1px solid {CHEAT_HEADER_LINE}; }}"
            )
        else:
            header.setStyleSheet(
                f"#awcHeader {{ background: {PANEL};"
                f" border-bottom: 1px solid {LINE}; }}"
            )
        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(20)
        header.setLayout(row)

        text = QVBoxLayout()
        text.setSpacing(3)
        line1 = QHBoxLayout()
        line1.setSpacing(8)
        chip = QLabel(
            f"CHEAT · TURN {self.game.turn}" if self.cheat else "NEW CAMPAIGN"
        )
        chip.setStyleSheet(
            (
                f"background: {CHEAT_CHIP_BG}; color: {AMBER};"
                if self.cheat
                else f"background: #22384A; color: {ACCENT};"
            )
            + " border-radius: 4px; padding: 2px 8px; font-size: 10px;"
            " font-weight: 700; letter-spacing: 0.8px;"
        )
        chip.setFixedHeight(18)
        line1.addWidget(chip)
        title = QLabel(
            "Editing a running campaign" if self.cheat else "Compose the air wing"
        )
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {TEXT_PRIMARY};"
        )
        line1.addWidget(title)
        line1.addStretch()
        text.addLayout(line1)
        hint = QLabel(
            "Changes apply to live squadrons. Aircraft added here are free; "
            "relocations happen instantly, pilots and inventory are kept."
            if self.cheat
            else "Nothing is placed yet — the squadrons below are the campaign's "
            "defaults; edit, add or remove freely."
        )
        hint.setStyleSheet(
            f"font-size: 12px; color: {CHEAT_HINT if self.cheat else TEXT_TERTIARY};"
        )
        text.addWidget(hint)
        row.addLayout(text)
        row.addStretch()

        # Just the side: a faction name runs to "WRL - Task Force Blue", which no
        # button in a header is going to hold. The name is the tooltip and the hint
        # line under the title already names the campaign.
        self.coalition_switch = Segmented(
            [
                ("Blue" if tab.coalition.player.is_blue else "Red", tab)
                for tab in self.tabs
            ],
            current=self.tabs[0],
        )
        for index, tab in enumerate(self.tabs):
            button = self.coalition_switch.group.button(index)
            if button is not None:
                button.setToolTip(tab.coalition.faction.name)
        self.coalition_switch.selection_changed.connect(self.show_tab)
        self.coalition_switch.setFixedWidth(170)
        row.addWidget(self.coalition_switch)

        self.totals_row = QHBoxLayout()
        self.totals_row.setSpacing(18)
        self.total_labels: dict[str, QLabel] = {}
        for key, label in (
            ("types", "TYPES"),
            ("squadrons", "SQUADRONS"),
            ("aircraft", "AIRCRAFT"),
            ("parking", "PARKING"),
        ):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            caption = _caption(label)
            value = QLabel("—")
            value.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 20px;"
                f" font-weight: 600; color: {TEXT_PRIMARY};"
            )
            cell.addWidget(caption)
            cell.addWidget(value)
            self.total_labels[key] = value
            self.totals_row.addLayout(cell)
        row.addLayout(self.totals_row)
        return header

    def show_tab(self, tab: AirWingConfigurationTab) -> None:
        for candidate in self.tabs:
            candidate.setVisible(candidate is tab)
        self.current = tab
        self.refresh_totals()

    def refresh_totals(self) -> None:
        totals = self.current.totals()
        self.total_labels["types"].setText(str(totals["types"]))
        self.total_labels["squadrons"].setText(str(totals["squadrons"]))
        self.total_labels["aircraft"].setText(str(totals["aircraft"]))
        over = totals["over"]
        parking = self.total_labels["parking"]
        if over:
            parking.setText(f"{over} over")
            parking.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 20px;"
                f" font-weight: 600; color: {RED};"
            )
        else:
            parking.setText("OK")
            parking.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 20px;"
                f" font-weight: 600; color: {GREEN};"
            )
        if hasattr(self, "status_label"):
            plural = "base" if over == 1 else "bases"
            self.status_label.setText(
                f"▲ {over} {plural} over capacity — you can still continue"
                if over
                else ""
            )
            self.status_label.setStyleSheet(f"font-size: 12px; color: {AMBER};")

    # --- footer --------------------------------------------------------------

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("awcFooter")
        footer.setFixedHeight(60)
        footer.setStyleSheet(
            f"#awcFooter {{ background: {HEADER}; border-top: 1px solid {LINE}; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(20, 10, 20, 12)
        row.setSpacing(10)
        footer.setLayout(row)

        preset = QVBoxLayout()
        preset.setSpacing(2)
        preset.addWidget(_caption("Preset"))
        preset_buttons = QHBoxLayout()
        preset_buttons.setSpacing(6)
        load = _secondary_button("Load…")
        load.clicked.connect(self.load_config)
        preset_buttons.addWidget(load)
        save = _secondary_button("Save as…")
        save.clicked.connect(self.save_config)
        preset_buttons.addWidget(save)
        preset.addLayout(preset_buttons)
        row.addLayout(preset)
        row.addStretch()

        self.status_label = QLabel()
        row.addWidget(self.status_label)

        reset = style_button(
            QPushButton("Discard changes" if self.cheat else "Reset changes"),
            "danger",
        )
        reset.setFixedHeight(32)
        reset.clicked.connect(self.revert)
        row.addWidget(reset)
        row.addSpacing(16)

        primary = QPushButton(
            # Doubled: a single "&" in a button label is a keyboard mnemonic.
            "Apply to campaign"
            if self.cheat
            else "Accept && start campaign"
        )
        primary.setFixedHeight(32)
        primary.setStyleSheet(
            (
                f"QPushButton {{ background: {AMBER}; color: #2A1F12;"
                if self.cheat
                else f"QPushButton {{ background: {ACCENT}; color: #0F1922;"
            )
            + " border: none; border-radius: 3px; padding: 0 18px;"
            " font-size: 12px; font-weight: 600; }"
        )
        primary.clicked.connect(self.accept)
        row.addWidget(primary)
        return footer

    # --- presets on disk ------------------------------------------------------

    def save_config(self) -> None:
        result = QMessageBox.information(
            None,
            "Save Air Wing?",
            "Revert will not be possible after saving a different Air Wing.<br />"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.No:
            return

        awd = airwing_dir()
        fd = QFileDialog(
            caption="Save Air Wing", directory=str(awd), filter="*.yaml;*.yml"
        )
        fd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        if fd.exec_():
            for tab in self.tabs:
                tab.apply()
            airwing = self._build_air_wing()
            filename = fd.selectedFiles()[0]
            with open(filename, "w") as f:
                f.write(yaml.dump(airwing))

    def _build_air_wing(self) -> dict:
        wing = self.current.coalition.air_wing
        squadrons: dict[Any, list[dict[str, Any]]] = {}
        for ac, sqs in wing.squadrons.items():
            for s in sqs:
                cp = s.location.at
                if isinstance(cp, Point):
                    key = s.location.full_name
                else:
                    key = cp.id
                name = (
                    s.name
                    if s.name in [x.name for x in wing.squadron_defs[ac]]
                    else s.aircraft.variant_id
                )
                entry = {
                    "primary": s.primary_task.value,
                    "secondary": [
                        sec.value
                        for sec in s.auto_assignable_mission_types
                        if sec.value != s.primary_task.value
                    ],
                    "aircraft": [name],
                    "aircraft_type": s.aircraft.display_name,
                    "size": s.max_size,
                }
                if squadrons.get(key):
                    squadrons[key].append(entry)
                else:
                    squadrons[key] = [entry]
        return squadrons

    def load_config(self) -> None:
        result = QMessageBox.information(
            None,
            "Load Air Wing?",
            "Revert will not be possible after loading a different Air Wing.<br />"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.No:
            return

        awd = airwing_dir()
        fd = QFileDialog(
            caption="Load Air Wing", directory=str(awd), filter="*.yaml;*.yml"
        )
        if fd.exec_():
            filename = fd.selectedFiles()[0]
            with open(filename, "r") as f:
                airwing = yaml.safe_load(f)
                self._construct_air_wing_tab(airwing)

    def _construct_air_wing_tab(self, airwing: dict[str, Any]) -> None:
        tab = self.current
        c = tab.coalition
        for s in c.air_wing.squadrons.values():
            for squadron in s:
                c.air_wing.unclaim_squadron_def(squadron)
        c.air_wing.squadrons = defaultdict(list)
        config = CampaignAirWingConfig.from_campaign_data(airwing, c.game.theater)
        c.configure_default_air_wing(config)
        tab.rebuild()
        if c.game.turn != 0:
            from game.server import EventStream
            from game.sim.gameupdateevents import GameUpdateEvents

            events = GameUpdateEvents()
            c.initialize_turn(False, events)
            EventStream.put_nowait(events)

    # --- window ---------------------------------------------------------------

    def revert(self) -> None:
        """Discard everything and leave.

        The button beside this one applies and closes, so this one closes too: an
        exit that leaves the window open reads as though nothing happened.
        """
        result = QMessageBox.question(
            self,
            "Discard changes?",
            "Put every squadron back the way it was and close?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        for tab in self.tabs:
            tab.discard()
        # QDialog's own reject: the override asks whether to keep the changes, which
        # is the question that was just answered.
        super().reject()

    def accept(self) -> None:
        for tab in self.tabs:
            tab.apply()
            # Local truco: when the Air Wing cheat is used mid-campaign, DON'T re-init
            # the turn -- initialize_turn() clears the ATO and re-plans (blue) / empties
            # (red) the packages. Keep the existing plan; the player re-plans by hand.
            # The wing changes are still applied via tab.apply(). (Turn 0 already skips
            # this.)
            if tab.coalition.game.turn != 0 and not self.cheat:
                from game.server import EventStream
                from game.sim.gameupdateevents import GameUpdateEvents

                events = GameUpdateEvents()
                tab.coalition.initialize_turn(False, events)
                EventStream.put_nowait(events)
        super().accept()

    def reject(self) -> None:
        """Closing the window is a question, not a discard.

        "Are you sure you want to discard your changes? Yes / No" asks you to answer a
        question about a question. Keep and Discard are the two things that can happen.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Close Air Wing Configuration")
        box.setText("Keep the changes you have made?")
        keep = box.addButton("Keep", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        keep.setStyleSheet(
            (
                f"background: {AMBER}; color: #2A1F12;"
                if self.cheat
                else f"background: {ACCENT}; color: #0F1922;"
            )
            + " border: none; border-radius: 3px; padding: 6px 18px;"
            " font-weight: 600;"
        )
        style_button(discard, "danger")
        box.setDefaultButton(keep)
        box.exec_()
        if box.clickedButton() is discard:
            super().reject()
        else:
            self.accept()


__all__ = ["AirWingConfigurationDialog", "PresetSquadronSelector"]
