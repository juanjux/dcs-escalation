"""Cards with their captions above them, the shape the redesigned dialogs use.

A ``QGroupBox`` puts its title inside its own frame, which means every section pays for
a border, a title inset and a set of margins before it shows anything. These draw the
caption above a plain card instead: the name reads as a heading, the card holds only
content, and two cards side by side line up on their contents rather than on their
frames.

Written once here because the debriefing, the flight dialog and the squadron dialog
were each about to grow their own copy, and a fourth would have drifted.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QSizePolicy,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

CARD_BG = "#14202B"
CARD_BORDER = "#1D2731"
CAPTION = "#6B7A87"
HINT = "#4F6070"
#: For a hint that explains why something is switched off.
LOUD_HINT = "#E0A86B"

CAPTION_HEIGHT = 20


#: Qt style sheets cascade to children, so "background: transparent; border: none;"
#: set on a card's contents strips the border off every line edit, button and combo
#: inside it -- which is exactly what happened: the text boxes and the Assign button
#: became invisible labels. Scoping the rule to one object name keeps it where it was
#: meant to be.
_TRANSPARENT_SERIAL = [0]


def make_transparent(widget: QWidget) -> QWidget:
    """Give this widget -- and only this widget -- no background and no border."""
    if not widget.objectName():
        _TRANSPARENT_SERIAL[0] += 1
        widget.setObjectName(f"cardInner{_TRANSPARENT_SERIAL[0]}")
    name = widget.objectName()
    existing = widget.styleSheet() or ""
    widget.setStyleSheet(
        f"{existing} #{name} {{ background: transparent; border: none; }}"
    )
    return widget


def shrinkable_widget(widget: QWidget) -> QWidget:
    """Let a widget be narrower than its contents want to be.

    A QLabel asks for the full width of whatever it is showing, and a layout has to
    honour that, so one long squadron name or one long list of SAM types sets the
    smallest the whole window can be -- and the window then grows itself the moment
    it is shown. These are things worth reading and not worth a horizontal
    scrollbar, so they give up the demand and clip instead.

    Ignored also makes a widget expand into whatever room there is, so a row that
    needs its pieces packed together should wrap them in a box and shrink the box.
    """
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    widget.setMinimumWidth(0)
    return widget


def shrinkable(label: QLabel) -> QLabel:
    """shrinkable_widget, for the common case of a label on its own."""
    shrinkable_widget(label)
    return label


def card() -> QWidget:
    """An empty card. Give it a layout and put the content in.

    Scoped to the card's own object name, because an unscoped rule cascades: a card
    that said "border: 1px solid" drew that border around every label inside it as
    well, and cancelling the cascade wholesale took the border off the line edits and
    buttons that needed one.
    """
    widget = QWidget()
    # A plain QWidget does not paint a stylesheet background unless it is told to.
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    _TRANSPARENT_SERIAL[0] += 1
    widget.setObjectName(f"card{_TRANSPARENT_SERIAL[0]}")
    widget.setStyleSheet(
        f"#{widget.objectName()} {{ background: {CARD_BG};"
        f" border: 1px solid {CARD_BORDER}; border-radius: 3px; }}"
    )
    return widget


def caption(text: str, hint: str = "", loud_hint: bool = False) -> QWidget:
    """A section's name, above its card rather than inside a frame.

    The hint is for the sentence a group box would have put inside itself and pushed
    the content down for -- "AUTO lets the generator pick", "TOT comes from the
    package". It belongs with the heading, in the quietest colour on the page.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    name = QLabel(text.upper())
    name.setStyleSheet(
        f"font-size: 11px; font-weight: bold; letter-spacing: 1px; color: {CAPTION};"
        " background: transparent; border: none;"
    )
    row.addWidget(name)

    if hint:
        note = QLabel(hint)
        # A hint that is a warning -- "this is off, and here is why" -- has to be
        # readable; the quiet grey is for hints you are free to ignore.
        colour = LOUD_HINT if loud_hint else HINT
        weight = "600" if loud_hint else "normal"
        note.setStyleSheet(
            f"font-size: {'11.5' if loud_hint else '11'}px; color: {colour};"
            f" font-weight: {weight}; background: transparent; border: none;"
        )
        row.addWidget(shrinkable(note), 1)

    row.addStretch()
    holder = QWidget()
    holder.setFixedHeight(CAPTION_HEIGHT)
    holder.setLayout(row)
    return holder


def section(
    name: str,
    content: QWidget,
    hint: str = "",
    spacing: int = 10,
    loud_hint: bool = False,
) -> QVBoxLayout:
    """A caption and its card, as one thing to add to a column."""
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(spacing)
    column.addWidget(caption(name, hint, loud_hint))
    column.addWidget(content)
    return column


def carded(
    name: str,
    inner: QWidget,
    hint: str = "",
    margins: Optional[tuple] = None,
    loud_hint: bool = False,
) -> QVBoxLayout:
    """The common case: wrap a widget in a card and give it a caption.

    ``inner`` keeps its own background, so anything that paints itself -- a scroll
    area, a table -- comes through unchanged and only the frame follows the card.
    """
    holder = card()
    layout = QVBoxLayout()
    left, top, right, bottom = margins if margins is not None else (12, 10, 12, 10)
    layout.setContentsMargins(left, top, right, bottom)
    layout.setSpacing(8)
    make_transparent(inner)
    layout.addWidget(inner)
    holder.setLayout(layout)
    return section(name, holder, hint, loud_hint=loud_hint)
