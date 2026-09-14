import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile
import logging
from typing import Dict, Optional, Union, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from dcs import lua

from game import Game
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import mono
from game.ato.flight import Flight
from game.ato.flightmember import FlightMember
from game.data.weapons import Pylon
from game.persistency import payloads_dir
from qt_ui.blocksignals import block_signals
from qt_ui.windows.mission.flight.payload.QPylonEditor import QPylonEditor


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically.

    A payload .lua is read by pydcs (during mission generation) at the same time
    the user can save one here. Writing in place leaves a window where the file
    is truncated, which makes the reader choke on a half-written number. Write to
    a temp file in the same directory and os.replace() it into place so a reader
    only ever sees the old or the new file, never a partial one.
    """
    directory = path.parent
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class QLoadoutEditor(QWidget):
    """The pylons, and the switch that decides whether you may touch them.

    A checkable group box before, which meant the switch was the section's title and
    the section's title was a switch. It is a plain card now with the checkbox in its
    own header row, so the caption above can name the section and the switch can look
    like a switch.
    """

    saved = Signal(str)
    #: Any pylon on any member changed.
    pylons_changed = Signal()
    #: Kept for the checkable-group-box API this used to have.
    toggled = Signal(bool)

    def __init__(self, flight: Flight, flight_member: FlightMember, game: Game) -> None:
        super().__init__()
        self.flight = flight
        self.flight_member = flight_member
        self.game = game

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self.custom_check = QCheckBox("Custom loadout")
        self.custom_check.setToolTip(
            "Off, the flight carries the selected preset. On, you choose each pylon."
        )
        self.custom_check.setChecked(flight_member.loadout.is_custom)
        self.custom_check.toggled.connect(self.toggled)
        self.custom_check.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        header = QHBoxLayout()
        header.setContentsMargins(14, 6, 14, 6)
        header.addWidget(self.custom_check)
        header.addStretch()
        header_holder = QWidget()
        make_transparent(header_holder)
        header_holder.setLayout(header)
        vbox.addWidget(header_holder)

        layout = QGridLayout()
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        for i, pylon in enumerate(Pylon.iter_pylons(self.flight.unit_type)):
            label = QLabel(str(pylon.number))
            label.setFont(mono(12))
            label.setFixedWidth(18)
            label.setStyleSheet(
                "color: #8E9DAA; background: transparent; border: none;"
            )
            label.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            )
            layout.addWidget(label, i, 0)
            editor = QPylonEditor(game, flight, flight_member, pylon)
            editor.setFixedHeight(30)
            editor.pylon_changed.connect(self.pylons_changed)
            layout.addWidget(editor, i, 1)

        vbox.addLayout(layout)

        footer = QHBoxLayout()
        footer.setContentsMargins(14, 8, 14, 4)
        footer.setSpacing(8)
        hint = QLabel("Turn on Custom loadout to edit pylons")
        hint.setStyleSheet(
            "font-size: 11px; color: #7C8B99; background: transparent; border: none;"
        )
        footer.addWidget(hint)
        footer.addStretch()

        self.purge_btn = QPushButton("Create backup")
        self.purge_btn.setProperty("style", "btn-success")
        self.purge_btn.setMaximumWidth(140)
        self.purge_btn.clicked.connect(self._backup_payloads)
        footer.addWidget(self.purge_btn)

        self.save_btn = QPushButton("Save payload")
        self.save_btn.setProperty("style", "btn-danger")
        self.save_btn.setMaximumWidth(140)
        self.save_btn.clicked.connect(self._save_payload)
        footer.addWidget(self.save_btn)

        footer_holder = QWidget()
        make_transparent(footer_holder)
        footer_holder.setLayout(footer)
        vbox.addWidget(footer_holder)

        self.hint = hint
        self.setLayout(vbox)

        self.custom_check.toggled.connect(self._sync_editable)
        self._sync_editable(self.custom_check.isChecked())

        for pylon_editor in self.iter_pylon_editors():
            pylon_editor.set_from(self.flight_member.loadout)

    # --- what the checkable group box used to give us -----------------------

    def isChecked(self) -> bool:  # noqa: N802 (Qt naming)
        return bool(self.custom_check.isChecked())

    def setChecked(self, checked: bool) -> None:  # noqa: N802 (Qt naming)
        self.custom_check.setChecked(checked)

    def _sync_editable(self, custom: bool) -> None:
        """Saving a payload only means anything once you have edited one."""
        self.save_btn.setEnabled(custom)
        self.hint.setVisible(not custom)
        for pylon_editor in self.iter_pylon_editors():
            pylon_editor.setEnabled(custom)

    def iter_pylon_editors(self) -> Iterator[QPylonEditor]:
        yield from self.findChildren(QPylonEditor)

    def set_flight_member(self, flight_member: FlightMember) -> None:
        self.flight_member = flight_member
        with block_signals(self):
            self.setChecked(self.flight_member.use_custom_loadout)
        for pylon_editor in self.iter_pylon_editors():
            pylon_editor.set_flight_member(flight_member)

    def _backup_payloads(self) -> None:
        ac_id = self.flight.unit_type.dcs_unit_type.id
        payload_file = payloads_dir() / f"{ac_id}.lua"
        if not payload_file.exists():
            return
        backup_folder = payloads_dir(backup=True)
        backup_file = backup_folder / f"{ac_id}.lua"
        copyfile(payload_file, backup_file)
        QMessageBox.information(
            QWidget(),
            "Backup Payload",
            f"Payload file for {self.flight.unit_type.dcs_unit_type.id} was backed up successfully.\n"
            f"Location: {backup_file}",
        )

    def _save_payload(self) -> None:
        payload_name_input = self._create_input_dialog()
        if not payload_name_input.exec_():
            return
        payload_name = payload_name_input.textValue()
        payload_file = self._persist_payload(payload_name)
        if payload_file is None:
            return
        self.saved.emit(payload_name)
        QMessageBox.information(
            QWidget(),
            "Payload Saved",
            f"Payload for {self.flight.unit_type.dcs_unit_type.id} was successfully saved.\n"
            f"Location: {payload_file}",
        )

    def save_as_task_default(self) -> None:
        """Make the selected payload the default for this aircraft + flight type.

        Records a mapping (aircraft, flight type) -> payload name that
        Loadout.default_for_task_and_aircraft consults first, so new flights of
        this aircraft + task start with this payload. The payload itself is NOT
        renamed or overwritten — this only changes which named payload is picked
        as the default. Custom (unsaved) loadouts must be saved + named first.
        """
        from game.ato.loadouts import set_default_loadout_override

        if self.isChecked() or self.flight_member.loadout.is_custom:
            QMessageBox.warning(
                QWidget(),
                "Set as default",
                'Save this as a named payload first ("Save Payload"), then select '
                "it from the list and set it as the default.",
            )
            return
        payload_name = self.flight_member.loadout.name
        ac_id = self.flight.unit_type.dcs_unit_type.id
        task = self.flight.flight_type
        reply = QMessageBox.question(
            QWidget(),
            "Set as default loadout",
            f'Make "{payload_name}" the default loadout for {ac_id} on '
            f"{task.value} missions?\n\n"
            f"It applies to NEW {task.value} flights only — flights already in the "
            f"ATO keep what they have.\n"
            f"It applies to BOTH sides: enemy {ac_id} flights on {task.value} get it "
            f"too.\n"
            f"It applies to every campaign until you clear it.\n\n"
            f"No payload file is modified — this only records which named payload "
            f"is picked.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        set_default_loadout_override(ac_id, task, payload_name)
        QMessageBox.information(
            QWidget(),
            "Default loadout set",
            f'"{payload_name}" is now the default loadout for {ac_id} on '
            f"{task.value} missions.",
        )

    def clear_task_default(self) -> None:
        """Drop the default payload for this aircraft + flight type, if any."""
        from game.ato.loadouts import (
            clear_default_loadout_override,
            get_default_loadout_override,
        )

        ac_id = self.flight.unit_type.dcs_unit_type.id
        task = self.flight.flight_type
        current = get_default_loadout_override(ac_id, task)
        if current is None:
            QMessageBox.information(
                QWidget(),
                "No default set",
                f"{ac_id} has no default loadout for {task.value} missions, so "
                f"there is nothing to clear.",
            )
            return
        reply = QMessageBox.question(
            QWidget(),
            "Clear default loadout",
            f'Stop using "{current}" as the default for {ac_id} on {task.value} '
            f"missions?\n\nNew flights will go back to the built-in choice. No "
            f"payload is deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        clear_default_loadout_override(ac_id, task)
        QMessageBox.information(
            QWidget(),
            "Default loadout cleared",
            f"{ac_id} is back to the built-in default for {task.value} missions.",
        )

    def _persist_payload(self, payload_name: str) -> Optional[Path]:
        """Write the payload into the aircraft's UnitPayloads file.

        Returns the file written, or None when nothing was written — the caller must
        not report success in that case. The in-memory payload table is updated only
        after the file is, so a failed write cannot leave memory and disk disagreeing.
        """
        ac_type = self.flight.unit_type.dcs_unit_type
        ac_id = ac_type.id
        payloads_folder = payloads_dir()
        payload_file = payloads_folder / f"{ac_id}.lua"
        entry = DcsPayload.from_flight_member(
            self.flight_member, payload_name
        ).to_dict()
        if payload_file.exists():
            self._create_backup_if_needed(ac_id)
            try:
                with payload_file.open("r", encoding="utf-8") as f:
                    payloads = lua.loads(f.read())
                pdict = payloads["unitPayloads"]["payloads"]
            except Exception:
                # An unparseable or unexpected file used to raise straight out of the
                # Qt slot, and one that merely parsed to nothing was skipped while
                # still reporting "saved". Leave it untouched and say what happened.
                logging.exception("Could not read %s", payload_file)
                QMessageBox.warning(
                    QWidget(),
                    "Payload not saved",
                    f"{payload_file} could not be read, so it was left untouched and "
                    f'"{payload_name}" was NOT saved.',
                )
                return None
            # The keys are the file's own numbering: they may have gaps or not start
            # at 1, so len()+1 could land on a live entry and overwrite it silently.
            numeric = [k for k in pdict if isinstance(k, int)]
            next_key = max(numeric) + 1 if numeric else 1
            for p in pdict:
                if pdict[p]["name"] == payload_name:
                    next_key = p
            pdict[next_key] = entry
            _atomic_write_text(
                payload_file,
                "local unitPayloads = "
                + lua.dumps(payloads["unitPayloads"], indent=1)
                + "\nreturn unitPayloads",
            )
        else:
            payloads = {
                "name": f"{ac_id}",
                "payloads": {
                    1: DcsPayload.from_flight_member(
                        self.flight_member, payload_name
                    ).to_dict(),
                },
                "unitType": f"{ac_id}",
            }
            _atomic_write_text(
                payload_file,
                "local unitPayloads = "
                + lua.dumps(payloads, indent=1)
                + "\nreturn unitPayloads",
            )
            ac_type.add_to_payload_cache(payload_file)
        ac_type.payloads[payload_name] = entry
        return payload_file

    def _create_backup_if_needed(self, ac_id):
        backup_file = payloads_dir(backup=True) / f"{ac_id}.lua"
        if not backup_file.exists():
            self._backup_payloads()

    def _create_input_dialog(self):
        payload_name_input = QInputDialog()
        payload_name_input.setWindowTitle("Save payload")
        payload_name_input.setLabelText("Enter a name for the payload to be saved:")
        payload_name_input.setTextValue(f"Custom {self.flight.flight_type.name}")
        payload_name_input.setFixedWidth(500)
        return payload_name_input

    def reset_pylons(self) -> None:
        self.flight_member.use_custom_loadout = self.isChecked()
        if not self.isChecked():
            for pylon_editor in self.iter_pylon_editors():
                pylon_editor.set_from(self.flight_member.loadout)


@dataclass
class DcsPayload:
    displayName: str
    name: str
    pylons: Dict[int, Dict[str, Union[str, int, Dict[str, Any]]]]
    tasks: Dict[int, int]

    @classmethod
    def from_flight_member(cls, member: FlightMember, payload_name: str):
        pylons = {}
        for i, nr in enumerate(member.loadout.pylons, 1):
            wpn = member.loadout.pylons[nr]
            clsid = wpn.clsid if wpn else "<CLEAN>"
            pylon_dict: Dict[str, Union[str, int, Dict[str, Any]]] = {
                "CLSID": clsid,
                "num": nr,
            }

            # Add weapon settings if present
            if nr in member.loadout.pylon_settings:
                settings = member.loadout.pylon_settings[nr]
                if settings:  # Only add if settings dict is non-empty
                    pylon_dict["settings"] = settings

            pylons[i] = pylon_dict

        return DcsPayload(
            f"{payload_name}",
            f"{payload_name}",
            pylons=pylons,
            tasks={1: 31},
        )

    def to_dict(self):
        return {
            "displayName": self.displayName,
            "name": self.name,
            "pylons": self.pylons,
            "tasks": self.tasks,
        }
