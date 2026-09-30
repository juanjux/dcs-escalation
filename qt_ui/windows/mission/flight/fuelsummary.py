"""Shared, per-refuel fuel estimates for the flight editor."""

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from game.ato.fuelestimate import FuelEstimate
from qt_ui.widgets.cards import make_transparent


def segment_label(index: int, count: int) -> str:
    if count == 1:
        return "Fuel"
    if count == 2:
        return "Before refuel" if index == 0 else "After refuel"
    if index == 0:
        return "To refuel 1"
    if index == count - 1:
        return f"After refuel {index}"
    return f"Refuel {index} → {index + 1}"


class FuelBar(QWidget):
    """What the plan asks for against what the flight carries, as a bar.

    "Fuel: ~10,057 of 13,033" is two numbers you have to divide in your head to know
    whether it is close. The bar is the division: the fill is what the route needs, the
    tick is what the aircraft has, and the fill turns red when it goes past the tick.
    """

    WIDTH = 220
    HEIGHT = 6

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self.WIDTH, self.HEIGHT + 6)
        self.required = 0.0
        self.carried = 0.0
        make_transparent(self)

    def show_fuel(self, required: float, carried: float) -> None:
        self.required, self.carried = required, carried
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            top = (self.height() - self.HEIGHT) // 2
            width = self.width()
            track = QRect(0, top, width, self.HEIGHT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1D2731"))
            painter.drawRoundedRect(track, 3, 3)

            if self.carried <= 0:
                return
            # The scale runs to whichever is larger, so an overrun has somewhere to be
            # drawn rather than being clipped at full.
            top_of_scale = max(self.carried, self.required)
            enough = self.required <= self.carried
            fill_width = int(width * self.required / top_of_scale)
            painter.setBrush(QColor("#86C39A" if enough else "#D9645E"))
            painter.drawRoundedRect(
                QRect(0, top, max(2, fill_width), self.HEIGHT), 3, 3
            )

            tick_x = int(width * self.carried / top_of_scale)
            painter.setBrush(QColor("#F2F7FA"))
            painter.drawRect(QRect(min(tick_x, width - 2), top - 2, 2, self.HEIGHT + 4))
        finally:
            painter.end()


class FuelSummary(QWidget):
    def __init__(self, *, show_bars: bool = False) -> None:
        super().__init__()
        self.show_bars = show_bars
        make_transparent(self)
        self.rows = QGridLayout(self)
        self.rows.setContentsMargins(0, 4, 0, 4)
        self.rows.setHorizontalSpacing(12)
        self.rows.setVerticalSpacing(6)

    def show_estimates(
        self, estimates: list[FuelEstimate], *, kg: bool = False
    ) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        unit = "kg" if kg else "lb"
        for index, estimate in enumerate(estimates):
            needed = estimate.required.kgs if kg else estimate.required.pounds
            carried = estimate.carried.kgs if kg else estimate.carried.pounds
            color = "#86C39A" if estimate.enough else "#D9645E"
            caption = QLabel(segment_label(index, len(estimates)))
            numbers = QLabel(f"~{needed:,.0f} / {carried:,.0f} {unit}")
            status = QLabel(
                f"+{carried - needed:,.0f} {unit}"
                if estimate.enough
                else f"short {needed - carried:,.0f} {unit}"
            )
            for column, label in enumerate((caption, numbers, status)):
                label.setStyleSheet(
                    f"font-size: 12px; color: {color if column == 2 else '#D3DFE8'};"
                    " background: transparent; border: none;"
                )
                if column:
                    label.setAlignment(Qt.AlignmentFlag.AlignRight)
                position = column + (1 if self.show_bars and column else 0)
                self.rows.addWidget(label, index, position)
            if self.show_bars:
                bar = FuelBar()
                bar.setFixedWidth(130)
                bar.show_fuel(estimate.required.pounds, estimate.carried.pounds)
                self.rows.addWidget(bar, index, 1)
        self.setToolTip(
            "Estimated requirement / available fuel, including safe reserve and 10% margin. "
            "At each refuel, assumes a tanker is available and fills internal and fitted "
            "external tanks. Does not model tank jettison."
        )
