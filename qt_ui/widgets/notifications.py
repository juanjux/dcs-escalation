"""Top-right campaign alert bell and an actionable, non-modal alert list."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from game.notifications import CampaignNotice, refresh, mark_read
from qt_ui.models import GameModel
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal


class NotificationList(QDialog):
    def __init__(self, bell: NotificationBell) -> None:
        super().__init__(bell, Qt.WindowType.Popup)
        self.bell = bell
        self.game = bell.game
        self.morale_expanded = False
        self.setWindowTitle("Campaign alerts")
        self.setObjectName("campaign-notifications")
        self.resize(590, 560)
        self.setStyleSheet("QDialog { background: #233442; color: #d5e4ef; }")
        column = QVBoxLayout(self)
        title = QLabel("Campaign alerts")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        column.addWidget(title)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        column.addWidget(self.area, 1)
        actions = QHBoxLayout()
        read_all = QPushButton("Mark all as read")
        read_all.setToolTip("Ongoing problems are reported again next turn.")
        read_all.clicked.connect(lambda: self.dismiss(self.bell.notices))
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        actions.addWidget(read_all)
        actions.addStretch()
        actions.addWidget(close)
        column.addLayout(actions)
        self.update_notices()

    def update_notices(self) -> None:
        holder = QWidget()
        column = QVBoxLayout(holder)
        if not self.bell.notices:
            column.addWidget(QLabel("No campaign alerts."))
        morale = [n for n in self.bell.notices if n.category == "pilot_morale"]
        grouped = False
        for notice in self.bell.notices:
            if notice.category == "pilot_morale":
                if not grouped:
                    column.addWidget(self._morale_group(morale))
                    grouped = True
            else:
                column.addWidget(self._notice_card(notice))
        column.addStretch()
        self.area.setWidget(holder)

    def _morale_group(self, notices: list[CampaignNotice]) -> QWidget:
        group = QWidget()
        column = QVBoxLayout(group)
        column.setContentsMargins(0, 0, 0, 0)
        toggle = QToolButton()
        toggle.setObjectName("low-morale-toggle")
        toggle.setText(f"Low morale ({len(notices)})")
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setCheckable(True)
        toggle.setChecked(self.morale_expanded)
        toggle.setMinimumHeight(32)
        toggle.setStyleSheet(
            "QToolButton { color: #f18a7b; background: #1a2934;"
            " font-weight: bold; padding: 6px; border-radius: 4px; }"
        )
        column.addWidget(toggle)
        content = QWidget()
        content.setObjectName("low-morale-notices")
        cards = QVBoxLayout(content)
        cards.setContentsMargins(12, 0, 0, 0)
        for notice in notices:
            cards.addWidget(self._notice_card(notice))
        column.addWidget(content)

        def expand(expanded: bool) -> None:
            self.morale_expanded = expanded
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
            content.setVisible(expanded)

        expand(self.morale_expanded)
        toggle.toggled.connect(expand)
        return group

    def _notice_card(self, notice: CampaignNotice) -> QWidget:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #1a2934; border-radius: 4px; }")
        row = QVBoxLayout(card)
        title = QLabel(notice.title)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("color: #f18a7b; font-weight: bold;")
        row.addWidget(title)
        detail = QLabel(f"Turn {notice.turn} · {notice.detail}")
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        row.addWidget(detail)
        buttons = QHBoxLayout()
        show = QPushButton("Show")
        show.clicked.connect(lambda checked=False: self.show_notice(notice))
        dismiss = QPushButton("Mark as read")
        dismiss.clicked.connect(lambda checked=False: self.dismiss([notice]))
        buttons.addWidget(show)
        buttons.addStretch()
        buttons.addWidget(dismiss)
        row.addLayout(buttons)
        return card

    def dismiss(self, notices: list[CampaignNotice]) -> None:
        if self.game is self.bell.model.game and self.game is not None:
            mark_read(self.game, notices)
        self.bell.refresh()

    def show_notice(self, notice: CampaignNotice) -> None:
        if self.game is not self.bell.model.game:
            self.close()
            return
        self.dismiss([notice])
        self.close()
        self.bell.navigate(notice)


class NotificationBell(QToolButton):
    def __init__(
        self,
        model: GameModel,
        navigate: Callable[[CampaignNotice], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.navigate = navigate
        self.game = model.game
        self.notices: list[CampaignNotice] = []
        self.popup: NotificationList | None = None
        self.setObjectName("campaign-alert-bell")
        self.setFixedSize(46, 30)
        self.setAutoRaise(True)
        self.clicked.connect(self.show_alerts)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            for changed in (
                signal.gameupdated,
                signal.budgetupdated,
                signal.missile_targets_changed,
                signal.ground_movements_changed,
            ):
                changed.connect(self.schedule_refresh)
        self.refresh()

    def schedule_refresh(self) -> None:
        QTimer.singleShot(0, self, self.refresh)

    def refresh(self) -> None:
        if self.model.game is not self.game:
            if self.popup is not None:
                self.popup.close()
            self.game = self.model.game
        notices = refresh(self.game) if self.game is not None else []
        changed = notices != self.notices
        self.notices = notices
        self.setEnabled(self.game is not None)
        self.setToolTip(f"{len(notices)} campaign alert(s)")
        self.setAccessibleName(f"Campaign alerts: {len(notices)}")
        self.update()
        if changed and self.popup is not None and self.popup.isVisible():
            self.popup.update_notices()

    def show_alerts(self) -> None:
        self.refresh()
        if self.popup is not None:
            self.popup.close()
            self.popup.deleteLater()
        self.popup = NotificationList(self)
        point = self.mapToGlobal(QPoint(self.width(), self.height()))
        screen = self.screen().availableGeometry()
        self.popup.move(
            max(
                screen.left(),
                min(
                    point.x() - self.popup.width(), screen.right() - self.popup.width()
                ),
            ),
            max(screen.top(), min(point.y(), screen.bottom() - self.popup.height())),
        )
        self.popup.show()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = QColor("#e76c62" if self.notices else "#718698")
        painter.setPen(QPen(colour, 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bell = QPainterPath()
        bell.moveTo(7, 21)
        bell.lineTo(10, 17)
        bell.lineTo(10, 11)
        bell.cubicTo(10, 3, 23, 3, 23, 11)
        bell.lineTo(23, 17)
        bell.lineTo(26, 21)
        bell.closeSubpath()
        painter.drawPath(bell)
        painter.drawArc(QRectF(14, 20, 5, 6), 180 * 16, 180 * 16)
        painter.drawLine(16, 3, 17, 3)
        if self.notices:
            badge = QRectF(25, 0, 21, 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#c94741"))
            painter.drawRoundedRect(badge, 7, 7)
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPixelSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                badge,
                Qt.AlignmentFlag.AlignCenter,
                str(len(self.notices)) if len(self.notices) < 100 else "99+",
            )
