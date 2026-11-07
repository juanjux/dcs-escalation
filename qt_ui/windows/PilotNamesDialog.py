"""Three-pane name library and squadron roster, with copy-only name drops."""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from game.squadrons.namepresets import (
    NameCategory,
    NameLibrary,
    autofill,
    clean_name,
    rename_pilot,
)
from game.squadrons.pilot import Pilot
from game.squadrons.squadron import Squadron
from qt_ui.widgets.controls import button
from qt_ui.widgets.cards import card, make_transparent, shrinkable
from qt_ui.widgets.pilotnamelist import DETAIL_ROLE, StyledNameList
from qt_ui.widgets.searchablecombo import SearchableComboBox
from qt_ui.windows.airwingconfig.common import (
    ACCENT,
    AMBER,
    BG,
    GREEN,
    HEADER,
    LINE,
    PANEL,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from qt_ui.windows.pilot.common import chip, label

NAME_MIME = "application/x-escalation-pilot-name"
USER_ROLE = Qt.ItemDataRole.UserRole


class NameList(StyledNameList):
    def __init__(self) -> None:
        super().__init__("names", "No names yet.\nAdd names to build this library.")
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def mimeData(self, items: Sequence[QListWidgetItem]) -> QMimeData:
        data = QMimeData()
        if len(items) == 1:
            text = items[0].text()
            data.setData(NAME_MIME, text.encode("utf-8"))
            data.setText(text)
        return data


class PilotList(StyledNameList):
    name_dropped = Signal(object, str)

    def __init__(self) -> None:
        super().__init__("pilots", "No pilots in this squadron.")
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setDropIndicatorShown(False)

    @staticmethod
    def accepts(source: object, data: QMimeData) -> bool:
        return isinstance(source, NameList) and data.hasFormat(NAME_MIME)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.accepts(event.source(), event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        if item is not None and self.accepts(event.source(), event.mimeData()):
            self.setCurrentItem(item)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        if item is None or not self.accepts(event.source(), event.mimeData()):
            event.ignore()
            return
        try:
            name = clean_name(
                bytes(event.mimeData().data(NAME_MIME).data()).decode("utf-8")
            )
        except (ValueError, UnicodeError):
            event.ignore()
            return
        self.name_dropped.emit(item.data(USER_ROLE), name)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()


class PilotNamesDialog(QDialog):
    pilots_changed = Signal(object)

    def __init__(
        self,
        squadrons: Sequence[Squadron],
        library: NameLibrary,
        selected: Squadron | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.library = library
        self.setWindowTitle("Assign Names")
        self.resize(1280, 800)
        self.setMinimumSize(1040, 640)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setObjectName("nameLibraryHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setStyleSheet(
            f"#nameLibraryHeader {{ background: {HEADER}; border-bottom: 1px solid {LINE}; }}"
        )
        heading = QHBoxLayout(header)
        heading.setContentsMargins(24, 18, 24, 18)
        identity = QVBoxLayout()
        identity.setSpacing(5)
        identity.addWidget(label("PERSONNEL  /  AIR WING", 10, TEXT_LABEL, True))
        identity.addWidget(label("Assign names", 26, TEXT_PRIMARY, True))
        identity.addWidget(
            label(
                "Rename individual pilots or fill a squadron from an ordered name library.",
                12,
                TEXT_SECONDARY,
            )
        )
        heading.addLayout(identity, 1)
        heading.addSpacing(28)
        self.library_total = label("0", 25, ACCENT, True)
        self.name_total = label("0", 25, TEXT_PRIMARY, True)
        for title, figure in (
            ("LIBRARIES", self.library_total),
            ("TOTAL NAMES", self.name_total),
        ):
            metric = QVBoxLayout()
            metric.setSpacing(7)
            metric.addWidget(label(title, 10, TEXT_LABEL, True))
            metric.addWidget(figure)
            heading.addLayout(metric)
            heading.addSpacing(24)
        root.addWidget(header)

        body = QWidget()
        make_transparent(body)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 18, 22, 18)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(14)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        body_layout.addWidget(splitter)
        root.addWidget(body, 1)

        category_pane, categories, self.category_count = self._pane("LIBRARIES")
        intro, intro_layout = self._intro()
        intro_layout.addWidget(label("Your collections", 16, TEXT_PRIMARY, True))
        intro_layout.addWidget(
            label("Built-in lists and your own categories.", 11, TEXT_LABEL)
        )
        categories.addWidget(intro)
        self.categories = StyledNameList(
            "categories", "No libraries yet.\nCreate a category to get started."
        )
        categories.addWidget(self.categories, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button("New…", handler=self.new_category))
        self.rename_category_button = button("Rename…", handler=self.rename_category)
        row.addWidget(self.rename_category_button)
        self.delete_category_button = button("Delete", handler=self.delete_category)
        row.addWidget(self.delete_category_button)
        categories.addLayout(row)
        splitter.addWidget(category_pane)

        names_pane, names, self.name_count = self._pane("NAME LIBRARY")
        intro, intro_layout = self._intro()
        self.selected_category = shrinkable(
            label("Select a library", 16, TEXT_PRIMARY, True)
        )
        self.selected_category.setTextFormat(Qt.TextFormat.PlainText)
        intro_layout.addWidget(self.selected_category)
        intro_layout.addWidget(
            label("Drag to assign · First to last for autofill", 11, TEXT_LABEL)
        )
        names.addWidget(intro)
        self.names = NameList()
        self.names.setToolTip(
            "Drag to copy a name. Use Move up/down to change autofill priority."
        )
        names.addWidget(self.names, 1)
        row = QHBoxLayout()
        self.add_names_button = button("Add…", handler=self.add_names)
        self.edit_name_button = button("Edit…", handler=self.edit_name)
        self.remove_name_button = button("Remove", handler=self.remove_name)
        for control in (
            self.add_names_button,
            self.edit_name_button,
            self.remove_name_button,
        ):
            row.addWidget(control)
        names.addLayout(row)
        row = QHBoxLayout()
        self.up_button = button("Move up", handler=lambda: self.move_name(-1))
        self.down_button = button("Move down", handler=lambda: self.move_name(1))
        row.addWidget(self.up_button)
        row.addWidget(self.down_button)
        names.addLayout(row)
        splitter.addWidget(names_pane)

        pilot_pane, pilots, self.pilot_count = self._pane("SQUADRON PILOTS")
        intro, intro_layout = self._intro()
        self.squadrons = SearchableComboBox(placeholder="Find a squadron…")
        self.squadrons.setFixedHeight(32)
        self.squadrons.setStyleSheet(
            f"QComboBox {{ background: {PANEL}; border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 10px; color: {TEXT_BASE}; font-size: 12px; }}"
        )
        for squadron in squadrons:
            self.squadrons.addItem(f"{squadron} · {squadron.location.name}", squadron)
        intro_layout.addWidget(self.squadrons)
        intro_layout.addWidget(
            label("Drop a name onto the pilot to replace it.", 11, TEXT_LABEL)
        )
        pilots.addWidget(intro)
        self.pilots = PilotList()
        pilots.addWidget(self.pilots, 1)
        self.autofill_button = button("Autofill", "primary", self.autofill_names)
        self.autofill_summary = label("", 11, TEXT_SECONDARY)
        self.autofill_summary.setWordWrap(True)
        pilots.addWidget(self.autofill_summary)
        self.autofill_button.setMinimumHeight(36)
        pilots.addWidget(self.autofill_button)
        splitter.addWidget(pilot_pane)
        splitter.setSizes([280, 410, 470])

        footer_widget = QWidget()
        footer_widget.setObjectName("nameLibraryFooter")
        footer_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer_widget.setStyleSheet(
            f"#nameLibraryFooter {{ background: {PANEL}; border-top: 1px solid {LINE}; }}"
        )
        footer = QHBoxLayout(footer_widget)
        footer.setContentsMargins(24, 14, 24, 14)
        messages = QVBoxLayout()
        messages.setSpacing(4)
        self.status = label(
            "Drag to assign one name. Autofill follows the order shown.",
            12,
            TEXT_SECONDARY,
        )
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        messages.addWidget(self.status)
        note = label(
            "Libraries save automatically on this computer. Pilot renames are saved with the campaign.",
            11,
            TEXT_LABEL,
        )
        note.setWordWrap(True)
        messages.addWidget(note)
        footer.addLayout(messages, 1)
        footer.addWidget(button("Close", handler=self.accept))
        root.addWidget(footer_widget)
        self.categories.currentRowChanged.connect(self.show_category)
        self.names.currentRowChanged.connect(self.update_buttons)
        self.names.itemDoubleClicked.connect(lambda _item: self.edit_name())
        self.squadrons.currentIndexChanged.connect(self.show_pilots)
        self.pilots.name_dropped.connect(self.assign_name)
        if selected is not None:
            for index in range(self.squadrons.count()):
                if self.squadrons.itemData(index) is selected:
                    self.squadrons.setCurrentIndex(index)
                    break
        self.refresh_categories()
        self.show_pilots()

    @staticmethod
    def _pane(title: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
        pane = QWidget()
        make_transparent(pane)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        heading.addWidget(label(title, 11, TEXT_LABEL, True))
        heading.addStretch()
        counter = chip("0", ACCENT, "#22384A")
        heading.addWidget(counter)
        layout.addLayout(heading)
        panel = card()
        content = QVBoxLayout(panel)
        content.setContentsMargins(10, 10, 10, 10)
        content.setSpacing(8)
        layout.addWidget(panel, 1)
        return pane, content, counter

    @staticmethod
    def _intro() -> tuple[QWidget, QVBoxLayout]:
        intro = QWidget()
        make_transparent(intro)
        intro.setFixedHeight(59)
        layout = QVBoxLayout(intro)
        layout.setContentsMargins(2, 0, 2, 4)
        layout.setSpacing(4)
        return intro, layout

    @property
    def category(self) -> NameCategory | None:
        item = self.categories.currentItem()
        return self.library.categories.get(item.data(USER_ROLE)) if item else None

    @property
    def squadron(self) -> Squadron | None:
        return self.squadrons.currentData()

    def refresh_categories(self, selected_id: str | None = None) -> None:
        self.categories.blockSignals(True)
        self.categories.clear()
        for category in self.library.categories.values():
            item = QListWidgetItem(category.name)
            item.setData(USER_ROLE, category.id)
            origin = "Custom"
            if category.id in self.library.defaults:
                origin = (
                    "Built-in"
                    if category == self.library.defaults[category.id]
                    else "Customised"
                )
            item.setData(DETAIL_ROLE, f"{len(category.names)} names · {origin}")
            item.setToolTip(category.name)
            self.categories.addItem(item)
            if category.id == selected_id:
                self.categories.setCurrentItem(item)
        if self.categories.currentRow() < 0 and self.categories.count():
            self.categories.setCurrentRow(0)
        self.categories.blockSignals(False)
        self.category_count.setText(str(self.categories.count()))
        self.library_total.setText(str(self.categories.count()))
        self.name_total.setText(
            str(sum(len(c.names) for c in self.library.categories.values()))
        )
        self.show_category()

    def show_category(self) -> None:
        self.names.clear()
        category = self.category
        self.selected_category.setText(
            category.name if category else "Select a library"
        )
        self.selected_category.setToolTip(category.name if category else "")
        if category is not None:
            self.names.addItems(category.names)
            for index, name in enumerate(category.names):
                self.names.item(index).setToolTip(name)
            if category.names:
                self.names.setCurrentRow(0)
        self.update_buttons()

    def show_pilots(self) -> None:
        self.pilots.clear()
        squadron = self.squadron
        if squadron is not None:
            for pilot in squadron.current_roster:
                item = QListWidgetItem(pilot.name)
                item.setData(USER_ROLE, pilot)
                status = pilot.status.value.replace("OnLeave", "On leave")
                item.setData(
                    DETAIL_ROLE, f"{'PLAYER' if pilot.player else 'AI'} · {status}"
                )
                item.setToolTip(f"{pilot.name} · {status}")
                self.pilots.addItem(item)
        self.update_buttons()

    def update_buttons(self) -> None:
        category = self.category
        row = self.names.currentRow()
        for control in (
            self.rename_category_button,
            self.delete_category_button,
            self.add_names_button,
        ):
            control.setEnabled(category is not None)
        for control in (self.edit_name_button, self.remove_name_button):
            control.setEnabled(row >= 0)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.names.count() - 1)
        count = min(self.names.count(), self.pilots.count())
        self.name_count.setText(str(self.names.count()))
        self.pilot_count.setText(str(self.pilots.count()))
        self.autofill_button.setEnabled(count > 0)
        self.autofill_button.setText(
            f"Autofill {count} {'pilot' if count == 1 else 'pilots'}"
            if count
            else "Autofill"
        )
        remaining = self.pilots.count() - count
        if count:
            summary = f"{count} of {self.pilots.count()} pilots will be renamed."
            if remaining:
                summary += (
                    " 1 pilot keeps their current name."
                    if remaining == 1
                    else f" {remaining} pilots keep their current names."
                )
        else:
            summary = "Add names and select a squadron to use autofill."
        self.autofill_summary.setText(summary)
        self.autofill_summary.setStyleSheet(
            f"font-size: 11px; color: {AMBER if remaining and count else TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self.autofill_button.setToolTip(
            f"Rename the first {count} of {self.pilots.count()} pilots. Others keep their names."
        )

    def _persist(self, change: Callable[[], object]) -> bool:
        previous = dict(self.library.categories)
        try:
            change()
            self.library.save()
        except (ValueError, OSError) as error:
            self.library.categories = previous
            QMessageBox.warning(self, "Cannot save name library", str(error))
            return False
        return True

    def new_category(self) -> None:
        text, ok = QInputDialog.getText(self, "New category", "Category title:")
        if ok:

            def create() -> None:
                self.library.put(None, text, ())

            if self._persist(create):
                self.refresh_categories(next(reversed(self.library.categories)))

    def rename_category(self) -> None:
        category = self.category
        if category is None:
            return
        text, ok = QInputDialog.getText(
            self, "Rename category", "Category title:", text=category.name
        )
        if ok and self._persist(
            lambda: self.library.put(category.id, text, category.names)
        ):
            self.refresh_categories(category.id)

    def delete_category(self) -> None:
        category = self.category
        if category is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete category",
            f'Delete "{category.name}" and its name list? Pilot names will not change.',
        )
        if answer == QMessageBox.StandardButton.Yes and self._persist(
            lambda: self.library.categories.pop(category.id)
        ):
            self.refresh_categories()

    def save_names(self, names: Sequence[str], selected_row: int = 0) -> None:
        category = self.category
        if category is not None and self._persist(
            lambda: self.library.put(category.id, category.name, names)
        ):
            self.refresh_categories(category.id)
            if self.names.count():
                self.names.setCurrentRow(min(selected_row, self.names.count() - 1))

    def add_names(self) -> None:
        category = self.category
        if category is None:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Add names", "One name per line, in autofill order:"
        )
        if ok:
            entries = [line.strip() for line in text.splitlines() if line.strip()]
            self.save_names([*category.names, *entries], len(category.names))

    def edit_name(self) -> None:
        category = self.category
        row = self.names.currentRow()
        if category is None or row < 0:
            return
        text, ok = QInputDialog.getText(
            self, "Edit name", "Name:", text=category.names[row]
        )
        if ok:
            entries = list(category.names)
            entries[row] = text
            self.save_names(entries, row)

    def remove_name(self) -> None:
        category = self.category
        row = self.names.currentRow()
        if category is not None and row >= 0:
            entries = list(category.names)
            del entries[row]
            self.save_names(entries, row)

    def move_name(self, offset: int) -> None:
        category = self.category
        row = self.names.currentRow()
        if (
            category is not None
            and row >= 0
            and 0 <= row + offset < len(category.names)
        ):
            entries = list(category.names)
            entries[row], entries[row + offset] = entries[row + offset], entries[row]
            self.save_names(entries, row + offset)

    def assign_name(self, pilot: Pilot, name: str) -> None:
        squadron = self.squadron
        if squadron is None or not any(p is pilot for p in squadron.current_roster):
            return
        rename_pilot(pilot, name)
        self.show_pilots()
        self.status.setText(f"Assigned {name}.")
        self.status.setStyleSheet(
            f"font-size: 12px; color: {GREEN}; background: transparent; border: none;"
        )
        self.pilots_changed.emit(squadron)

    def autofill_names(self) -> None:
        category, squadron = self.category, self.squadron
        if (
            category is None
            or squadron is None
            or not category.names
            or not squadron.current_roster
        ):
            return
        count = min(len(category.names), len(squadron.current_roster))
        answer = QMessageBox.question(
            self,
            "Autofill pilot names",
            f'Replace the first {count} pilot names in {squadron} using "{category.name}"? Remaining pilots keep their names.',
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        changed = autofill(squadron.current_roster, category.names)
        self.show_pilots()
        self.status.setText(f"Renamed {changed} pilots using {category.name}.")
        self.status.setStyleSheet(
            f"font-size: 12px; color: {GREEN}; background: transparent; border: none;"
        )
        self.pilots_changed.emit(squadron)
