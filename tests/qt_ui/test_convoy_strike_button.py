"""The convoy strike action stays visible inside the transparent scroll area."""

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_strike_button_is_visible_and_opens_the_convoy(monkeypatch: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
    from qt_ui.dialogs import Dialog
    from qt_ui.widgets.controls import BUTTON_KINDS, CONTROL_HEIGHT
    from qt_ui.windows.basemenu.DepartingConvoysMenu import ConvoyCard

    app = QApplication.instance() or QApplication([])
    convoy: Any = SimpleNamespace(name="Convoy 002", destination="FOB Galy", units={})
    open_package = Mock()
    monkeypatch.setattr(Dialog, "open_new_package_dialog", open_package)
    container = QWidget()
    container.setStyleSheet("background: transparent; border: none;")
    layout = QVBoxLayout(container)
    card = ConvoyCard(convoy)
    layout.addWidget(card)
    container.resize(850, 160)
    container.show()
    app.processEvents()
    try:
        [strike] = card.findChildren(QPushButton)
        assert strike.text() == "Plan strike…"
        assert strike.minimumHeight() >= CONTROL_HEIGHT
        assert strike.cursor().shape() == Qt.CursorShape.PointingHandCursor
        assert not strike.autoDefault()
        background, border, _, _ = BUTTON_KINDS["danger"]
        rendered = strike.grab().toImage()
        assert rendered.pixelColor(5, 5).name() == background.lower()
        assert rendered.pixelColor(rendered.width() // 2, 0).name() == border.lower()
        strike.click()
        open_package.assert_called_once_with(convoy, parent=container)
    finally:
        container.close()
