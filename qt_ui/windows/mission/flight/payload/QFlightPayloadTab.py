from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QSpinBox,
    QSlider,
    QCheckBox,
    QScrollArea,
    QPushButton,
)

from game import Game
from game.ato.flight import Flight
from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.ato.fuelestimate import estimate_fuel
from game.data.fueltanks import loadout_fuel
from game.utils import kgs
from qt_ui.widgets.QLabeledWidget import QLabeledWidget
from qt_ui.widgets.cards import CARD_BG, carded, make_transparent
from qt_ui.widgets.controls import Segmented, mono, styled_input
from qt_ui.widgets.combos.QSquadronLiverySelector import SquadronLiverySelector
from qt_ui.widgets.searchablecombo import LOADOUT_SEARCH_FLOOR, SearchableComboBox
from .QLoadoutEditor import QLoadoutEditor
from .ownlasercodeinfo import OwnLaserCodeInfo
from .propertyeditor import PropertyEditor
from .weaponlasercodeselector import WeaponLaserCodeSelector

#: The payload tab's two columns.
LEFT_WIDTH = 540
RIGHT_WIDTH = 556
GAP = 24
MARGIN = 20


class DcsLoadoutSelector(SearchableComboBox):
    """The preset list, which for a Hornet runs to a few hundred entries.

    Searchable, because finding "SEAD mio" in a list sorted alphabetically among every
    payload the community has ever saved is scrolling, not choosing.
    """

    def __init__(self, flight: Flight, member: FlightMember) -> None:
        super().__init__(
            placeholder="Type to find a payload…", threshold=LOADOUT_SEARCH_FLOOR
        )
        for loadout in Loadout.iter_for(flight):
            self.addItem(loadout.name, loadout)
        self.model().sort(0)
        self.setDisabled(member.loadout.is_custom)
        if member.loadout.is_custom:
            self.setCurrentText(Loadout.default_for(flight).name)
        else:
            self.setCurrentText(member.loadout.name)


class FlightMemberSelector(QWidget):
    """One button per seat, labelled with who is in it.

    A spin box before, which meant choosing whose loadout you were editing was
    "member 2" -- a number with no face. The buttons carry the pilot's name, so the
    seat you are editing is a person.
    """

    valueChanged = Signal(int)  # noqa: N815 (kept from the QSpinBox it replaces)

    def __init__(self, flight: Flight, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flight = flight
        self._index = 0

        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(2)
        self.setLayout(self._row)
        self._segmented: Segmented | None = None
        self.rebuild()

    def rebuild(self) -> None:
        if self._segmented is not None:
            self._segmented.setParent(None)
            self._segmented.deleteLater()
        options = []
        for index in range(self.flight.count):
            pilot = self.flight.roster.pilot_at(index)
            name = pilot.name if pilot is not None else "Unassigned"
            options.append((f"{index + 1}  {name}", index))
        self._index = min(self._index, max(0, self.flight.count - 1))
        self._segmented = Segmented(options, current=self._index)
        self._segmented.selection_changed.connect(self._on_selected)
        self._row.addWidget(self._segmented)

    def _on_selected(self, index: int) -> None:
        self._index = index
        self.valueChanged.emit(index + 1)

    def setMaximum(self, _value: int) -> None:  # noqa: N802 (Qt naming)
        """Kept from the spin box: the caller says the flight resized."""
        self.rebuild()

    def value(self) -> int:
        """The seat number, counting from one.

        Kept from the spin box this replaced, with the same off-by-one: five call
        sites read it, and changing what it means as well as what it looks like is two
        changes where one will do.
        """
        return self._index + 1

    @property
    def selected_member(self) -> FlightMember:
        return self.flight.roster.members[self._index]


class DcsFuelSelector(QWidget):
    #: Emitted whenever the fuel the aircraft leaves the ground with changes -- the
    #: slider, the unit swap, a new preset, or a pylon that gained or lost a tank.
    #: The waypoint tab's fuel estimate is computed from it and has no other way to
    #: know it moved.
    carried_fuel_changed = Signal()

    LBS2KGS_FACTOR = 0.45359237

    def __init__(self, flight: Flight) -> None:
        super().__init__()
        self.flight = flight
        self.unit_changing = False

        # Still SETS the internal quantity, the only fuel figure DCS takes, but says
        # what the aircraft carries with its tanks.
        row = QHBoxLayout()
        row.setContentsMargins(14, 8, 14, 0)
        row.setSpacing(10)

        self.max_fuel = int(flight.unit_type.dcs_unit_type.fuel_max)
        self.fuel = QSlider(Qt.Orientation.Horizontal)
        self.fuel.setRange(0, self.max_fuel)
        self.fuel.setValue(min(round(self.flight.fuel), self.max_fuel))
        self.fuel.setStyleSheet(
            "QSlider::groove:horizontal { height: 6px; background: #1D2731;"
            " border-radius: 3px; }"
            "QSlider::sub-page:horizontal { background: #3F5D73; border-radius: 3px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px;"
            " margin: -4px 0; background: #8FC3F0; border-radius: 7px; }"
        )
        self.fuel.valueChanged.connect(self.on_fuel_change)
        row.addWidget(self.fuel, 1)

        self.fuel_spinner = QSpinBox()
        self.fuel_spinner.setRange(0, self.max_fuel)
        self.fuel_spinner.setValue(self.fuel.value())
        self.fuel_spinner.valueChanged.connect(self.update_fuel_slider)
        row.addWidget(styled_input(self.fuel_spinner, width=96))

        self.unit = QComboBox()
        self.unit.insertItems(0, ["kg", "lbs"])
        self.unit.currentIndexChanged.connect(self.on_unit_change)
        self.unit.setCurrentIndex(1)
        row.addWidget(styled_input(self.unit, width=64))

        # Line two does the arithmetic the player was doing in their head: what the
        # tanks add, what that comes to, and whether the plan asks for more than that.
        self.tanks = QLabel()
        self.tanks.setFont(mono(12))
        self.tanks.setStyleSheet(
            "color: #8E9DAA; background: transparent; border: none;"
        )
        self.verdict = QLabel()
        self.verdict.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        self.verdict.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        second = QHBoxLayout()
        second.setContentsMargins(14, 2, 14, 8)
        second.setSpacing(10)
        second.addWidget(self.tanks)
        second.addStretch()
        second.addWidget(self.verdict)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(row)
        column.addLayout(second)
        self.setLayout(column)

        self.show_tanks(flight.roster.members[0].loadout)

    def _loadout(self) -> Loadout:
        return self.flight.roster.members[0].loadout

    def show_tanks(self, loadout: Loadout) -> None:
        """What the external tanks add, and what the aircraft therefore carries."""
        # Every path that changes carried fuel comes through here, so this is the one
        # place the signal has to be emitted from.
        self.carried_fuel_changed.emit()
        external = loadout_fuel(loadout)
        internal = kgs(self.fuel.value())
        if self.unit.currentIndex() == 0:
            unit, add, total = "kg", external.kgs, internal.kgs + external.kgs
            inner = internal.kgs
        else:
            unit, add, total = (
                "lb",
                external.pounds,
                internal.pounds + external.pounds,
            )
            inner = internal.pounds
        if add:
            self.tanks.setText(
                f"{inner:,.0f} internal + {add:,.0f} in tanks = {total:,.0f} {unit}"
            )
        else:
            self.tanks.setText(f"{inner:,.0f} {unit} internal, no tanks")
        self._show_verdict()

    def _show_verdict(self) -> None:
        """What the plan asks for, against what it is carrying.

        The figure is on the waypoint tab as well, but this is where you change the
        answer, and a number you have to go to another tab to check is a number you do
        not check.
        """
        estimate = estimate_fuel(self.flight)
        if estimate is None:
            self.verdict.setText("")
            return
        needed = estimate.required.pounds
        carried = estimate.carried.pounds
        if self.unit.currentIndex() == 0:
            shown = f"{estimate.required.kgs:,.0f} kg"
        else:
            shown = f"{needed:,.0f} lb"
        margin = (carried - needed) / needed * 100 if needed else 0.0
        if estimate.enough:
            self.verdict.setText(f"plan needs ~{shown}  ·  {margin:+.0f}%")
            self.verdict.setStyleSheet(
                "font-size: 12px; color: #86C39A; background: transparent;"
                " border: none;"
            )
        else:
            self.verdict.setText(f"plan needs ~{shown}  ·  {margin:+.0f}%")
            self.verdict.setStyleSheet(
                "font-size: 12px; color: #D9645E; background: transparent;"
                " border: none;"
            )

    def on_fuel_change(self, value: int) -> None:
        self.flight.fuel = value
        self.show_tanks(self._loadout())
        if self.unit.currentIndex() == 0:
            self.fuel_spinner.setValue(value)
        elif self.unit.currentIndex() == 1 and not self.unit_changing:
            self.fuel_spinner.setValue(self.kg2lbs(value))

    def update_fuel_slider(self, value: int) -> None:
        if self.unit_changing:
            return
        if self.unit.currentIndex() == 0:
            self.fuel.setValue(value)
        elif self.unit.currentIndex() == 1:
            self.unit_changing = True
            self.fuel.setValue(self.lbs2kg(value))
            self.unit_changing = False

    def on_unit_change(self, index: int) -> None:
        self.unit_changing = True
        if index == 0:
            self.fuel_spinner.setMaximum(self.max_fuel)
            self.fuel_spinner.setValue(self.fuel.value())
        elif index == 1:
            self.fuel_spinner.setMaximum(self.kg2lbs(self.max_fuel))
            self.fuel_spinner.setValue(self.kg2lbs(self.fuel.value()))
        self.unit_changing = False

    def kg2lbs(self, value: int) -> int:
        return round(value / self.LBS2KGS_FACTOR)

    def lbs2kg(self, value: int) -> int:
        return round(value * self.LBS2KGS_FACTOR)


class QFlightPayloadTab(QFrame):
    #: Re-emitted from the fuel selector: what the flight takes off with has changed,
    #: so anything showing a fuel figure needs to recompute.
    carried_fuel_changed = Signal()

    def __init__(self, flight: Flight, game: Game):
        super(QFlightPayloadTab, self).__init__()
        self.flight = flight
        self.payload_editor = QLoadoutEditor(
            flight, self.flight.roster.members[0], game
        )
        self.payload_editor.toggled.connect(self.on_custom_toggled)
        self.payload_editor.pylons_changed.connect(self.on_pylons_changed)
        self.payload_editor.saved.connect(self.on_saved_payload)

        layout = QVBoxLayout()
        layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        layout.setSpacing(18)

        # --- who you are editing, above both columns ------------------------
        self.member_selector = FlightMemberSelector(self.flight, self)
        self.member_selector.valueChanged.connect(self.rebind_to_selected_member)

        self.same_loadout_for_all_checkbox = QCheckBox("Same loadout for all")
        self.same_loadout_for_all_checkbox.setToolTip(
            "AI flights should use the same loadout for all members."
        )
        self.same_loadout_for_all_checkbox.setChecked(
            self.flight.use_same_loadout_for_all_members
        )
        self.same_loadout_for_all_checkbox.toggled.connect(self.on_same_loadout_toggled)

        self.same_livery_for_all_checkbox = QCheckBox("Same livery")
        self.same_livery_for_all_checkbox.setChecked(
            self.flight.use_same_livery_for_all_members
        )
        self.same_livery_for_all_checkbox.toggled.connect(self.on_same_livery_toggled)

        self.livery_selector = SquadronLiverySelector(
            self.flight.squadron, update_squadron=False
        )
        self.livery_selector.currentIndexChanged.connect(self.on_livery_change)

        strip = QHBoxLayout()
        strip.setContentsMargins(14, 0, 14, 0)
        strip.setSpacing(12)
        strip.addWidget(self.member_selector)
        strip.addStretch()
        strip.addWidget(self.same_loadout_for_all_checkbox)
        strip.addWidget(self.same_livery_for_all_checkbox)
        strip.addWidget(styled_input(self.livery_selector, width=260))
        strip_holder = QWidget()
        strip_holder.setFixedHeight(44)
        strip_holder.setStyleSheet(
            "background: #1B2732; border: 1px solid #1D2731; border-radius: 3px;"
        )
        strip_holder.setLayout(strip)
        layout.addWidget(strip_holder)

        scroll_content = QWidget()
        scrolling_layout = QVBoxLayout()
        scrolling_layout.setContentsMargins(14, 10, 14, 10)
        # Tight, and everything pinned to the top: the rows used to be spread down the
        # whole panel, so the sentence about laser codes floated half a screen away
        # from the laser codes it was about.
        scrolling_layout.setSpacing(6)
        scroll_content.setLayout(scrolling_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # The viewport covers the card completely, so rather than trying to see the
        # card through it, the viewport IS the card's face.
        scroll.viewport().setStyleSheet(f"background: {CARD_BG};")
        make_transparent(scroll)
        self.systems_scroll = scroll

        self.own_laser_code_info = OwnLaserCodeInfo(
            game, self.member_selector.selected_member
        )
        scrolling_layout.addLayout(self.own_laser_code_info)

        self.weapon_laser_code_selector = WeaponLaserCodeSelector(
            game, self.member_selector.selected_member, self
        )
        self.own_laser_code_info.assigned_laser_code_changed.connect(
            self.weapon_laser_code_selector.rebuild
        )
        scrolling_layout.addLayout(
            QLabeledWidget(
                "Preset laser code for weapons:", self.weapon_laser_code_selector
            )
        )
        scrolling_layout.addWidget(
            QLabel(
                "Equipped weapons will be pre-configured to the selected laser code at "
                "mission start."
            )
        )

        # A little air before the aircraft's own switches: they are a different
        # subject from the laser codes above them, and with everything pulled tight
        # the DATALINK heading sat on the sentence before it.
        scrolling_layout.addSpacing(24)

        self.property_editor = PropertyEditor(
            self.flight, self.member_selector.selected_member, game
        )
        scrolling_layout.addLayout(self.property_editor)
        scrolling_layout.addStretch()

        # Docs Link
        docsText = QLabel(
            '<a href="https://github.com/dcs-retribution/dcs-retribution/wiki/Custom-Loadouts"><span style="color:#FFFFFF;">How to create your own default loadout</span></a>'
        )
        docsText.setAlignment(Qt.AlignmentFlag.AlignCenter)
        docsText.setOpenExternalLinks(True)

        self.fuel_selector = DcsFuelSelector(flight)
        self.fuel_selector.carried_fuel_changed.connect(self.carried_fuel_changed)

        # --- the preset strip, above the pylons it chooses ------------------
        self.loadout_selector = DcsLoadoutSelector(
            flight, self.member_selector.selected_member
        )
        self.loadout_selector.currentIndexChanged.connect(self.on_new_loadout)

        self.set_default_btn = QPushButton("Set as default")
        self.set_default_btn.setToolTip(
            "Save the selected loadout as the default for this aircraft and mission "
            "type, so future flights of this type use it."
        )
        self.set_default_btn.clicked.connect(self.on_set_default)

        self.clear_default_btn = QPushButton("Clear")
        self.clear_default_btn.setToolTip(
            "Stop using a saved default for this aircraft and mission type, so new "
            "flights go back to the built-in choice. No payload is deleted."
        )
        self.clear_default_btn.clicked.connect(self.on_clear_default)

        preset = QHBoxLayout()
        preset.setContentsMargins(14, 0, 14, 0)
        preset.setSpacing(8)
        preset.addWidget(styled_input(self.loadout_selector), 1)
        for button in (self.set_default_btn, self.clear_default_btn):
            button.setFixedHeight(26)
            preset.addWidget(button)
        preset_holder = QWidget()
        preset_holder.setFixedHeight(44)
        preset_holder.setStyleSheet("background: #1B2732; border: none;")
        preset_holder.setLayout(preset)

        loadout_card = QVBoxLayout()
        loadout_card.setContentsMargins(0, 0, 0, 0)
        loadout_card.setSpacing(0)
        loadout_card.addWidget(preset_holder)
        loadout_card.addWidget(self.payload_editor, 1)
        loadout_card.addWidget(docsText)
        loadout_holder = QWidget()
        make_transparent(loadout_holder)
        loadout_holder.setLayout(loadout_card)

        # --- two columns ----------------------------------------------------
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)
        left.addLayout(
            carded(
                "Aircraft systems",
                scroll,
                "laser codes and the aircraft's own switches",
                margins=(0, 4, 0, 4),
            )
        )

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(18)
        right.addLayout(
            carded(
                "Fuel",
                self.fuel_selector,
                "internal + external tanks, against what the plan asks for",
                margins=(0, 0, 0, 0),
            )
        )
        right.addLayout(carded("Loadout", loadout_holder, margins=(0, 0, 0, 0)))
        right.addStretch()

        left_holder = QWidget()
        left_holder.setLayout(left)
        left_holder.setMinimumWidth(LEFT_WIDTH)
        right_holder = QWidget()
        right_holder.setLayout(right)
        right_holder.setMinimumWidth(RIGHT_WIDTH)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(GAP)
        columns.addWidget(left_holder, 1)
        columns.addWidget(right_holder, 1)
        layout.addLayout(columns, 1)

        self.setLayout(layout)

    def resize_for_flight(self) -> None:
        self.member_selector.setMaximum(self.flight.count - 1)

    def reload_from_flight(self) -> None:
        self.loadout_selector.setCurrentText(
            self.member_selector.selected_member.loadout.name
        )

    def rebind_to_selected_member(self) -> None:
        member = self.member_selector.selected_member
        self.property_editor.set_flight_member(member)
        self.loadout_selector.setCurrentText(member.loadout.name)
        self.loadout_selector.setDisabled(member.loadout.is_custom)
        self.livery_selector.setCurrentIndex(
            self.livery_selector.findData(member.livery)
        )
        self.payload_editor.set_flight_member(member)
        self.weapon_laser_code_selector.set_flight_member(member)
        self.own_laser_code_info.set_flight_member(member)
        if self.member_selector.value() != 1:
            self.loadout_selector.setDisabled(
                self.flight.use_same_loadout_for_all_members
            )
            self.payload_editor.setDisabled(
                self.flight.use_same_loadout_for_all_members
            )
            self.livery_selector.setDisabled(
                self.flight.use_same_livery_for_all_members
            )
        else:
            self.loadout_selector.setEnabled(True)
            self.payload_editor.setEnabled(True)
            self.livery_selector.setEnabled(True)

    def loadout_at(self, index: int) -> Loadout:
        loadout = self.loadout_selector.itemData(index)
        if loadout is None:
            return Loadout.empty_loadout()
        return loadout

    def current_loadout(self) -> Loadout:
        loadout = self.loadout_selector.currentData()
        if loadout is None:
            return Loadout.empty_loadout()
        return loadout

    def on_new_loadout(self, index: int) -> None:
        loadout = self.loadout_at(index)
        self.member_selector.selected_member.loadout = loadout
        if self.flight.use_same_loadout_for_all_members:
            self.flight.roster.use_same_loadout_for_all_members()
        self.payload_editor.reset_pylons()
        self.fuel_selector.show_tanks(loadout)

    def on_pylons_changed(self) -> None:
        self.fuel_selector.show_tanks(self.member_selector.selected_member.loadout)

    def on_clear_default(self) -> None:
        self.payload_editor.clear_task_default()

    def on_set_default(self) -> None:
        # The selected member's loadout already mirrors the dropdown selection (or
        # the custom loadout when "Use custom loadout" is on); persist it as the
        # default for this aircraft + mission type.
        self.payload_editor.save_as_task_default()

    def on_custom_toggled(self, use_custom: bool) -> None:
        self.loadout_selector.setDisabled(use_custom)
        member = self.member_selector.selected_member
        member.use_custom_loadout = use_custom
        if use_custom:
            member.loadout = member.loadout.derive_custom("Custom")
        else:
            member.loadout = self.current_loadout()
            self.payload_editor.reset_pylons()
        if self.flight.use_same_loadout_for_all_members:
            self.flight.roster.use_same_loadout_for_all_members()

    def on_saved_payload(self, payload_name: str) -> None:
        loadout = self.member_selector.selected_member.loadout
        self.loadout_selector.addItem(payload_name, loadout)
        self.loadout_selector.setCurrentIndex(self.loadout_selector.count() - 1)

    def on_same_loadout_toggled(self, checked: bool) -> None:
        self.flight.use_same_loadout_for_all_members = checked
        if self.member_selector.value():
            self.loadout_selector.setDisabled(checked)
            self.payload_editor.setDisabled(checked)
        if checked:
            self.flight.roster.use_same_loadout_for_all_members()
            if self.member_selector.value():
                self.rebind_to_selected_member()
        else:
            self.flight.roster.use_distinct_loadouts_for_each_member()

    def on_same_livery_toggled(self, checked: bool) -> None:
        self.flight.use_same_livery_for_all_members = checked
        if self.member_selector.value():
            self.livery_selector.setDisabled(checked)
        if checked:
            self.flight.roster.use_same_livery_for_all_members()
            if self.member_selector.value():
                self.rebind_to_selected_member()

    def on_livery_change(self) -> None:
        livery = self.livery_selector.currentData()
        use_livery_set = self.livery_selector.using_livery_set
        if self.flight.use_same_livery_for_all_members:
            for m in self.flight.roster.members:
                m.livery = livery
                m.use_livery_set = use_livery_set
        else:
            self.member_selector.selected_member.livery = livery
            self.member_selector.selected_member.use_livery_set = use_livery_set
