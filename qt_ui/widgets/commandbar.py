"""The status and action strip above the map.

Six group boxes used to sit here — turn, weather, factions, budget, intel and a row of
buttons — each with its own frame, its own margins and its own type sizes. They are one
strip now, 80 px, with hairline dividers between cells and the same 10.5 px caps
captions used everywhere else in the fork.

The rule the layout follows: **a frame means you can click it.** Turn, weather and
factions are read-only and sit frameless; Budget and Intel open dialogs and are drawn as
cells with a border, an accent caption and a chevron.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.income import Income
from game.theater import Player
from game.weather.conditions import Conditions
from qt_ui import uiconstants as CONST
from qt_ui.widgets.conditions.QWeatherWidget import forecast_summary, wind_summary

BAR_BG = "#26343F"
#: The weather refresh button. Big enough to be an easy target between planning and
#: take-off, with the icon inset so it reads as a button rather than as a character
#: that happens to be clickable.
REFRESH_BUTTON_PX = 28
REFRESH_ICON_PX = 16

CELL_BG = "#2D3E50"
CELL_BORDER = "#3A4B5C"
CELL_HOVER = "#33475C"
DIVIDER = "#3A4B5C"

CAPTION = "#6B7A87"
ACCENT = "#8FC3F0"
VALUE = "#F2F7FA"
SECONDARY = "#D3DFE8"
TERTIARY = "#8E9DAA"

GOOD = "#86C39A"
EVEN = "#E0A86B"
BAD = "#D9645E"

BLUE_SWATCH = "#5FA8E6"
RED_SWATCH = "#E06565"

BAR_HEIGHT = 80
CELL_HEIGHT = 52
#: Below this the strip has to give something up; Intel goes first, then the winds.
MIN_WIDTH_FOR_INTEL = 1880
MIN_WIDTH_FOR_WINDS = 1660


def _font(
    pixels: float, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False
):
    font = QFont("Consolas") if mono else QFont()
    font.setPixelSize(int(pixels))
    font.setWeight(weight)
    return font


def _label(
    text: str = "",
    pixels: float = 12,
    colour: str = SECONDARY,
    weight: QFont.Weight = QFont.Weight.Normal,
    mono: bool = False,
) -> QLabel:
    label = QLabel(text)
    label.setFont(_font(pixels, weight, mono))
    label.setStyleSheet(f"color: {colour}; background: transparent;")
    return label


def _caption(text: str, colour: str = CAPTION) -> QLabel:
    """The 10.5 px letter-spaced caps every section in the fork is titled with."""
    label = QLabel(text.upper())
    font = _font(10.5, QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
    label.setFont(font)
    label.setStyleSheet(f"color: {colour}; background: transparent;")
    return label


class Divider(QFrame):
    """One hairline between two cells."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(1, CELL_HEIGHT)
        self.setStyleSheet(f"background: {DIVIDER};")


class Cell(QWidget):
    """A caption over its content. Sized by what it holds, never fixed."""

    def __init__(
        self, caption: str, *, clickable: bool = False, chevron: bool = True
    ) -> None:
        super().__init__()
        self.clickable = clickable
        # An object name, not the class name: a Qt type selector matches the exact
        # class, so `Cell { ... }` never reached BudgetCell or IntelCell and the two
        # cells that open dialogs were drawn with no frame at all.
        self.setObjectName("commandCell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QVBoxLayout()
        # A framed cell needs padding inside its border; a bare one does not.
        column.setContentsMargins(*((10, 8, 10, 8) if clickable else (0, 6, 0, 6)))
        column.setSpacing(3)
        self.setLayout(column)

        self.caption = _caption(caption, ACCENT if chevron and clickable else CAPTION)
        if clickable:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            row.addWidget(self.caption)
            if chevron:
                row.addWidget(_label("›", 11, ACCENT, QFont.Weight.Bold))
            row.addStretch()
            column.addLayout(row)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._paint_frame(CELL_BG)
        else:
            column.addWidget(self.caption)
            self._paint_bare()
        self.body = QHBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        column.addLayout(self.body)
        column.addStretch()

    def _paint_frame(self, background: str) -> None:
        self.setStyleSheet(
            f"#commandCell {{ background: {background};"
            f" border: 1px solid {CELL_BORDER}; border-radius: 3px; }}"
        )

    def _paint_bare(self) -> None:
        """No frame, and no inherited fill from the application stylesheet either."""
        self.setStyleSheet("#commandCell { background: transparent; border: none; }")

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        if self.clickable:
            self._paint_frame(CELL_HOVER)

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        if self.clickable:
            self._paint_frame(CELL_BG)


class ClickableCell(Cell):
    """A cell that opens a dialog."""

    def __init__(self, caption: str, on_click: Callable[[], None]) -> None:
        super().__init__(caption, clickable=True)
        self._on_click = on_click
        self.enabled = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if self.enabled and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()


class TurnCell(Cell):
    """Which turn it is, and when that is."""

    def __init__(self) -> None:
        # Framed without a chevron: a double click opens the conditions dialog, so it
        # is not read-only, but it is not a button either.
        super().__init__("Turn", clickable=True, chevron=False)
        self.number = _label("—", 24, VALUE, QFont.Weight.DemiBold, mono=True)
        self.body.addWidget(self.number)
        stack = QVBoxLayout()
        stack.setContentsMargins(0, 2, 0, 0)
        stack.setSpacing(1)
        self.date = _label("", 13, SECONDARY, QFont.Weight.Medium)
        self.clock = _label("", 11.5, TERTIARY)
        stack.addWidget(self.date)
        stack.addWidget(self.clock)
        self.body.addLayout(stack)

    def set_turn(self, turn: int, conditions: Conditions) -> None:
        self.number.setText(str(turn))
        self.date.setText(conditions.start_time.strftime("%d %B %Y"))
        self.clock.setText(
            f"{conditions.start_time.strftime('%H:%M')} local"
            f" · {conditions.time_of_day.name.lower()}"
        )


class WeatherCell(Cell):
    """What the sky is doing, and the winds at the three levels that matter."""

    def __init__(self, on_refresh: Callable[[], None]) -> None:
        super().__init__("Weather", clickable=True, chevron=False)
        self.icon = QLabel()
        self.icon.setFixedSize(24, 24)
        self.icon.setStyleSheet("background: transparent;")
        self.body.addWidget(self.icon)

        stack = QVBoxLayout()
        stack.setContentsMargins(0, 1, 0, 0)
        stack.setSpacing(1)
        self.clouds = _label("", 13, SECONDARY, QFont.Weight.Medium)
        self.rain_and_fog = _label("", 11.5, TERTIARY)
        stack.addWidget(self.clouds)
        stack.addWidget(self.rain_and_fog)
        self.body.addLayout(stack)

        self.winds_holder = QWidget()
        self.winds_holder.setStyleSheet("background: transparent;")
        winds = QVBoxLayout()
        winds.setContentsMargins(12, 0, 0, 0)
        winds.setSpacing(0)
        self.winds_holder.setLayout(winds)
        self.winds: list[QLabel] = []
        for _ in range(3):
            line = _label("", 11, SECONDARY, mono=True)
            winds.addWidget(line)
            self.winds.append(line)
        self.body.addWidget(self.winds_holder)

        # A drawn icon rather than the text glyph U+27F3, which falls back to
        # whatever font on the machine has it: wrong weight, off the button's
        # centre, and on some machines not an arrow at all. The icon set already
        # carries reload.png for both themes.
        #
        # The same fix was made to QWeatherWidget, which is the panel this command
        # bar REPLACED -- so it was invisible, and the button people actually press
        # kept its glyph.
        self.refresh = QPushButton()
        self.refresh.setIcon(QIcon(CONST.ICONS["Reload"]))
        self.refresh.setIconSize(QSize(REFRESH_ICON_PX, REFRESH_ICON_PX))
        self.refresh.setFixedSize(REFRESH_BUTTON_PX, REFRESH_BUTTON_PX)
        self.refresh.setToolTip("Fetch a fresh observation")
        self.refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh.setStyleSheet(
            f"QPushButton {{ background: {CELL_BG}; border: 1px solid {CELL_BORDER};"
            f" border-radius: 3px; color: {SECONDARY}; }}"
            f"QPushButton:hover {{ background: {CELL_HOVER}; }}"
        )
        self.refresh.clicked.connect(on_refresh)
        self.refresh.setVisible(False)
        self.body.addWidget(self.refresh)

    def set_weather(self, conditions: Conditions, can_refresh: bool) -> None:
        clouds, rain, fog, kind = forecast_summary(conditions)
        self.clouds.setText(clouds)
        self.rain_and_fog.setText(
            f"{rain.lower()} · {fog.lower()}"
            if rain.lower().startswith("no")
            else f"{rain} · {fog.lower()}"
        )
        for label, (level, speed, direction) in zip(
            self.winds, wind_summary(conditions)
        ):
            label.setText(f"{level:<5}{speed} {direction}")
        self.refresh.setVisible(can_refresh)

    def set_icon(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is not None:
            self.icon.setPixmap(
                pixmap.scaled(
                    QSize(24, 24),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def show_winds(self, shown: bool) -> None:
        self.winds_holder.setVisible(shown)


class _Swatch(QWidget):
    """The 8 px square that says which side a faction is."""

    def __init__(self, colour: str) -> None:
        super().__init__()
        self.colour = colour
        self.setFixedSize(8, 8)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colour))
        painter.drawRoundedRect(0, 0, 8, 8, 2, 2)


class FactionsCell(Cell):
    """Who is fighting, blue over red."""

    def __init__(self) -> None:
        super().__init__("Factions")
        stack = QVBoxLayout()
        stack.setContentsMargins(0, 1, 0, 0)
        stack.setSpacing(3)
        self.names = []
        for colour in (BLUE_SWATCH, RED_SWATCH):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(7)
            swatch = _Swatch(colour)
            row.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)
            name = _label("", 12.5, SECONDARY)
            row.addWidget(name)
            row.addStretch()
            stack.addLayout(row)
            self.names.append(name)
        self.body.addLayout(stack)

    def set_factions(self, blue: str, red: str) -> None:
        self.names[0].setText(blue)
        self.names[1].setText(red)


class BudgetCell(ClickableCell):
    """What there is to spend, and what next turn brings."""

    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__("Budget", on_click)
        self.amount = _label("—", 24, VALUE, QFont.Weight.DemiBold, mono=True)
        self.body.addWidget(self.amount)
        self.delta = _label("", 12.5, GOOD, QFont.Weight.DemiBold, mono=True)
        self.body.addWidget(self.delta, 0, Qt.AlignmentFlag.AlignBottom)
        self.body.addStretch()

    def set_budget(self, budget: float, income: float) -> None:
        self.amount.setText(f"${budget:.1f}M")
        sign = "+" if income >= 0 else "−"
        self.delta.setText(f"{sign}{abs(income):.1f}M")
        self.delta.setStyleSheet(
            f"color: {GOOD if income >= 0 else BAD}; background: transparent;"
        )
        self.setToolTip(f"{income:+.1f}M per turn")


class _Track(QWidget):
    """One 52×6 bar: how a side compares, as a length and a colour."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(52, 6)
        self.fraction = 0.0
        self.colour = TERTIARY

    def set_state(self, fraction: float, colour: str) -> None:
        self.fraction = max(0.05, min(1.0, fraction))
        self.colour = colour
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1D2731"))
        painter.drawRect(0, 0, 52, 6)
        painter.setBrush(QColor(self.colour))
        painter.drawRect(0, 0, int(52 * self.fraction), 6)


class IntelCell(ClickableCell):
    """Three comparisons, as bars rather than sentences."""

    COLUMNS = ("Air superiority", "Front line", "Economy")

    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__("Intel", on_click)
        self.tracks: list[_Track] = []
        self.words: list[QLabel] = []
        for name in self.COLUMNS:
            column = QVBoxLayout()
            column.setContentsMargins(0, 1, 0, 0)
            column.setSpacing(3)
            column.addWidget(_label(name, 11.5, TERTIARY))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(7)
            track = _Track()
            row.addWidget(track, 0, Qt.AlignmentFlag.AlignVCenter)
            word = _label("", 11, TERTIARY, QFont.Weight.DemiBold)
            row.addWidget(word)
            row.addStretch()
            column.addLayout(row)
            self.body.addLayout(column)
            self.body.addSpacing(6)
            self.tracks.append(track)
            self.words.append(word)

    @staticmethod
    def state_for(ratio: float) -> tuple[str, str]:
        """A word and a colour for how one side compares with the other."""
        if ratio >= 1.2:
            return "strong", GOOD
        if ratio >= 0.8:
            return "even", EVEN
        return "weak", BAD

    def set_intel(self, ratios: list[float], gathering: bool = False) -> None:
        for track, word, ratio in zip(self.tracks, self.words, ratios):
            if gathering:
                track.set_state(0.05, TERTIARY)
                word.setText("no data")
                word.setStyleSheet(f"color: {TERTIARY}; background: transparent;")
                continue
            text, colour = self.state_for(ratio)
            # Even sides fill half the track, so the length reads as the ratio does.
            track.set_state(ratio / 2, colour)
            word.setText(text)
            word.setStyleSheet(f"color: {colour}; background: transparent;")


def force_ratio(own: int, enemy: int) -> float:
    """Enemy eliminated counts as the top of the scale rather than a division by zero."""
    if not enemy:
        return 2.0
    return own / enemy


def intel_ratios(game: Game) -> list[float]:
    data = game.game_stats.data_per_turn[-1]
    return [
        force_ratio(data.allied_units.aircraft_count, data.enemy_units.aircraft_count),
        force_ratio(data.allied_units.vehicles_count, data.enemy_units.vehicles_count),
        force_ratio(
            int(Income(game, player=Player.BLUE).total),
            int(Income(game, player=Player.RED).total),
        ),
    ]


def blend_into_bar(layout: QLayout) -> None:
    """Take a shared widget's own colours off it so it sits in the strip.

    MaxPlayerCount is a QLabeledWidget used only here, and its labels carry whatever
    the application stylesheet gives a QLabel -- which in the strip reads as a patch of
    a different colour. The count goes mono, like the other numbers.
    """
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if not isinstance(widget, QLabel):
            continue
        mono = widget.text().strip().isdigit()
        widget.setFont(
            _font(11, QFont.Weight.DemiBold if mono else QFont.Weight.Normal, mono)
        )
        widget.setStyleSheet(
            f"color: {SECONDARY if mono else TERTIARY}; background: transparent;"
        )
