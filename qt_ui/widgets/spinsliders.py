import re
from datetime import timedelta
from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QSlider, QHBoxLayout

from qt_ui.widgets.floatspinners import FloatSpinner

#: Wide enough to aim with, narrow enough that the settings stay a column rather
#: than stretching across whatever width the dialog happens to have.
SLIDER_WIDTH = 260


class FloatSpinSlider(QHBoxLayout):
    def __init__(
        self,
        minimum: float,
        maximum: float,
        initial: float,
        divisor: int,
        prefix: str = "X ",
        decimals: int = 1,
    ) -> None:
        super().__init__()

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimumWidth(SLIDER_WIDTH)
        slider.setMinimum(int(minimum * divisor))
        slider.setMaximum(int(maximum * divisor))
        slider.setValue(int(initial * divisor))
        self.spinner = FloatSpinner(
            divisor, minimum, maximum, initial, prefix, decimals
        )
        slider.valueChanged.connect(lambda x: self.spinner.setValue(x))
        self.spinner.valueChanged.connect(lambda x: slider.setValue(x))

        self.addWidget(slider)
        self.addWidget(self.spinner)

    @property
    def value(self) -> float:
        return self.spinner.real_value


class TimeInputs(QtWidgets.QHBoxLayout):
    def __init__(self, initial: timedelta, minimum: int, maximum: int) -> None:
        super().__init__()

        initial_minutes = int(initial.total_seconds() / 60)

        slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        slider.setMinimumWidth(SLIDER_WIDTH)
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setValue(initial_minutes)
        self.spinner = TimeSpinner(minimum, maximum, initial_minutes)
        slider.valueChanged.connect(lambda x: self.spinner.setValue(x))
        self.spinner.valueChanged.connect(lambda x: slider.setValue(x))

        self.addWidget(slider)
        self.addWidget(self.spinner)

    @property
    def value(self) -> timedelta:
        return timedelta(minutes=self.spinner.value())


class MinuteSecondSpinner(QtWidgets.QSpinBox):
    """Seconds, shown as mm:ss, and stepped a whole minute at a time.

    A QTimeEdit is the obvious widget for this and was the one here. Two things were
    wrong with it. Its arrows step whichever section the cursor happens to sit in, so
    pressing up moved a flight by one *second* and there was no way to tell why; and a
    stylesheet that gives it a border makes Qt lay out its sub-controls itself, which
    left the buttons somewhere clicks did not land -- so clicking an arrow selected the
    text instead of changing anything.

    A spin box has one value and one pair of arrows, which is what this setting is.
    Seconds can still be typed.
    """

    def __init__(self, seconds: int, maximum: int) -> None:
        super().__init__()
        self.setRange(0, maximum)
        self.setSingleStep(60)
        self.setValue(seconds)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def textFromValue(self, val: int) -> str:
        return f"{val // 60:02d}:{val % 60:02d}"

    def valueFromText(self, text: str) -> int:
        minutes, _, seconds = text.strip().partition(":")
        try:
            return int(minutes or 0) * 60 + int(seconds or 0)
        except ValueError:
            return 0

    def validate(self, text: str, pos: int) -> object:
        """Accept mm:ss, and everything half-typed on the way to it."""
        stripped = text.strip()
        if re.fullmatch(r"\d{0,2}", stripped) or re.fullmatch(r"\d{1,2}:\d?", stripped):
            return QValidator.State.Intermediate, text, pos
        if re.fullmatch(r"\d{1,2}:[0-5]\d", stripped):
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Invalid, text, pos


class TimeSpinner(QtWidgets.QSpinBox):
    def __init__(
        self,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        initial: Optional[int] = None,
    ) -> None:
        super().__init__()

        if minimum is not None:
            self.setMinimum(minimum)
        if maximum is not None:
            self.setMaximum(maximum)
        if initial is not None:
            self.setValue(initial)

    def textFromValue(self, val: int) -> str:
        return f"{val} minutes"


class CurrencySpinner(QtWidgets.QSpinBox):
    def __init__(
        self,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        initial: Optional[int] = None,
    ) -> None:
        super().__init__()

        if minimum is not None:
            self.setMinimum(minimum)
        if maximum is not None:
            self.setMaximum(maximum)
        if initial is not None:
            self.setValue(initial)

    def textFromValue(self, val: int) -> str:
        return f"${val}"
