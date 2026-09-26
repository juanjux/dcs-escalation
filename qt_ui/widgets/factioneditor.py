"""The running campaign's faction catalogue, with one equipment pool in view.

The wizard still owns its checkbox workflow. This view reuses its catalogue and
mutation handlers so country restrictions, cache invalidation and in-use guards
remain the same for both coalitions.
"""

from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.data.doctrine import ALL_DOCTRINES
from game.factions import Faction
from qt_ui.widgets.cards import caption, card, make_transparent, shrinkable
from qt_ui.widgets.controls import button, styled_input
from qt_ui.widgets.searchablecombo import SearchableComboBox
from qt_ui.windows.newgame.WizardPages.QFactionSelection import QFactionUnits

# Label, faction collection, existing combo attribute, catalogue source.
POOLS = (
    ("Aircraft", "aircraft", "add_ac_combo", "aircraft"),
    ("AWACS", "awacs", "add_awacs_combo", "awacs"),
    ("Tankers", "tankers", "add_tanker_combo", "tanker"),
    (
        "Frontline vehicles",
        "frontline_units",
        "add_frontline_combo",
        ["Frontline vehicles"],
    ),
    ("Artillery", "artillery_units", "add_artillery_combo", ["Artillery"]),
    ("Logistics", "logistics_units", "add_logistics_combo", ["Logistics"]),
    ("Infantry", "infantry_units", "add_infantry_combo", ["Infantry"]),
    ("Preset groups", "preset_groups", "add_preset_group_combo", "presets"),
    (
        "Air defenses",
        "air_defense_units",
        "add_air_defense_combo",
        ["EarlyWarningRadar", "AAA", "SHORAD"],
    ),
    ("Naval units", "naval_units", "add_naval_combo", "naval"),
    ("Missile units", "missiles", "add_missile_combo", ["Missile"]),
)

TREE_STYLE = """
QTreeWidget { background: #14202B; color: #D3DFE8; border: none;
    outline: none; font-size: 13px; }
QTreeWidget::item { height: 36px; border-bottom: 1px solid #1D2731; padding: 0 10px; }
QTreeWidget::item:hover { background: #1A2A38; }
QTreeWidget::item:selected { background: #1E3A52; color: #FFFFFF; }
QHeaderView::section { background: #26343F; color: #8E9DAA; border: none;
    padding: 8px 10px; font-size: 11px; }
"""


def _label(text: str, size: int = 12, colour: str = "#8E9DAA") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setStyleSheet(
        f"color: {colour}; font-size: {size}px; background: transparent; border: none;"
    )
    return label


def _tree() -> QTreeWidget:
    tree = QTreeWidget()
    tree.setColumnCount(2)
    tree.setRootIsDecorated(False)
    tree.setUniformRowHeights(True)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tree.setMouseTracking(True)
    tree.setStyleSheet(TREE_STYLE)
    tree.header().setStretchLastSection(False)
    tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    return tree


class FactionEditor(QFactionUnits):
    def __init__(
        self,
        faction: Faction,
        parent: Optional[QWidget] = None,
        *,
        side: str,
        in_use: Optional[Callable[[Any], Optional[str]]] = None,
    ) -> None:
        self.side = side
        super().__init__(
            faction,
            parent,
            show_jtac=True,
            show_doctrine=True,
            editable=True,
            in_use=in_use,
        )
        self.setFrameShape(QFrame.Shape.NoFrame)

    def _create_checkboxes(self, show_jtac: bool, show_doctrine: bool) -> None:
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        headline = card()
        head = QHBoxLayout(headline)
        head.setContentsMargins(16, 12, 16, 12)
        identity = QVBoxLayout()
        identity.setSpacing(4)
        accent = "#8FC3F0" if self.side == "OWNFOR" else "#D9645E"
        identity.addWidget(_label(self.side + "  /  FACTION", 11, accent))
        self.name_label = shrinkable(_label(self.faction.name, 20, "#F2F7FA"))
        identity.addWidget(self.name_label)
        self.summary = _label("")
        identity.addWidget(self.summary)
        head.addLayout(identity, 1)

        settings = QVBoxLayout()
        settings.setSpacing(6)
        settings.addWidget(make_transparent(caption("Doctrine")))
        self.doctrine_combo = QComboBox()
        styled_input(self.doctrine_combo, 200)
        doctrines = list(ALL_DOCTRINES)
        if self.faction.doctrine not in doctrines:
            doctrines.insert(0, self.faction.doctrine)
        for doctrine in doctrines:
            self.doctrine_combo.addItem(doctrine.name, doctrine)
        self.doctrine_combo.setCurrentText(self.faction.doctrine.name)
        self.doctrine_combo.currentIndexChanged.connect(self._set_doctrine)
        settings.addWidget(self.doctrine_combo)
        self.jtac = QCheckBox("JTAC support")
        self.jtac.setChecked(self.faction.has_jtac)
        self.jtac.setStyleSheet(
            "QCheckBox { color: #B7C6D2; font-size: 12px; background: transparent; }"
        )
        self.jtac.toggled.connect(self._set_jtac)
        settings.addWidget(self.jtac)
        head.addLayout(settings)
        layout.addWidget(headline)

        body = QHBoxLayout()
        body.setSpacing(16)
        navigation = QVBoxLayout()
        navigation.setSpacing(8)
        navigation.addWidget(caption("Equipment pools"))
        self.categories = _tree()
        self.categories.setHeaderHidden(True)
        self.categories.setFixedWidth(248)
        for title, *_ in POOLS:
            self.categories.addTopLevelItem(QTreeWidgetItem([title, ""]))
        navigation.addWidget(self.categories, 1)
        body.addLayout(navigation)

        detail = QVBoxLayout()
        detail.setSpacing(8)
        self.pool_title = _label("", 14, "#F2F7FA")
        detail.addWidget(self.pool_title)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter this pool…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Filter faction equipment")
        styled_input(self.search)
        self.search.textChanged.connect(self._filter)
        toolbar.addWidget(self.search, 1)
        self.count_label = _label("")
        toolbar.addWidget(self.count_label)
        detail.addLayout(toolbar)

        self.units = _tree()
        self.units.setHeaderLabels(["UNIT TYPE", "CAMPAIGN USE"])
        self.units.itemSelectionChanged.connect(self._selection_changed)
        detail.addWidget(self.units, 1)
        self.empty = _label("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.addWidget(self.empty)

        actions = QHBoxLayout()
        self.selection_hint = shrinkable(
            _label("Select a unit to inspect its availability.")
        )
        actions.addWidget(self.selection_hint, 1)
        self.remove_button = button("Remove selected", handler=self._remove_selected)
        self.remove_button.setAutoDefault(False)
        self.remove_button.setEnabled(False)
        actions.addWidget(self.remove_button)
        detail.addLayout(actions)
        detail.addWidget(caption("Add to faction"))
        self.add_holder = QWidget()
        self.add_layout = QVBoxLayout(self.add_holder)
        self.add_layout.setContentsMargins(0, 0, 0, 0)
        detail.addWidget(self.add_holder)
        body.addLayout(detail, 1)
        layout.addLayout(body, 1)
        layout.addWidget(
            _label("Changes apply immediately to this faction’s available equipment.")
        )
        self.categories.currentItemChanged.connect(self._category_changed)
        self._refresh_counts()
        self.categories.setCurrentItem(self.categories.topLevelItem(0))

    def _refresh_counts(self) -> None:
        total = 0
        for index, (_, attribute, *_) in enumerate(POOLS):
            count = len(getattr(self.faction, attribute))
            total += count
            item = self.categories.topLevelItem(index)
            item.setText(1, str(count))
            item.setTextAlignment(
                1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.summary.setText(
            f"{total} catalogue entries  ·  {len(POOLS)} equipment pools"
        )

    def _category_changed(self, *_: Any) -> None:
        self.search.clear()
        self._populate()

    def _populate(self) -> None:
        index = self.categories.indexOfTopLevelItem(self.categories.currentItem())
        title, attribute, combo_name, source = POOLS[index]
        self.pool_title.setText(title)
        self.collection = getattr(self.faction, attribute)
        self.units.clear()
        for unit in sorted(self.collection, key=lambda value: str(value).casefold()):
            reason = self.in_use(unit) if self.in_use else None
            item = QTreeWidgetItem([str(unit), "In use" if reason else "Not in use"])
            item.setData(0, Qt.ItemDataRole.UserRole, unit)
            item.setData(1, Qt.ItemDataRole.UserRole, reason)
            item.setForeground(1, QColor("#E0A86B" if reason else "#8E9DAA"))
            item.setToolTip(0, str(unit))
            item.setToolTip(1, reason or "Can be removed from this faction.")
            self.units.addTopLevelItem(item)

        # Replace only the add controls; the navigation and search keep their state.
        while self.add_layout.count():
            old = self.add_layout.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        holder = QWidget()
        combo = SearchableComboBox(placeholder=f"Find in {title.lower()}…")
        combo.setMinimumContentsLength(20)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setAccessibleName(f"Add to {title.lower()}")
        setattr(self, combo_name, combo)
        if isinstance(source, list):
            row = self._create_unit_combobox(
                combo,
                lambda: self._on_add_unit(self.collection, combo),
                self.collection,
                source,
            )
        elif source == "naval":
            row = self._create_naval_combobox(
                combo, lambda: self._on_add_unit(self.collection, combo)
            )
        elif source == "presets":
            row = self._create_preset_group_combobox(
                combo, lambda: self._on_add_preset_group(self.collection, combo)
            )
        else:
            predicate = getattr(self, f"_{source}_predicate")
            row = self._create_aircraft_combobox(
                combo, lambda: self._on_add_ac(self.collection, combo), predicate
            )
        holder.setLayout(row)
        if source == "presets":
            self.add_button.setText("Add group")
        self.add_layout.addWidget(holder)
        self._filter(self.search.text())
        self._selection_changed()

    def _format(self, cb: QComboBox, callback: Callable) -> QHBoxLayout:
        styled_input(cb)
        add = button("Add unit", "primary", callback)
        self.add_button = add
        add.setAutoDefault(False)
        add.setEnabled(cb.count() > 0)
        cb.setEnabled(cb.count() > 0)
        if not cb.count():
            cb.setPlaceholderText("No more entries available")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(cb, 1)
        row.addWidget(add)
        return row

    def _filter(self, text: str) -> None:
        needle = text.strip().casefold()
        visible = 0
        total = self.units.topLevelItemCount()
        for index in range(total):
            item = self.units.topLevelItem(index)
            matches = needle in item.text(0).casefold()
            item.setHidden(not matches)
            visible += matches
            if not matches:
                item.setSelected(False)
        self.count_label.setText(
            f"{visible} of {total}" if needle else f"{total} entries"
        )
        self.empty.setText(
            "No matching units." if total else "This pool is empty. Add a unit below."
        )
        self.empty.setVisible(visible == 0)

    def _selection_changed(self) -> None:
        selected = self.units.selectedItems()
        reason = selected[0].data(1, Qt.ItemDataRole.UserRole) if selected else None
        self.remove_button.setEnabled(bool(selected) and not reason)
        hint = (
            f"In use: {reason}."
            if reason
            else (
                "Available to remove from this faction."
                if selected
                else "Select a unit to inspect its availability."
            )
        )
        self.selection_hint.setText(hint)
        self.selection_hint.setToolTip(hint)
        self.remove_button.setToolTip(hint)

    def _remove_selected(self) -> None:
        selected = self.units.selectedItems()
        if selected:
            self._on_remove_unit(
                selected[0].data(0, Qt.ItemDataRole.UserRole), self.collection
            )

    def updateFaction(self, faction: Faction) -> None:
        self.faction = faction
        self.name_label.setText(faction.name)
        position = self.units.verticalScrollBar().value()
        self._refresh_counts()
        self._populate()
        self.units.verticalScrollBar().setValue(position)

    def _set_doctrine(self, index: int) -> None:
        super()._set_doctrine(index)
        self.faction_changed.emit(self.faction)

    def _set_jtac(self, state: bool) -> None:
        super()._set_jtac(state)
        self.faction_changed.emit(self.faction)
