"""The plain-words description of a unit class."""

from __future__ import annotations

import pytest

from game.data.units import UNIT_CLASS_NOTES, UnitClass


@pytest.mark.parametrize(
    "unit_class", [c for c in UnitClass if c is not UnitClass.UNKNOWN]
)
def test_every_class_says_what_it_is(unit_class: UnitClass) -> None:
    assert unit_class.description


def test_an_unknown_class_says_nothing() -> None:
    assert UnitClass.UNKNOWN.description == ""
    assert UnitClass.UNKNOWN.note == ""


def test_the_description_is_the_job_not_the_model() -> None:
    assert UnitClass.SEARCH_TRACK_RADAR.description == "search & track radar"
    assert UnitClass.COMMAND_POST.description == "command post"
    assert UnitClass.TANK.description == "tank"


def test_only_the_units_a_site_depends_on_carry_a_note() -> None:
    assert UnitClass.POWER.note
    assert UnitClass.COMMAND_POST.note
    assert not UnitClass.TANK.note
    assert not UnitClass.LAUNCHER.note


def test_notes_are_written_for_classes_that_exist() -> None:
    assert set(UNIT_CLASS_NOTES) <= set(UnitClass)
