"""Live OPFOR commander status and connection controls."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QIcon, QPainter, QPen, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game.agent.session import ACTIVE_WINDOW, AI_SESSION
from qt_ui.widgets.cards import card
from qt_ui.widgets.controls import style_button


def status_label(snapshot: dict[str, Any]) -> str:
    if snapshot["cancelled"]:
        return "Cancel requested"
    return "Active" if snapshot["active"] else "Idle"


class CommanderButton(QPushButton):
    """A compact status button with a vector radar sweep while active."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("OPFOR AI · Idle", parent)
        self._active = False
        self._angle = 0
        self._state = ""
        self._ink = "#8FC3F0"
        self.setIconSize(QSize(20, 20))
        self.setAccessibleName("OPFOR AI commander status")
        self._animation = QTimer(self)
        self._animation.setInterval(40)
        self._animation.timeout.connect(self._advance)
        self.set_snapshot({"active": False, "cancelled": False, "status": ""})

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        state = status_label(snapshot)
        self._active = bool(snapshot["active"] and not snapshot["cancelled"])
        self._ink = "#E7BC77" if self._active else "#8FC3F0"
        if state != self._state:
            self._state = state
            self.setText(f"OPFOR AI · {state}")
            style_button(self, "primary" if self._active else "normal")
        self.setToolTip(
            f"{state}\n{snapshot['status'] or 'Waiting for commander activity'}\nClick to view status and connections"
        )
        self._sync_animation()
        self._paint_icon()

    def _sync_animation(self) -> None:
        if self._active and self.isVisible():
            if not self._animation.isActive():
                self._animation.start()
        else:
            self._animation.stop()
            self._angle = 0

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        self._animation.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._angle = (self._angle + 6) % 360
        self._paint_icon()

    def _paint_icon(self) -> None:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(20 * ratio), round(20 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#52697C"), 1.2))
        painter.drawEllipse(QRectF(2, 2, 16, 16))
        painter.drawEllipse(QRectF(6, 6, 8, 8))
        painter.translate(10, 10)
        painter.rotate(self._angle if self._active else -35)
        painter.setPen(QPen(QColor(self._ink), 1.8))
        painter.drawLine(0, 0, 0, -7)
        painter.setBrush(QColor(self._ink))
        painter.drawEllipse(QRectF(-1.5, -1.5, 3, 3))
        painter.end()
        self.setIcon(QIcon(pixmap))


class OpforAiDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OPFOR AI Commander")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(640, 540)
        self.resize(760, 660)
        self.setStyleSheet(
            "QDialog { background: #202B36; }"
            " QLabel { color: #B7C6D2; background: transparent; border: none; }"
            " QCheckBox { color: #B7C6D2; background: transparent; }"
        )
        self._last_activity: Optional[tuple[str, str]] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        summary = card()
        summary_layout = QVBoxLayout(summary)
        heading = QHBoxLayout()
        title = QLabel("OPFOR COMMANDER")
        title.setStyleSheet("color: #F2F7FA; font-size: 18px; font-weight: 600;")
        heading.addWidget(title)
        heading.addStretch()
        self.state = QLabel()
        heading.addWidget(self.state)
        summary_layout.addLayout(heading)
        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setMaximumHeight(88)
        self.status.setStyleSheet(
            "background: #16232D; color: #D3DFE8; border: none; padding: 8px;"
        )
        summary_layout.addWidget(self.status)
        self.updated = QLabel()
        summary_layout.addWidget(self.updated)
        note = QLabel(
            f"Active means an API request arrived within the last {ACTIVE_WINDOW.total_seconds():g} seconds. Take off is blocked while active."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #94A8B8;")
        summary_layout.addWidget(note)
        layout.addWidget(summary)

        connections = card()
        connection_layout = QVBoxLayout(connections)
        connection_layout.addWidget(QLabel("CONNECT YOUR COMMANDER"))
        self.fields: list[QLineEdit] = []
        self.copy_buttons: list[QPushButton] = []
        for caption in ("REST", "MCP"):
            row = QHBoxLayout()
            label = QLabel(caption)
            label.setFixedWidth(44)
            row.addWidget(label)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setAccessibleName(f"{caption} connection URL")
            row.addWidget(field, 1)
            copy = style_button(QPushButton("Copy"))
            copy.clicked.connect(
                lambda _checked=False, f=field: QApplication.clipboard().setText(
                    f.text()
                )
            )
            row.addWidget(copy)
            self.fields.append(field)
            self.copy_buttons.append(copy)
            connection_layout.addLayout(row)
        reveal = QCheckBox("Show connection URLs")
        reveal.toggled.connect(self._show_urls)
        connection_actions = QHBoxLayout()
        connection_actions.addWidget(reveal)
        connection_actions.addStretch()
        refresh = style_button(QPushButton("Refresh connections"))
        refresh.clicked.connect(self._read_connections)
        connection_actions.addWidget(refresh)
        connection_layout.addLayout(connection_actions)
        self.connection_note = QLabel(
            "Choose the connection supported by your AI client. URLs include the access token."
        )
        self.connection_note.setWordWrap(True)
        connection_layout.addWidget(self.connection_note)
        layout.addWidget(connections)

        layout.addWidget(QLabel("RECENT ACTIVITY · while this window is open"))
        self.activity = QListWidget()
        self.activity.setStyleSheet(
            "background: #16232D; color: #B7C6D2; border: 1px solid #3A4B5C; padding: 6px;"
        )
        self.activity.setWordWrap(True)
        layout.addWidget(self.activity, 1)
        footer = QHBoxLayout()
        self.cancel = style_button(QPushButton("Cancel AI turn"), "danger")
        self.cancel.clicked.connect(self._cancel)
        footer.addWidget(self.cancel)
        footer.addStretch()
        close = style_button(QPushButton("Close"))
        close.clicked.connect(self.close)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self._read_connections()
        self.refresh()

    def _read_connections(self) -> None:
        from game.agent import service

        try:
            urls = (service.connect_url(), service.mcp_url())
            self.connection_note.setText(
                "Choose the connection supported by your AI client. URLs include the access token."
            )
        except Exception:
            urls = ("", "")
            self.connection_note.setText(
                "Connection details are unavailable until the campaign server is ready."
            )
        for field, button, url in zip(self.fields, self.copy_buttons, urls):
            field.setText(url)
            field.setPlaceholderText("Unavailable")
            button.setEnabled(bool(url))

    def _show_urls(self, show: bool) -> None:
        for field in self.fields:
            field.setEchoMode(
                QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
            )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        snapshot = AI_SESSION.snapshot()
        state = status_label(snapshot)
        self.state.setText(state.upper())
        colour = "#E7BC77" if snapshot["active"] else "#8FC3F0"
        self.state.setStyleSheet(f"color: {colour}; font-size: 12px; font-weight: 600;")
        message = snapshot["status"] or "Waiting for commander activity."
        if self.status.toPlainText() != message:
            self.status.setPlainText(message)
        when = snapshot["updated_at"]
        if when:
            when = datetime.fromisoformat(when).astimezone().strftime("%H:%M:%S")
        self.updated.setText(f"Last update: {when or 'No activity yet'}")
        self.cancel.setEnabled(bool(snapshot["active"] and not snapshot["cancelled"]))
        key = (state, message)
        if key != self._last_activity:
            self._last_activity = key
            self.activity.insertItem(
                0, f"{datetime.now():%H:%M:%S} · {state} · {message}"
            )
            while self.activity.count() > 100:
                self.activity.takeItem(self.activity.count() - 1)

    def _cancel(self) -> None:
        AI_SESSION.cancel()
        self.refresh()
