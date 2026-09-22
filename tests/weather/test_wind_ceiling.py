"""DCS models no more than 97 knots of wind, so nothing may brief more than that.

The generated wind was already held to it. A live observation was not, and a real jet
stream at FL260 beats it routinely -- the mission took the number, the sim ignored it,
and the kneeboard printed it.
"""

from __future__ import annotations

from typing import Any

import pytest

from dcs.weather import Wind

from game.utils import knots, mps
from game.weather.wind import MAX_WIND_SPEED, capped


def test_the_ceiling_is_what_dcs_flies() -> None:
    assert MAX_WIND_SPEED == knots(97)


def test_an_ordinary_wind_is_untouched() -> None:
    wind = Wind(270, 20.0)
    assert capped(wind) is wind


def test_a_jet_stream_is_held_to_the_ceiling() -> None:
    capped_wind = capped(Wind(270, mps(knots(140).meters_per_second).meters_per_second))
    assert round(mps(capped_wind.speed).knots) == 97


def test_the_direction_survives_the_cap() -> None:
    assert capped(Wind(123, 90.0)).direction == 123


def test_a_live_observation_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ATMOS-X reader is the path that had no ceiling."""
    from game.weather import atmosxliveweather

    wind = atmosxliveweather._wind({"dir": 300, "speed": 80.0})
    assert wind is not None
    assert round(mps(wind.speed).knots) == 97
    assert wind.direction == 300


def test_a_live_observation_below_the_ceiling_is_verbatim() -> None:
    from game.weather import atmosxliveweather

    wind = atmosxliveweather._wind({"dir": 90, "speed": 12.5})
    assert wind is not None
    assert wind.speed == 12.5


def test_the_generated_wind_uses_the_same_ceiling() -> None:
    import game.weather.windspeedgenerators as gen

    assert gen.MAX_WIND_SPEED is MAX_WIND_SPEED
