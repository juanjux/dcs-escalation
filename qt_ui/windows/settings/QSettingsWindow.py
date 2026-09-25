import json
import logging
import os
import textwrap
import zipfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from PySide6 import QtWidgets
from PySide6.QtCore import QItemSelectionModel, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import qt_ui.uiconstants as CONST
from game.game import Game
from game.theater import Player
from game.persistency import settings_dir
from game.server import EventStream
from game.settings import (
    BooleanOption,
    BoundedFloatOption,
    BoundedIntOption,
    ChoicesOption,
    MinutesOption,
    OptionDescription,
    Settings,
    TextOption,
)
from game.settings.ISettingsContainer import SettingsContainer
from game.settings.settings import (
    LIVE_PILOTS_FRIENDSHIP_SECTION,
    LIVE_PILOTS_HARDENING_SECTION,
    LIVE_PILOTS_MORALE_EVENTS_SECTION,
    LIVE_PILOTS_MORALE_STATES_SECTION,
    LIVE_PILOTS_MORALE_SECTION,
    LIVE_PILOTS_RANKS_SECTION,
    LIVE_PILOTS_SURVIVAL_SECTION,
    LIVE_PILOTS_PAGE,
    OPFOR_AI_SECTION,
)
from game.squadrons.pilotranks import RANK_NAMES_CUSTOM, ranks_for
from game.weather.cloudpresetpacks import apply_cloud_preset_pack
from game.sim import GameUpdateEvents
from qt_ui.widgets.QLabeledWidget import QLabeledWidget
from qt_ui.widgets.gearbutton import gear_button
from qt_ui.widgets.controls import style_button
from qt_ui.widgets.spinsliders import FloatSpinSlider, TimeInputs
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.settings.plugins import PluginsPage

#: Label, control, then slack. Without a column to send the leftovers to, a wide
#: dialog pushes every switch out to its right-hand edge.
SLACK_COLUMN = 2

#: Rank, short name, full name and price, and then the ladder's own slack.
RANK_PRICE_COLUMN = 3
RANK_SLACK_COLUMN = 4

#: The dialog's own list of pages, and the search results that replace it.
CATEGORY_LIST_WIDTH = 175

#: The morale bands are set by a ladder rather than a row each, so the layout picks
#: them out of the box they are declared in.
MORALE_STATE_PREFIX = "morale_state_"


class CheatSettingsBox(QGroupBox):
    def __init__(
        self, sc: SettingsContainer, apply_settings: Callable[[], None]
    ) -> None:
        super().__init__("Cheat Settings")
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Frontline
        self.frontline_cheat_checkbox = QCheckBox()
        self.frontline_cheat_checkbox.setChecked(sc.settings.enable_frontline_cheats)
        self.frontline_cheat_checkbox.toggled.connect(apply_settings)
        self.frontline_cheat = QLabeledWidget(
            "Enable Frontline Cheats:", self.frontline_cheat_checkbox
        )
        self.main_layout.addLayout(self.frontline_cheat)

        # Base capture
        self.base_capture_cheat_checkbox = QCheckBox()
        self.base_capture_cheat_checkbox.setChecked(
            sc.settings.enable_base_capture_cheat
        )
        self.base_capture_cheat_checkbox.toggled.connect(apply_settings)
        self.base_capture_cheat = QLabeledWidget(
            "Enable Base Capture Cheat:", self.base_capture_cheat_checkbox
        )
        self.main_layout.addLayout(self.base_capture_cheat)

        # Runway state
        self.base_runway_state_cheat_checkbox = QCheckBox()
        self.base_runway_state_cheat_checkbox.setChecked(
            sc.settings.enable_runway_state_cheat
        )
        self.base_runway_state_cheat_checkbox.toggled.connect(apply_settings)
        self.main_layout.addLayout(
            QLabeledWidget(
                "Enable Runway State Cheat:", self.base_runway_state_cheat_checkbox
            )
        )

        # Instant transfer
        self.transfer_cheat_checkbox = QCheckBox()
        self.transfer_cheat_checkbox.setChecked(sc.settings.enable_transfer_cheat)
        self.transfer_cheat_checkbox.toggled.connect(apply_settings)
        self.transfer_cheat = QLabeledWidget(
            "Enable Instant Squadron Transfer Cheat:", self.transfer_cheat_checkbox
        )
        self.main_layout.addLayout(self.transfer_cheat)

        # Air wing adjustments
        self.air_wing_adjustments_checkbox = QCheckBox()
        self.air_wing_adjustments_checkbox.setChecked(
            sc.settings.enable_air_wing_adjustments
        )
        self.air_wing_adjustments_checkbox.toggled.connect(apply_settings)
        self.air_wing_cheat = QLabeledWidget(
            "Enable Air Wing adjustments:", self.air_wing_adjustments_checkbox
        )
        self.main_layout.addLayout(self.air_wing_cheat)

        # What may be done to one pilot: rename, promote, heal, revive.
        self.pilot_cheats_checkbox = QCheckBox()
        self.pilot_cheats_checkbox.setChecked(sc.settings.enable_pilot_cheats)
        self.pilot_cheats_checkbox.toggled.connect(apply_settings)
        self.pilot_cheat = QLabeledWidget(
            "Enable pilot cheats:", self.pilot_cheats_checkbox
        )
        self.main_layout.addLayout(self.pilot_cheat)

        # Everything at one location, destroyed or brought back from its window.
        self.location_cheat_checkbox = QCheckBox()
        self.location_cheat_checkbox.setChecked(sc.settings.enable_location_cheat)
        self.location_cheat_checkbox.toggled.connect(apply_settings)
        self.main_layout.addLayout(
            QLabeledWidget(
                "Enable Location Destroy/Revive Cheat:", self.location_cheat_checkbox
            )
        )

        # Buy/Sell actions for OPFOR
        self.opfor_buysell_checkbox = QCheckBox()
        self.opfor_buysell_checkbox.setChecked(sc.settings.enable_enemy_buy_sell)
        self.opfor_buysell_checkbox.toggled.connect(apply_settings)
        self.redfor_buysell_cheat = QLabeledWidget(
            "Enable OPFOR Buy/Sell actions Cheat:", self.opfor_buysell_checkbox
        )
        self.main_layout.addLayout(self.redfor_buysell_cheat)

    @property
    def show_frontline_cheat(self) -> bool:
        return self.frontline_cheat_checkbox.isChecked()

    @property
    def show_base_capture_cheat(self) -> bool:
        return self.base_capture_cheat_checkbox.isChecked()

    @property
    def show_transfer_cheat(self) -> bool:
        return self.transfer_cheat_checkbox.isChecked()

    @property
    def enable_runway_state_cheat(self) -> bool:
        return self.base_runway_state_cheat_checkbox.isChecked()

    @property
    def enable_air_wing_cheats(self) -> bool:
        return self.air_wing_adjustments_checkbox.isChecked()

    @property
    def enable_pilot_cheats(self) -> bool:
        return self.pilot_cheats_checkbox.isChecked()

    @property
    def enable_redfor_buysell(self) -> bool:
        return self.opfor_buysell_checkbox.isChecked()

    @property
    def enable_location_cheat(self) -> bool:
        return self.location_cheat_checkbox.isChecked()


class AutoSettingsLayout(QGridLayout):
    def __init__(
        self,
        page: str,
        section: str,
        sc: SettingsContainer,
        write_full_settings: Callable[[], None],
        subsection: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.page = page
        self.section = section
        #: When set, this lays out one box within the section rather than the section.
        self.subsection = subsection
        self.sc = sc
        self.write_full_settings = write_full_settings
        self.settings_map: Dict[str, QWidget] = {}
        self.label_map: Dict[str, QWidget] = {}
        #: For a setting that is more than one widget -- a switch with a gear beside
        #: it -- what to show, hide and grey out as a whole.
        self.cell_map: Dict[str, QWidget] = {}
        #: The boxes within this section, each laying itself out.
        self.boxes: List["AutoSettingsLayout"] = []
        #: Set by the page once every group exists. A setting can hide one in
        #: another group, so a change here has to re-evaluate the whole page.
        self.on_settings_changed: Optional[Callable[[], None]] = None
        #: Extra work a hand-built section needs doing whenever a value changes.
        self.refresh_hooks: List[Callable[[], None]] = []
        self._rank_rows: List[Tuple[QLineEdit, QLineEdit]] = []
        self._rank_names: List[Tuple[str, str]] = []
        self._rank_prices: List[Tuple[str, QSpinBox]] = []
        self._rank_labels: List[QLabel] = []
        self._rank_combo_label: Optional[QLabel] = None

        self.init_ui()

    def init_ui(self):
        if self.section == LIVE_PILOTS_RANKS_SECTION:
            self._build_rank_grid()
            self._settle(RANK_SLACK_COLUMN)
            return
        row = 0
        for name, description in self.own_fields():
            if name.startswith(MORALE_STATE_PREFIX):
                continue  # laid out as a ladder below, not as a row of its own
            self.label_map[name] = self.add_label(row, description)
            if isinstance(description, BooleanOption):
                self.add_checkbox_for(row, name, description)
            elif isinstance(description, ChoicesOption):
                self.add_combobox_for(row, name, description)
            elif isinstance(description, BoundedFloatOption):
                self.add_float_spin_slider_for(row, name, description)
            elif isinstance(description, BoundedIntOption):
                self.add_spinner_for(row, name, description)
            elif isinstance(description, MinutesOption):
                self.add_duration_controls_for(row, name, description)
            elif isinstance(description, TextOption):
                self.add_line_edit_for(row, name, description)
            else:
                raise TypeError(f"Unhandled option type: {description}")
            row += 1
        if self.subsection == LIVE_PILOTS_MORALE_STATES_SECTION:
            self._build_morale_state_ladder()
        self._build_boxes()
        self.apply_visibility()
        if self.section == OPFOR_AI_SECTION:
            self._wire_opfor_ai()
        if self.page == LIVE_PILOTS_PAGE:
            self._wire_live_pilots_master()
        if self.section == LIVE_PILOTS_MORALE_SECTION:
            # Everything here, boxes included, is a detail of morale being on -- and
            # of Live Pilots, or this would hand back what the master just took.
            self._wire_enabled(
                [name for name in self.settings_map if name != "morale_enabled"],
                lambda settings: settings.live_pilots_enabled
                and getattr(settings, "morale_enabled", True),
            )
        if self.section == LIVE_PILOTS_HARDENING_SECTION:
            # It is earned from the morale bands and most of what it does is to
            # morale, so it follows morale as well as Live Pilots.
            morale_on = lambda settings: settings.live_pilots_enabled and getattr(
                settings, "morale_enabled", True
            )
            self._wire_enabled(["hardening_enabled"], morale_on)
            self._wire_enabled(
                [name for name in self.settings_map if name != "hardening_enabled"],
                lambda settings: morale_on(settings)
                and getattr(settings, "hardening_enabled", True),
            )
        if self.section == LIVE_PILOTS_FRIENDSHIP_SECTION:
            # As with morale: the whole section is a detail of the switch at the top
            # of it, and of Live Pilots.
            self._wire_enabled(
                [name for name in self.settings_map if name != "friendship_enabled"],
                lambda settings: settings.live_pilots_enabled
                and getattr(settings, "friendship_enabled", True),
            )
        if self.section == LIVE_PILOTS_SURVIVAL_SECTION:
            self._wire_survival_odds()
        self._settle()

    def own_fields(self) -> Iterable[Tuple[str, OptionDescription]]:
        return Settings.fields(self.page, self.section, self.subsection)

    def control_for(self, name: str) -> Optional[QWidget]:
        """What to grey out for this setting: its whole cell where it has one."""
        return self.cell_map.get(name) or self.settings_map.get(name)

    def _build_boxes(self) -> None:
        """The section's own boxes, each a grid of its own, after its plain rows.

        Their widgets are folded into this layout's maps so everything that greys a
        section out, or reads it back from the settings, keeps working unchanged.
        """
        if self.subsection is not None:
            return  # one level of nesting is a box; two is a filing cabinet
        for name in Settings.subsections(self.page, self.section):
            layout = AutoSettingsLayout(
                self.page, self.section, self.sc, self.write_full_settings, name
            )
            layout.on_settings_changed = self.settings_changed
            box = QGroupBox(name)
            # Its own frame, drawn explicitly: the section above it is frameless and
            # anything it says about borders would otherwise be inherited. The top
            # margin keeps the caption off the first row, which in the morale box had
            # "Lost his aircraft" wearing the title.
            box.setObjectName("settingsBox")
            box.setStyleSheet(
                "QGroupBox#settingsBox { border: 1px solid palette(mid);"
                " border-radius: 4px; margin-top: 14px; padding: 12px 8px 8px 8px; }"
                "QGroupBox#settingsBox::title { subcontrol-origin: margin;"
                " subcontrol-position: top left; left: 10px; padding: 0 4px; }"
            )
            box.setLayout(layout)
            self.addWidget(box, self.rowCount(), 0, 1, SLACK_COLUMN + 1)
            self.boxes.append(layout)
            self.settings_map.update(layout.settings_map)
            self.label_map.update(layout.label_map)
            self.cell_map.update(layout.cell_map)

    #: What the controls column is at least. Its width otherwise comes from the
    #: widest control in the section, so a section with a single checkbox in it put
    #: that checkbox hard against its label while every other page had a rail.
    CONTROL_COLUMN_WIDTH = 340

    def _settle(self, stretch_column: int = SLACK_COLUMN) -> None:
        """Send the slack to the bottom and the right, not between the rows.

        A grid given more room than it needs shares it out among its rows and
        columns, which on a tall dialog with four settings on it puts a hand's width
        between one row and the next, and the switches out at the far edge of the
        window. The boxes span the slack column so they still fill the width.
        """
        self.setRowStretch(self.rowCount(), 1)
        self.setColumnStretch(stretch_column, 1)
        if self.subsection is None and stretch_column == SLACK_COLUMN:
            self.setColumnMinimumWidth(1, self.CONTROL_COLUMN_WIDTH)

    def _build_rank_grid(self) -> None:
        """The rank ladder: five rungs, short and full form side by side.

        Not one setting per row like every other section. Ten rows reading "Cadet
        (short)", "Cadet (full)" is a form to fill in; a rung per row under two column
        headings is a ladder you can read down.
        """
        row = 0
        for name, description in Settings.fields(self.page, self.section):
            if isinstance(description, ChoicesOption):
                # The naming choice belongs at the head of the ladder it names.
                self._rank_combo_label = self.add_label(row, description)
                self.label_map[name] = self._rank_combo_label
                self.add_combobox_for(row, name, description)
                self._rank_combo = self.settings_map[name]
                self.removeWidget(self._rank_combo)
                self.addWidget(self._rank_combo, row, 1, 1, 2)
                row += 1
                continue
            if not name.endswith("_short"):
                continue
            if not self._rank_rows:
                for column, heading in (
                    (1, "Short"),
                    (2, "Full"),
                    (RANK_PRICE_COLUMN, "XP to reach"),
                ):
                    header = QLabel(f"<b>{heading}</b>")
                    self.addWidget(header, row, column)
                    self._rank_labels.append(header)
                row += 1
            full_name = name[: -len("_short")] + "_full"
            label = QLabel(f"<strong>{description.text}</strong>")
            self.addWidget(label, row, 0)
            # One label serves both boxes, so both names have to find it.
            self.label_map[name] = label
            self.label_map[full_name] = label
            self._rank_labels.append(label)

            max_length = getattr(description, "max_length", None)
            short = self._rank_edit(name, 60, max_length)
            full = self._rank_edit(full_name, 156)
            self.addWidget(short, row, 1)
            self.addWidget(full, row, 2)
            self._rank_rows.append((short, full))
            self._rank_names.append((name, full_name))
            self._add_rank_price(row, name[: -len("_short")] + "_xp")
            row += 1

        self.setColumnStretch(RANK_SLACK_COLUMN, 1)
        self.refresh_hooks.append(self._sync_rank_boxes)
        self.refresh_hooks.append(self._sync_rank_prices)
        self._sync_rank_boxes()
        self._sync_rank_prices()

    def _add_rank_price(self, row: int, name: str) -> None:
        """What this rung costs. Editable whoever is naming the ranks.

        The names are a preview of somebody else's ladder unless they are the custom
        ones; the prices are always the campaign's own, so they never grey out with
        the boxes beside them.
        """
        if name not in self.sc.settings.__dict__:
            # Cadet: where every pilot starts, so it has no price to set.
            self.addWidget(QLabel("<i>start</i>"), row, RANK_PRICE_COLUMN)
            return
        spinner = QSpinBox()
        spinner.setRange(0, 1000000)
        spinner.setSingleStep(100)
        spinner.setFixedWidth(110)
        spinner.setValue(int(self.sc.settings.__dict__[name]))
        spinner.valueChanged.connect(
            lambda value, key=name: self._set_rank_price(key, value)
        )
        self.addWidget(spinner, row, RANK_PRICE_COLUMN)
        self.settings_map[name] = spinner
        self._rank_prices.append((name, spinner))

    def _set_rank_price(self, name: str, value: int) -> None:
        self.sc.settings.__dict__[name] = value
        self._sync_rank_prices()
        self.settings_changed()

    def _sync_rank_prices(self) -> None:
        """Keep the prices a ladder: no rung may cost less than the one below it."""
        if not self._rank_prices:
            return
        prices = [int(self.sc.settings.__dict__[name]) for name, _ in self._rank_prices]
        live = bool(self.sc.settings.live_pilots_enabled)
        for index, (name, spinner) in enumerate(self._rank_prices):
            below = prices[index - 1] + 1 if index else 1
            above = prices[index + 1] - 1 if index + 1 < len(prices) else 1000000
            low, high = min(below, above), max(below, above)
            value = max(low, min(high, prices[index]))
            if value != prices[index]:
                self.sc.settings.__dict__[name] = value
            spinner.blockSignals(True)
            spinner.setRange(low, high)
            spinner.setValue(value)
            spinner.blockSignals(False)
            spinner.setEnabled(live)

    def _build_morale_state_ladder(self) -> None:
        """What the player is told instead of a number, and where each band starts.

        A row per band, with the span it covers written out beside it, because the
        thing being set is a boundary and a boundary is only legible next to the one
        above it. The bottom band has no setting: it is the bottom of the scale.
        """
        from game.squadrons.morale import MORALE_MAX, MORALE_MIN, MORALE_STATES

        row = self.rowCount()
        caption = QLabel(
            "What each band is called and where it starts. A Triumphant pilot flies "
            "one rung above his rank; a Shattered or Broken one, a rung below it."
        )
        caption.setWordWrap(True)
        self.addWidget(caption, row, 0, 1, SLACK_COLUMN + 1)
        row += 1

        self._morale_state_rows: List[Tuple[str, QSpinBox, QLabel]] = []
        for state in MORALE_STATES:
            label = QLabel(f"<strong>{state.name}</strong>")
            self.addWidget(label, row, 0)
            span = QLabel()
            if state.key is None:
                span.setText(f"{MORALE_MIN} only")
                self.addWidget(span, row, 1)
                self._morale_state_span_bottom = span
            else:
                spinner = QSpinBox()
                spinner.setMinimum(MORALE_MIN)
                spinner.setMaximum(MORALE_MAX)
                spinner.setValue(int(self.sc.settings.__dict__[state.key]))
                spinner.setFixedWidth(70)
                spinner.valueChanged.connect(
                    lambda value, key=state.key: self._set_morale_floor(key, value)
                )
                cell = QWidget()
                line = QHBoxLayout(cell)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(8)
                line.addWidget(spinner)
                line.addWidget(span, 1)
                self.addWidget(cell, row, 1, 1, SLACK_COLUMN)
                self.settings_map[state.key] = spinner
                self.label_map[state.key] = label
                self._morale_state_rows.append((state.key, spinner, span))
            row += 1

        self.refresh_hooks.append(self._sync_morale_states)
        self._sync_morale_states()

    def _set_morale_floor(self, key: str, value: int) -> None:
        self.sc.settings.__dict__[key] = value
        self._sync_morale_states()
        self.settings_changed()

    def _sync_morale_states(self) -> None:
        """Keep the ladder a ladder: no band may start below the one under it."""
        from game.squadrons.morale import MORALE_MAX, MORALE_MIN

        rows = getattr(self, "_morale_state_rows", [])
        if not rows:
            return
        floors = [int(self.sc.settings.__dict__[key]) for key, _, _ in rows]
        for index, (key, spinner, span) in enumerate(rows):
            below = floors[index + 1] + 1 if index + 1 < len(floors) else MORALE_MIN + 1
            above = floors[index - 1] - 1 if index else MORALE_MAX
            spinner.blockSignals(True)
            spinner.setMinimum(min(below, above))
            spinner.setMaximum(max(below, above))
            spinner.setValue(floors[index])
            spinner.blockSignals(False)
            top = floors[index - 1] - 1 if index else MORALE_MAX
            span.setText(f"to {top}" if top > floors[index] else "only")
        bottom = getattr(self, "_morale_state_span_bottom", None)
        if bottom is not None:
            top = floors[-1] - 1
            bottom.setText(f"to {top}" if top > MORALE_MIN else f"{MORALE_MIN} only")

    def _rank_edit(
        self, name: str, width: int, max_length: Optional[int] = None
    ) -> QLineEdit:
        edit = QLineEdit(self.sc.settings.__dict__[name])
        if max_length is not None:
            edit.setMaxLength(max_length)
        edit.setFixedWidth(width)

        def on_changed(value: str) -> None:
            self.sc.settings.__dict__[name] = value.strip()

        edit.textChanged.connect(on_changed)
        self.settings_map[name] = edit
        return edit

    def _sync_rank_boxes(self) -> None:
        """Show the ladder the chosen naming produces, editable only when it is custom.

        The other namings write nothing back: their values are a preview, the boxes are
        read-only while one is on display, and switching to Custom restores whatever the
        player last typed -- blanks included, which is how a rung asks for its generic
        name.
        """
        settings = self.sc.settings
        editable = (
            bool(settings.live_pilots_enabled)
            and settings.live_pilots_rank_names == RANK_NAMES_CUSTOM
        )
        if editable:
            pairs = [
                (settings.__dict__[short], settings.__dict__[full])
                for short, full in self._rank_names
            ]
        else:
            # The container is the settings window, which knows the campaign; country
            # ranks are per squadron, so the player faction is the honest preview.
            faction = getattr(getattr(self.sc, "game", None), "blue", None)
            country = getattr(getattr(faction, "faction", None), "country", None)
            ladder = ranks_for(settings.live_pilots_rank_names, country)
            pairs = [(rank.abbreviation, rank.name) for rank in ladder]

        # The choice follows the master switch; the ladder follows the choice.
        master_on = bool(settings.live_pilots_enabled)
        combo = getattr(self, "_rank_combo", None)
        if combo is not None:
            combo.setEnabled(master_on)
        if self._rank_combo_label is not None:
            self._rank_combo_label.setEnabled(master_on)
        for rank_label in self._rank_labels:
            rank_label.setEnabled(editable)
        for (short_edit, full_edit), (short_text, full_text) in zip(
            self._rank_rows, pairs
        ):
            for edit, text in ((short_edit, short_text), (full_edit, full_text)):
                # Disabled, not read-only: the greyed-out tone is what a player reads
                # as "you cannot type here", and it comes from the theme rather than
                # from a colour hard-coded here.
                edit.setEnabled(editable)
                if edit.text() != text:
                    edit.blockSignals(True)
                    edit.setText(text)
                    edit.blockSignals(False)

    def _wire_live_pilots_master(self) -> None:
        """Everything on the page is a detail of Live Pilots, so it all follows it.

        Named by page rather than by a list of settings: whatever is added later --
        friendship, say -- is covered without anyone remembering to come back here.
        Both ways, because a switch that only ever takes things away leaves them dead
        when it is turned back on -- and the finer rules registered after this one
        narrow what it allows rather than widening it.
        """

        def refresh() -> None:
            live = bool(self.sc.settings.live_pilots_enabled)
            for name in list(self.settings_map):
                if name == "live_pilots_enabled":
                    continue
                widget = self.control_for(name)
                if widget is not None:
                    widget.setEnabled(live)
                label = self.label_map.get(name)
                if label is not None:
                    label.setEnabled(live)
            for label in self._rank_labels:
                label.setEnabled(live)

        self.refresh_hooks.append(refresh)
        refresh()

    def _wire_enabled(self, names: Iterable[str], live: Callable[[Any], bool]) -> None:
        """Grey out settings whose master lives somewhere else on the page.

        Read from the settings rather than from a checkbox: the page re-runs every
        group when anything changes, so the value is always current.
        """
        names = list(names)

        def refresh() -> None:
            enabled = bool(live(self.sc.settings))
            for name in names:
                self.set_enabled(name, enabled)

        self.refresh_hooks.append(refresh)
        refresh()

    def set_enabled(self, name: str, enabled: bool) -> None:
        for target in (self.control_for(name), self.label_map.get(name)):
            if target is not None:
                target.setEnabled(enabled)

    def _wire_survival_odds(self) -> None:
        """The odds follow their own switch, and the switch follows Live Pilots.

        Two masters and one of them lives in another section, so this refreshes from
        the settings rather than from the checkbox: the page re-runs every group when
        any of them changes.
        """
        master = self.settings_map.get("live_pilots_rank_survival")
        rungs = [
            name
            for name, _ in Settings.fields(self.page, self.section)
            if name.startswith("live_pilots_survival_")
        ]

        def refresh() -> None:
            live = bool(self.sc.settings.live_pilots_enabled)
            rolling = live and bool(self.sc.settings.live_pilots_rank_survival)
            # The wound roll is flat and rank-free, so it follows the master switch
            # rather than the rank one: it still applies with rank survival off.
            for name, enabled in [
                ("live_pilots_rank_survival", live),
                ("live_pilots_wounded_chance", live),
            ] + [(rung, rolling) for rung in rungs]:
                for target in (self.control_for(name), self.label_map.get(name)):
                    if isinstance(target, QWidget):
                        target.setEnabled(enabled)

        if isinstance(master, QCheckBox):
            master.toggled.connect(lambda _=None: refresh())
        self.refresh_hooks.append(refresh)
        refresh()

    def _wire_opfor_ai(self) -> None:
        """Show the REST/MCP connect URLs when OPFOR AI control is enabled."""
        master = self.settings_map.get("opfor_ai_enabled")

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 4, 0, 0)
        v.addWidget(QLabel("<b>Connect your LLM (paste a URL):</b>"))
        self._opfor_ai_rest = self._url_row(v, "REST — any HTTP/REST client or curl")
        self._opfor_ai_mcp = self._url_row(v, "MCP — any MCP-compatible client")
        self.addWidget(box, self.rowCount(), 0, 1, SLACK_COLUMN + 1)
        self._opfor_ai_box = box

        def refresh() -> None:
            show = bool(master and master.isChecked())
            self._opfor_ai_box.setVisible(show)
            if show:
                try:
                    from game.agent import service

                    self._opfor_ai_rest.setText(service.connect_url())
                    self._opfor_ai_mcp.setText(service.mcp_url())
                except Exception:
                    self._opfor_ai_rest.setText(
                        "(start a campaign to generate the URL)"
                    )
                    self._opfor_ai_mcp.setText("")

        if master is not None:
            master.toggled.connect(lambda _=None: refresh())
        refresh()

    def _url_row(self, parent_layout: QVBoxLayout, label: str) -> QLineEdit:
        h = QHBoxLayout()
        h.addWidget(QLabel(label + ":"))
        field = QLineEdit()
        field.setReadOnly(True)
        h.addWidget(field, 1)
        copy = style_button(QPushButton("Copy"))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(field.text()))
        h.addWidget(copy)
        parent_layout.addLayout(h)
        return field

    def add_label(self, row: int, description: OptionDescription) -> QLabel:
        wrapped_title = "<br />".join(textwrap.wrap(description.text, width=55))
        text = f"<strong>{wrapped_title}</strong>"
        if description.detail is not None:
            wrapped = "<br />".join(textwrap.wrap(description.detail, width=55))
            text += f"<br />{wrapped}"
        label = QLabel(text)
        if description.tooltip is not None:
            label.setToolTip(description.tooltip)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.addWidget(label, row, 0)
        return label

    def add_checkbox_for(self, row: int, name: str, description: BooleanOption) -> None:
        def on_toggle(value: bool) -> None:
            if description.invert:
                value = not value
            self.sc.settings.__dict__[name] = value
            self.settings_changed()
            if description.causes_expensive_game_update:
                self.write_full_settings()

        checkbox = QCheckBox()
        value = self.sc.settings.__dict__[name]
        if description.invert:
            value = not value
        checkbox.setChecked(value)
        checkbox.toggled.connect(on_toggle)
        self.settings_map[name] = checkbox

        if description.opens_section is None:
            self.addWidget(checkbox, row, 1, Qt.AlignmentFlag.AlignRight)
            return

        # A switch with its own tuning behind it: the knobs open from the row rather
        # than filling a section the player has to find, and are dead until the
        # switch that uses them is on.
        cell = QWidget()
        line = QHBoxLayout(cell)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addStretch()
        line.addWidget(checkbox)
        gear = gear_button(f"{description.text} options")
        section = description.opens_section
        gear.clicked.connect(lambda: self.open_section_dialog(section))
        line.addWidget(gear)
        self.addWidget(cell, row, 1, Qt.AlignmentFlag.AlignRight)
        self.cell_map[name] = cell
        checkbox.toggled.connect(gear.setEnabled)
        gear.setEnabled(checkbox.isChecked())

    def open_section_dialog(self, section: str) -> None:
        self._section_dialog = SectionDialog(
            self.page, section, self.sc, self.write_full_settings, self.parentWidget()
        )
        self._section_dialog.exec()
        self.settings_changed()

    def add_combobox_for(self, row: int, name: str, description: ChoicesOption) -> None:
        combobox = QComboBox()

        def on_changed(index: int) -> None:
            self.sc.settings.__dict__[name] = combobox.itemData(index)
            self.settings_changed()

        for text, value in description.choices.items():
            combobox.addItem(text, value)
        combobox.setCurrentText(
            description.text_for_value(self.sc.settings.__dict__[name])
        )
        combobox.currentIndexChanged.connect(on_changed)
        self.addWidget(combobox, row, 1, Qt.AlignmentFlag.AlignRight)
        self.settings_map[name] = combobox

    def add_line_edit_for(self, row: int, name: str, description: TextOption) -> None:
        edit = QLineEdit(self.sc.settings.__dict__[name])
        if description.placeholder is not None:
            edit.setPlaceholderText(description.placeholder)

        def on_changed(value: str) -> None:
            self.sc.settings.__dict__[name] = value.strip()

        edit.textChanged.connect(on_changed)
        if description.max_length is not None:
            edit.setMaxLength(description.max_length)
            edit.setMinimumWidth(90)
        else:
            edit.setMinimumWidth(260)
        self.addWidget(edit, row, 1, Qt.AlignmentFlag.AlignRight)
        self.settings_map[name] = edit

    def add_float_spin_slider_for(
        self, row: int, name: str, description: BoundedFloatOption
    ) -> None:
        spinner = FloatSpinSlider(
            description.min,
            description.max,
            self.sc.settings.__dict__[name],
            divisor=description.divisor,
            prefix=description.prefix,
            decimals=description.decimals,
        )

        def on_changed() -> None:
            self.sc.settings.__dict__[name] = spinner.value

        spinner.spinner.valueChanged.connect(on_changed)
        self.addLayout(spinner, row, 1, Qt.AlignmentFlag.AlignRight)
        self.settings_map[name] = spinner

    def add_spinner_for(
        self, row: int, name: str, description: BoundedIntOption
    ) -> None:
        def on_changed(value: int) -> None:
            self.sc.settings.__dict__[name] = value
            if description.causes_expensive_game_update:
                self.write_full_settings()

        spinner = QSpinBox()
        spinner.setMinimum(description.min)
        spinner.setMaximum(description.max)
        spinner.setValue(self.sc.settings.__dict__[name])

        spinner.valueChanged.connect(on_changed)
        self.addWidget(spinner, row, 1, Qt.AlignmentFlag.AlignRight)
        self.settings_map[name] = spinner

    def add_duration_controls_for(
        self, row: int, name: str, description: MinutesOption
    ) -> None:
        inputs = TimeInputs(
            self.sc.settings.__dict__[name], description.min, description.max
        )

        def on_changed() -> None:
            self.sc.settings.__dict__[name] = inputs.value

        inputs.spinner.valueChanged.connect(on_changed)
        self.addLayout(inputs, row, 1, Qt.AlignmentFlag.AlignRight)
        self.settings_map[name] = inputs

    def settings_changed(self) -> None:
        """A value changed: re-evaluate visibility, page-wide when the page said how."""
        if self.on_settings_changed is not None:
            self.on_settings_changed()
        else:
            self.apply_visibility()

    def apply_visibility(self) -> bool:
        """Hide the settings whose visible_when says they do not apply right now.

        Returns whether anything is left showing, so a section whose every setting is
        conditional can hide its own group box instead of leaving an empty frame.
        """
        any_visible = False
        for name, description in self.own_fields():
            if description.enabled_when is not None:
                self.set_enabled(name, bool(description.enabled_when(self.sc.settings)))
            if description.visible_when is None:
                any_visible = True
                continue
            visible = bool(description.visible_when(self.sc.settings))
            any_visible = any_visible or visible
            self.label_map[name].setVisible(visible)
            entry = self.cell_map.get(name) or self.settings_map[name]
            # The spinner and time options register a layout rather than a widget,
            # and a layout cannot be hidden -- its contents can.
            if isinstance(entry, QLayout):
                for i in range(entry.count()):
                    if (child := entry.itemAt(i).widget()) is not None:
                        child.setVisible(visible)
            else:
                entry.setVisible(visible)
        for box in self.boxes:
            any_visible = box.apply_visibility() or any_visible
        for hook in self.refresh_hooks:
            hook()
        return any_visible

    def update_from_settings(self) -> None:
        for box in self.boxes:
            box.update_from_settings()
        for hook in self.refresh_hooks:
            hook()
        for name, description in self.own_fields():
            widget = self.settings_map[name]
            value = self.sc.settings.__dict__[name]
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QComboBox):
                if (index := widget.findData(value)) > -1:
                    widget.setCurrentIndex(index)
                elif (index := widget.findText(value)) > -1:
                    widget.setCurrentIndex(index)
                else:
                    logging.error(
                        f"Incompatible type '{type(value)}' for ComboBox option {name}"
                    )
            elif isinstance(widget, FloatSpinSlider):
                widget.spinner.setValue(int(value * widget.spinner.divisor))
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            elif isinstance(widget, TimeInputs):
                widget.spinner.setValue(value.seconds // 60)
        self.apply_visibility()


class AutoSettingsGroup(QGroupBox):
    def __init__(
        self,
        page: str,
        section: str,
        sc: SettingsContainer,
        write_full_settings: Callable[[], None],
    ) -> None:
        super().__init__(section)
        self.section = section
        self.layout = AutoSettingsLayout(page, section, sc, write_full_settings)
        self.setLayout(self.layout)

    def hide_frame(self) -> None:
        """Drop the box, keeping the name for whoever is indexing us.

        A framed box titled the same as the entry you clicked to get here says the
        section's name twice and fences off a page that has nothing to be fenced from.

        Selected by object name, not by class: a stylesheet set on a widget applies
        to its children too, so a plain QGroupBox rule here took the frame off the
        boxes inside the section as well and left them looking like stray labels.
        """
        self.setObjectName("framelessSection")
        self.setStyleSheet(
            "QGroupBox#framelessSection { border: none; margin-top: 0;"
            " padding-top: 0; }"
            "QGroupBox#framelessSection::title { width: 0; height: 0; margin: 0;"
            " padding: 0; }"
        )
        self.setTitle("")

    def title(self) -> str:  # type: ignore[override]
        # QGroupBox.title is the frame's caption, which hide_frame clears; the name
        # of the section is not the caption's to lose.
        return self.section

    def apply_visibility(self, hide_self: bool = True) -> bool:
        """Whether this section has anything left to show.

        A page that puts its sections in a stack shows one at a time and asks the
        stack to do it, so it passes hide_self=False and hides the section's entry in
        the index instead.
        """
        shown = self.layout.apply_visibility()
        if hide_self:
            self.setVisible(shown)
        return shown

    def update_from_settings(self) -> None:
        self.layout.update_from_settings()
        self.apply_visibility()


class SectionDialog(QDialog):
    """A section a switch owns, opened from the gear on its row."""

    def __init__(
        self,
        page: str,
        section: str,
        sc: SettingsContainer,
        write_full_settings: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(section)
        self.setWindowIcon(CONST.ICONS["Settings"])
        self.setModal(True)

        column = QVBoxLayout()
        self.setLayout(column)
        self.group = AutoSettingsGroup(page, section, sc, write_full_settings)
        column.addWidget(self.group)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        column.addLayout(buttons)


#: The index of sections down the left of a page, between the settings dialog's own
#: list and the settings themselves.
SECTION_LIST_WIDTH = 170


class AutoSettingsPage(QWidget):
    """A settings page: its sections, and an index of them when there are several.

    A page with seven boxes on it is a scroll rather than a thing you navigate, so
    anything with more than one section gets a list of them beside it and shows one
    at a time -- the same move the dialog itself makes with its pages.
    """

    def __init__(
        self,
        page: str,
        sc: SettingsContainer,
        write_full_settings: Callable[[], None],
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.groups = [
            AutoSettingsGroup(page, section, sc, write_full_settings)
            for section in Settings.sections(page)
        ]
        for group in self.groups:
            # A setting can decide what another page shows -- Live Pilots greys out
            # AI pilot levelling over on Campaign Management -- so a change has to
            # reach every page that has been built, not just this one.
            group.layout.on_settings_changed = on_change or self.refresh_page

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self.setLayout(row)

        self.stack = QStackedWidget()
        self.sections: Optional[QListWidget] = None
        if len(self.groups) > 1:
            self.sections = QListWidget()
            self.sections.setFixedWidth(SECTION_LIST_WIDTH)
            for group in self.groups:
                self.sections.addItem(QListWidgetItem(group.title()))
                # The index already names the section, so the box would say it twice.
                group.hide_frame()
            self.sections.setCurrentRow(0)
            self.sections.currentRowChanged.connect(self._show_section)
            row.addWidget(self.sections)
        for group in self.groups:
            self.stack.addWidget(group)
            # A stack asks for room enough for its tallest page, so the one long
            # section had every short one showing a scrollbar it did not need.
            # Only the section on display gets a say in the height.
            group.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored
            )

        # The scroll belongs to the settings, not to the page: with the index inside
        # it, reading down a long section carried the list of sections away with it.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setWidget(self.stack)
        row.addWidget(self.scroll, 1)

        # Only now do the group boxes have a parent, and only now is hiding one of
        # them a layout change rather than a stray window.
        self._only_this_one_decides_the_height(self.stack.currentIndex())
        self.refresh_page()

    def _show_section(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self._only_this_one_decides_the_height(index)
            self.scroll_to_top()

    def _only_this_one_decides_the_height(self, index: int) -> None:
        for i, group in enumerate(self.groups):
            group.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                (
                    QSizePolicy.Policy.Preferred
                    if i == index
                    else QSizePolicy.Policy.Ignored
                ),
            )
        current = self.stack.currentWidget()
        if current is not None:
            current.adjustSize()

    def scroll_to_top(self) -> None:
        """A new section, or a new page, starts at its first setting.

        Otherwise a page opened after reading down a long one starts halfway
        through itself, which reads as settings missing from the top.
        """
        self.scroll.verticalScrollBar().setValue(0)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt naming
        # Qt tells us when the page comes to the front, whichever way it got there.
        super().showEvent(event)
        self.scroll_to_top()

    def refresh_page(self) -> None:
        """Re-evaluate every group, since one section can hide another's settings.

        A section with nothing left to show drops out of the index rather than
        leaving an empty box behind it.
        """
        stacked = self.sections is not None
        first_shown = None
        for index, group in enumerate(self.groups):
            shown = group.apply_visibility(hide_self=not stacked)
            if not stacked:
                continue
            assert self.sections is not None
            self.sections.item(index).setHidden(not shown)
            if shown and first_shown is None:
                first_shown = index
        if stacked and first_shown is not None:
            assert self.sections is not None
            if self.sections.item(self.sections.currentRow()).isHidden():
                self.sections.setCurrentRow(first_shown)

    def update_from_settings(self) -> None:
        for group in self.groups:
            group.update_from_settings()
        self.refresh_page()

    def show_section_named(self, section: str) -> bool:
        for index, group in enumerate(self.groups):
            if group.title() != section:
                continue
            if self.sections is not None:
                self.sections.setCurrentRow(index)
            else:
                self.stack.setCurrentIndex(index)
            return True
        return False

    def reveal(self, name: str) -> bool:
        """Show the section holding this setting, scroll to it and flash its label.

        The flash is the point: a search that drops you on a page of forty rows has
        told you where the answer is and left you looking for it.
        """
        for index, group in enumerate(self.groups):
            label = group.layout.label_map.get(name)
            if label is None:
                continue
            if self.sections is not None:
                self.sections.setCurrentRow(index)
            else:
                self.stack.setCurrentIndex(index)
            QTimer.singleShot(0, lambda w=label: self._flash(w))
            return True
        return False

    def open_gear(self, section: str) -> None:
        """Open the dialog a gear on this page opens, for the search to land in."""
        for group in self.groups:
            for name, description in group.layout.own_fields():
                if description.opens_section == section:
                    group.layout.open_section_dialog(section)
                    return

    def _flash(self, label: QWidget) -> None:
        self.scroll.ensureWidgetVisible(label, 0, 80)
        was = label.styleSheet()
        # Amber rather than the palette's highlight, which in this theme is the red
        # it uses for warnings: a setting you asked to be shown should not look like
        # something has gone wrong with it.
        label.setStyleSheet("background: #E0A86B; color: #14202B;")
        QTimer.singleShot(1600, lambda: label.setStyleSheet(was))


class QSettingsWindow(QDialog):
    #: Emitted exactly once when settings are successfully applied, loaded, or
    #: default-loaded. ``QLiberationWindow.showSettingsDialog`` connects this to
    #: ``TransferModel.sync_game_and_visibility``.
    settings_applied = Signal()

    def __init__(self, game: Game):
        super().__init__()
        self.game = game
        self.settings_widget = QSettingsWidget(game.settings, game)
        self.setLayout(self.settings_widget.layout)
        # Forward successful settings completion to the outer window signal.
        self.settings_widget.settings_applied.connect(self.settings_applied)

        self.setModal(True)
        self.setWindowTitle("Settings")
        self.setWindowIcon(CONST.ICONS["Settings"])
        self.setMinimumSize(840, 480)
        self.resize(*self.opening_size())

    @staticmethod
    def opening_size() -> Tuple[int, int]:
        """Wide enough that nothing has to be scrolled to sideways.

        A setting whose switch is off the right-hand edge reads as one that is not
        there. The widest section wants about 1,550 px with both indexes beside it,
        so that is what it opens at -- unless the monitor is smaller, in which case
        it takes what there is.
        """
        wanted = (1560, 960)
        screen = QApplication.primaryScreen()
        if screen is None:
            return wanted
        room = screen.availableGeometry()
        return (
            min(wanted[0], int(room.width() * 0.92)),
            min(wanted[1], int(room.height() * 0.92)),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._handle_mod_settings()
        if self.game is not None and self.game.settings.live_pilots_enabled:
            # Idempotent: it starts the ladder the first time and does nothing after,
            # so the player is free to raise the coalition skills again afterwards.
            self.game.begin_live_pilots()
        super().closeEvent(event)

    def _handle_mod_settings(self) -> None:
        # Applied again on every weather generation, so this is only about the choice
        # taking effect the moment the dialog is closed rather than a turn later.
        apply_cloud_preset_pack(self.game.settings)


class QSettingsWidget(QtWidgets.QWizardPage, SettingsContainer):
    #: Emitted exactly once when settings are successfully applied, loaded, or
    #: default-loaded. Cancelled or failed loads emit zero times.
    settings_applied = Signal()

    def __init__(self, settings: Settings, game: Optional[Game] = None):
        super().__init__()

        self.settings = game.settings if game else settings
        self.game = game

        #: Only the pages the player has actually looked at. See _ensure_page.
        self.pages: dict[str, AutoSettingsPage] = {}
        self._page_names: list[str] = list(Settings.pages())
        self._page_scrolls: dict[int, QScrollArea] = {}

        self.pluginsPage = PluginsPage(self)

        self.updating_ui = False

        self.initUi()

    def initUi(self):
        self.layout = QGridLayout()

        self.categoryList = QListView()
        self.right_layout = QStackedLayout()

        self.categoryList.setMaximumWidth(CATEGORY_LIST_WIDTH)

        self.categoryModel = QStandardItemModel(self.categoryList)

        self.categoryList.setIconSize(QSize(32, 32))

        for index, name in enumerate(self._page_names):
            page_item = QStandardItem(name)
            if name in CONST.ICONS:
                page_item.setIcon(CONST.ICONS[name])
            else:
                page_item.setIcon(CONST.ICONS["Generator"])
            page_item.setEditable(False)
            page_item.setSelectable(True)
            self.categoryModel.appendRow(page_item)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            self._page_scrolls[index] = scroll
            self.right_layout.addWidget(scroll)

        self.initCheatLayout()
        cheat = QStandardItem("Cheat Menu")
        cheat.setIcon(CONST.ICONS["Cheat"])
        cheat.setEditable(False)
        cheat.setSelectable(True)
        self.categoryModel.appendRow(cheat)
        self.right_layout.addWidget(self.cheatPage)

        # One page, not two: the switch and what it turns on belong together, and the
        # options open from the row rather than filling a page of their own.
        plugins = QStandardItem("Mission Plugins")
        plugins.setIcon(CONST.ICONS["Plugins"])
        plugins.setEditable(False)
        plugins.setSelectable(True)
        self.categoryModel.appendRow(plugins)
        plugin_scroll = QScrollArea()
        plugin_scroll.setWidget(self.pluginsPage)
        plugin_scroll.setWidgetResizable(True)
        self.right_layout.addWidget(plugin_scroll)

        self.categoryList.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.categoryList.setModel(self.categoryModel)
        self.categoryList.selectionModel().setCurrentIndex(
            self.categoryList.indexAt(QPoint(1, 1)),
            QItemSelectionModel.SelectionFlag.Select,
        )
        # The default selection is set before the signal is connected, so nothing
        # would build the page the dialog opens on.
        self._ensure_page(0)
        self.categoryList.selectionModel().selectionChanged.connect(
            self.onSelectionChanged
        )

        self.initSearch()
        self.layout.addWidget(self.search, 0, 0, 1, 1)
        self.layout.addWidget(self.left_stack, 1, 0, 1, 1)
        self.layout.addLayout(self.right_layout, 0, 1, 5, 1)
        self.layout.setColumnStretch(1, 1)

        load = style_button(QPushButton("Load Settings"))
        load.clicked.connect(self.load_settings)
        self.layout.addWidget(load, 2, 0, 1, 1)
        save = style_button(QPushButton("Save Settings"))
        save.clicked.connect(self.save_settings)
        self.layout.addWidget(save, 3, 0, 1, 1)

        self.setLayout(self.layout)

    def initSearch(self) -> None:
        """A box that takes the word the player remembers and finds the setting.

        Two hundred settings across six pages, and the plugins' own options behind
        their gears: whichever page the answer is on, it is not the one you are
        looking at. The results take the place of the page list while there is
        something typed, so the column never grows and nothing else moves.
        """
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings...")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(CATEGORY_LIST_WIDTH)
        self.search.textChanged.connect(self.on_search)

        self.results = QListWidget()
        self.results.setMaximumWidth(CATEGORY_LIST_WIDTH)
        self.results.setWordWrap(True)
        self.results.itemActivated.connect(self.on_result_chosen)
        self.results.itemClicked.connect(self.on_result_chosen)

        self.left_stack = QStackedWidget()
        # The cap has to be on the stack as well as on what it holds: a stack asks
        # for room enough for its widest child and ignores their own limits, so
        # without this the column swallowed a third of the dialog.
        self.left_stack.setMaximumWidth(CATEGORY_LIST_WIDTH)
        self.left_stack.addWidget(self.categoryList)
        self.left_stack.addWidget(self.results)

    def on_search(self, query: str) -> None:
        from game.settings.search import search

        if not query.strip():
            self.left_stack.setCurrentWidget(self.categoryList)
            return
        self.results.clear()
        for hit in search(query, self.settings):
            # The label, then where it lives, so a row that reads the same as
            # another -- there are two settings called "Cadet" -- is still telling
            # you which one it is.
            item = QListWidgetItem("{}\n{}".format(hit.label, hit.where))
            item.setData(Qt.ItemDataRole.UserRole, hit)
            item.setToolTip("{}\n{}".format(hit.label, hit.where))
            self.results.addItem(item)
        if self.results.count() == 0:
            empty = QListWidgetItem("Nothing matches")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.results.addItem(empty)
        self.left_stack.setCurrentWidget(self.results)

    def on_result_chosen(self, item: QListWidgetItem) -> None:
        hit = item.data(Qt.ItemDataRole.UserRole)
        if hit is None:
            return
        self.go_to(hit)

    def go_to(self, hit: Any) -> None:
        """Open whatever has to be opened for this setting to be on the screen."""
        if hit.plugin is not None:
            self.show_page(self.categoryModel.rowCount() - 1)
            self.pluginsPage.open_options_for(hit.plugin, hit.key)
            return

        page, section = hit.page, hit.section
        if hit.is_section:
            self.show_page(self._page_names.index(page))
            shown = self.pages.get(page)
            if shown is not None:
                shown.show_section_named(section)
            return

        # A section behind a gear is on no page: go to the switch that opens it and
        # open it.
        owner = Settings.switch_that_opens(section)
        if owner is not None:
            name, page, section = owner
        if page not in self._page_names:
            return
        index = self._page_names.index(page)
        self.show_page(index)
        shown = self.pages.get(page)
        if shown is None:
            return
        if owner is not None:
            shown.reveal(owner[0])
            shown.open_gear(section)
        else:
            shown.reveal(hit.key)

    def show_page(self, index: int) -> None:
        self.categoryList.selectionModel().setCurrentIndex(
            self.categoryModel.index(index, 0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        self._ensure_page(index)
        self.right_layout.setCurrentIndex(index)

    def initCheatLayout(self):
        self.cheatPage = QWidget()
        self.cheatLayout = QVBoxLayout()
        self.cheatPage.setLayout(self.cheatLayout)

        self.cheat_options = CheatSettingsBox(self, self.applySettings)
        self.cheatLayout.addWidget(self.cheat_options)

        # One box per coalition so money can be given/taken to OWNFOR and OPFOR.
        # (OPFOR money used to be reachable only via the negative-aircraft exploit.)
        money_row = QHBoxLayout()
        money_row.addWidget(
            self._build_money_cheat_box("OWNFOR (BLUE) Money Cheat", Player.BLUE)
        )
        money_row.addWidget(
            self._build_money_cheat_box("OPFOR (RED) Money Cheat", Player.RED)
        )
        self.cheatLayout.addLayout(money_row, stretch=1)

    def _build_money_cheat_box(self, title: str, player: Player) -> QGroupBox:
        box = QGroupBox(title)
        box.setDisabled(self.game is None)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout = QGridLayout()
        box.setLayout(layout)
        cheats_amounts = [25, 50, 100, 200, 500, 1000, -25, -50, -100, -200]
        for i, amount in enumerate(cheats_amounts):
            if amount > 0:
                btn = QPushButton("Cheat +" + str(amount) + "M")
                btn.setProperty("style", "btn-success")
            else:
                btn = QPushButton("Cheat " + str(amount) + "M")
                btn.setProperty("style", "btn-danger")
            btn.clicked.connect(self.cheatLambda(amount, player))
            layout.addWidget(btn, i // 2, i % 2)
        return box

    def cheatLambda(self, amount, player):
        return lambda: self.cheatMoney(amount, player)

    def cheatMoney(self, amount, player):
        logging.info(f"CHEATING {player} FOR AMOUNT : {amount}M")
        self.game.coalition_for(player).budget += amount
        GameUpdateSignal.get_instance().updateGame(self.game)

    def applySettings(self):
        if self.updating_ui:
            return
        self.settings.enable_frontline_cheats = self.cheat_options.show_frontline_cheat
        self.settings.enable_base_capture_cheat = (
            self.cheat_options.show_base_capture_cheat
        )
        self.settings.enable_transfer_cheat = self.cheat_options.show_transfer_cheat
        self.settings.enable_runway_state_cheat = (
            self.cheat_options.enable_runway_state_cheat
        )
        self.settings.enable_air_wing_adjustments = (
            self.cheat_options.enable_air_wing_cheats
        )
        self.settings.enable_enemy_buy_sell = self.cheat_options.enable_redfor_buysell
        self.settings.enable_pilot_cheats = self.cheat_options.enable_pilot_cheats
        self.settings.enable_location_cheat = self.cheat_options.enable_location_cheat

        self._publish_settings_update()

        # Announce successful completion exactly once. The ``updating_ui`` early
        # return above ensures programmatic refreshes never emit.
        self.settings_applied.emit()

    def _publish_settings_update(self) -> None:
        if self.game is None:
            return
        events = GameUpdateEvents()
        self.game.compute_unculled_zones(events)
        events.update_motorpools_at(*self.game.theater.controlpoints)
        EventStream.put_nowait(events)
        GameUpdateSignal.get_instance().updateGame(self.game)

    def _ensure_page(self, index: int) -> None:
        """Build a settings page the first time it is looked at.

        The seven pages together are 192 settings and some six hundred widgets, and
        the dialog is rebuilt from scratch on every open -- it used to build all of
        them to show one, which is the couple of seconds before the window appears.
        """
        scroll = self._page_scrolls.get(index)
        if scroll is None or scroll.widget() is not None:
            return
        name = self._page_names[index]
        page = AutoSettingsPage(name, self, self.applySettings, self.refresh_all_pages)
        self.pages[name] = page
        scroll.setWidget(page)

    def onSelectionChanged(self) -> None:
        index = self.categoryList.selectionModel().currentIndex().row()
        self._ensure_page(index)
        self.right_layout.setCurrentIndex(index)
        shown = self.right_layout.currentWidget()
        if isinstance(shown, AutoSettingsPage):
            shown.scroll_to_top()
        elif isinstance(shown, QScrollArea):
            shown.verticalScrollBar().setValue(0)

    def refresh_all_pages(self) -> None:
        """Re-evaluate every page that has been built, not just the one in front."""
        for page in self.pages.values():
            page.refresh_page()

    def update_from_settings(self) -> None:
        self.updating_ui = True
        for p in self.pages.values():
            p.update_from_settings()

        self.cheat_options.base_capture_cheat_checkbox.setChecked(
            self.settings.enable_base_capture_cheat
        )
        self.cheat_options.frontline_cheat_checkbox.setChecked(
            self.settings.enable_frontline_cheats
        )
        self.cheat_options.transfer_cheat_checkbox.setChecked(
            self.settings.enable_transfer_cheat
        )
        self.cheat_options.base_runway_state_cheat_checkbox.setChecked(
            self.settings.enable_runway_state_cheat
        )
        self.cheat_options.air_wing_adjustments_checkbox.setChecked(
            self.settings.enable_air_wing_adjustments
        )
        self.cheat_options.opfor_buysell_checkbox.setChecked(
            self.settings.enable_enemy_buy_sell
        )
        self.cheat_options.pilot_cheats_checkbox.setChecked(
            self.settings.enable_pilot_cheats
        )
        self.cheat_options.location_cheat_checkbox.setChecked(
            self.settings.enable_location_cheat
        )

        self.pluginsPage.update_from_settings()

        self.updating_ui = False

    def load_settings(self):
        sd = settings_dir()
        fd = QFileDialog(caption="Load Settings", directory=str(sd), filter="*.zip")
        if fd.exec_():
            zipfilename = fd.selectedFiles()[0]
            with zipfile.ZipFile(zipfilename, "r") as zf:
                filename = os.path.basename(zipfilename).replace(".zip", ".json")
                settings = json.loads(
                    zf.read(filename).decode("utf-8"),
                    object_hook=self.settings.obj_hook,
                )
                self.settings.__setstate__(settings)
                self.update_from_settings()
            self._publish_settings_update()
            # Emit exactly once only after an accepted, successfully decoded
            # and applied archive.
            self.settings_applied.emit()

    def save_settings(self):
        sd = settings_dir()
        fd = QFileDialog(caption="Save Settings", directory=str(sd), filter="*.zip")
        fd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        if fd.exec_():
            zipfilename = fd.selectedFiles()[0]
            with zipfile.ZipFile(zipfilename, "w", zipfile.ZIP_DEFLATED) as zf:
                filename = os.path.basename(zipfilename).replace(".zip", ".json")
                zf.writestr(
                    filename,
                    json.dumps(
                        self.settings.__dict__,
                        indent=2,
                        default=self.settings.default_json,
                    ),
                    zipfile.ZIP_DEFLATED,
                )

    def load_default_settings(self):
        sd = settings_dir()
        default_zip_path = sd / "Default.zip"
        if default_zip_path.exists():
            with zipfile.ZipFile(default_zip_path, "r") as zf:
                filename = [n for n in zf.namelist() if n.lower() == "default.json"]
                if not filename:
                    return
                filename = filename[0]
                settings_data = json.loads(
                    zf.read(filename).decode("utf-8"),
                    object_hook=self.settings.obj_hook,
                )
                self.settings.__setstate__(settings_data)
        else:
            if self.settings is None:
                default_settings = Settings()
            else:
                default_settings = self.settings
            with zipfile.ZipFile(default_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                filename = "Default.json"
                zf.writestr(
                    filename,
                    json.dumps(
                        default_settings.__dict__,
                        indent=2,
                        default=default_settings.default_json,
                    ),
                    zipfile.ZIP_DEFLATED,
                )
            self.settings.__setstate__(default_settings.__dict__)

        self._publish_settings_update()
        # Emit exactly once after loading or creating/applying defaults.
        self.settings_applied.emit()
