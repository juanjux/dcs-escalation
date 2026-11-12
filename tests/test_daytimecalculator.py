import datetime

import pytest
from dcs.mapping import LatLng

from game.theater.daytimecalculator import (
    _sun_times,
    includes_darkness,
    solar_daytime_map,
    solar_noon,
)

KOLA_TZ = datetime.timezone(datetime.timedelta(hours=3))
SYRIA_TZ = datetime.timezone(datetime.timedelta(hours=3))
KOLA = LatLng(69.3, 30.0)
SYRIA = LatLng(33.5, 36.3)
# Well south of the arctic circle, so every date has a sunrise and a sunset.
NEVADA_TZ = datetime.timezone(datetime.timedelta(hours=-8))
NEVADA = LatLng(36.2, -115.0)


def _hours(time_range: tuple[datetime.time, datetime.time]) -> tuple[int, int]:
    return time_range[0].hour, time_range[1].hour


def test_slots_are_two_hour_windows() -> None:
    daytime = solar_daytime_map(SYRIA, SYRIA_TZ, datetime.date(2011, 6, 15))
    for time_range in (daytime.dawn, daytime.day, daytime.dusk, daytime.night):
        begin, end = _hours(time_range)
        assert (end - begin) % 24 == 2


@pytest.mark.parametrize(
    "position,tz,date",
    [
        (SYRIA, SYRIA_TZ, datetime.date(2011, 1, 15)),
        (SYRIA, SYRIA_TZ, datetime.date(2011, 6, 15)),
        (NEVADA, NEVADA_TZ, datetime.date(2011, 1, 15)),
        (NEVADA, NEVADA_TZ, datetime.date(2011, 6, 15)),
        (KOLA, KOLA_TZ, datetime.date(1983, 3, 15)),
        (KOLA, KOLA_TZ, datetime.date(1983, 9, 15)),
    ],
)
def test_midday_is_around_noon(
    position: LatLng, tz: datetime.timezone, date: datetime.date
) -> None:
    """The day slot must land near local noon everywhere, in every season.

    Taking it from the midpoint of sunrise and sunset put it twelve hours out
    whenever the two fell on different UTC days, which is most of the year for a
    theater east of Greenwich.
    """
    begin, _ = _hours(solar_daytime_map(position, tz, date).day)
    assert 10 <= begin <= 13


def test_dawn_follows_sunrise_across_the_seasons() -> None:
    """Summer dawn must be earlier than winter dawn, which the fixed tables miss."""
    summer, _ = _hours(
        solar_daytime_map(SYRIA, SYRIA_TZ, datetime.date(2011, 6, 15)).dawn
    )
    winter, _ = _hours(
        solar_daytime_map(SYRIA, SYRIA_TZ, datetime.date(2011, 12, 15)).dawn
    )
    assert summer < winter


def test_polar_night_hangs_off_solar_noon() -> None:
    """Above the arctic circle in midwinter there is no sunrise to anchor to.

    The slots still have to differ from each other, and the darkness is the
    correct answer rather than something to paper over.
    """
    daytime = solar_daytime_map(KOLA, KOLA_TZ, datetime.date(1983, 12, 15))
    noon = solar_noon(KOLA.lng, KOLA_TZ, datetime.date(1983, 12, 15)).hour
    assert _hours(daytime.day)[0] == (noon - 1) % 24
    assert len({_hours(daytime.dawn), _hours(daytime.dusk), _hours(daytime.night)}) == 3


def test_polar_day_hangs_off_solar_noon() -> None:
    daytime = solar_daytime_map(KOLA, KOLA_TZ, datetime.date(1983, 6, 15))
    noon = solar_noon(KOLA.lng, KOLA_TZ, datetime.date(1983, 6, 15)).hour
    assert _hours(daytime.day)[0] == (noon - 1) % 24


def test_solar_noon_tracks_longitude() -> None:
    """A theater on the eastern edge of its time zone sees noon earlier."""
    date = datetime.date(2011, 6, 15)
    east = solar_noon(45.0, SYRIA_TZ, date)
    west = solar_noon(30.0, SYRIA_TZ, date)
    assert east < west


@pytest.mark.parametrize("month", [1, 6])
def test_darkness_includes_sunset_and_uses_local_times(month: int) -> None:
    day = datetime.date(2020, month, 1)
    times = _sun_times(NEVADA.lat, NEVADA.lng, NEVADA_TZ, day)
    assert times is not None
    sunrise, sunset = times
    assert sunrise.date() == sunset.date() == day
    minute = datetime.timedelta(minutes=1)
    start = sunrise.replace(tzinfo=None)
    assert not includes_darkness(NEVADA, NEVADA_TZ, start, sunset - minute)
    assert includes_darkness(
        NEVADA, NEVADA_TZ, start, sunset.astimezone(datetime.timezone.utc)
    )
    assert includes_darkness(NEVADA, NEVADA_TZ, sunrise - minute, sunrise)


@pytest.mark.parametrize("month,dark", [(6, False), (12, True)])
def test_darkness_for_polar_flights_that_cross_midnight(month: int, dark: bool) -> None:
    start = datetime.datetime(2020, month, 15, 23, tzinfo=KOLA_TZ)
    end = start + datetime.timedelta(hours=2)
    assert includes_darkness(KOLA, KOLA_TZ, start, end) is dark


def test_darkness_when_local_sunset_is_shortly_after_midnight() -> None:
    day = datetime.date(2020, 5, 16)
    times = _sun_times(KOLA.lat, KOLA.lng, KOLA_TZ, day)
    assert times is not None
    sunrise, sunset = times
    assert sunset < sunrise
    midnight = datetime.datetime.combine(day, datetime.time(), tzinfo=KOLA_TZ)
    assert not includes_darkness(KOLA, KOLA_TZ, midnight, midnight)
    assert includes_darkness(KOLA, KOLA_TZ, midnight, sunrise)
    assert not includes_darkness(KOLA, KOLA_TZ, sunrise, sunrise)
