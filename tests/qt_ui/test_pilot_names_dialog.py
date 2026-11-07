from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import Mock, patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
)

from game.squadrons.namepresets import NameLibrary
from game.squadrons.pilot import Pilot, PilotStatus
from qt_ui.windows.PilotNamesDialog import NAME_MIME, USER_ROLE, PilotNamesDialog


@pytest.fixture(scope="module", autouse=True)
def app() -> Any:
    return QApplication.instance() or QApplication([])


class SquadronStub:
    def __init__(self, name: str, count: int = 4) -> None:
        self.name = name
        self.id = uuid4()
        self.location = SimpleNamespace(name="Kabul")
        self.current_roster = [Pilot(f"Pilot {i}") for i in range(count)]

    def __str__(self) -> str:
        return self.name


@pytest.fixture
def dialog(tmp_path: Path, app: Any) -> Iterator[PilotNamesDialog]:
    squadron = SquadronStub("VFA-106")
    widget = PilotNamesDialog(
        cast(Any, [squadron]), NameLibrary.load(tmp_path / "names.json")
    )
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


class Drop:
    def __init__(
        self,
        dialog: PilotNamesDialog,
        row: int,
        *,
        source: Any = None,
        name: str | None = None,
    ) -> None:
        self.origin = source if source is not None else dialog.names
        self.data = dialog.names.mimeData([dialog.names.item(0)])
        if name is not None:
            self.data.setData(NAME_MIME, name.encode("utf-8"))
        self.point = QPointF(
            dialog.pilots.visualItemRect(dialog.pilots.item(row)).center()
        )
        self.accepted = False
        self.action: Any = None

    def position(self) -> QPointF:
        return self.point

    def source(self) -> Any:
        return self.origin

    def mimeData(self) -> QMimeData:
        return self.data

    def setDropAction(self, action: Any) -> None:
        self.action = action

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


def test_initial_three_panes_and_priority_order(dialog: PilotNamesDialog) -> None:
    assert dialog.categories.count() == 13
    assert [dialog.names.item(i).text() for i in range(2)] == [
        "Luke Skywalker",
        "Darth Vader",
    ]
    assert dialog.pilots.count() == 4
    assert dialog.autofill_button.isEnabled()
    assert dialog.names.dragEnabled() and not dialog.pilots.dragEnabled()


def test_header_counts_and_autofill_preview_track_library_edits(
    dialog: PilotNamesDialog,
) -> None:
    assert dialog.library_total.text() == "13"
    assert dialog.name_total.text() == "377"
    assert dialog.name_count.text() == "32" and dialog.pilot_count.text() == "4"
    dialog.save_names(["Luke", "Vader", "Leia"])
    assert dialog.name_total.text() == "348"
    assert dialog.name_count.text() == "3"
    assert dialog.autofill_button.text() == "Autofill 3 pilots"
    assert "1 pilot keeps their current name" in dialog.autofill_summary.text()


def test_row_geometry_and_scrollbars_follow_airwing_design(
    dialog: PilotNamesDialog,
) -> None:
    from PySide6.QtWidgets import QStyleOptionViewItem
    from qt_ui.widgets.pilotnamelist import DETAIL_ROLE, NameRowDelegate

    for view, height in (
        (dialog.categories, 52),
        (dialog.names, 36),
        (dialog.pilots, 52),
    ):
        delegate = view.itemDelegate()
        assert isinstance(delegate, NameRowDelegate)
        assert (
            delegate.sizeHint(QStyleOptionViewItem(), view.model().index(0, 0)).height()
            == height
        )
        assert view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert dialog.categories.item(0).data(DETAIL_ROLE) == "32 names · Built-in"
    assert dialog.pilots.item(0).data(DETAIL_ROLE) == "AI · Active"
    assert dialog.names.verticalScrollBar().maximum() > 0


def test_custom_row_paint_uses_airwing_selection_and_card_colours(
    dialog: PilotNamesDialog,
) -> None:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
    from qt_ui.widgets.cards import CARD_BG
    from qt_ui.windows.airwingconfig.common import ACCENT

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 300, 52)
    image = QImage(300, 52, QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    try:
        option.state = QStyle.StateFlag.State_Selected
        dialog.categories.itemDelegate().paint(
            painter, option, dialog.categories.model().index(0, 0)
        )
        assert image.pixelColor(1, 10) == QColor(ACCENT)
        assert image.pixelColor(10, 10) == QColor("#1E3A52")
        option.state = QStyle.StateFlag.State_None
        dialog.categories.itemDelegate().paint(
            painter, option, dialog.categories.model().index(0, 0)
        )
        assert image.pixelColor(10, 10) == QColor(CARD_BG)
    finally:
        painter.end()


def test_drop_renames_target_only_and_copies_name_without_removing_it(
    dialog: PilotNamesDialog,
) -> None:
    squadron = dialog.squadron
    assert squadron is not None
    pilots = list(squadron.current_roster)
    state = dict(pilots[2].__dict__)
    changed = Mock()
    dialog.pilots_changed.connect(changed)
    event = Drop(dialog, 2)
    dialog.pilots.dropEvent(cast(Any, event))
    assert event.accepted and event.action == Qt.DropAction.CopyAction
    assert [p.name for p in pilots] == [
        "Pilot 0",
        "Pilot 1",
        "Luke Skywalker",
        "Pilot 3",
    ]
    assert {k: v for k, v in pilots[2].__dict__.items() if k != "name"} == {
        k: v for k, v in state.items() if k != "name"
    }
    assert dialog.names.item(0).text() == "Luke Skywalker"
    assert dialog.pilots.item(2).data(USER_ROLE) is pilots[2]
    changed.assert_called_once_with(squadron)


@pytest.mark.parametrize(
    "invalid", ["outside", "blank", "no-format", "bad-name", "bad-utf8"]
)
def test_bad_drops_do_not_change_pilots(dialog: PilotNamesDialog, invalid: str) -> None:
    event = Drop(dialog, 0)
    if invalid == "outside":
        event.origin = object()
    elif invalid == "blank":
        event.point = QPointF(5, dialog.pilots.height() - 5)
    elif invalid == "no-format":
        event.data = QMimeData()
        event.data.setText("External text")
    elif invalid == "bad-name":
        event.data.setData(NAME_MIME, b" ")
    else:
        event.data.setData(NAME_MIME, b"\xff")
    dialog.pilots.dropEvent(cast(Any, event))
    assert not event.accepted
    assert [dialog.pilots.item(i).text() for i in range(4)] == [
        f"Pilot {i}" for i in range(4)
    ]


def test_drag_enter_and_move_accept_only_valid_name_sources(
    dialog: PilotNamesDialog,
) -> None:
    event = Drop(dialog, 1)
    dialog.pilots.dragEnterEvent(cast(Any, event))
    assert event.accepted
    dialog.pilots.dragMoveEvent(cast(Any, event))
    assert dialog.pilots.currentRow() == 1
    bad = Drop(dialog, 1, source=object())
    dialog.pilots.dragEnterEvent(cast(Any, bad))
    assert not bad.accepted
    dialog.pilots.dragMoveEvent(cast(Any, bad))
    assert not bad.accepted


def test_autofill_uses_visible_order_and_leaves_remainder_unchanged(
    dialog: PilotNamesDialog,
) -> None:
    dialog.save_names(["Vader", "Luke"])
    changed = Mock()
    dialog.pilots_changed.connect(changed)
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ):
        dialog.autofill_button.click()
    assert [dialog.pilots.item(i).text() for i in range(4)] == [
        "Vader",
        "Luke",
        "Pilot 2",
        "Pilot 3",
    ]
    assert dialog.names.count() == 2
    changed.assert_called_once_with(dialog.squadron)


def test_autofill_cancel_does_not_change_any_pilot(dialog: PilotNamesDialog) -> None:
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.No
    ):
        dialog.autofill_button.click()
    assert dialog.pilots.item(0).text() == "Pilot 0"


def test_name_priority_can_be_edited_and_survives_reload(
    dialog: PilotNamesDialog,
) -> None:
    dialog.save_names(["Luke", "Vader", "Leia"])
    dialog.down_button.click()
    assert dialog.category is not None
    assert dialog.category.names == ("Vader", "Luke", "Leia")
    assert dialog.names.currentRow() == 1
    dialog.up_button.click()
    assert NameLibrary.load(dialog.library.path).categories["star-wars"].names == (
        "Luke",
        "Vader",
        "Leia",
    )


def test_create_category_add_edit_remove_names_and_rename(
    dialog: PilotNamesDialog,
) -> None:
    with patch.object(
        QInputDialog, "getText", return_value=("Amigos Personajes", True)
    ):
        dialog.new_category()
    assert dialog.category is not None and dialog.category.name == "Amigos Personajes"
    key = dialog.category.id
    assert dialog.names.count() == 0 and not dialog.autofill_button.isEnabled()
    with patch.object(
        QInputDialog, "getMultiLineText", return_value=("  Álex\n\nZoë\n", True)
    ):
        dialog.add_names()
    assert dialog.category.names == ("Álex", "Zoë")
    with patch.object(QInputDialog, "getText", return_value=("Captain Alex", True)):
        dialog.edit_name()
    dialog.names.setCurrentRow(1)
    dialog.remove_name()
    with patch.object(QInputDialog, "getText", return_value=("Multiplayer", True)):
        dialog.rename_category()
    category = NameLibrary.load(dialog.library.path).categories[key]
    assert category.name == "Multiplayer" and category.names == ("Captain Alex",)


def test_cancel_library_edits_do_not_create_a_file(dialog: PilotNamesDialog) -> None:
    with patch.object(QInputDialog, "getText", return_value=("Ignored", False)):
        dialog.new_category()
        dialog.rename_category()
        dialog.edit_name()
    with patch.object(
        QInputDialog, "getMultiLineText", return_value=("Ignored", False)
    ):
        dialog.add_names()
    assert not dialog.library.path.exists()


def test_library_write_failure_rolls_back_ui_and_memory(
    dialog: PilotNamesDialog,
) -> None:
    before = dialog.category
    with patch.object(
        dialog.library, "save", side_effect=OSError("Disk full")
    ), patch.object(QMessageBox, "warning") as warning:
        dialog.save_names(["Changed"])
    warning.assert_called_once()
    assert dialog.category == before
    assert dialog.names.item(0).text() == "Luke Skywalker"


def test_delete_category_does_not_rename_pilots(dialog: PilotNamesDialog) -> None:
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ):
        dialog.delete_category()
    assert "star-wars" not in NameLibrary.load(dialog.library.path).categories
    assert dialog.pilots.item(0).text() == "Pilot 0"


def test_switching_squadron_targets_only_selected_roster(
    dialog: PilotNamesDialog,
) -> None:
    first = dialog.squadron
    other = SquadronStub("VFA-34", 2)
    dialog.squadrons.addItem(str(other), other)
    dialog.squadrons.setCurrentIndex(1)
    event = Drop(dialog, 0)
    dialog.pilots.dropEvent(cast(Any, event))
    assert other.current_roster[0].name == "Luke Skywalker"
    assert first is not None and first.current_roster[0].name == "Pilot 0"
    dialog.assign_name(first.current_roster[0], "Must not leak")
    assert first.current_roster[0].name == "Pilot 0"


def test_empty_roster_or_library_disables_autofill(dialog: PilotNamesDialog) -> None:
    other = SquadronStub("Empty", 0)
    dialog.squadrons.addItem(str(other), other)
    dialog.squadrons.setCurrentIndex(1)
    assert not dialog.autofill_button.isEnabled()
    dialog.squadrons.setCurrentIndex(0)
    dialog.library.categories.clear()
    dialog.refresh_categories()
    assert not dialog.autofill_button.isEnabled()
    assert not dialog.add_names_button.isEnabled()


def test_initial_squadron_can_be_selected_explicitly(tmp_path: Path) -> None:
    first, second = SquadronStub("First"), SquadronStub("Second", 2)
    widget = PilotNamesDialog(
        cast(Any, [first, second]),
        NameLibrary.load(tmp_path / "names.json"),
        cast(Any, second),
    )
    try:
        assert widget.squadron is second and widget.pilots.count() == 2
    finally:
        widget.deleteLater()


def test_squadron_button_opens_names() -> None:
    from qt_ui.windows.SquadronDialog import SquadronDialog

    window = SimpleNamespace(
        discharge_pilot=Mock(),
        open_names=Mock(),
        rename_pilot=Mock(),
        toggle_ai=Mock(),
        toggle_leave=Mock(),
        reset_button_states=Mock(),
        pilot_list=Mock(),
    )
    panel = SquadronDialog._build_buttons(cast(Any, window))
    try:
        assert window.assign_names_button.text() == "Assign Names"
        window.assign_names_button.click()
        window.open_names.assert_called_once()
    finally:
        for index in range(panel.count()):
            item = panel.itemAt(index)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


def test_squadron_names_preselects_current_squadron(tmp_path: Path) -> None:
    from game import persistency
    from qt_ui.windows.SquadronDialog import SquadronDialog

    selected, other = SquadronStub("Selected"), SquadronStub("Other")
    cast(Any, selected).coalition = SimpleNamespace(
        air_wing=SimpleNamespace(iter_squadrons=lambda: iter([other, selected]))
    )
    window = SimpleNamespace(squadron=selected, pilot_names_changed=Mock())
    with patch(
        "qt_ui.windows.SquadronDialog.PilotNamesDialog"
    ) as factory, patch.object(persistency, "settings_dir", return_value=tmp_path):
        SquadronDialog.open_names(cast(Any, window))
    args = factory.call_args.args
    assert args[0] == [other, selected] and args[2] is selected
    assert isinstance(args[1], NameLibrary)
    factory.return_value.exec.assert_called_once()
    factory.return_value.deleteLater.assert_called_once()


def test_name_change_notifications_are_limited_to_affected_flights() -> None:
    from qt_ui.windows.SquadronDialog import SquadronDialog

    squadron = SquadronStub("Changed")
    other = SquadronStub("Other")

    class FlightStub:
        def __init__(self, wing: Any) -> None:
            self.squadron = wing

    flight, untouched = FlightStub(squadron), FlightStub(other)
    game = SimpleNamespace(
        coalitions=[
            SimpleNamespace(
                ato=SimpleNamespace(
                    packages=[SimpleNamespace(flights=[flight, untouched])]
                )
            )
        ]
    )
    cast(Any, squadron).coalition = SimpleNamespace(game=game)
    controller = SimpleNamespace(sim_update=Mock())
    window = SimpleNamespace(
        squadron=squadron, sim_controller=controller, _pilot_changed=Mock()
    )
    with patch("qt_ui.windows.SquadronDialog.EventStream.put_nowait") as send, patch(
        "qt_ui.windows.SquadronDialog.live_window", return_value=None
    ):
        SquadronDialog.pilot_names_changed(cast(Any, window), cast(Any, squadron))
    assert send.call_args.args[0].updated_flights == {flight}
    controller.sim_update.emit.assert_called_once()
    window._pilot_changed.assert_called_once()
