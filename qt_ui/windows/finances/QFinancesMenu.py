from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import qt_ui.uiconstants as CONST
from game.game import Game
from game.income import BuildingIncome, Income
from game.theater import Player

#: Auto-spend categories: (last_turn_expenses key, label, settings flag). A row is
#: shown only if its flag exists in the running build.
_EXPENSE_CATEGORIES = [
    ("front_line", "Front line reinforcement", "automate_front_line_reinforcements"),
    ("aircraft", "Aircraft purchases", "automate_aircraft_reinforcements"),
    ("ground_objects", "SAM / ground repairs", "automate_ground_object_repairs"),
    ("buildings", "Building repairs", "automate_building_repairs"),
    ("runways", "Runway repairs", "automate_runway_repair"),
]

_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
_COLLAPSED = "▶"  # ▶
_EXPANDED = "▼"  # ▼


def _money(value: float, signed: bool = False) -> str:
    rounded = round(value)
    if signed:
        sign = "+" if rounded > 0 else ("-" if rounded < 0 else "")
        return f"{sign}{abs(rounded)}M"
    return f"{rounded}M"


def _label(
    text: str,
    style: Optional[str] = None,
    *,
    right: bool = False,
    center: bool = False,
    bold: bool = False,
) -> QLabel:
    label = QLabel(text)
    if right:
        label.setAlignment(_RIGHT)
    elif center:
        label.setAlignment(_CENTER)
    if style is not None:
        label.setProperty("style", style)
    if bold:
        font = label.font()
        font.setBold(True)
        label.setFont(font)
    return label


def _restyle(widget: QWidget, style: str) -> None:
    """Swap a widget's `style` property and force a QSS re-evaluation."""
    widget.setProperty("style", style)
    qstyle = widget.style()
    qstyle.unpolish(widget)
    qstyle.polish(widget)


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class QFinancesMenu(QDialog):
    """Finances dialog showing gross income, automated HQ spending and net.

    The income the player sees on the map is mostly auto-spent on reinforcements
    and repairs (when the matching automation is enabled) before they ever touch
    it. This dialog spells out income, that spending per category, and the net
    that actually reaches the budget, so the gap is no longer a mystery.
    """

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.setModal(True)
        self.setWindowTitle(f"Finances - Turn {game.turn}")
        self.setWindowIcon(CONST.ICONS["Money"])
        self.setMinimumSize(540, 440)

        income = Income(game, Player.BLUE)
        coalition = game.coalition_for(Player.BLUE)
        expenses = getattr(coalition, "last_turn_expenses", {}) or {}
        # No spend has been recorded yet on saves created before this feature,
        # or before the first turn is ended. Don't fake a net in that case.
        recorded = bool(expenses)
        total_spent = sum(expenses.values())
        gross = income.total
        net = gross - total_spent
        balance = coalition.budget

        root = QVBoxLayout(self)
        root.addWidget(self._summary(gross, total_spent, net, balance, recorded))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        detail = QVBoxLayout(content)
        detail.addWidget(self._income_box(income))
        detail.addWidget(self._expenses_box(expenses, total_spent, recorded))
        detail.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def _summary(
        self,
        gross: float,
        spent: float,
        net: float,
        balance: float,
        recorded: bool,
    ) -> QFrame:
        frame = QFrame()
        frame.setProperty("style", "summary-box")
        grid = QGridLayout(frame)
        grid.addWidget(_label("Gross income (next turn)"), 0, 0)
        grid.addWidget(_label(_money(gross, signed=True), "green", right=True), 0, 1)
        grid.addWidget(_label("HQ auto-spending (last turn)"), 1, 0)
        if recorded:
            grid.addWidget(
                _label(_money(-spent, signed=True), "expense", right=True), 1, 1
            )
        else:
            grid.addWidget(_label("n/a", "muted", right=True), 1, 1)
        grid.addWidget(_hline(), 2, 0, 1, 2)
        grid.addWidget(_label("NET (est.)", bold=True), 3, 0)
        if recorded:
            grid.addWidget(
                _label(
                    _money(net, signed=True),
                    "net" if net >= 0 else "net-neg",
                    right=True,
                ),
                3,
                1,
            )
        else:
            grid.addWidget(_label("n/a", "muted", right=True), 3, 1)
        grid.addWidget(_label("Available balance"), 4, 0)
        grid.addWidget(_label(f"{balance:.1f}M", "balance", right=True), 4, 1)
        return frame

    def _income_box(self, income: Income) -> QGroupBox:
        box = QGroupBox(f"Income - multiplier x{income.multiplier:.2f}")
        layout = QVBoxLayout(box)
        gross_pre = income.total_buildings + income.from_bases
        layout.addWidget(
            _label(
                f"{_money(gross_pre)} -> {_money(income.total)}", "muted", right=True
            )
        )

        layout.addWidget(_label("Bases", bold=True))
        bases = QGridLayout()
        control_points = reversed(
            sorted(income.control_points, key=lambda c: c.income_per_turn)
        )
        for i, cp in enumerate(control_points):
            bases.addWidget(_label(f"    {cp.name}"), i, 0)
            bases.addWidget(_label(_money(cp.income_per_turn), right=True), i, 1)
        layout.addLayout(bases)
        layout.addWidget(_hline())

        layout.addWidget(_label("Buildings", bold=True))
        by_category: dict[str, List[BuildingIncome]] = {}
        for building in income.buildings:
            by_category.setdefault(building.category, []).append(building)
        for category in sorted(
            by_category, key=lambda c: -sum(b.income for b in by_category[c])
        ):
            rows = sorted(by_category[category], key=lambda b: -b.income)
            subtotal = sum(b.income for b in rows)
            layout.addWidget(self._category_group(category, subtotal, rows))
        return box

    def _category_group(
        self, category: str, subtotal: float, rows: List[BuildingIncome]
    ) -> QWidget:
        """A disclosure section: an arrow header that expands its building rows."""
        title = f"{category.upper()} - {_money(subtotal)}"

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QPushButton(f"{_COLLAPSED}  {title}")
        header.setProperty("style", "disclosure")
        header.setCheckable(True)
        header.setChecked(False)
        outer.addWidget(header)

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(18, 0, 6, 4)
        for i, building in enumerate(rows):
            dead = round(building.income) == 0
            style = "muted" if dead else None
            grid.addWidget(_label(building.name, style), i, 0)
            grid.addWidget(
                _label(
                    f"{building.number} x {building.income_per_building}M =",
                    "muted",
                    right=True,
                ),
                i,
                1,
            )
            grid.addWidget(_label(_money(building.income), style, right=True), i, 2)
        inner.setVisible(False)
        outer.addWidget(inner)

        def toggle(checked: bool) -> None:
            inner.setVisible(checked)
            arrow = _EXPANDED if checked else _COLLAPSED
            header.setText(f"{arrow}  {title}")

        header.toggled.connect(toggle)
        return container

    def _expenses_box(
        self, expenses: dict[str, float], total_spent: float, recorded: bool
    ) -> QGroupBox:
        box = QGroupBox("HQ auto-spending - last turn")
        grid = QGridLayout(box)
        settings = self.game.settings
        row = 0

        if not recorded:
            note = _label(
                "No spending recorded yet - end a turn to populate these.", "muted"
            )
            grid.addWidget(note, row, 0, 1, 3)
            row += 1

        for key, label, flag in _EXPENSE_CATEGORIES:
            # Only show categories whose automation exists in this build.
            if not hasattr(type(settings), flag):
                continue
            enabled = bool(getattr(settings, flag, False))
            grid.addWidget(_label(label), row, 0)

            toggle = QPushButton(" ON " if enabled else " OFF")
            toggle.setCheckable(True)
            toggle.setChecked(enabled)
            toggle.setProperty("style", "pill-on" if enabled else "pill-off")
            toggle.setToolTip("Click to toggle. Takes effect from the next turn.")
            toggle.toggled.connect(self._make_automation_toggle(flag, toggle))
            grid.addWidget(toggle, row, 1)

            if not enabled:
                amount_text, amount_style = _money(0), "muted"
            elif not recorded or key not in expenses:
                amount_text, amount_style = "-", "muted"  # on, but not recorded yet
            else:
                amount = expenses[key]
                if round(amount) == 0:
                    amount_text, amount_style = _money(0), "muted"
                else:
                    amount_text, amount_style = _money(-amount, signed=True), "expense"
            grid.addWidget(_label(amount_text, amount_style, right=True), row, 2)
            row += 1

        grid.addWidget(_hline(), row, 0, 1, 3)
        grid.addWidget(_label("Total spent by HQ", bold=True), row + 1, 0)
        total_text = _money(-total_spent, signed=True) if recorded else "n/a"
        grid.addWidget(
            _label(total_text, "expense" if recorded else "muted", right=True),
            row + 1,
            2,
        )
        return box

    def _make_automation_toggle(
        self, flag: str, button: QPushButton
    ) -> Callable[[bool], None]:
        def handler(checked: bool) -> None:
            setattr(self.game.settings, flag, checked)
            button.setText(" ON " if checked else " OFF")
            _restyle(button, "pill-on" if checked else "pill-off")

        return handler
