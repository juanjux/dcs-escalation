"""Partial health is orange and leaves the missing fraction unfilled."""

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from qt_ui.windows.groundobject.common import BAR_TRACK, DAMAGED_INK, HealthBar


def test_partial_health_renders_orange_and_not_full() -> None:
    app: Any = QApplication.instance() or QApplication([])
    bar = HealthBar(0.65, 0, 1, width=200, height=10, damaged=True)
    bar.show()
    app.processEvents()
    image = bar.grab().toImage()
    assert image.pixelColor(60, 5).name() == DAMAGED_INK.lower()
    assert image.pixelColor(160, 5).name() == BAR_TRACK.lower()
    bar.close()
