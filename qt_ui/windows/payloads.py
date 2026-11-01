"""Aircraft payload library, independent of the campaign and flight roster."""

from __future__ import annotations

import copy
from typing import Any

from dcs import task
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.data.gunammunition import GAU8_AIRCRAFT, GAU8_AMMUNITION
from game.data.weapons import Pylon, Weapon
from game.dcs.aircrafttype import AircraftType
from game.payloadlibrary import PayloadEntry, PayloadLibrary
from qt_ui.blocksignals import block_signals
from qt_ui.widgets.searchablecombo import SearchableComboBox
from qt_ui.windows.mission.flight.payload.QWeaponSettingsDialog import (
    QWeaponSettingsDialog,
)


class PayloadsDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, aircraft: AircraftType | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Payloads editor")
        self.resize(1160, 820)
        self.library = PayloadLibrary()
        self.modified = False
        self.dirty = False
        self.entry: PayloadEntry | None = None
        self.draft: dict[str, Any] = {}
        self._aircraft_index = 0
        self.pylons: dict[int, SearchableComboBox] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(QLabel("Aircraft"))
        self.aircraft_combo = SearchableComboBox(placeholder="Find an aircraft…")
        self.aircraft_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.aircraft_combo.setMinimumContentsLength(28)
        by_id = {a.dcs_id: a for a in AircraftType.iter_all()}
        if aircraft is not None:
            by_id[aircraft.dcs_id] = aircraft
        for airframe in sorted(by_id.values(), key=lambda a: a.display_name.casefold()):
            self.aircraft_combo.addItem(
                f"{airframe.display_name} ({airframe.dcs_id})", airframe
            )
        if aircraft is not None:
            self.aircraft_combo.setCurrentIndex(self.aircraft_combo.findData(aircraft))
        self._aircraft_index = self.aircraft_combo.currentIndex()
        row.addWidget(self.aircraft_combo, 1)
        outer.addLayout(row)
        hint = QLabel(
            "Presets are shared by all campaigns. Editing this library does not change "
            "payloads already assigned to flights. Escalation originals can be restored."
        )
        hint.setWordWrap(True)
        outer.addWidget(hint)
        splitter = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(290)
        splitter.addWidget(self.tree)
        self.editor_scroll = QScrollArea()
        self.editor_scroll.setWidgetResizable(True)
        splitter.addWidget(self.editor_scroll)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        buttons = QHBoxLayout()
        self.new_button = QPushButton("New payload")
        self.new_button.clicked.connect(self.new_payload)
        buttons.addWidget(self.new_button)
        self.copy_button = QPushButton("Duplicate as Custom")
        self.copy_button.clicked.connect(self.duplicate)
        buttons.addWidget(self.copy_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setProperty("style", "btn-danger")
        self.delete_button.clicked.connect(self.delete_payload)
        buttons.addWidget(self.delete_button)
        self.restore_button = QPushButton("Restore Escalation presets…")
        self.restore_button.clicked.connect(self.restore)
        buttons.addWidget(self.restore_button)
        buttons.addStretch()
        self.save_button = QPushButton("Save changes")
        self.save_button.setDefault(True)
        self.save_button.setProperty("style", "btn-primary")
        self.save_button.clicked.connect(self.save_payload)
        buttons.addWidget(self.save_button)
        close = QPushButton("Close")
        close.setProperty("style", "btn-primary")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)
        self.aircraft_combo.currentIndexChanged.connect(self._change_aircraft)
        self.tree.currentItemChanged.connect(self._select)
        self._reload()

    @property
    def aircraft(self) -> AircraftType:
        return self.aircraft_combo.currentData()

    def _reload(self, name: str | None = None, source: str | None = None) -> None:
        read_error = None
        with block_signals(self.tree):
            self.tree.clear()
            roots = {
                label: QTreeWidgetItem(self.tree, [label])
                for label in ("Escalation", "Custom")
            }
            selected = None
            try:
                entries = self.library.entries(self.aircraft.dcs_id)
            except Exception as error:
                read_error = str(error)
                entries = []
            for entry in entries:
                item = QTreeWidgetItem(roots[entry.source], [entry.name])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(0, f"{entry.name}\n{entry.path}")
                if entry.name == name and (source is None or entry.source == source):
                    selected = item
            for root in roots.values():
                root.setFlags(Qt.ItemFlag.ItemIsEnabled)
                root.setExpanded(True)
                if root.childCount() and selected is None:
                    selected = root.child(0)
            self._set_current(selected)
        self._load_entry(
            selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        )
        self.status.setToolTip("")
        if read_error is not None:
            self.status.setText(read_error)
        elif self.library.errors:
            self.status.setText(
                f"{len(self.library.errors)} payload file(s) could not be read and were left untouched. Hover for details."
            )
            self.status.setToolTip("\n".join(self.library.errors))

    def _set_current(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            self.tree.setCurrentIndex(QModelIndex())
        else:
            self.tree.setCurrentItem(item)

    def _pending(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved payload",
            "Save changes to this payload?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_payload()
        if answer == QMessageBox.StandardButton.Discard:
            self._load_entry(self.entry)
            return True
        return False

    def _change_aircraft(self, index: int) -> None:
        # Save pending changes against the old airframe, not the new selection.
        with block_signals(self.aircraft_combo):
            self.aircraft_combo.setCurrentIndex(self._aircraft_index)
        if not self._pending():
            return
        with block_signals(self.aircraft_combo):
            self.aircraft_combo.setCurrentIndex(index)
        self._aircraft_index = index
        self.dirty = False
        self._reload()

    def _select(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None
    ) -> None:
        entry = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if not self._pending():
            with block_signals(self.tree):
                self._set_current(previous)
            return
        if self.tree.currentItem() is not current and entry is not None:
            # Saving pending changes rebuilds the tree and deletes its old items.
            self._reload(entry.name, entry.source)
            return
        self._load_entry(entry)

    def _load_entry(self, entry: PayloadEntry | None) -> None:
        self.entry = entry
        self.draft = (
            copy.deepcopy(entry.payload)
            if entry
            else {"name": "New payload", "pylons": {}, "tasks": {1: 31}}
        )
        self.dirty = False
        self.status.setText(
            f"{entry.source}: {entry.name}" if entry else "Create a new Custom payload."
        )
        self._build_editor()
        self.delete_button.setEnabled(entry is not None)
        self.save_button.setEnabled(False)

    def _changed(self, *_args: Any) -> None:
        self.dirty = True
        self.save_button.setEnabled(True)

    def _build_editor(self) -> None:
        old = self.editor_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        form = QFormLayout()
        self.name_edit = QLineEdit(self.draft["name"])
        self.name_edit.textEdited.connect(self._changed)
        form.addRow("Name", self.name_edit)
        self.ammo_combo = QComboBox()
        self.ammo_combo.addItem("Aircraft default", None)
        for value, label in GAU8_AMMUNITION.items():
            self.ammo_combo.addItem(label, value)
        ammo = self.draft.get("ammo_type")
        if ammo is not None and self.ammo_combo.findData(ammo) < 0:
            self.ammo_combo.addItem(f"Unknown ammunition ({ammo})", ammo)
        self.ammo_combo.setCurrentIndex(
            max(0, self.ammo_combo.findData(self.draft.get("ammo_type")))
        )
        self.ammo_combo.currentIndexChanged.connect(self._changed)
        if self.aircraft.dcs_id in GAU8_AIRCRAFT:
            form.addRow("GAU-8 ammunition", self.ammo_combo)
        layout.addLayout(form)
        self.training = QCheckBox("Show training and non-combat stores")
        self.training.toggled.connect(self._refresh_weapons)
        layout.addWidget(self.training)
        self.pylons = {}
        stations = {p.number: p for p in Pylon.iter_pylons(self.aircraft)}
        for station in self.draft.get("pylons", {}).values():
            number = station["num"]
            stations.setdefault(number, Pylon(number, set()))
        for number, pylon in sorted(stations.items()):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Station {number}"))
            combo = SearchableComboBox(placeholder="Find a weapon…")
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(24)
            combo.setProperty("pylon", pylon)
            self.pylons[number] = combo
            self._populate(combo, self._station(number).get("CLSID", ""))
            combo.currentIndexChanged.connect(
                lambda _i, n=number: self._weapon_changed(n)
            )
            row.addWidget(combo, 1)
            settings = QPushButton("Settings…")
            settings.clicked.connect(lambda _checked=False, n=number: self._settings(n))
            row.addWidget(settings)
            layout.addLayout(row)
        layout.addWidget(QLabel("Mission roles"))
        self.roles = QListWidget()
        self.roles.setMaximumHeight(180)
        active = set(self.draft.get("tasks", {}).values())
        for role in sorted(task.MainTask.map.values(), key=lambda t: t.__name__):
            item = QListWidgetItem(role.__name__, self.roles)
            item.setData(Qt.ItemDataRole.UserRole, role.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if role.id in active else Qt.CheckState.Unchecked
            )
        self.roles.itemChanged.connect(self._changed)
        layout.addWidget(self.roles)
        layout.addStretch()
        self.editor_scroll.setWidget(content)

    def _station(self, number: int) -> dict[str, Any]:
        return next(
            (v for v in self.draft.get("pylons", {}).values() if v["num"] == number), {}
        )

    def _populate(self, combo: SearchableComboBox, clsid: str) -> None:
        pylon = combo.property("pylon")
        with block_signals(combo):
            combo.clear()
            combo.addItem("None", "")
            combo.addItem("Clean", "<CLEAN>")
            for weapon in sorted(pylon.allowed, key=lambda w: w.name.casefold()):
                if (
                    self.training.isChecked()
                    or not weapon.is_training_or_non_combat
                    or weapon.clsid == clsid
                ):
                    combo.addItem(weapon.name, weapon.clsid)
            index = combo.findData(clsid)
            if index < 0:
                weapon = Weapon.with_clsid(clsid)
                combo.addItem(
                    weapon.name if weapon else f"Unknown store: {clsid}", clsid
                )
                index = combo.count() - 1
            combo.setCurrentIndex(index)

    def _refresh_weapons(self) -> None:
        for combo in self.pylons.values():
            self._populate(combo, combo.currentData())

    def _weapon_changed(self, number: int) -> None:
        pylons = self.draft.setdefault("pylons", {})
        key = next((k for k, v in pylons.items() if v["num"] == number), None)
        if key is None:
            key = max((k for k in pylons if isinstance(k, int)), default=0) + 1
        # Only replacing a store resets its weapon-specific settings.
        clsid = self.pylons[number].currentData()
        if clsid:
            pylons[key] = {"num": number, "CLSID": clsid}
        else:
            pylons.pop(key, None)
        self._changed()

    def _settings(self, number: int) -> None:
        station = self._station(number)
        weapon = Weapon.with_clsid(station.get("CLSID", ""))
        if weapon is None or not weapon.has_settings():
            QMessageBox.information(
                self, "Weapon settings", "This store has no configurable settings."
            )
            return
        dialog = QWeaponSettingsDialog(weapon, station.get("settings"), self)
        if dialog.exec():
            station["settings"] = {
                **station.get("settings", {}),
                **dialog.get_settings_dict(),
            }
            self._changed()

    def save_payload(self) -> bool:
        payload = copy.deepcopy(self.draft)
        payload["name"] = self.name_edit.text().strip()
        # Preserve unrecognised role IDs as well as the roles shown in the UI.
        known_roles = {
            self.roles.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.roles.count())
        }
        ids = set(payload.get("tasks", {}).values()) - known_roles
        ids.update(
            self.roles.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.roles.count())
            if self.roles.item(i).checkState() == Qt.CheckState.Checked
        )
        payload["tasks"] = dict(enumerate(sorted(ids), 1))
        if self.aircraft.dcs_id in GAU8_AIRCRAFT:
            if self.ammo_combo.currentData() is None:
                payload.pop("ammo_type", None)
            else:
                payload["ammo_type"] = self.ammo_combo.currentData()
        try:
            self.library.save(self.aircraft.dcs_unit_type, payload, self.entry)
        except Exception as error:
            QMessageBox.warning(self, "Payload not saved", str(error))
            return False
        source = self.entry.source if self.entry else "Custom"
        self.dirty = False
        self.modified = True
        self._reload(payload["name"], source)
        return True

    def new_payload(self) -> None:
        if self._pending():
            with block_signals(self.tree):
                self._set_current(None)
            self._load_entry(None)
            self._changed()

    def duplicate(self) -> None:
        if not self._pending():
            return
        draft = copy.deepcopy(self.draft)
        draft["name"] = self.name_edit.text() + " copy"
        self.entry = None
        self.draft = draft
        self._build_editor()
        self.delete_button.setEnabled(False)
        self._changed()

    def delete_payload(self) -> None:
        if self.entry is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete payload",
                f'Delete "{self.entry.name}"? Existing flights keep their assigned payload.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.library.delete(self.aircraft.dcs_unit_type, self.entry)
        except Exception as error:
            QMessageBox.warning(self, "Payload not deleted", str(error))
            return
        self.modified = True
        self.dirty = False
        self._reload()

    def restore(self) -> None:
        if not self._pending():
            return
        if (
            QMessageBox.question(
                self,
                "Restore Escalation presets",
                "Restore all original Escalation presets for this aircraft? Custom payloads will not change.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.library.restore_builtins(self.aircraft.dcs_unit_type)
        except Exception as error:
            QMessageBox.warning(self, "Presets not restored", str(error))
            return
        self.modified = True
        self.dirty = False
        self._reload()

    def reject(self) -> None:
        if self._pending():
            super().reject()
