"""Surface wind is preserved, including recovery from legacy forced-calm saves."""

import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs import Mission
from dcs.weather import Weather, Wind

from game.missiongenerator.environmentgenerator import EnvironmentGenerator
from game.settings import Settings
from game.theater import ConflictTheater
from game.timeofday import TimeOfDay
from game.weather.conditions import Conditions
from game.weather.weather import ClearSkies
from game.weather.wind import WindConditions
from game.weather.atmosxliveweather import apply_weather, parse_preset
from tests.weather.test_atmosx_live_weather import PRESET


def _turn_weather() -> Any:
    weather = ClearSkies.__new__(ClearSkies)
    weather.wind = WindConditions(Wind(308, 11.7), Wind(337, 22.2), Wind(9, 39.1))
    return weather


def test_removed_setting_is_not_exposed() -> None:
    assert "no_surface_wind" not in Settings.__dataclass_fields__


def test_new_turn_keeps_generated_wind_even_with_a_legacy_setting(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        Conditions, "generate_weather", staticmethod(lambda *_: _turn_weather())
    )
    settings = Settings()
    settings.atmosx_live_weather = False
    setattr(settings, "no_surface_wind", True)
    conditions = Conditions.generate(
        theater=cast(ConflictTheater, SimpleNamespace(seasonal_conditions=None)),
        day=datetime.date(2026, 6, 1),
        time_of_day=TimeOfDay.Day,
        settings=settings,
        forced_time=datetime.time(12),
    )
    assert conditions.weather.wind.at_0m.speed == 11.7


def test_environment_exports_all_three_actual_winds() -> None:
    mission = Mission()
    weather = _turn_weather()
    EnvironmentGenerator(
        mission, cast(Any, None), datetime.datetime(2026, 6, 1, 12), False
    ).set_wind(weather.wind)
    assert (
        mission.weather.wind_at_ground.direction,
        mission.weather.wind_at_ground.speed,
    ) == (308, 11.7)
    assert (
        mission.weather.wind_at_2000.direction,
        mission.weather.wind_at_2000.speed,
    ) == (337, 22.2)
    assert (
        mission.weather.wind_at_8000.direction,
        mission.weather.wind_at_8000.speed,
    ) == (9, 39.1)


def test_live_observation_keeps_surface_wind() -> None:
    weather = Weather("Syria")
    preset = parse_preset(PRESET)["vdata"]
    apply_weather(weather, preset)
    assert weather.wind_at_ground.speed > 0
    assert weather.wind_at_ground.speed == preset["wind"]["atGround"]["speed"]


def test_legacy_forecast_is_restored_once_without_changing_winds_aloft() -> None:
    weather = _turn_weather()
    original = weather.wind.at_0m
    weather.forecast_surface_wind = original
    weather.wind = WindConditions(
        Wind(308, 0), weather.wind.at_2000m, weather.wind.at_8000m
    )
    assert weather.restore_surface_wind()
    assert weather.wind.at_0m is original
    assert weather.wind.at_2000m.speed == 22.2
    assert weather.wind.at_8000m.speed == 39.1
    assert not weather.restore_surface_wind()


@pytest.mark.parametrize("speed", [0, 11.7])
def test_saves_without_a_retained_forecast_keep_their_recorded_wind(
    speed: float,
) -> None:
    weather = _turn_weather()
    weather.wind = WindConditions(
        Wind(308, speed), weather.wind.at_2000m, weather.wind.at_8000m
    )
    assert not weather.restore_surface_wind()
    assert weather.wind.at_0m.speed == speed
