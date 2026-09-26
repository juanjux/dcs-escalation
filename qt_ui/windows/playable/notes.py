"""Autosaved player notes for the selected aircraft."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget

from qt_ui.windows.playable.model import Aircraft


class AircraftNotesPane(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.aircraft: Optional[Aircraft] = None
        self.editors: list[QPlainTextEdit] = []
        layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)
        note = QLabel(
            "Saved automatically with the campaign, per pilot and aircraft type. Included on the kneeboard; DCS shares pages between aircraft of the same type."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #B7C6D2; font-size: 11px;")
        layout.addWidget(note)
        self.show_aircraft(None)

    def show_aircraft(self, aircraft: Optional[Aircraft]) -> None:
        self.aircraft = aircraft
        self.editors = []
        content = QWidget()
        fields = QVBoxLayout(content)
        fields.setContentsMargins(0, 0, 0, 0)
        pilots = (
            [
                member.pilot
                for member in aircraft.flight.iter_members()
                if member.is_player and member.pilot is not None
            ]
            if aircraft is not None
            else []
        )
        airframe = aircraft.dcs_id if aircraft is not None else ""
        for pilot in pilots or [None]:
            if len(pilots) > 1:
                fields.addWidget(QLabel(pilot.name))
            editor = QPlainTextEdit()
            editor.setMinimumHeight(120)
            editor.setPlaceholderText(
                "Checklists, radio frequencies, reminders…"
                if pilot is not None
                else "Select an aircraft to edit its notes."
            )
            editor.setAccessibleName(
                f"Aircraft notes for {pilot.name}"
                if pilot is not None
                else "Aircraft notes"
            )
            editor.setPlainText(getattr(pilot, "aircraft_notes", {}).get(airframe, ""))
            editor.setEnabled(pilot is not None)
            editor.textChanged.connect(
                lambda p=pilot, kind=airframe, field=editor: self._save(p, kind, field)
            )
            fields.addWidget(editor, 1)
            self.editors.append(editor)
        self.scroll.setWidget(content)

    @staticmethod
    def _save(pilot: Any, airframe: str, editor: QPlainTextEdit) -> None:
        if pilot is None:
            return
        if not hasattr(pilot, "aircraft_notes"):
            pilot.aircraft_notes = {}
        pilot.aircraft_notes[airframe] = editor.toPlainText()


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
