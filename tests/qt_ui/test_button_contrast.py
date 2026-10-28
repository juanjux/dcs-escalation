"""Default DCS-theme actions stay legible without per-dialog overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def luminance(color: Any) -> float:
    channels = [color.redF(), color.greenF(), color.blueF()]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


@pytest.mark.parametrize("role", [None, "btn-primary"])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("hovered", [False, True])
def test_default_button_contrast(
    qt_app: Any, role: str | None, enabled: bool, hovered: bool
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter, QPalette
    from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton

    previous = qt_app.styleSheet()
    theme = Path(__file__).resolve().parents[2] / "resources/stylesheets/style-dcs.css"
    qt_app.setStyleSheet(theme.read_text(encoding="utf-8"))
    widget = QPushButton("Assign target")
    if role:
        widget.setProperty("style", role)
    widget.setEnabled(enabled)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.resize(220, 40)
    widget.show()
    try:
        qt_app.processEvents()
        option = QStyleOptionButton()
        option.initFrom(widget)
        option.state &= ~QStyle.StateFlag.State_MouseOver
        if hovered:
            option.state |= QStyle.StateFlag.State_MouseOver
        image = QImage(widget.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        widget.style().drawControl(
            QStyle.ControlElement.CE_PushButton, option, painter, widget
        )
        painter.end()
        background = image.pixelColor(10, 10)
        foreground = widget.palette().color(QPalette.ColorRole.ButtonText)
        light, dark = sorted(
            (luminance(background), luminance(foreground)), reverse=True
        )
        assert (light + 0.05) / (dark + 0.05) >= 4.5
        assert background.name() == (
            "#1b2530" if not enabled else "#34617f" if hovered else "#2b506d"
        )
    finally:
        widget.close()
        qt_app.setStyleSheet(previous)
