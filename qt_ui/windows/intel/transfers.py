"""Pending transfers inside Intelligence, filtered by faction."""

from __future__ import annotations

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from game.theater import Player
from qt_ui.models import TransferModel
from qt_ui.widgets.cards import CARD_BG, CARD_BORDER
from qt_ui.widgets.controls import style_button


class TransferRow(QStyledItemDelegate):
    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(400, 62)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#2B506D" if selected else CARD_BG))
        rect = option.rect.adjusted(14, 8, -14, -8)
        transfer = index.data(TransferModel.TransferRole)
        font = QFont(option.font)
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#F2F7FA"))
        title = painter.fontMetrics().elidedText(
            str(index.data()), Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.drawText(
            rect.adjusted(0, 0, 0, -22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#B7C6D2"))
        description = painter.fontMetrics().elidedText(
            transfer.description, Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.drawText(
            rect.adjusted(0, 24, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            description,
        )
        painter.setPen(QColor(CARD_BORDER))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class TransferFilter(QSortFilterProxyModel):
    player = Player.BLUE

    def filterAcceptsRow(
        self, row: int, parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        model = self.sourceModel()
        index = model.index(row, 0, parent)
        transfer = index.data(TransferModel.TransferRole)
        return transfer.player == self.player and super().filterAcceptsRow(row, parent)


class TransfersPane(QWidget):
    def __init__(self, model: TransferModel) -> None:
        super().__init__()
        self.model = model
        self.proxy = TransferFilter(self)
        self.proxy.setSourceModel(model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        bar = QHBoxLayout()
        self.count = QLabel()
        bar.addWidget(self.count)
        bar.addStretch()
        search = QLineEdit()
        search.setPlaceholderText("Filter transfers…")
        search.setClearButtonEnabled(True)
        search.textChanged.connect(self.proxy.setFilterFixedString)
        bar.addWidget(search)
        layout.addLayout(bar)
        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(TransferRow(self.view))
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setStyleSheet(
            f"QListView {{ background: {CARD_BG}; color: #D3DFE8; border: 1px solid {CARD_BORDER}; }}"
            "QListView::item { padding: 10px; border-bottom: 1px solid #33414F; }"
            "QListView::item:selected { background: #2B506D; color: #F2F7FA; }"
        )
        layout.addWidget(self.view, 1)
        self.empty = QLabel("No pending transfers for this faction.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty)
        self.cancel = style_button(QPushButton("Cancel selected transfer"), "danger")
        self.cancel.clicked.connect(self.cancel_selected)
        layout.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignRight)
        self.view.selectionModel().selectionChanged.connect(self.refresh)
        for signal in (
            self.proxy.modelReset,
            self.proxy.rowsInserted,
            self.proxy.rowsRemoved,
            self.proxy.layoutChanged,
        ):
            signal.connect(self.refresh)
        self.refresh()

    def show_side(self, player: Player) -> None:
        self.proxy.player = player
        self.proxy.invalidateFilter()
        self.refresh()

    def refresh(self) -> None:
        count = self.proxy.rowCount()
        self.count.setText(f"{count} pending transfer{'s' if count != 1 else ''}")
        self.empty.setVisible(count == 0)
        index = self.view.currentIndex()
        transfer = index.data(TransferModel.TransferRole) if index.isValid() else None
        self.cancel.setEnabled(transfer is not None and transfer.player.is_blue)

    def cancel_selected(self) -> None:
        index = self.view.currentIndex()
        if index.isValid() and index.data(TransferModel.TransferRole).player.is_blue:
            self.model.cancel_transfer_at_index(self.proxy.mapToSource(index))
        self.refresh()
