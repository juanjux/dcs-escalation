"""Location coordinate buttons save campaign GPS points without a player flight."""

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMenu

from game.ato.savedpoints import PointKind, SavedPoint, campaign_points, points_of
from qt_ui.widgets import coordinatelabel
from qt_ui.widgets.coordinatelabel import CoordinateLabel
from qt_ui.windows.groundobject import buildingcard, unitcard


@pytest.fixture(scope="module")
def qt_app() -> Any:
    return QApplication.instance() or QApplication([])


def _game() -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(),
        blue=SimpleNamespace(ato=SimpleNamespace(packages=[])),
    )


def _position() -> Any:
    return SimpleNamespace(
        x=1.0, y=2.0, latlng=lambda: SimpleNamespace(lat=36.0, lng=-115.0)
    )


def _choose_action(monkeypatch: pytest.MonkeyPatch, text: str) -> Mock:
    opened = Mock()

    class SelectingMenu(QMenu):
        def exec(self, _position: QPoint) -> None:  # type: ignore[override]
            opened()
            actions = {a.text(): a for a in self.actions() if not a.isSeparator()}
            assert list(actions) == ["Copy coordinates", "Save as waypoint"]
            assert actions[text].isEnabled()
            actions[text].trigger()

    monkeypatch.setattr(coordinatelabel, "QMenu", SelectingMenu)
    return opened


@pytest.mark.parametrize("building", [True, False], ids=["building", "vehicle"])
@pytest.mark.parametrize("height", [338, 0, None])
def test_location_row_saves_with_no_scheduled_flights(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch, building: bool, height: int | None
) -> None:
    game = _game()
    position = _position()
    unit: Any = SimpleNamespace(
        name="Location element",
        id=1,
        alive=True,
        health_fraction=1.0,
        repairable=False,
        position=position,
    )
    site: Any = SimpleNamespace(category="oil", repair_cost=lambda: 40, groups=[])
    if building:
        monkeypatch.setattr(buildingcard, "buildings_of", lambda _: [])
        monkeypatch.setattr(buildingcard, "thumbnail", lambda _: None)
        card = buildingcard.BuildingCard(site, game.settings, None, game=game)
        row = card._row(unit)
    else:
        monkeypatch.setattr(unitcard, "type_name", lambda _: "Depot vehicle")
        monkeypatch.setattr(unitcard, "describe_unit", lambda _: "")
        monkeypatch.setattr(unitcard, "unit_note", lambda _: "")
        units = unitcard.UnitCard(site, game.settings, None, game=game)
        row = units._unit_row(unit, 0)
    coordinate = row.findChild(CoordinateLabel)
    assert coordinate is not None
    opened = _choose_action(monkeypatch, "Save as waypoint")
    elevation = Mock(return_value=height)
    publish = Mock()
    monkeypatch.setattr("game.elevation.elevation_ft", elevation)
    monkeypatch.setattr(
        "game.server.savedpoints.notifications.publish_points_changed", publish
    )

    coordinate.button.click()

    opened.assert_called_once()
    elevation.assert_called_once_with(36.0, -115.0)
    publish.assert_called_once()
    (point,) = campaign_points(game.blue)
    assert point.kind is PointKind.WAYPOINT
    assert point.name == coordinate.text
    assert (point.x, point.y) == (position.x, position.y)
    assert point.altitude_ft == (height if height is not None else 0)

    flight: Any = SimpleNamespace(
        squadron=SimpleNamespace(coalition=game.blue), client_count=1
    )
    game.blue.ato.packages.append(SimpleNamespace(flights=[flight]))
    assert points_of(flight)[0] is point
    row.close()


@pytest.mark.parametrize(
    "crewed,dcs_id", [(0, "FA-18C_hornet"), (1, "F-16C_50"), (1, "unknown")]
)
def test_save_is_not_gated_by_crew_or_export_capacity(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch, crewed: int, dcs_id: str
) -> None:
    game = _game()
    flight = SimpleNamespace(
        client_count=crewed,
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=dcs_id)),
    )
    game.blue.ato.packages.append(SimpleNamespace(flights=[flight]))
    points = campaign_points(game.blue)
    points.extend(SavedPoint(PointKind.WAYPOINT, f"P{n}", 0, 0) for n in range(24))
    coordinate = CoordinateLabel(_position(), game.settings, game=game)
    _choose_action(monkeypatch, "Save as waypoint")
    monkeypatch.setattr("game.elevation.elevation_ft", lambda *_: 100)
    monkeypatch.setattr(
        "game.server.savedpoints.notifications.publish_points_changed", Mock()
    )

    coordinate.button.click()

    assert len(points) == 25


@pytest.mark.parametrize("has_campaign", [False, True])
def test_copy_coordinates_still_works(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch, has_campaign: bool
) -> None:
    game = _game() if has_campaign else None
    coordinate = CoordinateLabel(_position(), None, game=game)
    if has_campaign:
        _choose_action(monkeypatch, "Copy coordinates")
    else:
        monkeypatch.setattr(
            coordinatelabel, "QMenu", Mock(side_effect=AssertionError("No menu"))
        )
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    before = clipboard.text()
    try:
        coordinate.button.click()
        assert clipboard.text() == coordinate.text
        if game is not None:
            assert not campaign_points(game.blue)
    finally:
        clipboard.setText(before)
