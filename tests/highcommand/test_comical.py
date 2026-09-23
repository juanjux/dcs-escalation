"""The comical lines for the least important objectives."""

from __future__ import annotations

from typing import Any

import pytest
from dcs.mapping import Point

from game.data.units import UnitClass
from game.highcommand.comical import (
    ANY,
    TAGS,
    Jokes,
    comical_lines,
    jokes,
    tags_of,
)
from game.highcommand.objectives import Effort, Objective
from game.theater.controlpoint import OffMapSpawn, Player
from tests.highcommand.stubs import armour, building, unit


def _objective(target: Any) -> Objective:
    return Objective(
        name=target.name,
        kind="",
        targets=(target,),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
    )


def _jokes(
    lines: dict[str, list[str]],
    people: dict[str, list[str]] | None = None,
    deeds: list[str] | None = None,
) -> Jokes:
    return Jokes.parse({"lines": lines, "people": people or {}, "deeds": deeds or []})


def test_the_file_reads_and_every_tag_has_something() -> None:
    found = jokes()

    for line in found.lines:
        assert line.text[-1] in '.!?"', line.text
    for deed in found.deeds:
        assert deed[0].islower() and deed[-1] in '.!?"', deed
    for person in found.people:
        assert person.text[0].isupper() and person.text[-1] not in ".!?", person.text
    covered = {tag for line in found.lines for tag in line.tags} | {
        tag for person in found.people for tag in person.tags
    }
    assert covered == TAGS


def test_unknown_tags_and_placeholders_are_refused() -> None:
    with pytest.raises(ValueError):
        _jokes({"antena": ["It broadcasts reggaeton."]})
    with pytest.raises(ValueError):
        _jokes({ANY: ["The {nmae} crashes our systems."]})
    with pytest.raises(ValueError):
        _jokes({"any, radar": ["It turns anticlockwise."]})


def test_a_line_for_what_the_objective_is_goes_to_nothing_else() -> None:
    found = _jokes({"antenna": ["It plays reggaeton."], "factory": ["No overtime."]})
    tower = _objective(building("FENNEC", "comms", 0, standing=1))
    works = _objective(building("DRAGON", "factory", 0, standing=1))

    for seed in range(10):
        assert comical_lines([tower, works], seed, found) == {
            "FENNEC": "It plays reggaeton.",
            "DRAGON": "No overtime.",
        }


def test_no_line_is_given_twice_while_others_are_left() -> None:
    found = _jokes({ANY: ["One.", "Two.", "Three."]})
    objectives = [
        _objective(building(name, "factory", 0, standing=1)) for name in ("A", "B", "C")
    ]

    assert sorted(comical_lines(objectives, 7, found).values()) == [
        "One.",
        "Three.",
        "Two.",
    ]


def test_a_turn_keeps_its_lines_and_the_next_one_changes_them() -> None:
    objectives = [
        _objective(building(f"SITE{n}", "factory", 0, standing=1)) for n in range(8)
    ]

    first = comical_lines(objectives, 12)

    assert comical_lines(objectives, 12) == first
    assert any(comical_lines(objectives, turn) != first for turn in range(13, 18))


def test_someone_there_did_something() -> None:
    found = _jokes(
        {},
        people={"vehicles": ["One of their drivers"]},
        deeds=["puts ketchup on steak."],
    )
    tanks = _objective(armour("BABOON", 0, [unit("T-72B")]))

    assert comical_lines([tanks], 1, found) == {
        "BABOON": "One of their drivers puts ketchup on steak."
    }


def test_a_line_can_name_the_objective_and_its_base() -> None:
    found = _jokes({ANY: ["The name {name} at {base} crashes our systems."]})
    site = building("GULL", "ammo", 0, standing=1)
    site.control_point.name = "Kutaisi"
    depot = _objective(site)

    assert comical_lines([depot], 1, found) == {
        "GULL": "The name GULL at Kutaisi crashes our systems."
    }


def test_what_an_objective_is_in_tags() -> None:
    field = OffMapSpawn(
        name="Kutaisi",
        position=Point(0, 0, None),  # type: ignore[arg-type]
        theater=None,  # type: ignore[arg-type]
        starts_blue=Player.RED,
    )
    guns = unit("ZU-23", unit_class=UnitClass.AAA, reach_nm=1.5, anti_air=True)

    assert tags_of(_objective(building("FENNEC", "comms", 0, 1))) == {ANY, "antenna"}
    assert tags_of(_objective(building("DOVE", "power", 0, 1))) == {
        ANY,
        "power",
        "business",
    }
    assert tags_of(_objective(armour("BABOON", 0, [unit("T-72B"), guns]))) == {
        ANY,
        "armour",
        "troops",
        "vehicles",
        "air-defence",
    }
    assert tags_of(_objective(field)) == {ANY, "runway", "troops"}
