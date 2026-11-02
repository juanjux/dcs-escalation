"""F10 objective labels identify the installation as well as its codename."""

from types import SimpleNamespace
from typing import Any
from pathlib import Path
from zipfile import ZipFile

import pytest
from dcs import Point
from dcs.action import MarkToAll
from dcs.mission import Mission
from dcs.terrain import Caucasus

from game.missiongenerator.triggergenerator import TriggerGenerator
from game.theater import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import BuildingGroundObject, NAME_BY_CATEGORY


def generate_markers(
    categories: list[str], owner: Player = Player.RED, enabled: bool = True
) -> Mission:
    terrain = Caucasus()
    cp: Any = SimpleNamespace(captured=owner, ground_objects=[])
    for index, category in enumerate(categories):
        location = PresetLocation("Building", Point(index * 100, 0, terrain))
        objective = BuildingGroundObject(f"BONGO {index}", category, location, cp, None)
        group: Any = SimpleNamespace(
            units=[SimpleNamespace(alive=True, position=location)]
        )
        objective.groups.append(group)
        cp.ground_objects.append(objective)
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(generate_marks=enabled),
        theater=SimpleNamespace(controlpoints=[cp]),
    )
    mission = Mission(terrain)
    TriggerGenerator(mission, game)._gen_markers()
    return mission


def marker_actions(mission: Mission) -> list[MarkToAll]:
    result = []
    for action in mission.triggerrules.triggers[0].actions:
        assert isinstance(action, MarkToAll)
        result.append(action)
    return result


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize(
    ("category", "label"),
    [
        ("ammo", "AMMO DEPOT"),
        ("derrick", "OIL DERRICK"),
        ("oil", "OIL PLATFORM"),
        ("fuel", "FUEL DEPOT"),
        ("factory", "FACTORY"),
        ("power", "POWER PLANT"),
        ("comms", "COMMUNICATIONS TOWER"),
        ("commandcenter", "COMMAND CENTER"),
    ],
)
def test_markers_include_codename_type_and_allegiance(
    category: str, label: str, owner: Player
) -> None:
    mission = generate_markers([category], owner)
    action = marker_actions(mission)[0]
    allegiance = "ALLY" if owner.is_blue else "ENEMY"
    assert str(action.text.id) == f"BONGO 0 - {label} [{allegiance}]"


@pytest.mark.parametrize("category", [*NAME_BY_CATEGORY, "CARRIER", "LHA", "custom"])
def test_every_objective_category_has_a_marker_label(category: str) -> None:
    mission = generate_markers([category])
    action = marker_actions(mission)[0]
    label = str(action.text.id)
    assert label.startswith("BONGO 0 - ")
    assert label.endswith(" [ENEMY]")
    expected = NAME_BY_CATEGORY.get(category, category).upper()
    assert expected in label


def test_marker_positions_ids_and_readonly_state_are_preserved() -> None:
    mission = generate_markers(["ammo", "oil"])
    actions = marker_actions(mission)
    assert [action.value for action in actions] == [10, 11]
    assert all(action.readonly for action in actions)
    zones = list(mission.triggers.zones())
    assert len(zones) == 2
    assert [zone.position.x for zone in zones] == [0, 100]
    assert all(zone.hidden for zone in zones)
    assert [action.zone for action in actions] == [zone.id for zone in zones]


def test_disabled_objective_markers_remain_disabled() -> None:
    mission = generate_markers(["ammo"], enabled=False)
    assert not mission.triggerrules.triggers
    assert not list(mission.triggers.zones())


def test_objective_types_are_written_to_the_miz(tmp_path: Path) -> None:
    mission = generate_markers(["ammo", "derrick", "oil"])
    output = tmp_path / "objective-markers.miz"
    mission.save(str(output))

    with ZipFile(output) as archive:
        text = archive.read("mission").decode("utf-8")
    for index, kind in enumerate(["AMMO DEPOT", "OIL DERRICK", "OIL PLATFORM"]):
        assert f"BONGO {index} - {kind} [ENEMY]" in text
