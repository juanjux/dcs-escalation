"""What the player is flying this turn, and what is written down for each aircraft.

The information existed, in three places: the air tasking order knew the flight, the
flight dialog knew the pilot, and the map knew the points. None of them answered the
one question a player asks before a sortie -- what am I sitting in, and what have I
noted for it -- so this does, as a master list of aircraft with one aircraft's points
beside it.

It does not create points: they are written from the map. This is where they are
named, copied between aircraft, shown and deleted.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPoint, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from game.ato.savedpoints import PointKind, remove_point
from qt_ui.widgets.cards import CAPTION, CARD_BG, CARD_BORDER, card
from qt_ui.widgets.controls import mono, style_button
from qt_ui.windows.playable import model as data
from qt_ui.windows.playable.rows import (
    AircraftDelegate,
    AircraftModel,
    DANGER_TEXT,
    FAINT_INK,
    HEADER_BG,
    IDLE_BAR,
    MARKPOINT,
    PointDelegate,
    PointRow,
    PointsModel,
    QUIET_INK,
    TITLE_INK,
    WAYPOINT,
)

#: The zoom the map takes when a point is shown on it. Tighter than a base, because
#: a written-down point is a spot rather than a place.
POINT_ZOOM = 13


def _label(text: str, css: str) -> QLabel:
    widget = QLabel(text)
    widget.setStyleSheet(f"{css} background: transparent; border: none;")
    return widget


def _captioned(
    name: str, inner: QWidget, right: Optional[QWidget] = None
) -> tuple[QWidget, QLabel]:
    """A caption over a card, with an optional note on the right of the caption.

    ``cards.carded`` is the shared version and does not take the right-hand note,
    which here carries how many slots the aircraft has left.
    """
    label = _label(
        name.upper(),
        f"font-size: 11px; font-weight: bold; letter-spacing: 1px; color: {CAPTION};",
    )
    heading = QHBoxLayout()
    heading.setContentsMargins(0, 0, 0, 0)
    heading.addWidget(label)
    heading.addStretch()
    if right is not None:
        heading.addWidget(right)
    head = QWidget()
    head.setFixedHeight(20)
    head.setLayout(heading)

    holder = card()
    holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    body = QVBoxLayout()
    body.setContentsMargins(1, 1, 1, 1)
    body.addWidget(inner)
    holder.setLayout(body)

    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(8)
    column.addWidget(head)
    column.addWidget(holder, 1)
    wrapper = QWidget()
    wrapper.setLayout(column)
    return wrapper, label


class Headline(QWidget):
    """Three figures and the turn, above the two lists."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(54)
        self.band = QWidget()
        self.band.setFixedWidth(4)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(0)
        layout.addWidget(self.band)
        self.figures = QHBoxLayout()
        self.figures.setContentsMargins(16, 0, 0, 0)
        self.figures.setSpacing(0)
        layout.addLayout(self.figures)
        layout.addStretch()
        self.turn = _label("", f"font-size: 12px; color: {QUIET_INK};")
        layout.addWidget(self.turn)
        self.setLayout(layout)
        self.setStyleSheet(f"background: {HEADER_BG};")

    def show_figures(self, aircraft: int, packages: int, points: int) -> None:
        while self.figures.count():
            item = self.figures.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.band.setStyleSheet(f"background: {WAYPOINT if aircraft else IDLE_BAR};")
        pairs = (
            (
                aircraft,
                "aircraft this turn" if aircraft else "No player seat this turn",
            ),
            (packages, "packages"),
            (points, "saved points"),
        )
        for number, caption in pairs if aircraft else pairs[:1]:
            value = QLabel(str(number))
            font = mono(22)
            font.setPixelSize(22)
            value.setFont(font)
            value.setStyleSheet(
                f"color: {TITLE_INK}; background: transparent; border: none;"
            )
            self.figures.addWidget(value)
            self.figures.addWidget(
                _label(f"  {caption}", f"font-size: 12px; color: {QUIET_INK};")
            )
            self.figures.addSpacing(28)


class PlayableAircraftDialog(QDialog):
    """The window. Non-modal, so showing a point on the map does not close it."""

    def __init__(self, game_model: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self.clipboard = data.Clipboard()
        self.setWindowTitle("Playable aircraft")
        self.setMinimumSize(920, 600)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setStyleSheet(f"QDialog {{ background: #202B36; }}")

        self.headline = Headline()
        self.aircraft_model = AircraftModel([])
        self.aircraft_view = self._aircraft_list()
        self.points_model = PointsModel()
        self.points_view = self._points_list()
        self.copy_all = style_button(QPushButton("Copy all"), "normal")
        self.paste = style_button(QPushButton("Paste"), "normal")
        self.status = _label("", f"font-size: 11px; color: {QUIET_INK};")
        self.slots = _label("", f"font-size: 11px; color: {QUIET_INK};")
        self.empty = _label(
            "Pick a squadron in the Air Wing and convert a pilot to player, or set"
            " client slots on a flight in the ATO.",
            f"font-size: 12px; color: {QUIET_INK};",
        )

        self._build()
        self._wire()
        self.reload()

    # ----------------------------------------------------------------- layout

    def _aircraft_list(self) -> QListView:
        view = QListView()
        view.setModel(self.aircraft_model)
        self.aircraft_delegate = AircraftDelegate(view)
        view.setItemDelegate(self.aircraft_delegate)
        view.setMouseTracking(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setStyleSheet(
            f"QListView {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
            f" outline: none; }}"
        )
        view.viewport().installEventFilter(self)
        return view

    def _points_list(self) -> QListView:
        view = QListView()
        view.setModel(self.points_model)
        self.point_delegate = PointDelegate(self.points_model, view)
        view.setItemDelegate(self.point_delegate)
        view.setMouseTracking(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setStyleSheet(
            f"QListView {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
            f" outline: none; }}"
        )
        view.viewport().installEventFilter(self)
        return view

    def _build(self) -> None:
        left, _ = _captioned("Aircraft", self.aircraft_view)
        left.setMinimumWidth(400)

        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"background: {HEADER_BG};")
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 0, 10, 0)
        bar.setSpacing(8)
        bar.addWidget(self.copy_all)
        bar.addWidget(self.paste)
        bar.addWidget(self.status)
        bar.addStretch()
        bar.addWidget(_label("●  waypoint", f"font-size: 11px; color: {WAYPOINT};"))
        bar.addWidget(_label("◆  markpoint", f"font-size: 11px; color: {MARKPOINT};"))
        toolbar.setLayout(bar)

        right_inner = QWidget()
        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(toolbar)
        inner.addWidget(self.points_view)
        right_inner.setLayout(inner)

        self.points_caption, self.points_label = _captioned(
            "Saved points", right_inner, right=self.slots
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.points_caption)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.splitter = splitter

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.headline)
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(12, 12, 12, 8)
        body_layout.setSpacing(12)
        body_layout.addWidget(splitter, 1)
        body_layout.addWidget(self.empty)
        body.setLayout(body_layout)
        layout.addWidget(body, 1)
        layout.addWidget(
            _label(
                "Points are written from the map — right-click a unit or any spot."
                " This window edits them, it does not create them.",
                f"font-size: 11px; color: {FAINT_INK}; padding: 6px 12px 10px;",
            )
        )
        self.setLayout(layout)

    def _wire(self) -> None:
        self.aircraft_view.selectionModel().currentChanged.connect(
            lambda *_: self.show_points()
        )
        self.copy_all.clicked.connect(self.copy_everything)
        self.paste.clicked.connect(self.paste_everything)
        self.points_view.customContextMenuRequested.connect(self.point_menu_at)
        self.points_view.doubleClicked.connect(lambda index: self.show_on_map(index))
        for key, handler in (
            ("Return", lambda: self.show_on_map(self.points_view.currentIndex())),
            ("Ctrl+C", self.copy_coordinates),
            ("F2", self.rename_current),
            ("Del", self.delete_current),
        ):
            shortcut = QShortcut(QKeySequence(key), self.points_view)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
        rename_aircraft = QShortcut(QKeySequence("F2"), self.aircraft_view)
        rename_aircraft.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        rename_aircraft.activated.connect(
            lambda: self.aircraft_view.edit(self.aircraft_view.currentIndex())
        )

    # ------------------------------------------------------------------ state

    @property
    def game(self) -> Any:
        return getattr(self.game_model, "game", None)

    def reload(self) -> None:
        aircraft = data.aircraft_of(self.game)
        self.aircraft_model.set_aircraft(aircraft)
        self.headline.show_figures(*data.figures(aircraft))
        game = self.game
        if game is not None:
            self.headline.turn.setText(
                f"Turn {game.turn} · {game.conditions.start_time:%H:%M}Z"
            )
        flying = bool(aircraft)
        self.splitter.setVisible(flying)
        self.empty.setVisible(not flying)
        if flying:
            self.aircraft_view.setCurrentIndex(self.aircraft_model.index(0, 0))
        self.show_points()

    @property
    def selected(self) -> Optional[data.Aircraft]:
        return self.aircraft_model.at(self.aircraft_view.currentIndex())

    def show_points(self) -> None:
        one = self.selected
        self.points_model.show(one, self._coordinates)
        self._retitle()
        self._restate()

    def _coordinates(self, point: Any) -> str:
        game = self.game
        if game is None:
            return ""
        from dcs.mapping import Point

        from game.coordinates import format_for

        return format_for(game.settings, Point(point.x, point.y, game.theater.terrain))

    def _retitle(self) -> None:
        one = self.selected
        caption = "SAVED POINTS"
        if one is not None:
            caption = f"SAVED POINTS · {one.title.upper()}"
        self.points_label.setText(caption)
        self.slots.setText("" if one is None else f"{one.total_room} slots free")

    def _restate(self) -> None:
        one = self.selected
        self.copy_all.setEnabled(one is not None and one.total_used > 0)
        if self.clipboard.empty:
            self.paste.setEnabled(False)
            self.paste.setText("Paste")
            self.paste.setToolTip("Copy the points of an aircraft first")
            self.status.setText("Nothing copied yet")
            self.status.setStyleSheet(
                f"font-size: 11px; color: {FAINT_INK};"
                " background: transparent; border: none;"
            )
            return
        held = len(self.clipboard.points)
        self.paste.setEnabled(one is not None)
        self.paste.setText(f"Paste {held}")
        self.paste.setToolTip("")
        if one is None:
            return
        fits = self.clipboard.fits(one)
        if fits < held:
            self.status.setText(f"Only {fits} fit — the rest will not be pasted")
            self.status.setStyleSheet(
                f"font-size: 11px; color: {MARKPOINT};"
                " background: transparent; border: none;"
            )
        else:
            self.status.setText(f"{held} points from {self.clipboard.source}")
            self.status.setStyleSheet(
                f"font-size: 11px; color: {QUIET_INK};"
                " background: transparent; border: none;"
            )

    # ---------------------------------------------------------------- actions

    def copy_everything(self) -> None:
        one = self.selected
        if one is None:
            return
        self.clipboard.take(one)
        self._restate()

    def paste_everything(self) -> None:
        one = self.selected
        if one is None or self.clipboard.empty:
            return
        self.clipboard.paste_into(one)
        self.show_points()
        self.aircraft_model.layoutChanged.emit()

    def current_point(self) -> Optional[PointRow]:
        row = self.points_model.at(self.points_view.currentIndex())
        return None if row is None or row.is_header else row

    def show_on_map(self, index: QModelIndex) -> None:
        """The map goes to the point. This window stays where it is."""
        row = self.points_model.at(index)
        if row is None or row.is_header:
            return
        game = self.game
        if game is None:
            return
        from dcs.mapping import Point

        from game.server import EventStream
        from game.sim import GameUpdateEvents

        where = Point(row.point.x, row.point.y, game.theater.terrain)
        EventStream.put_nowait(GameUpdateEvents().look_at(where.latlng(), POINT_ZOOM))

    def copy_coordinates(self) -> None:
        row = self.current_point()
        if row is None:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.points_model.coordinates_of(row.point))

    def rename_current(self) -> None:
        index = self.points_view.currentIndex()
        row = self.points_model.at(index)
        if row is not None and not row.is_header:
            self.points_view.edit(index)

    def delete_current(self) -> None:
        row = self.current_point()
        one = self.selected
        if row is None or one is None or row.index is None:
            return
        remove_point(one.flight, row.index)
        self.show_points()
        self.aircraft_model.layoutChanged.emit()

    def point_menu_at(self, where: QPoint) -> None:
        index = self.points_view.indexAt(where)
        row = self.points_model.at(index)
        if row is None or row.is_header:
            return
        self.points_view.setCurrentIndex(index)
        menu = QMenu(self)
        for text, shortcut, handler in (
            ("Show on map", "Enter", lambda: self.show_on_map(index)),
            ("Copy coordinates", "Ctrl+C", self.copy_coordinates),
            ("Rename", "F2", self.rename_current),
        ):
            action = QAction(text, menu)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(handler)
            menu.addAction(action)
        menu.addSeparator()
        delete = QAction("Delete", menu)
        delete.setShortcut(QKeySequence("Del"))
        delete.triggered.connect(self.delete_current)
        menu.addAction(delete)
        menu.setStyleSheet(f"QMenu::item:last {{ color: {DANGER_TEXT}; }}")
        menu.exec(self.points_view.viewport().mapToGlobal(where))

    # ----------------------------------------------------- clicks on a delegate

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().eventFilter(watched, event)
        if watched is self.aircraft_view.viewport():
            self._aircraft_clicked(event)
        elif watched is self.points_view.viewport():
            self._point_clicked(event)
        return super().eventFilter(watched, event)

    def _aircraft_clicked(self, event: Any) -> None:
        position = event.position().toPoint()
        index = self.aircraft_view.indexAt(position)
        one = self.aircraft_model.at(index)
        if one is None or not one.assigned:
            return
        top = self.aircraft_view.visualRect(index).top()
        if self.aircraft_delegate.link_at(index.row(), position, top):
            self.open_package(one)

    def _point_clicked(self, event: Any) -> None:
        position = event.position().toPoint()
        index = self.points_view.indexAt(position)
        row = self.points_model.at(index)
        if row is None or row.is_header:
            return
        if PointDelegate.on_menu_button(self.points_view.visualRect(index), position):
            self.point_menu_at(position)

    def open_package(self, one: data.Aircraft) -> None:
        """The package this aircraft flies in, in its own window."""
        from qt_ui.dialogs import Dialog

        model = self.game_model
        ato = getattr(model, "ato_model", None)
        if ato is None:
            return
        package_model = ato.find_matching_package_model(one.flight.package)
        if package_model is not None:
            Dialog.open_edit_package_dialog(package_model)
