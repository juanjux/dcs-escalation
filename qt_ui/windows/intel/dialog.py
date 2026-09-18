"""The Intelligence window: what a side has, and where.

Three tabs answering three questions -- what it earns, what it flies, what it drives --
and one switch that swaps all three to the other side. That switch was a checkbox
labelled "Enemy Info" in the top-left corner, and nothing else on screen said whose
numbers you were reading; own and enemy looked identical. It is now the first thing in
the window: a two-way control beside the side's name, with a coloured band down the
left edge and the same colour on every share bar, so a number cannot be read without
knowing whose it is.

Nothing here is editable. The window is for reading, so what it spends its room on is
making a long list readable: a headline of three figures before the list, groups that
fold, a filter, a sort, and a total pinned below the scroll.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from game.game import Game
from game.theater import Player
from qt_ui.uiconstants import ICONS
from qt_ui.widgets.cards import CARD_BG, CARD_BORDER, card, make_transparent
from qt_ui.widgets.controls import mono, style_button, styled_input
from qt_ui.windows.intel import model as data
from qt_ui.windows.intel.rows import (
    ENEMY_ACCENT,
    HeaderLine,
    IntelDelegate,
    IntelListModel,
    OWN_ACCENT,
    economy_lines,
    force_lines,
)

#: The window itself takes the side's colour, not just a badge in the corner.
OWN_WINDOW = "#2D3E50"
ENEMY_WINDOW = "#33333A"
OWN_LABEL = "#F2F7FA"
#: The rust lifted until it reads at 4.5:1 on the enemy strip.
ENEMY_LABEL = "#E8B79E"
SUB_LABEL = "#7C8B99"
CAPTION_INK = "#6B7A87"
DIVIDER = "#1D2731"
TOTAL_BAR = "#26343F"

ECONOMY, AIR, GROUND = 0, 1, 2
TAB_NAMES = ("Economy", "Air forces", "Ground forces")


def _label(text: str, css: str) -> QLabel:
    widget = QLabel(text)
    widget.setStyleSheet(f"{css} background: transparent; border: none;")
    return widget


class SideSwitch(QWidget):
    """Own forces / Enemy, as a control rather than a tick box."""

    def __init__(self, on_change) -> None:
        super().__init__()
        self._on_change = on_change
        self.buttons: dict[Player, QPushButton] = {}

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        for player, text in ((Player.BLUE, "Own forces"), (Player.RED, "Enemy")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(30)
            button.clicked.connect(
                lambda _checked=False, side=player: self._on_change(side)
            )
            self.buttons[player] = button
            row.addWidget(button)
        self.setLayout(row)
        make_transparent(self)

    def show_side(self, player: Player) -> None:
        for side, button in self.buttons.items():
            chosen = side is player
            button.setChecked(chosen)
            accent = OWN_ACCENT if side.is_blue else ENEMY_ACCENT
            ink = "#0F1922" if side.is_blue else "#1A0F0A"
            button.setStyleSheet(
                "QPushButton { background: #26343F; color: #B7C6D2;"
                " border: 1px solid #3A4B5C; border-radius: 3px;"
                " padding: 0 12px; font-size: 12px; }"
                f"QPushButton:checked {{ background: {accent.name()}; color: {ink};"
                " font-weight: 600; }"
            )


class ForcesPane(QWidget):
    """One of the two force tabs: headline, controls, list, total."""

    def __init__(self, window: "IntelWindow", tab: int) -> None:
        super().__init__()
        self.window_ = window
        self.tab = tab
        self.lines = IntelListModel(self)

        self.figures = Figures()

        self.sort = styled_input(QComboBox(), width=110)
        for option in data.Sort:
            self.sort.addItem(option.value, option)
        self.sort.currentIndexChanged.connect(lambda _i: window.redraw())

        self.fold_all = style_button(QPushButton("Collapse all"))
        self.fold_all.clicked.connect(self._toggle_all)

        self.view = QListView()
        self.view.setModel(self.lines)
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Every row is painted to the width it is given, so a horizontal scrollbar
        # can only ever be Qt disagreeing with the delegate about that width.
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setFrameShape(QListView.Shape.NoFrame)
        self.view.setStyleSheet(f"QListView {{ background: {CARD_BG}; border: none; }}")
        self.view.clicked.connect(self._clicked)

        self.empty = _label("", f"color: {SUB_LABEL}; font-size: 12px;")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.hide()

        self.total_name = _label(
            "", f"color: {CAPTION_INK}; font-size: 10px; font-weight: bold;"
        )
        self.total_value = _label("", "color: #F2F7FA;")
        self.total_value.setFont(mono(14))
        self.total_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        total = QHBoxLayout()
        total.setContentsMargins(16, 0, 16, 0)
        total.addWidget(self.total_name)
        total.addStretch()
        total.addWidget(self.total_value)
        self.total = QWidget()
        self.total.setFixedHeight(34)
        self.total.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.total.setObjectName("intelTotal")
        self.total.setStyleSheet(
            f"#intelTotal {{ background: {TOTAL_BAR}; border: none; }}"
        )
        self.total.setLayout(total)

        controls = QHBoxLayout()
        controls.setContentsMargins(16, 0, 16, 0)
        controls.setSpacing(8)
        controls.addWidget(self.figures, 1)
        controls.addWidget(_label("Sort", f"color: {SUB_LABEL}; font-size: 11px;"))
        controls.addWidget(self.sort)
        controls.addWidget(self.fold_all)
        head = QWidget()
        head.setFixedHeight(72)
        make_transparent(head)
        head.setLayout(controls)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(head)
        body.addWidget(_rule())
        body.addWidget(self.view, 1)
        body.addWidget(self.empty, 1)
        body.addWidget(self.total)

        holder = card()
        holder.setLayout(body)
        outer = QVBoxLayout()
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(holder)
        self.setLayout(outer)

    def _clicked(self, index: QModelIndex) -> None:
        line = self.lines.line(index)
        if isinstance(line, HeaderLine):
            self.window_.toggle_fold(self.tab, line.group.name)

    def _toggle_all(self) -> None:
        self.window_.toggle_all(self.tab)

    def refresh(self, accent: QColor, tab: data.ForceTab, folded: set[str]) -> None:
        self.view.setItemDelegate(IntelDelegate(accent, self.view))
        self.figures.show_figures(tab.figures)
        self.lines.set_lines(force_lines(tab.groups, folded))
        self.sort.setCurrentIndex(
            [option for option in data.Sort].index(self.chosen_sort)
        )
        everything_folded = bool(tab.groups) and all(
            group.name in folded for group in tab.groups
        )
        self.fold_all.setText("Expand all" if everything_folded else "Collapse all")
        self.fold_all.setEnabled(bool(tab.groups))
        self.total_name.setText(tab.total_caption)
        self.total_value.setText(str(tab.total))
        if tab.empty is not None:
            headline, note = tab.empty
            self.empty.setText(
                f"<div style='font-size:14px;color:#B7C6D2'>{headline}</div>"
                f"<div style='margin-top:6px'>{note}</div>"
            )
        self.empty.setVisible(tab.empty is not None)
        self.view.setVisible(tab.empty is None)

    @property
    def chosen_sort(self) -> data.Sort:
        chosen = self.sort.currentData()
        return chosen if isinstance(chosen, data.Sort) else data.Sort.BASE_SIZE


class EconomyPane(QWidget):
    """The Economy tab: the same shell without sort, fold or a total bar."""

    def __init__(self) -> None:
        super().__init__()
        self.lines = IntelListModel(self)

        self.figures = Figures()
        head = QHBoxLayout()
        head.setContentsMargins(16, 0, 16, 0)
        head.addWidget(self.figures, 1)
        holder_head = QWidget()
        holder_head.setFixedHeight(72)
        make_transparent(holder_head)
        holder_head.setLayout(head)

        self.view = QListView()
        self.view.setModel(self.lines)
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Every row is painted to the width it is given, so a horizontal scrollbar
        # can only ever be Qt disagreeing with the delegate about that width.
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QListView.Shape.NoFrame)
        self.view.setStyleSheet(f"QListView {{ background: {CARD_BG}; border: none; }}")

        self.empty = _label("", f"color: {SUB_LABEL}; font-size: 12px;")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(holder_head)
        body.addWidget(_rule())
        body.addWidget(self.view, 1)
        body.addWidget(self.empty, 1)

        holder = card()
        holder.setLayout(body)
        outer = QVBoxLayout()
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(holder)
        self.setLayout(outer)

    def refresh(self, accent: QColor, tab: data.EconomyTab) -> None:
        self.view.setItemDelegate(IntelDelegate(accent, self.view))
        self.figures.show_figures(tab.figures)
        self.lines.set_lines(economy_lines(tab.sections))
        if tab.empty is not None:
            headline, note = tab.empty
            self.empty.setText(
                f"<div style='font-size:14px;color:#B7C6D2'>{headline}</div>"
                f"<div style='margin-top:6px'>{note}</div>"
            )
        self.empty.setVisible(tab.empty is not None)
        self.view.setVisible(tab.empty is None)


def _rule() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    line.setObjectName("intelRule")
    line.setStyleSheet(f"#intelRule {{ background: {DIVIDER}; }}")
    return line


class Figures(QWidget):
    """The three numbers a tab opens with: how much, before the list says where.

    Built once and refilled. Rebuilt widgets were left painted over their
    replacements for a frame -- deleteLater does not run until the event loop does --
    so two answers were on screen at once every time the side changed.
    """

    def __init__(self) -> None:
        super().__init__()
        self.captions: list[QLabel] = []
        self.values: list[QLabel] = []
        self.notes: list[QLabel] = []

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(32)
        for position in range(3):
            if position:
                row.addWidget(_divider())
            caption = _label(
                "",
                f"color: {CAPTION_INK}; font-size: 10px; font-weight: bold;"
                " letter-spacing: 1px;",
            )
            caption.setFixedHeight(14)
            # The first figure is the answer; the other two are context, a step down.
            value = _label("", "")
            value.setFont(mono(26 if position == 0 else 20))
            value.setFixedHeight(32)
            note = _label("", f"color: {SUB_LABEL}; font-size: 12px;")

            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            line.addWidget(value)
            line.addWidget(note)
            line.addStretch()

            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(4)
            column.addStretch()
            column.addWidget(caption)
            column.addLayout(line)
            column.addStretch()

            holder = QWidget()
            make_transparent(holder)
            holder.setLayout(column)
            row.addWidget(holder)

            self.captions.append(caption)
            self.values.append(value)
            self.notes.append(note)
        row.addStretch()
        self.setLayout(row)
        make_transparent(self)

    def show_figures(self, figures: Sequence[data.Figure]) -> None:
        for position in range(3):
            figure = figures[position] if position < len(figures) else None
            caption = self.captions[position]
            value = self.values[position]
            note = self.notes[position]
            caption.setText(figure.caption if figure else "")
            value.setText(figure.value if figure else "")
            note.setText(figure.note if figure else "")
            money = bool(figure) and figure.value.startswith(("+$", "-$", "$"))
            green = money and figure is not None and figure.value.startswith("+$")
            ink = "#86C39A" if green else "#F2F7FA"
            value.setStyleSheet(f"color: {ink}; background: transparent; border: none;")
            note.setVisible(bool(figure and figure.note))


def _divider() -> QWidget:
    line = QWidget()
    line.setFixedWidth(1)
    line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    line.setObjectName("intelFigureRule")
    line.setStyleSheet(f"#intelFigureRule {{ background: {DIVIDER}; }}")
    return line


class IntelWindow(QDialog):
    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.player = Player.BLUE
        self.setModal(True)
        self.setWindowTitle("Intelligence")
        self.setWindowIcon(ICONS["Statistics"])
        self.setMinimumSize(720, 640)

        #: Folded groups, per side and per tab: switching sides and coming back
        #: should find the window as it was left.
        self.folded: dict[tuple[bool, int], set[str]] = {}

        self.side_switch = SideSwitch(self.show_side)
        self.side_name = _label("", "font-size: 15px; font-weight: 600;")
        self.side_note = _label("", f"color: {SUB_LABEL}; font-size: 12px;")
        self.filter = styled_input(QLineEdit(), width=220)
        self.filter.setPlaceholderText("Filter…")
        self.filter.textChanged.connect(lambda _text: self.redraw())
        self.match_count = _label("", f"color: {SUB_LABEL}; font-size: 11px;")

        strip = QHBoxLayout()
        strip.setContentsMargins(18, 0, 14, 0)
        strip.setSpacing(14)
        strip.addWidget(self.side_switch)
        strip.addWidget(self.side_name)
        strip.addWidget(self.side_note)
        strip.addStretch()
        strip.addWidget(self.match_count)
        strip.addWidget(self.filter)
        self.strip = QWidget()
        self.strip.setFixedHeight(54)
        self.strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.strip.setObjectName("intelStrip")
        self.strip.setLayout(strip)

        self.economy = EconomyPane()
        self.air = ForcesPane(self, AIR)
        self.ground = ForcesPane(self, GROUND)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.economy, TAB_NAMES[ECONOMY])
        self.tabs.addTab(self.air, TAB_NAMES[AIR])
        self.tabs.addTab(self.ground, TAB_NAMES[GROUND])
        # Three tabs always fit; the scroll arrows only ever appeared because the
        # selected tab's border made the bar ask for a few pixels more than it had.
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.currentChanged.connect(lambda _i: self.redraw())

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.strip)
        layout.addWidget(self.tabs, 1)
        self.setLayout(layout)
        self.redraw()

    # ------------------------------------------------------------------ state

    @property
    def accent(self) -> QColor:
        return OWN_ACCENT if self.player.is_blue else ENEMY_ACCENT

    def show_side(self, player: Player) -> None:
        self.player = player
        # The filter belongs to the question, not to the side, so it survives the
        # switch: "where are the Smerch" is usually asked of both.
        self.redraw()

    def fold_state(self, tab: int) -> set[str]:
        return self.folded.setdefault((self.player.is_blue, tab), set())

    def toggle_fold(self, tab: int, name: str) -> None:
        folded = self.fold_state(tab)
        folded.symmetric_difference_update({name})
        self.redraw()

    def toggle_all(self, tab: int) -> None:
        folded = self.fold_state(tab)
        forces = self._forces(tab)
        names = {group.name for group in forces.groups}
        folded.clear()
        if names - self.fold_state(tab):
            folded.update(names)
        self.redraw()

    # ----------------------------------------------------------------- drawing

    def _forces(self, tab: int) -> data.ForceTab:
        pane = self.air if tab == AIR else self.ground
        build = data.air_forces if tab == AIR else data.ground_forces
        return build(self.game, self.player, pane.chosen_sort, self.filter.text())

    def redraw(self) -> None:
        own = self.player.is_blue
        window = OWN_WINDOW if own else ENEMY_WINDOW
        accent = self.accent
        self.setStyleSheet(
            f"QDialog {{ background: {window}; }}"
            f"#intelStrip {{ background: {window};"
            f" border-left: 4px solid {accent.name()}; }}"
            f"QTabWidget::pane {{ border: none; background: {window}; }}"
            f"QTabBar::tab {{ background: transparent; color: #B7C6D2;"
            " padding: 6px 16px; font-size: 13px; border: none; }"
            f"QTabBar::tab:selected {{ background: {CARD_BG}; color: #F2F7FA;"
            f" font-weight: 600; border: 1px solid {CARD_BORDER};"
            " border-bottom: none; }"
        )
        self.side_switch.show_side(self.player)
        self.side_name.setText("BLUFOR" if own else "OPFOR")
        self.side_name.setStyleSheet(
            f"font-size: 15px; font-weight: 600; background: transparent;"
            f" border: none; color: {OWN_LABEL if own else ENEMY_LABEL};"
        )
        faction = self.game.coalition_for(self.player).faction.name
        # An enemy figure is an estimate, and saying so costs nothing: if the game
        # ever grows fog of war, the confidence goes on this line.
        self.side_note.setText(
            f"{faction} · Turn {self.game.turn}"
            if own
            else f"{faction} · estimate, turn {self.game.turn}"
        )

        self.economy.refresh(accent, data.economy(self.game, self.player))
        air = self._forces(AIR)
        ground = self._forces(GROUND)
        self.air.refresh(accent, air, self.fold_state(AIR))
        self.ground.refresh(accent, ground, self.fold_state(GROUND))

        needle = self.filter.text().strip()
        current = self.tabs.currentIndex()
        showing = air if current == AIR else ground if current == GROUND else None
        if needle and showing is not None:
            rows = sum(len(group.rows) for group in showing.groups)
            self.match_count.setText(f"{rows} row" + ("s" if rows != 1 else ""))
        else:
            self.match_count.setText("")
        self.filter.setEnabled(current != ECONOMY)
