"""The mission can be written with no wind at the surface, keeping the winds aloft."""

from __future__ import annotations

from dcs.weather import Weather, Wind

from game.missiongenerator.environmentgenerator import calm_surface
from game.settings import Settings
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
