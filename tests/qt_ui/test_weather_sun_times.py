"""Local solar times reach the visible WEATHER cell and refresh with the turn."""

import datetime as dt
import os
from types import SimpleNamespace as NS
from typing import Any, Iterator
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from dcs.mapping import LatLng
from dcs.weather import Wind
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from game.theater.daytimecalculator import _sun_times
from game.timeofday import TimeOfDay
from game.utils import inches_hg
from game.weather.conditions import Conditions
from game.weather.wind import WindConditions
from qt_ui import uiconstants as CONST
from qt_ui.widgets.conditions.QWeatherWidget import QWeatherWidget


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[QWeatherWidget]:
    for key in (
        "Dawn",
        "Day",
        "Dusk",
        "Night",
        "Weather_winds",
        "Reload",
        "Weather_day-clear",
    ):
        monkeypatch.setitem(CONST.ICONS, key, QPixmap(8, 8))
    weather = QWeatherWidget()
    yield weather
    weather.close()


def _conditions(start: dt.datetime) -> Conditions:
    weather: Any = NS(
        clouds=None,
        fog=None,
        wind=WindConditions(Wind(0, 0), Wind(0, 0), Wind(0, 0)),
        atmospheric=NS(
            temperature_celsius=20, qnh=inches_hg(29.92), turbulence_per_10cm=0
        ),
    )
    return Conditions(TimeOfDay.Dusk, start, weather)


def _theater(
    latitude: float = -54.8, longitude: float = -68.3, offset: int = -3
) -> Any:
    return NS(
        reference_position=LatLng(latitude, longitude),
        timezone=dt.timezone(dt.timedelta(hours=offset)),
    )


@pytest.mark.parametrize(
    "latitude,longitude,offset",
    [(-54.8, -68.3, -3), (13.4, 144.8, 10), (36.2, -115.0, -8)],
)
def test_tooltip_uses_campaign_solar_calculator_and_local_hours(
    widget: QWeatherWidget, latitude: float, longitude: float, offset: int
) -> None:
    start = dt.datetime(2026, 3, 21, 19)
    theater = _theater(latitude, longitude, offset)
    times = _sun_times(latitude, longitude, theater.timezone, start.date())
    assert times is not None
    sunrise, sunset = times
    widget.setCurrentTurn(1, _conditions(start), theater=theater)
    tooltip = widget.toolTip()
    assert "Sunrise (local)" in tooltip and sunrise.strftime("%H:%M") in tooltip
    assert "Sunset (local)" in tooltip and sunset.strftime("%H:%M") in tooltip
    assert "campaign reference position" in tooltip
    assert "Twilight continues after sunset" in tooltip
    assert "QNH" in tooltip and "Generated forecast" in tooltip


def test_aware_start_uses_mission_local_date_not_utc_or_computer_date(
    widget: QWeatherWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[float, float, dt.timezone, dt.date]] = []

    def sun_times(
        lat: float, lon: float, timezone: dt.timezone, date: dt.date
    ) -> tuple[dt.datetime, dt.datetime]:
        calls.append((lat, lon, timezone, date))
        return (
            dt.datetime.combine(date, dt.time(6, 12), timezone),
            dt.datetime.combine(date, dt.time(18, 34), timezone),
        )

    monkeypatch.setattr("qt_ui.widgets.conditions.QWeatherWidget._sun_times", sun_times)
    theater = _theater()
    widget.setCurrentTurn(
        1,
        _conditions(dt.datetime(2026, 7, 1, 1, tzinfo=dt.timezone.utc)),
        theater=theater,
    )
    assert calls == [(-54.8, -68.3, theater.timezone, dt.date(2026, 6, 30))]
    assert "06:12" in widget.toolTip() and "18:34" in widget.toolTip()


@pytest.mark.parametrize("month", [6, 12])
def test_polar_conditions_do_not_invent_sun_times(
    widget: QWeatherWidget, month: int
) -> None:
    widget.setCurrentTurn(
        1, _conditions(dt.datetime(2026, month, 21, 19)), theater=_theater(69.3, 30, 3)
    )
    assert "Unavailable (polar conditions)" in widget.toolTip()
    assert "Sunrise (local)" not in widget.toolTip()


def test_solar_times_update_with_date_and_clear_without_theater(
    widget: QWeatherWidget,
) -> None:
    theater = _theater()
    widget.setCurrentTurn(1, _conditions(dt.datetime(2026, 3, 21, 19)), theater=theater)
    first = widget.sun_details()
    widget.setCurrentTurn(2, _conditions(dt.datetime(2026, 6, 21, 19)), theater=theater)
    assert widget.sun_details() != first
    widget.setCurrentTurn(3, _conditions(dt.datetime(2026, 6, 22, 19)))
    assert widget.sun_details() == []
    assert "Sunrise" not in widget.toolTip() and "Sun times" not in widget.toolTip()


def test_top_panel_propagates_sun_times_to_visible_weather_cell(
    widget: QWeatherWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qt_ui.widgets.QConditionsWidget import QConditionsWidget
    from qt_ui.widgets.QTopPanel import QTopPanel
    from qt_ui.widgets.commandbar import WeatherCell

    monkeypatch.setattr("qt_ui.widgets.QTopPanel.live_weather_enabled", lambda _: False)
    monkeypatch.setattr("qt_ui.widgets.QTopPanel.Income", lambda *a, **kw: NS(total=10))
    monkeypatch.setattr("qt_ui.widgets.commandbar.intel_ratios", lambda _: [1, 1, 1])
    conditions_widget = QConditionsWidget(MagicMock())
    weather_cell = WeatherCell(lambda: None)
    panel: Any = MagicMock()
    panel.conditionsWidget = conditions_widget
    panel.weather_cell = weather_cell
    game: Any = MagicMock()
    game.turn = 2
    game.conditions = _conditions(dt.datetime(2026, 3, 21, 19))
    game.theater = _theater()
    try:
        QTopPanel.setGame(panel, game)
        expected = conditions_widget.weather_widget.toolTip()
        assert "Sunrise (local)" in expected and "Sunset (local)" in expected
        assert weather_cell.toolTip() == expected
        assert conditions_widget.toolTip() == expected
        panel.turn_cell.setToolTip.assert_called_once_with(expected)
    finally:
        weather_cell.close()
        conditions_widget.close()
