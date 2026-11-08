"""Intel location links retain source identity and use real Qt hit testing."""

import os
from types import SimpleNamespace as NS
from typing import Any
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dcs.mapping import LatLng
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QIcon, QMouseEvent, QStandardItemModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QTabWidget, QWidget
import pytest

from game.income import BuildingIncome, Income
from game.server import EventStream
from game.theater import Player
from qt_ui.windows.basemenu.QBaseMenuTabs import QBaseMenuTabs
from qt_ui.windows.intel import model as data
from qt_ui.windows.intel.dialog import AIR, GROUND, ICONS, IntelWindow
from qt_ui.windows.intel.rows import EconomyLine, HeaderLine
from .test_intel_dialog import _base, _game


def location(name: str, lat: float = 33) -> Any:
    return NS(name=name, id=uuid4(), position=NS(latlng=lambda: LatLng(lat, 69)))


@pytest.fixture
def intel(monkeypatch: pytest.MonkeyPatch) -> Any:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setitem(ICONS, "Statistics", QIcon())
    sent: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    blue = _base("Same base", {"F-16CM": 3}, {"M1": 2}, income=20)
    red = _base("Same base", {"Su-27": 4}, {"T-72": 5}, income=10)
    for base, lat in ((blue, 33), (red, 34)):
        base.id = uuid4()
        base.position = NS(latlng=lambda latitude=lat: LatLng(latitude, 69))
    site = location("PIKE")
    game = _game()
    game.theater.control_points_for = lambda player: [blue if player.is_blue else red]
    game.game_stats = NS(data_per_turn=[])
    monkeypatch.setattr(
        data,
        "Income",
        lambda game, player: NS(
            multiplier=1,
            control_points=[blue if player.is_blue else red],
            buildings=[BuildingIncome("PIKE", "oil", 2, 10, 2, ground_object=site)],
            from_bases=20,
            total_buildings=20,
            total=40,
        ),
    )
    model: Any = NS(game=game, transfer_model=QStandardItemModel())
    window = IntelWindow(game, model)
    window.resize(1000, 680)
    window.show()
    app.processEvents()
    yield NS(
        app=app,
        window=window,
        game=game,
        model=model,
        blue=blue,
        red=red,
        site=site,
        sent=sent,
    )
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def link(view: Any, row: int) -> QPoint:
    index = view.model().index(row, 0)
    return (
        view.itemDelegate()
        .action_rect(view.visualRect(index), index.data(Qt.ItemDataRole.UserRole))
        .center()
    )


def move_mouse(view: Any, point: QPoint) -> None:
    # Send the actual Qt mouse event; offscreen cursor warps can miss hover events
    # when other tests have opened and closed windows at the same coordinates.
    QCoreApplication.sendEvent(
        view.viewport(),
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(point),
            QPointF(view.viewport().mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("sort", list(data.Sort))
@pytest.mark.parametrize("needle", ["", "same", "f-16", "absent"])
def test_force_links_keep_the_original_base_through_sort_and_filter(
    side: Player, sort: data.Sort, needle: str
) -> None:
    first = _base("Same base", {"F-16": 2}, {"Tank": 2})
    second = _base("Same base", {"F-16": 4}, {"Tank": 4})
    game = _game(first, second)
    for build in (data.air_forces, data.ground_forces):
        groups = build(game, side, sort, needle).groups
        assert len(groups) == 2
        expected = (first, second) if sort is data.Sort.BASE_NAME else (second, first)
        assert groups[0].control_point is expected[0]
        assert groups[1].control_point is expected[1]


def test_economy_retains_each_building_source_without_name_lookup() -> None:
    first, second = location("SAME"), location("SAME", 34)
    for site, standing in ((first, 1), (second, 2)):
        site.obj_name = "SAME"
        site.category = "oil"
        site.statics = [NS(alive=index < standing) for index in range(2)]
    base = _base("Base", income=20)
    base.ground_objects = [first, second]
    game = _game(base)
    game.settings = NS(player_income_multiplier=1, enemy_income_multiplier=1)
    breakdown = Income(game, Player.BLUE)
    assert breakdown.buildings[0].ground_object is first
    assert breakdown.buildings[1].ground_object is second
    sources = data.economy(game, Player.BLUE).sections
    assert sources[0].rows[0].target is base
    assert sources[1].rows[0].target is second
    assert sources[1].rows[1].target is first


@pytest.mark.parametrize("row", [1, 3])
def test_economy_hover_highlights_the_exact_icon_and_click_moves_the_map(
    intel: Any, row: int
) -> None:
    pane = intel.window.economy
    target = pane.lines.line(pane.lines.index(row, 0)).row.target
    point = link(pane.view, row)
    move_mouse(pane.view, point)
    intel.app.processEvents()
    assert intel.sent[-1].map_hover[1:] == (target.id, target.position.latlng())
    assert all(event.fly_to is None for event in intel.sent)
    assert pane.view.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(pane.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert intel.sent[-1].fly_to == target.position.latlng()
    assert intel.sent[-1].fly_to_zoom is None


def test_moving_off_a_link_or_hiding_intel_clears_highlighting(intel: Any) -> None:
    view = intel.window.economy.view
    move_mouse(view, link(view, 1))
    intel.app.processEvents()
    owner = intel.sent[-1].map_hover[0]
    move_mouse(
        view,
        QPoint(8, view.visualRect(view.model().index(1, 0)).center().y()),
    )
    intel.app.processEvents()
    assert intel.sent[-1].map_hover == (owner, None, None)
    move_mouse(view, link(view, 1))
    intel.app.processEvents()
    intel.window.hide()
    intel.app.processEvents()
    assert intel.sent[-1].map_hover == (owner, None, None)


def test_scroll_and_model_reset_do_not_leave_a_stale_hover(intel: Any) -> None:
    view = intel.window.economy.view
    rows = [
        EconomyLine(
            data.EconomyRow(
                "Oil",
                "",
                "",
                "",
                10,
                0.1,
                target=location(str(index), 33 + index / 100),
            )
        )
        for index in range(40)
    ]
    intel.window.economy.lines.set_lines(rows)
    intel.app.processEvents()
    move_mouse(view, link(view, 0))
    intel.app.processEvents()
    before = intel.sent[-1].map_hover[1]
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
    intel.app.processEvents()
    assert intel.sent[-1].map_hover[1] != before
    intel.window.economy.lines.set_lines([])
    intel.app.processEvents()
    assert intel.sent[-1].map_hover[1:] == (None, None)


@pytest.mark.parametrize("tab,section", [(AIR, "Aircraft"), (GROUND, "Ground forces")])
@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_force_links_open_the_exact_base_without_folding(
    intel: Any, monkeypatch: pytest.MonkeyPatch, tab: int, section: str, side: Player
) -> None:
    import importlib

    opened = []

    class BaseDialog(QDialog):
        def __init__(self, parent: Any, base: Any, model: Any) -> None:
            super().__init__(parent)
            self.tabs = NS(
                select_section=lambda name: opened.append((base, model, name))
            )

    monkeypatch.setattr(
        importlib.import_module("qt_ui.windows.basemenu.QBaseMenu2"),
        "QBaseMenu2",
        BaseDialog,
    )
    intel.window.show_side(side)
    intel.window.tabs.setCurrentIndex(tab)
    intel.app.processEvents()
    pane = intel.window.air if tab == AIR else intel.window.ground
    QTest.mouseClick(
        pane.view.viewport(), Qt.MouseButton.LeftButton, pos=link(pane.view, 0)
    )
    assert opened == [(intel.blue if side.is_blue else intel.red, intel.model, section)]
    assert intel.window.fold_state(tab) == set()
    assert isinstance(pane.lines.line(pane.lines.index(0, 0)), HeaderLine)


def test_header_click_still_folds_and_enter_activates_the_base_link(
    intel: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pane = intel.window.air
    intel.window.tabs.setCurrentIndex(AIR)
    intel.app.processEvents()
    opened = []
    monkeypatch.setattr(
        intel.window, "open_base", lambda base, section: opened.append((base, section))
    )
    rect = pane.view.visualRect(pane.lines.index(0, 0))
    QTest.mouseClick(
        pane.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=QPoint(60, rect.center().y()),
    )
    assert intel.window.fold_state(AIR) == {"Same base"}
    pane.view.setCurrentIndex(pane.lines.index(0, 0))
    QTest.keyClick(pane.view, Qt.Key.Key_Return)
    assert opened == [(intel.blue, "Aircraft")]


def test_base_section_selection_ignores_counts_and_respects_enemy_permissions(
    intel: Any,
) -> None:
    tabs: Any = QTabWidget()
    tabs.sections = {}
    QBaseMenuTabs._add(tabs, QWidget(), "Intel")
    QBaseMenuTabs._add(tabs, QWidget(), "Aircraft", count=5)
    QBaseMenuTabs._add(tabs, QWidget(), "Ground forces", count=8)
    tabs.setTabText(1, "Aircraft  999")
    QBaseMenuTabs.select_section(tabs, "Aircraft")
    assert tabs.currentIndex() == 1
    tabs.setTabEnabled(2, False)
    QBaseMenuTabs.select_section(tabs, "Ground forces")
    assert tabs.currentIndex() == 0
    assert not tabs.isTabEnabled(2)
    del tabs.sections["Aircraft"]
    QBaseMenuTabs.select_section(tabs, "Aircraft")
    assert tabs.currentIndex() == 0
    tabs.deleteLater()


@pytest.mark.parametrize("source", ["current", "missing", "stale"])
def test_legacy_intel_entry_uses_only_the_current_campaign_model(
    intel: Any, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    import importlib

    opened = []

    class BaseDialog(QDialog):
        def __init__(self, parent: Any, base: Any, model: Any) -> None:
            super().__init__(parent)
            self.tabs = NS(
                select_section=lambda name: opened.append((base, model, name))
            )

    monkeypatch.setattr(
        importlib.import_module("qt_ui.windows.basemenu.QBaseMenu2"),
        "QBaseMenu2",
        BaseDialog,
    )
    model = (
        intel.model
        if source == "current"
        else NS(game=object()) if source == "stale" else None
    )
    monkeypatch.setattr(
        importlib.import_module("qt_ui.windows.highcommand.dialog"),
        "main_window",
        lambda: NS(game_model=model),
    )
    intel.window.game_model = None
    intel.window.open_base(intel.blue, "Aircraft")
    assert opened == (
        [(intel.blue, intel.model, "Aircraft")] if source == "current" else []
    )
