"""Clickable links in Intel's painted lists, with shared transient map highlighting."""

from typing import Any

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QPoint,
    QPersistentModelIndex,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QEnterEvent, QHideEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QListView

from qt_ui.widgets.maphover import bind_map_hover
from .rows import EconomyLine, HeaderLine, IntelDelegate, IntelListModel


class IntelListView(QListView):
    action_clicked = Signal(QModelIndex)

    def __init__(self, model: IntelListModel) -> None:
        super().__init__()
        self.setModel(model)
        self.setMouseTracking(True)
        self._hover_pos: QPoint | None = None
        self._pressed = QPersistentModelIndex()
        self._map_hover = bind_map_hover(self.viewport(), self._hover_target)
        model.modelAboutToBeReset.connect(self._clear_hover)
        model.modelReset.connect(self._reset_hover)
        self.verticalScrollBar().valueChanged.connect(self._refresh_hover)

    def action_at(self, point: QPoint) -> QModelIndex:
        index = self.indexAt(point)
        delegate = self.itemDelegate()
        if not index.isValid() or not isinstance(delegate, IntelDelegate):
            return QModelIndex()
        line = index.data(Qt.ItemDataRole.UserRole)
        if delegate.action_rect(self.visualRect(index), line).contains(point):
            return index
        return QModelIndex()

    def _hover_target(self) -> Any:
        if self._hover_pos is None:
            return None
        index = self.action_at(self._hover_pos)
        line = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(line, EconomyLine):
            return line.row.target
        if isinstance(line, HeaderLine):
            return line.group.control_point
        return None

    def _clear_hover(self) -> None:
        self._map_hover.clear()
        self._pressed = QPersistentModelIndex()
        self.viewport().unsetCursor()

    def _reset_hover(self) -> None:
        self._clear_hover()
        QTimer.singleShot(0, self._refresh_hover)

    def _refresh_hover(self) -> None:
        if not self.isVisible():
            self._clear_hover()
            return
        self._map_hover.refresh()
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._hover_pos is not None and self.action_at(self._hover_pos).isValid()
            else Qt.CursorShape.ArrowCursor
        )

    def viewportEvent(self, event: QEvent) -> bool:
        if isinstance(event, QEnterEvent):
            self._hover_pos = event.position().toPoint()
            self._refresh_hover()
        elif event.type() == QEvent.Type.Leave:
            self._hover_pos = None
            self._map_hover.clear()
            self.viewport().unsetCursor()
        return super().viewportEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._hover_pos = event.position().toPoint()
        super().mouseMoveEvent(event)
        self._refresh_hover()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.action_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid():
            self.setCurrentIndex(index)
            self.setFocus()
            self._pressed = QPersistentModelIndex(index)
            event.accept()
            return
        self._pressed = QPersistentModelIndex()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pressed.isValid():
            index = self.action_at(event.position().toPoint())
            activate = (
                event.button() == Qt.MouseButton.LeftButton and index == self._pressed
            )
            self._pressed = QPersistentModelIndex()
            if activate:
                self._map_hover.clear()
                self.action_clicked.emit(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        delegate = self.itemDelegate()
        index = self.currentIndex()
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and isinstance(delegate, IntelDelegate)
            and delegate.action_text(index.data(Qt.ItemDataRole.UserRole))
        ):
            self._map_hover.clear()
            self.action_clicked.emit(index)
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._hover_pos = None
        self._clear_hover()
        super().hideEvent(event)
