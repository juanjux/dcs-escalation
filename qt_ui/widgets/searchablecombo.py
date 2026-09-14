"""A combo box you can type into to narrow a long list.

A preset list runs to a few hundred payloads, a livery list to every skin the community
has made for the airframe, and the predefined-waypoint list to every feature on the map.
Finding one in a plain combo means scrolling a list sorted by a rule you did not choose.

This puts a search field at the top of the popup: type, and the list narrows to the
items that contain what you typed, in order. Nothing else about the combo changes --
the same items, the same data, the same signals -- so a caller only has to construct a
different class.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
)

SEARCH_HEIGHT = 26

#: Below this many items, a search field is furniture: the list already fits on screen
#: and typing is slower than looking.
WORTH_SEARCHING = 12

#: Loadout lists are the exception. The names are long, arbitrary and community-made
#: ("SEAD mio", "CAP LONG RANGE 2"), so even a short one is read rather than scanned,
#: and an aircraft that has three today has thirty the day its presets are imported.
LOADOUT_SEARCH_FLOOR = 2


class SearchableComboBox(QComboBox):
    """A combo whose popup opens with a search field above the list."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        placeholder: str = "Type to filter…",
        threshold: int = WORTH_SEARCHING,
    ) -> None:
        super().__init__(parent)
        self.threshold = threshold

        self._popup = QWidget(self, Qt.WindowType.Popup)
        self._popup.setStyleSheet(
            "background: #14202B; border: 1px solid #3A4B5C; border-radius: 3px;"
        )
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText(placeholder)
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(SEARCH_HEIGHT)
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListView()
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list.clicked.connect(self._chose)
        layout.addWidget(self._list)

        self._popup.setLayout(layout)
        self._popup.installEventFilter(self)
        self._search.installEventFilter(self)

    # --- opening and closing -------------------------------------------------

    def showPopup(self) -> None:  # noqa: N802 (Qt naming)
        if self.count() < self.threshold:
            # Short lists keep the ordinary popup: a search field over six items is
            # one more thing to read past.
            super().showPopup()
            return

        self._list.setModel(self.model())
        # The popup draws the items, so it needs whatever delegate the combo was given
        # -- the flight creator sets one to put the pylon list in a tooltip, and it was
        # being dropped the moment the list became searchable.
        self._list.setItemDelegate(self.itemDelegate())
        self._search.clear()
        self._filter("")

        width = max(self.width(), self._list.sizeHintForColumn(0) + 48)
        rows = min(14, self.count())
        height = SEARCH_HEIGHT + 16 + rows * max(18, self._list.sizeHintForRow(0))
        self._popup.setFixedSize(width, height)
        self._popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self._popup.show()
        self._search.setFocus()
        self._scroll_to_current()

    def hidePopup(self) -> None:  # noqa: N802 (Qt naming)
        self._popup.hide()
        super().hidePopup()

    def _scroll_to_current(self) -> None:
        index = self.model().index(self.currentIndex(), self.modelColumn())
        if index.isValid():
            self._list.setCurrentIndex(index)
            self._list.scrollTo(index)

    # --- filtering -----------------------------------------------------------

    def _filter(self, needle: str) -> None:
        """Hide the rows that do not contain what was typed.

        Rows are hidden rather than the model being swapped for a proxy: the combo's
        own current index refers to rows of this model, and a proxy would have to be
        mapped through on every read.
        """
        wanted = needle.strip().lower()
        first_visible = -1
        for row in range(self.count()):
            matches = not wanted or wanted in self.itemText(row).lower()
            self._list.setRowHidden(row, not matches)
            if matches and first_visible < 0:
                first_visible = row
        if wanted and first_visible >= 0:
            index = self.model().index(first_visible, self.modelColumn())
            self._list.setCurrentIndex(index)
            self._list.scrollTo(index)

    def _chose(self, index: object) -> None:
        row = index.row()  # type: ignore[attr-defined]
        if row >= 0:
            self.setCurrentIndex(row)
        self._popup.hide()

    # --- keyboard ------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            assert isinstance(key_event, QKeyEvent)
            key = key_event.key()
            if key in (Qt.Key.Key_Escape,):
                self._popup.hide()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self._list.currentIndex()
                if current.isValid() and not self._list.isRowHidden(current.row()):
                    self.setCurrentIndex(current.row())
                self._popup.hide()
                return True
            if key in (
                Qt.Key.Key_Down,
                Qt.Key.Key_Up,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_PageUp,
            ):
                # Arrow keys drive the list even while the cursor is in the field.
                self._list.setFocus()
                self._list.keyPressEvent(key_event)
                self._search.setFocus()
                return True
        return super().eventFilter(watched, event)
