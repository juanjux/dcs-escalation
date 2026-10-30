"""Squadron drawing management, synchronized with the main map."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game.ato.savedpoints import drawings_of
from game.server.savedpoints.notifications import publish_points_changed
from qt_ui.widgets.controls import style_button


class DrawingsPane(QWidget):
    def __init__(self, game: Any) -> None:
        super().__init__()
        self.game = game
        self.aircraft: Any = None
        self.setObjectName("saved-drawings-pane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#saved-drawings-pane { background: #202B36; }")
        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background: #15212B; color: #D3DFE8; border: 1px solid #3A4B5C; }"
            "QListWidget::item { padding: 9px; }"
            "QListWidget::item:selected { background: #294B66; color: #FFFFFF; }"
        )
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rename = QPushButton("Rename")
        self.delete = QPushButton("Delete")
        self.show_map = QPushButton("Show on map")
        self.help = QLabel(
            "Use Draw on the main map to save lines and areas for this squadron. "
            "All drawings reach the map and kneeboard. Cockpit export is limited: "
            "Hornet/CJS: 2 outlines of 7 points; Viper: 3 outlines sharing 15 points; "
            "Apache: available TSD lines and four-corner areas. "
            "Extra vertices are simplified for Hornet/Viper export only. "
            "Other aircraft, including the A-10, use map and kneeboard only."
        )
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color: #B7C6D2; font-size: 11px; padding: 4px;")
        bar = QHBoxLayout()
        for button in (self.rename, self.delete, self.show_map):
            style_button(button)
            bar.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.help)
        layout.addWidget(self.list)
        layout.addLayout(bar)
        self.rename.clicked.connect(self.rename_current)
        self.delete.clicked.connect(self.delete_current)
        self.show_map.clicked.connect(self.show_current)
        self.list.itemDoubleClicked.connect(lambda _: self.rename_current())
        self.list.currentRowChanged.connect(lambda _: self._enable())

    def show_aircraft(self, aircraft: Any) -> None:
        self.aircraft = aircraft
        self.refresh()

    def refresh(self) -> None:
        current = self.list.currentItem()
        identity = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.list.clear()
        if self.aircraft is not None:
            for drawing in drawings_of(self.aircraft.flight):
                item = QListWidgetItem(
                    f"{drawing.name} · {'Area' if drawing.closed else 'Line'} "
                    f"· {len(drawing.points)} vertices"
                )
                item.setData(Qt.ItemDataRole.UserRole, drawing.id)
                self.list.addItem(item)
                if drawing.id == identity:
                    self.list.setCurrentItem(item)
        self._enable()

    def _selected(self) -> Any:
        item = self.list.currentItem()
        if item is None or self.aircraft is None:
            return None
        identity: UUID = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (d for d in drawings_of(self.aircraft.flight) if d.id == identity), None
        )

    def _enable(self) -> None:
        for button in (self.rename, self.delete, self.show_map):
            button.setEnabled(self._selected() is not None)

    def rename_current(self) -> None:
        drawing = self._selected()
        if drawing is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename drawing", "Name", text=drawing.name
        )
        # A map edit may have removed the object while the modal dialog was open.
        if ok and name.strip() and self._selected() is drawing:
            drawing.name = name.strip()[:24]
            self.refresh()
            publish_points_changed()

    def delete_current(self) -> None:
        drawing = self._selected()
        if drawing is not None:
            drawings = drawings_of(self.aircraft.flight)
            drawings[:] = [one for one in drawings if one is not drawing]
            self.refresh()
            publish_points_changed()

    def show_current(self) -> None:
        drawing = self._selected()
        if drawing is None or self.game is None:
            return
        from dcs.mapping import Point
        from game.server import EventStream
        from game.sim import GameUpdateEvents

        x = sum(p[0] for p in drawing.points) / len(drawing.points)
        y = sum(p[1] for p in drawing.points) / len(drawing.points)
        EventStream.put_nowait(
            GameUpdateEvents().look_at(
                Point(x, y, self.game.theater.terrain).latlng(), 10
            )
        )
