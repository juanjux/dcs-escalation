"""One box that finds anything: settings, bases, objectives, squadrons, pilots,
flights, and every command in the menus.

Ctrl+P, type, Enter. Everything the application can do or show was behind a menu, a
dialog or an icon on the map, each in a different place, and two of them had a search
of their own that found only their own things.

The searching is :mod:`game.search`; what is here is the box, the list and the
keyboard.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.search.index import Hit, Index
from qt_ui.widgets.cards import CARD_BG, CARD_BORDER, HINT
from qt_ui.windows.palette.actions import action_entries
from qt_ui.windows.palette.follow import follow
from qt_ui.windows.palette.resultrow import (
    KINDS,
    ROW_HEIGHT,
    HitRole,
    ResultDelegate,
)

#: How long to wait after the last keystroke. A search costs about a millisecond on a
#: campaign of a thousand entries, so this is about not searching four times while a
#: word is being typed rather than about the cost of any one of them.
TYPING_PAUSE_MS = 60

#: How many rows to show. More than fits the box is a list nobody reads to the end of.
SHOWN = 30

WIDTH = 720
HEIGHT = 460


class CommandPalette(QDialog):
    """The box itself. One per main window, reopened rather than rebuilt."""

    RECENT_KEY = "commandPaletteRecent"
    RECENT_LIMIT = 10

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window_ = window

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setObjectName("commandPalette")
        self.setStyleSheet(
            f"#commandPalette {{ background: {CARD_BG};"
            f" border: 1px solid {CARD_BORDER}; border-radius: 4px; }}"
        )

        self.query = QLineEdit()
        self.query.setPlaceholderText(
            "Find a setting, a base, an objective, a squadron, a pilot, a command…"
        )
        self.query.setStyleSheet(
            "background: transparent; border: none; border-bottom: 1px solid"
            f" {CARD_BORDER}; padding: 12px 14px; font-size: 16px; color: #E8F0FB;"
        )
        self.query.textChanged.connect(self.on_typed)
        self.query.returnPressed.connect(self.follow_selected)

        self.results = QListWidget()
        self.results.setItemDelegate(ResultDelegate(self.results))
        self.results.setMouseTracking(True)
        self.results.setUniformItemSizes(True)
        self.results.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
        )
        self.results.itemActivated.connect(lambda _item: self.follow_selected())
        self.results.itemClicked.connect(lambda _item: self.follow_selected())

        self.hint = QLabel()
        self.hint.setStyleSheet(
            f"color: {HINT}; font-size: 11px; padding: 6px 14px;"
            f" border-top: 1px solid {CARD_BORDER};"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.query)
        layout.addWidget(self.results, 1)
        layout.addWidget(self.hint)
        self.setLayout(layout)

        self._hits: list[Hit] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TYPING_PAUSE_MS)
        self._timer.timeout.connect(self.run_search)

    # -- opening and closing -------------------------------------------------

    def open_over(self, window: QWidget) -> None:
        """Centred on the window it belongs to, with the last query selected.

        Selected rather than cleared: opening it again to change one word is the
        commonest second use, and typing over a selection is how every other box
        with a history behaves.
        """
        self.query.selectAll()
        self.query.setFocus()
        self.run_search()
        centre = window.geometry().center()
        self.move(centre.x() - WIDTH // 2, centre.y() - HEIGHT // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Up and down belong to the list even while the caret is in the box: taking
        # the hand off the keyboard for every letter is the thing this replaces.
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.step(1 if key == Qt.Key.Key_Down else -1)
            event.accept()
            return
        super().keyPressEvent(event)

    def step(self, by: int) -> None:
        count = self.results.count()
        if not count:
            return
        self.results.setCurrentRow((self.results.currentRow() + by) % count)

    # -- searching -----------------------------------------------------------

    def on_typed(self, _text: str) -> None:
        self._timer.start()

    def run_search(self) -> None:
        self._timer.stop()
        typed = self.query.text()
        self._hits = self.hits_for(typed)

        self.results.clear()
        for hit in self._hits:
            item = QListWidgetItem()
            item.setData(HitRole, hit)
            item.setSizeHint(QSize(WIDTH - 24, ROW_HEIGHT))
            self.results.addItem(item)
        if self._hits:
            self.results.setCurrentRow(0)
        self.hint.setText(self.summary(typed))

    def hits_for(self, typed: str) -> list[Hit]:
        """What to show for what has been typed, or for nothing having been typed.

        The menus are indexed here rather than with the campaign: they belong to the
        window, not to the campaign, and there are few enough of them that walking
        them again per search costs nothing measurable.
        """
        campaign = self.window_.search_index.of(self.window_.game_model.game)
        commands = Index(action_entries(self.window_.menuBar()))

        if not typed.strip():
            return self.recently_followed(campaign, commands)

        found = campaign.search(typed, limit=SHOWN)
        found += commands.search(typed, limit=SHOWN)
        found.sort(key=lambda hit: hit.order)
        return found[:SHOWN]

    def recently_followed(self, *indexes: Index) -> list[Hit]:
        """The last few things chosen, so an empty box is still worth opening."""
        wanted = self.recent_keys()
        if not wanted:
            return []
        by_key = {
            f"{entry.follow.kind}:{entry.follow.key}": entry
            for index in indexes
            for entry in index.entries
        }
        return [Hit(by_key[key], 0) for key in wanted if key in by_key]

    def summary(self, typed: str) -> str:
        if not typed.strip():
            if self._hits:
                return "Recently opened. Type to find anything else."
            return "Type to search. Enter opens, Escape closes."
        if not self._hits:
            return "Nothing matches."
        kinds = {hit.entry.follow.kind for hit in self._hits}
        names = sorted(KINDS.get(kind, (kind, None))[0].lower() for kind in kinds)
        return f"{len(self._hits)} results · {', '.join(names)}"

    # -- following -----------------------------------------------------------

    def follow_selected(self) -> None:
        row = self.results.currentRow()
        if row < 0 or row >= len(self._hits):
            return
        chosen = self._hits[row]
        self.remember(chosen)
        self.close()
        follow(self.window_, chosen.entry.follow)

    @staticmethod
    def _qsettings() -> QSettings:
        return QSettings("DCS Retribution", "Qt UI")

    def recent_keys(self) -> list[str]:
        stored = self._qsettings().value(self.RECENT_KEY)
        return [str(key) for key in stored] if isinstance(stored, list) else []

    def remember(self, hit: Hit) -> None:
        """The last few things followed, so the box opens on something useful."""
        key = f"{hit.entry.follow.kind}:{hit.entry.follow.key}"
        recent = [key] + [other for other in self.recent_keys() if other != key]
        self._qsettings().setValue(self.RECENT_KEY, recent[: self.RECENT_LIMIT])
