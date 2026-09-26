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
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from game.ato.savedpoints import PointKind, remove_point
from qt_ui.widgets.cards import CAPTION, CARD_BG, CARD_BORDER, card
from qt_ui.widgets.controls import mono, style_button, styled_input
from qt_ui.windows.playable import model as data
from qt_ui.windows.playable import rows
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


class NewPoint(QDialog):
    """A position typed in, or pasted from wherever the player read it.

    Any of the formats the campaign writes is accepted, and which one it is comes
    from the shape of what was typed: what is on the clipboard did not necessarily
    come from this campaign. Nothing is saved until it reads as a position, and the
    line under the field says what it read.
    """

    def __init__(self, aircraft: data.Aircraft, parent: Optional[QWidget]) -> None:
        super().__init__(parent)
        self.aircraft = aircraft
        self.latlng: Any = None
        self.setWindowTitle("Add a point")
        self.setMinimumWidth(420)
        self.setStyleSheet("QDialog { background: #202B36; }")

        self.position = styled_input(QLineEdit())
        self.position.setPlaceholderText("S53°47.220' W067°44.890'")
        self.name = styled_input(QLineEdit())
        self.name.setMaxLength(data.NAME_LENGTH)
        self.name.setPlaceholderText("Optional")
        # The height matters: a weapon aimed at a point on the ground from the wrong
        # elevation lands short or long, which is what a JDAM or a JSOW does with a
        # target-of-opportunity point.
        self.altitude = styled_input(QLineEdit(), width=110)
        self.altitude.setPlaceholderText("0")
        self.units = QComboBox()
        self.units.addItems(["feet", "metres"])
        styled_input(self.units, width=100)
        self.read = _label("", f"font-size: 11px; color: {QUIET_INK};")
        self.save = style_button(QPushButton("Save"), "primary")
        self.save.setEnabled(False)
        cancel = style_button(QPushButton("Cancel"), "normal")

        form = QVBoxLayout()
        form.setContentsMargins(16, 16, 16, 12)
        form.setSpacing(6)
        form.addWidget(
            _label("Position", f"font-size: 11px; font-weight: bold; color: {CAPTION};")
        )
        form.addWidget(self.position)
        form.addWidget(self.read)
        form.addSpacing(6)
        form.addWidget(
            _label("Name", f"font-size: 11px; font-weight: bold; color: {CAPTION};")
        )
        form.addWidget(self.name)
        form.addSpacing(6)
        form.addWidget(
            _label(
                "Elevation", f"font-size: 11px; font-weight: bold; color: {CAPTION};"
            )
        )
        height = QHBoxLayout()
        height.setContentsMargins(0, 0, 0, 0)
        height.setSpacing(8)
        height.addWidget(self.altitude)
        height.addWidget(self.units)
        height.addWidget(
            _label(
                "Above sea level. Left empty it is written down as 0.",
                f"font-size: 11px; color: {QUIET_INK};",
            )
        )
        height.addStretch()
        form.addLayout(height)
        form.addSpacing(10)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.save)
        form.addLayout(buttons)
        self.setLayout(form)

        self.position.textChanged.connect(self._reread)
        self.position.returnPressed.connect(
            lambda: self.save.isEnabled() and self.accept()
        )
        self.name.returnPressed.connect(lambda: self.save.isEnabled() and self.accept())
        self.save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self._paste_what_is_on_the_clipboard()

    def _paste_what_is_on_the_clipboard(self) -> None:
        """A position on the clipboard is almost certainly what the button was for."""
        clipboard = QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        from game.coordinates import parse_latlng

        if text and parse_latlng(text) is not None:
            self.position.setText(text.strip())
        self.position.selectAll()

    def _suggest_the_ground(self) -> None:
        """Fill in how high the ground is, unless the player typed something.

        It is looked up from a public elevation model rather than from DCS, which
        answers only inside a running mission, so it is the real world's height and
        close rather than exact -- and very much closer than the zero it replaces.
        """
        if self.altitude.text().strip() or self.latlng is None:
            return
        from game.elevation import elevation_ft

        feet = elevation_ft(self.latlng.lat, self.latlng.lng)
        if feet is None:
            return
        self.units.setCurrentText("feet")
        self.altitude.setText(str(feet))

    @property
    def altitude_ft(self) -> int:
        """What was typed, in the feet a saved point is kept in."""
        text = self.altitude.text().strip().replace(",", ".")
        try:
            value = float(text) if text else 0.0
        except ValueError:
            return 0
        if self.units.currentText() == "metres":
            value /= 0.3048
        return max(0, round(value))

    def _reread(self) -> None:
        from game.coordinates import CoordinateFormat, format_latlng, parse_latlng

        text = self.position.text().strip()
        self.latlng = parse_latlng(text) if text else None
        self.save.setEnabled(self.latlng is not None)
        if not text:
            self.read.setText("Degrees, decimal minutes, seconds or MGRS")
            colour = QUIET_INK
        elif self.latlng is None:
            self.read.setText("Not a position this can read")
            colour = DANGER_TEXT
        else:
            self.read.setText(
                "Read as "
                + format_latlng(self.latlng, CoordinateFormat.DD)
                + "  ·  "
                + format_latlng(self.latlng, CoordinateFormat.MGRS)
            )
            colour = QUIET_INK
            self._suggest_the_ground()
        self.read.setStyleSheet(
            f"font-size: 11px; color: {colour};"
            " background: transparent; border: none;"
        )


class PlayableAircraftDialog(QDialog):
    """The window. Non-modal, so showing a point on the map does not close it."""

    def __init__(self, game_model: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self.clipboard = data.Clipboard()
        self.setWindowTitle("Player Aircrafts")
        self.setMinimumSize(1120, 640)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setStyleSheet(f"QDialog {{ background: #202B36; }}")

        self.headline = Headline()
        self.aircraft_model = AircraftModel([])
        self.aircraft_view = self._aircraft_list()
        self.points_model = PointsModel()
        self.points_view = self._points_list()
        self.add = style_button(QPushButton("Add"), "normal")
        self.add.setToolTip("Type or paste a position")
        self.copy_all = style_button(QPushButton("Copy all"), "normal")
        self.paste = style_button(QPushButton("Paste"), "normal")
        self.status = _label("", f"font-size: 11px; color: {QUIET_INK};")
        self.slots = _label("", f"font-size: 11px; color: {QUIET_INK};")
        self.carried = _label("", f"font-size: 11px; color: {FAINT_INK};")
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

    def _points_list(self) -> QTreeView:
        """A table with a header, because a coordinate is only readable whole.

        The player drags the columns to fit whichever format the campaign writes --
        MGRS and decimal degrees are not the same width -- and the group headers span
        the row so the two kinds still read as groups.
        """
        view = QTreeView()
        view.setModel(self.points_model)
        self.point_delegate = PointDelegate(self.points_model, view)
        view.setItemDelegate(self.point_delegate)
        view.setMouseTracking(True)
        view.setRootIsDecorated(False)
        view.setUniformRowHeights(False)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.setStyleSheet(
            f"QTreeView {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
            f" outline: none; }}"
            f"QHeaderView::section {{ background: {HEADER_BG}; color: {QUIET_INK};"
            f" border: none; border-bottom: 1px solid {CARD_BORDER};"
            " padding: 4px 8px; font-size: 11px; }"
        )
        header = view.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.resizeSection(rows.NAME, 260)
        header.resizeSection(rows.POSITION, 240)
        header.resizeSection(rows.ELEVATION, 80)
        header.resizeSection(rows.ACTIONS, 44)
        header.setSectionResizeMode(rows.ACTIONS, QHeaderView.ResizeMode.Fixed)
        view.viewport().installEventFilter(self)
        return view

    def _build(self) -> None:
        left, _ = _captioned("Aircraft", self.aircraft_view)
        left.setMinimumWidth(460)

        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"background: {HEADER_BG};")
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 0, 10, 0)
        bar.setSpacing(8)
        bar.addWidget(self.add)
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
        self.carried.setContentsMargins(12, 4, 12, 4)
        self.carried.setWordWrap(True)
        inner.addWidget(self.carried)
        inner.addWidget(self.points_view)
        right_inner.setLayout(inner)

        self.points_caption, self.points_label = _captioned(
            "Saved points", right_inner, right=self.slots
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        from qt_ui.windows.playable.notes import AircraftNotesPane, CampaignNotesPane

        self.notes = AircraftNotesPane()
        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(self.points_caption, "Saved points")
        self.detail_tabs.addTab(self.notes, "Aircraft notes")
        self.detail_tabs.addTab(CampaignNotesPane(self.game), "Campaign notes")
        splitter.addWidget(self.detail_tabs)
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
                "GPS Points can also be added from the map by clicking on any unit"
                " or empty spot. They belong to the squadron, so cancelling a"
                " flight and planning another does not lose them.",
                f"font-size: 11px; color: {FAINT_INK}; padding: 6px 12px 10px;",
            )
        )
        self.setLayout(layout)

    def _wire(self) -> None:
        self.aircraft_view.selectionModel().currentChanged.connect(
            lambda *_: self.show_points()
        )
        self.add.clicked.connect(self.add_by_hand)
        self.copy_all.clicked.connect(self.copy_everything)
        self.paste.clicked.connect(self.paste_everything)
        self.points_view.customContextMenuRequested.connect(self.point_menu_at)
        self.points_view.doubleClicked.connect(self.rename_at)
        for key, handler in (
            ("Return", self.show_current_on_map),
            ("Enter", self.show_current_on_map),
            ("Ctrl+C", self.copy_coordinates),
            ("F2", self.rename_current),
            ("Del", self.delete_current),
        ):
            shortcut = QShortcut(QKeySequence(key), self.points_view)
            # The view itself, not its children: an open name editor is a child, and
            # a Return it does not get is a name the player cannot finish typing.
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(handler)
        rename_aircraft = QShortcut(QKeySequence("F2"), self.aircraft_view)
        rename_aircraft.setContext(Qt.ShortcutContext.WidgetShortcut)
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
        self.splitter.setVisible(True)
        self.empty.setVisible(not flying)
        if flying:
            self.aircraft_view.setCurrentIndex(self.aircraft_model.index(0, 0))
        self.show_points()

    @property
    def selected(self) -> Optional[data.Aircraft]:
        return self.aircraft_model.at(self.aircraft_view.currentIndex())

    def show_points(self) -> None:
        one = self.selected
        self.notes.show_aircraft(one)
        self.points_model.show(one, self._coordinates)
        for row in self.points_model.header_rows():
            self.points_view.setFirstColumnSpanned(row, QModelIndex(), True)
        self.carried.setText(self._how_it_is_carried(one))
        self._retitle()
        self._restate()

    def _how_it_is_carried(self, one: Optional[data.Aircraft]) -> str:
        """What this airframe does with the points, said where they are edited.

        Every aeroplane does something different with them and none of it is
        guessable: a Hornet finds them on a second route sequence, an A-10 has to be
        told to read its database, and the rest have only the kneeboard.
        """
        if one is None:
            return ""
        from game.missiongenerator.dtc import CARTRIDGES
        from game.missiongenerator.a10cdu import AIRCRAFT as DTS_AIRCRAFT

        if one.dcs_id in CARTRIDGES and CARTRIDGES[one.dcs_id].takes_saved_points:
            return (
                "Loaded from the data cartridge, numbered after the flight plan and"
                " on route sequence 2 — SEQ1 is still the route."
            )
        if one.dcs_id in DTS_AIRCRAFT:
            return (
                "In the navigation computer from the start, on flight plan EXTRA so"
                " the mission route is untouched. The aircraft works out the ground"
                " height under each one itself."
            )
        return "Nothing loads a point into this airframe: they go on the kneeboard."

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

    def add_by_hand(self) -> None:
        """A point the player has as a number rather than as a spot on the map."""
        one = self.selected
        game = self.game
        if one is None or game is None:
            return
        asked = NewPoint(one, self)
        if asked.exec() != QDialog.DialogCode.Accepted or asked.latlng is None:
            return
        from dcs.mapping import Point

        from game.ato.savedpoints import SavedPoint, add_point, kinds_for

        kinds = kinds_for(one.dcs_id)
        where = Point.from_latlng(asked.latlng, game.theater.terrain)
        add_point(
            one.flight,
            SavedPoint(
                kind=kinds[0] if kinds else PointKind.WAYPOINT,
                name=asked.name.text().strip() or "Point",
                x=where.x,
                y=where.y,
                altitude_ft=asked.altitude_ft,
            ),
        )
        self.show_points()
        self.aircraft_model.layoutChanged.emit()

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
        """To Windows, and to the window's own clipboard.

        Copying one point and finding Paste still greyed out is the control saying it
        did nothing. One point is a copy of one point.
        """
        row = self.current_point()
        one = self.selected
        if row is None or one is None:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.points_model.coordinates_of(row.point))
        self.clipboard.take_one(row.point, one.title)
        self._restate()

    def rename_current(self) -> None:
        self.rename_at(self.points_view.currentIndex())

    def rename_at(self, index: QModelIndex) -> None:
        row = self.points_model.at(index)
        if row is not None and not row.is_header:
            self.points_view.setCurrentIndex(index)
            self.points_view.edit(index)

    def show_current_on_map(self) -> None:
        self.show_on_map(self.points_view.currentIndex())

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
        link = self.aircraft_delegate.clicked_link(index.row(), position, top)
        if link == "squadron":
            self.open_air_wing()
        elif link == "package":
            self.open_package(one)

    def open_air_wing(self) -> None:
        from qt_ui.dialogs import open_once
        from qt_ui.windows.AirWingDialog import AirWingDialog

        self._air_wing = open_once(
            "air-wing", lambda: AirWingDialog(self.game_model, self.window())
        )

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
