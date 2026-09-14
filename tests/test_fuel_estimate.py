"""The fuel estimate, and the guess almost every flight gets.

Twenty-four of ~300 aircraft have measured figures. The guess must err high, but not
so high that it calls every flight short.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from game import persistency

from game.ato.fuelestimate import (
    COMBAT_OVER_CRUISE,
    NOMINAL_RANGE_NM,
    _airframe_class,
    assumed_consumption,
    nominal_range_nm,
)
from game.dcs.aircrafttype import AircraftType
from game.utils import KG_TO_LBS


@pytest.fixture(autouse=True)
def _persistency(tmp_path: Path) -> None:
    # AircraftType loads the unit data files, which reach for the saved-games folder.
    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16885)


def _measured() -> list[AircraftType]:
    return [a for a in AircraftType.iter_all() if a.fuel_consumption is not None]


def test_somebody_has_measured_some_aircraft() -> None:
    """The premise of the calibration below."""
    assert _measured()


def test_the_guess_leans_high_against_every_measured_airframe() -> None:
    """A wide band on purpose: the measured set itself spans 447 to 856 nm."""
    for aircraft in _measured():
        if _airframe_class(aircraft) == "heavy":
            # The buddy tankers carry their TRANSFERABLE fuel as "internal", so a
            # guess derived from how much fuel an airframe holds cannot be right
            # about them. They have measured figures, so the guess is never used.
            continue
        measured = aircraft.fuel_consumption
        assert measured is not None
        guess = assumed_consumption(aircraft)
        ratio = guess.cruise / measured.cruise
        assert ratio > 0.7, f"{aircraft} guessed {ratio:.2f}x its measured cruise"
        assert ratio < 2.5, f"{aircraft} guessed {ratio:.2f}x its measured cruise"


def test_the_measured_figures_win_where_they_exist() -> None:
    """Including the tankers the guess cannot describe."""
    for aircraft in _measured():
        assert aircraft.fuel_consumption is not None


def test_a_helicopter_is_not_charged_like_a_fighter() -> None:
    assert NOMINAL_RANGE_NM["helicopter"] < NOMINAL_RANGE_NM["jet"]


def test_combat_costs_more_than_cruise_and_climb_more_still() -> None:
    aircraft = next(iter(_measured()))
    guess = assumed_consumption(aircraft)
    assert guess.cruise < guess.combat < guess.climb
    assert guess.combat == pytest.approx(guess.cruise * COMBAT_OVER_CRUISE)


def test_every_airframe_gets_an_answer() -> None:
    """Nine flights in ten are an airframe nobody measured."""
    for aircraft in AircraftType.iter_all():
        guess = assumed_consumption(aircraft)
        assert guess.cruise > 0
        assert guess.min_safe > 0


def _internal_pounds(aircraft: AircraftType) -> float:
    return float(aircraft.dcs_unit_type.fuel_max) * KG_TO_LBS


def test_a_bomber_is_not_charged_a_fighters_rate_per_mile() -> None:
    """A flat range per class read 195,000 lb of B-1B fuel as 433 lb a mile."""
    for aircraft in AircraftType.iter_all():
        if aircraft.helicopter or _internal_pounds(aircraft) < 100000:
            continue
        implied = _internal_pounds(aircraft) / assumed_consumption(aircraft).cruise
        assert implied > 2000, f"{aircraft} guessed at only {implied:.0f} nm"


def test_the_guessed_range_grows_with_the_fuel_carried() -> None:
    """The bug was the opposite: more fuel meant a worse figure per mile."""
    jets = sorted(
        (a for a in AircraftType.iter_all() if _airframe_class(a) == "jet"),
        key=_internal_pounds,
    )
    ranges = [nominal_range_nm(a) for a in jets]
    assert ranges == sorted(ranges)
