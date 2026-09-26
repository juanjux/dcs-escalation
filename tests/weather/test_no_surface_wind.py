"""The mission can be written with no wind at the surface, keeping the winds aloft."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any, cast

from dcs.weather import Weather, Wind

from game.missiongenerator.environmentgenerator import calm_surface
from game.settings import Settings
from game.theater import ConflictTheater
from game.timeofday import TimeOfDay
from game.weather.conditions import Conditions
from game.weather.weather import ClearSkies
from game.weather.wind import WindConditions
from game.weather.atmosxliveweather import apply_weather, parse_preset
from tests.weather.test_atmosx_live_weather import PRESET


def test_the_surface_is_calm_and_the_winds_aloft_stay() -> None:
    weather = Weather("Falklands")
    weather.wind_at_ground = Wind(308, 11.7)
    weather.wind_at_2000 = Wind(337, 22.2)
    weather.wind_at_8000 = Wind(9, 39.1)

    calm_surface(weather)

    assert weather.wind_at_ground.speed == 0
    assert weather.wind_at_ground.direction == 308
    assert (weather.wind_at_2000.direction, weather.wind_at_2000.speed) == (337, 22.2)
    assert (weather.wind_at_8000.direction, weather.wind_at_8000.speed) == (9, 39.1)


def test_it_calms_a_live_observation_too() -> None:
    weather = Weather("Syria")
    apply_weather(weather, parse_preset(PRESET)["vdata"])
    aloft = weather.wind_at_8000.direction, weather.wind_at_8000.speed

    calm_surface(weather)

    assert weather.wind_at_ground.speed == 0
    assert (weather.wind_at_8000.direction, weather.wind_at_8000.speed) == aloft


def test_it_is_on_by_default() -> None:
    assert Settings().no_surface_wind is True


def _turn_weather() -> Any:
    """A generated turn's weather, as a save holds it: built without __init__, so
    it has no forecast_surface_wind of its own, like one pickled before it existed."""
    weather = ClearSkies.__new__(ClearSkies)
    weather.wind = WindConditions(Wind(308, 11.7), Wind(337, 22.2), Wind(9, 39.1))
    return weather


def test_the_turn_weather_is_calmed_and_given_back() -> None:
    weather = _turn_weather()

    assert weather.calm_surface(True) is True
    assert weather.wind.at_0m.speed == 0
    assert weather.wind.at_2000m.speed == 22.2
    assert weather.wind.at_8000m.speed == 39.1
    assert weather.calm_surface(True) is False

    assert weather.calm_surface(False) is True
    assert (weather.wind.at_0m.direction, weather.wind.at_0m.speed) == (308, 11.7)
    assert weather.calm_surface(False) is False


def test_a_new_turn_is_given_the_calm_surface(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        Conditions, "generate_weather", staticmethod(lambda *_: _turn_weather())
    )
    for calm, expected in ((True, 0), (False, 11.7)):
        settings = Settings()
        settings.atmosx_live_weather = False
        settings.no_surface_wind = calm
        conditions = Conditions.generate(
            theater=cast(ConflictTheater, SimpleNamespace(seasonal_conditions=None)),
            day=datetime.date(2026, 6, 1),
            time_of_day=TimeOfDay.Day,
            settings=settings,
            forced_time=datetime.time(12, 0),
        )
        assert conditions.weather.wind.at_0m.speed == expected
