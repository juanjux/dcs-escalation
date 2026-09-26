"""Autosaved player notes for the selected aircraft."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QComboBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from qt_ui.windows.playable.model import Aircraft


class AircraftNotesPane(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.aircraft: Optional[Aircraft] = None
        self.pilot: Any = None
        layout = QVBoxLayout(self)
        self.players = QComboBox()
        self.players.currentIndexChanged.connect(self._select_pilot)
        layout.addWidget(self.players)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Checklists, radio frequencies, reminders…")
        self.editor.textChanged.connect(self._save)
        layout.addWidget(self.editor, 1)
        note = QLabel(
            "Saved automatically with the campaign, per pilot and aircraft type. Included on the kneeboard; DCS shares pages between aircraft of the same type."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #B7C6D2; font-size: 11px;")
        layout.addWidget(note)

    def show_aircraft(self, aircraft: Optional[Aircraft]) -> None:
        self.aircraft = aircraft
        self.players.blockSignals(True)
        self.players.clear()
        if aircraft is not None:
            for member in aircraft.flight.iter_members():
                if member.is_player and member.pilot is not None:
                    self.players.addItem(member.pilot.name, member.pilot)
        self.players.blockSignals(False)
        self._select_pilot()

    def _select_pilot(self) -> None:
        self.pilot = self.players.currentData()
        self.editor.blockSignals(True)
        text = ""
        if self.pilot is not None and self.aircraft is not None:
            text = getattr(self.pilot, "aircraft_notes", {}).get(
                self.aircraft.dcs_id, ""
            )
        self.editor.setPlainText(text)
        self.editor.setEnabled(self.pilot is not None)
        self.editor.blockSignals(False)

    def _save(self) -> None:
        if self.pilot is None or self.aircraft is None:
            return
        if not hasattr(self.pilot, "aircraft_notes"):
            self.pilot.aircraft_notes = {}
        self.pilot.aircraft_notes[self.aircraft.dcs_id] = self.editor.toPlainText()


class CampaignNotesPane(QWidget):
    def __init__(self, game: Any) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        hint = QLabel("Shared campaign notes · included on every kneeboard")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        editor = QPlainTextEdit()
        editor.setPlainText(getattr(game, "notes", ""))
        editor.setEnabled(game is not None)
        editor.textChanged.connect(lambda: setattr(game, "notes", editor.toPlainText()))
        layout.addWidget(editor)
