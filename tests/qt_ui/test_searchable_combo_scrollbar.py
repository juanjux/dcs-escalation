"""Search popups expose a visible, usable scrollbar for long lists."""

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


@pytest.fixture(params=["style-dcs.css", "windows-style.css"])
def combo(qt_app: Any, request: Any) -> Any:
    from qt_ui.widgets.searchablecombo import SearchableComboBox

    previous_style = qt_app.styleSheet()
    theme = Path(__file__).resolve().parents[2] / "resources" / "stylesheets"
    qt_app.setStyleSheet((theme / request.param).read_text())
    widget = SearchableComboBox()
    widget.addItems([f"Aircraft livery {number:02d}" for number in range(50)])
    widget.resize(420, 36)
    widget.show()
    widget.showPopup()
    qt_app.processEvents()
    try:
        yield widget
    finally:
        widget.hidePopup()
        widget.close()
        qt_app.setStyleSheet(previous_style)


def test_scrollbar_thumb_contrasts_with_track_and_can_be_dragged(combo: Any) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle, QStyleOptionSlider

    bar = combo._list.verticalScrollBar()
    assert bar.isVisible()
    assert bar.maximum() > 0
    option = QStyleOptionSlider()
    option.initFrom(bar)
    option.orientation = Qt.Orientation.Vertical
    option.minimum = bar.minimum()
    option.maximum = bar.maximum()
    option.pageStep = bar.pageStep()
    option.sliderPosition = bar.sliderPosition()
    option.sliderValue = bar.value()
    thumb = bar.style().subControlRect(
        QStyle.ComplexControl.CC_ScrollBar,
        option,
        QStyle.SubControl.SC_ScrollBarSlider,
        bar,
    )
    groove = bar.style().subControlRect(
        QStyle.ComplexControl.CC_ScrollBar,
        option,
        QStyle.SubControl.SC_ScrollBarGroove,
        bar,
    )
    image = bar.grab().toImage()
    thumb_color = image.pixelColor(thumb.center())
    track_color = image.pixelColor(groove.center().x(), groove.bottom() - 2)
    assert thumb_color != track_color
    assert thumb.width() >= 10
    assert thumb.height() >= 24

    end = QPoint(thumb.center().x(), groove.bottom())
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=thumb.center())
    QTest.mouseMove(bar, end)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
    assert bar.value() == bar.maximum()


def test_scrollbar_reaches_last_item(combo: Any, qt_app: Any) -> None:
    bar = combo._list.verticalScrollBar()
    bar.setValue(bar.maximum())
    qt_app.processEvents()
    last = combo.model().index(combo.count() - 1, 0)
    viewport = combo._list.viewport().rect()
    item = combo._list.visualRect(last)
    assert viewport.top() <= item.top() <= item.bottom() <= viewport.bottom()


def test_filter_hides_and_restores_scrollbar(combo: Any, qt_app: Any) -> None:
    combo._search.setText("livery 49")
    qt_app.processEvents()
    bar = combo._list.verticalScrollBar()
    assert not bar.isVisible()
    assert bar.maximum() == 0

    combo._search.clear()
    qt_app.processEvents()
    assert bar.isVisible()
    assert bar.maximum() > 0
