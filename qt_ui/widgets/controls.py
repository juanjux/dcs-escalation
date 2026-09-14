"""The small controls the redesigned dialogs are built from.

A segmented control instead of a combo box for a handful of mutually exclusive
choices, and a key/value row instead of a label-and-field grid. Both exist because a
form of combo boxes reads as a form: you have to open each one to find out what it
says. Four flat buttons say it without being touched, and a key/value row puts the
answer where the eye already is.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from qt_ui.widgets.cards import make_transparent

ROW_HEIGHT = 36
CONTROL_HEIGHT = 28

KEY = "#B7C6D2"
VALUE = "#D3DFE8"
SELECTED_BG = "#8FC3F0"
SELECTED_TEXT = "#0F1922"
IDLE_TEXT = "#B7C6D2"
IDLE_BG = "#26343F"
BORDER = "#3A4B5C"

#: Greyed: there is nothing to choose here until something else is turned off.
DISABLED_BG = "#1B2530"
DISABLED_TEXT = "#4F6070"
DISABLED_BORDER = "#28333D"


def mono(size: int = 13) -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(size)
    return font


class Segmented(QWidget):
    """One button per choice, the chosen one filled.

    For a short, fixed set where seeing the options *is* the point -- a start type,
    behind-or-ahead. A combo box hides three of the four answers behind a click and
    tells you nothing about how many there were.
    """

    selection_changed = Signal(object)

    def __init__(
        self,
        options: Sequence[tuple[str, Any]],
        current: Any = None,
        parent: Optional[QWidget] = None,
        fill: bool = True,
    ) -> None:
        super().__init__(parent)
        self._values: list[Any] = []

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        for index, (label, value) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(CONTROL_HEIGHT)
            # Filling is right for a set of equals -- a start type, behind-or-ahead --
            # and wrong for a filter bar, where the widths should say how long the
            # words are rather than how many filters there happen to be.
            button.setSizePolicy(
                (
                    QSizePolicy.Policy.Expanding
                    if fill
                    else QSizePolicy.Policy.Preferred
                ),
                QSizePolicy.Policy.Fixed,
            )
            button.setStyleSheet(
                f"QPushButton {{ background: {IDLE_BG}; color: {IDLE_TEXT};"
                f" border: 1px solid {BORDER}; border-radius: 3px;"
                f" padding: 0 10px; font-size: 12px; }}"
                f"QPushButton:checked {{ background: {SELECTED_BG};"
                f" color: {SELECTED_TEXT}; font-weight: 600; }}"
                f"QPushButton:disabled {{ color: #4F6070; }}"
            )
            self.group.addButton(button, index)
            self._values.append(value)
            row.addWidget(button)
            if value == current:
                button.setChecked(True)

        if not fill:
            row.addStretch()
        self.setLayout(row)
        self.group.idClicked.connect(self._on_clicked)

    def _on_clicked(self, index: int) -> None:
        self.selection_changed.emit(self._values[index])

    @property
    def value(self) -> Any:
        index = self.group.checkedId()
        return self._values[index] if index >= 0 else None

    def set_value(self, value: Any) -> None:
        """Move the selection without announcing it, for a change made elsewhere."""
        for index, candidate in enumerate(self._values):
            if candidate == value:
                button = self.group.button(index)
                if button is not None and not button.isChecked():
                    button.setChecked(True)
                return

    def set_enabled(self, enabled: bool) -> None:
        for button in self.group.buttons():
            button.setEnabled(enabled)


def key_value(
    key: str,
    value: QWidget,
    height: int = ROW_HEIGHT,
    key_width: int = 136,
) -> QWidget:
    """One row of a key/value card: the name on the left, the answer on the right."""
    row = QHBoxLayout()
    row.setContentsMargins(14, 0, 14, 0)
    row.setSpacing(10)

    label = QLabel(key)
    label.setFixedWidth(key_width)
    label.setStyleSheet(
        f"font-size: 12px; color: {KEY}; background: transparent; border: none;"
    )
    row.addWidget(label)
    row.addWidget(value, 1)

    holder = QWidget()
    holder.setFixedHeight(height)
    make_transparent(holder)
    holder.setLayout(row)
    return holder


def value_label(
    text: str, monospace: bool = False, align_right: bool = False
) -> QLabel:
    """The right-hand half of a key/value row when it is only text."""
    label = QLabel(text)
    if monospace:
        label.setFont(mono())
    label.setStyleSheet(
        f"font-size: 13px; color: {VALUE}; background: transparent; border: none;"
    )
    if align_right:
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return label


def styled_input(widget: QWidget, width: Optional[int] = None) -> QWidget:
    """Give a combo or spinner the card vocabulary's field styling."""
    widget.setFixedHeight(CONTROL_HEIGHT)
    if width is not None:
        widget.setFixedWidth(width)
    # The disabled state is spelled out, because a stylesheet replaces the palette
    # the style would otherwise have greyed for us: the payload preset is disabled
    # whenever Custom loadout is on, and without this it looked like a combo that
    # simply refused to open.
    # The two sub-control rules are not decoration. Giving a spin box a border in a
    # stylesheet hands its whole layout to the stylesheet style, and with nothing said
    # about the buttons they end up somewhere the clicks do not land: pressing an arrow
    # selected the text instead of stepping the value. Saying where they are puts them
    # back, and the right-hand padding keeps the digits out from under them.
    widget.setStyleSheet(
        f"QWidget {{ background: {IDLE_BG}; color: {VALUE};"
        f" border: 1px solid {BORDER}; border-radius: 3px; padding: 0 6px;"
        " font-size: 12px; }"
        f"QWidget:disabled {{ background: {DISABLED_BG}; color: {DISABLED_TEXT};"
        f" border-color: {DISABLED_BORDER}; }}"
        " QAbstractSpinBox { padding-right: 20px; }"
        " QAbstractSpinBox::up-button { subcontrol-origin: border;"
        " subcontrol-position: top right; width: 18px; border: none;"
        " image: url(resources/stylesheets/chevron-up.png); }"
        " QAbstractSpinBox::down-button { subcontrol-origin: border;"
        " subcontrol-position: bottom right; width: 18px; border: none;"
        " image: url(resources/stylesheets/chevron-down.png); }"
    )
    return widget


def on_click(button: QPushButton, handler: Callable[[], None]) -> QPushButton:
    button.clicked.connect(lambda _checked=False: handler())
    return button


#: The app-wide QPushButton is a light grey gradient with white text on it, which is
#: hard to read anywhere and unreadable on a dark panel. These are the same three
#: meanings in the palette the rest of these controls use.
BUTTON_KINDS = {
    "normal": (IDLE_BG, BORDER, VALUE, "#31424F"),
    "primary": ("#2B506D", "#3F6B8C", "#DCE9F4", "#34617F"),
    "danger": ("#4A2A2A", "#6E3B3B", "#E8C5C5", "#5C3434"),
}


def button(
    text: str,
    kind: str = "normal",
    handler: Optional[Callable[[], None]] = None,
) -> QPushButton:
    """A button in the window's own palette rather than the app's grey gradient."""
    background, border, ink, hover = BUTTON_KINDS[kind]
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setMinimumHeight(CONTROL_HEIGHT)
    widget.setStyleSheet(
        f"QPushButton {{ background: {background}; color: {ink};"
        f" border: 1px solid {border}; border-radius: 3px; padding: 4px 14px;"
        f" font-size: 12px; font-weight: {'600' if kind != 'normal' else 'normal'}; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:disabled {{ background: {DISABLED_BG}; color: {DISABLED_TEXT};"
        f" border-color: {DISABLED_BORDER}; }}"
    )
    if handler is not None:
        on_click(widget, handler)
    return widget


#: Qt lays a plain-text tooltip out on one line per paragraph and lets it run as wide
#: as it likes, so a paragraph of explanation becomes a band across the whole monitor.
#: Rich text wraps where it is told to, so the wrapping is done here.
TOOLTIP_COLUMNS = 82


def wrapped_tooltip(text: str, columns: int = TOOLTIP_COLUMNS) -> str:
    """A long explanation as rich text, wrapped to a readable column."""
    import html
    import textwrap

    blank_line = chr(10) * 2
    paragraphs = []
    for block in text.split(blank_line):
        lines: list[str] = []
        for raw in block.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            # Keep the indent of a bulleted line, so a list still reads as a list.
            indent = " " * (len(raw) - len(raw.lstrip()))
            lines.extend(
                textwrap.wrap(
                    stripped,
                    width=columns,
                    initial_indent=indent,
                    # Only a line that was already indented -- a bullet -- keeps a hanging
                    # indent; an ordinary paragraph would just look ragged.
                    subsequent_indent=indent + ("  " if indent else ""),
                )
                or [""]
            )
        paragraphs.append("<br>".join(html.escape(line) for line in lines))
    return "<div>" + "<br><br>".join(paragraphs) + "</div>"
