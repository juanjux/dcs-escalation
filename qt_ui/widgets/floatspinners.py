from typing import Optional

from PySide6.QtWidgets import QSpinBox


class FloatSpinner(QSpinBox):
    def __init__(
        self,
        divisor: int,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        initial: Optional[float] = None,
        prefix: str = "X ",
        decimals: int = 1,
    ) -> None:
        super().__init__()
        self.divisor = divisor
        #: What the number means. Most of these are multipliers, which is why "X " is
        #: the default, but a setting that is a quantity rather than a multiplier
        #: passes its own -- an empty one included.
        self.prefix = prefix
        #: How many decimals to show. A setting whose real value is 0.05 read as "0.1"
        #: at one, which is not the number the player is setting.
        self.decimals = decimals

        if minimum is not None:
            self.setMinimum(int(minimum * divisor))
        if maximum is not None:
            self.setMaximum(int(maximum * divisor))
        if initial is not None:
            self.setValue(int(initial * divisor))

    def textFromValue(self, val: int) -> str:
        return f"{self.prefix}{val / self.divisor:.{self.decimals}f}"

    @property
    def real_value(self) -> float:
        return self.value() / self.divisor
