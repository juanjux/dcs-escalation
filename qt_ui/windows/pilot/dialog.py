"""The pilot dialog: what he has done on the left, how he is on the right.

The record only grows; the state changes every turn. Keeping them in separate columns is
what lets a dead pilot use the same layout with the right column frozen and a card added
at the top left.

Built from the pilot and the game, and finds his squadron itself, so anything holding a
pilot can open it.
"""

from __future__ import annotations

from typing import Callable, Optional
from uuid import UUID

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qt_ui.uiconstants import app_settings
from game.game import Game
from game.squadrons.pilot import Pilot
from game.squadrons.squadron import Squadron
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import button
from qt_ui.windows.pilot.cheats import CheatStrip
from qt_ui.windows.pilot.common import LINE, PANEL, TEXT_LABEL, label
from qt_ui.windows.pilot.header import PilotHeader
from qt_ui.windows.pilot.record import record_column
from qt_ui.windows.pilot.state import relationships_section, state_column

DIALOG_WIDTH = 920
DIALOG_HEIGHT = 760
MIN_WIDTH = 860
MIN_HEIGHT = 680

#: The state column is a fixed width because its cards are read as a pair and a bar
#: that changes length between pilots cannot be compared with the last one.
STATE_WIDTH = 400
FOOTER_HEIGHT = 56

QSETTINGS_GEOMETRY = "pilotDialog/geometry"


def squadron_of(game: Game, pilot: Pilot) -> Optional[Squadron]:
    """Which squadron he belongs to, asked of the game rather than of him.

    A pilot does not carry his squadron -- the roster is the squadron's -- so this is
    the one place that walks the wings to find him.
    """
    for coalition in game.coalitions:
        for squadron in coalition.air_wing.iter_squadrons():
            if any(other is pilot for other in squadron.current_roster):
                return squadron
    return None


class PilotDialog(QDialog):
    """Everything one campaign remembers about one man."""

    #: Something was done to him that the lists he was opened from should know about.
    pilot_changed = Signal()

    def __init__(
        self,
        pilot: Pilot,
        game: Game,
        parent: Optional[QWidget] = None,
        open_squadron: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.pilot = pilot
        self.game = game
        self.open_squadron = open_squadron
        squadron = squadron_of(game, pilot)
        if squadron is None:
            raise RuntimeError(f"{pilot.name} belongs to no squadron in this game")
        self.squadron = squadron

        self.setWindowTitle(f"Pilot — {pilot.name}")
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setStyleSheet(
            "QDialog { background: #2D3E50; }" "QLabel { background: transparent; }"
        )

        self.root = QVBoxLayout()
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)
        self.setLayout(self.root)

        self.content = self._build()
        self.root.addWidget(self.content)
        self._restore_geometry()

    # -- the whole of it ------------------------------------------------------

    def _build(self) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        holder.setLayout(column)

        column.addWidget(PilotHeader(self.pilot, self.squadron))
        if self.game.settings.enable_pilot_cheats:
            strip = CheatStrip(self.pilot, self.squadron)
            strip.changed.connect(self._changed)
            column.addWidget(strip)
        column.addWidget(self._body(), 1)
        column.addWidget(self._footer())
        return holder

    def _body(self) -> QWidget:
        """The two columns, in a scroll area: a long record must not clip the footer."""
        inner = QWidget()
        make_transparent(inner)
        columns = QHBoxLayout()
        columns.setContentsMargins(20, 18, 20, 20)
        columns.setSpacing(20)
        inner.setLayout(columns)

        wing = self._wing()
        columns.addLayout(
            record_column(
                self.pilot,
                relationships_section(self.pilot, self.squadron, wing),
            ),
            1,
        )
        state = state_column(self.pilot, self.squadron, wing)
        if state is not None:
            holder = QWidget()
            make_transparent(holder)
            holder.setFixedWidth(STATE_WIDTH)
            holder.setLayout(state)
            columns.addWidget(holder)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        area.setWidget(inner)
        return area

    def _wing(self) -> dict[UUID, tuple[Squadron, Pilot]]:
        """Everybody a friendship of his could be about."""
        return self.squadron.coalition.air_wing.pilot_index()

    def _footer(self) -> QWidget:
        footer = QWidget()
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer.setObjectName("pilotFooter")
        footer.setStyleSheet(
            f"#pilotFooter {{ background: {PANEL}; border-top: 1px solid {LINE}; }}"
        )
        footer.setFixedHeight(FOOTER_HEIGHT)

        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(8)
        footer.setLayout(row)
        row.addWidget(
            label(f"{self.squadron} · {self.squadron.location.name}", 11.5, TEXT_LABEL)
        )
        row.addStretch()
        if self.open_squadron is not None:
            row.addWidget(button("Open squadron", handler=self._open_squadron))
            row.addSpacing(8)
        row.addWidget(button("Close", "primary", self.close))
        return footer

    # -- keeping up with what the cheats did ----------------------------------

    def _changed(self) -> None:
        """Rebuilt rather than patched: a rename moves the title, a promotion moves the
        stars, the bar and the ladder, and a revival moves half the dialog."""
        self.pilot_changed.emit()
        # Deferred: the strip that asked for this is inside what is about to be
        # deleted, and it is still in the middle of its own signal.
        QTimer.singleShot(0, self._rebuild)

    def _rebuild(self) -> None:
        self.setWindowTitle(f"Pilot — {self.pilot.name}")
        old = self.content
        self.content = self._build()
        self.root.replaceWidget(old, self.content)
        old.setParent(None)
        old.deleteLater()

    def _open_squadron(self) -> None:
        if self.open_squadron is not None:
            self.open_squadron()

    # -- where it was last time -----------------------------------------------

    @staticmethod
    def _qsettings() -> QSettings:
        return app_settings()

    def _restore_geometry(self) -> None:
        saved = self._qsettings().value(QSETTINGS_GEOMETRY)
        if saved is not None:
            self.restoreGeometry(saved)
        else:
            self.resize(DIALOG_WIDTH, DIALOG_HEIGHT)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._qsettings().setValue(QSETTINGS_GEOMETRY, self.saveGeometry())
        super().closeEvent(event)
