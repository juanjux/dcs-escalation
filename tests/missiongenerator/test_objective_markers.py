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
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    NAME_BY_CATEGORY,
    MotorpoolGroundObject,
    SamGroundObject,
    TheaterGroundObject,
    VehicleGroupGroundObject,
)


def generate_markers(
    categories: list[str],
    owner: Player = Player.RED,
    enabled: bool = True,
    unit_states: tuple[bool, ...] = (True,),
    cleared: bool = False,
) -> Mission:
    terrain = Caucasus()
    cp: Any = SimpleNamespace(captured=owner, ground_objects=[])
    for index, category in enumerate(categories):
        location = PresetLocation("Building", Point(index * 100, 0, terrain))
        objective: TheaterGroundObject
        if category == "armor":
            objective = VehicleGroupGroundObject(f"BONGO {index}", location, cp, None)
        elif category == "aa":
            objective = SamGroundObject(f"BONGO {index}", location, cp, None)
        elif category == "motorpool":
            objective = MotorpoolGroundObject(f"BONGO {index}", location, cp, None)
        else:
            objective = BuildingGroundObject(
                f"BONGO {index}", category, location, cp, None
            )
        group: Any = SimpleNamespace(
            units=[
                SimpleNamespace(
                    alive=alive, position=Point(location.x + n * 10, 0, terrain)
                )
                for n, alive in enumerate(unit_states)
            ]
        )
        objective.groups.append(group)
        if cleared:
            objective.clear()
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


@pytest.mark.parametrize("destroyed", [False, True])
def test_objective_types_are_written_to_the_miz(
    tmp_path: Path, destroyed: bool
) -> None:
    mission = generate_markers(["ammo", "derrick", "oil"], unit_states=(not destroyed,))
    output = tmp_path / "objective-markers.miz"
    mission.save(str(output))

    with ZipFile(output) as archive:
        text = archive.read("mission").decode("utf-8")
    for index, kind in enumerate(["AMMO DEPOT", "OIL DERRICK", "OIL PLATFORM"]):
        suffix = " [DESTROYED]" if destroyed else ""
        assert f"BONGO {index} - {kind} [ENEMY]{suffix}" in text


@pytest.mark.parametrize("category", ["ammo", "armor", "aa", "oil"])
@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_fully_destroyed_sites_retain_labels(category: str, owner: Player) -> None:
    mission = generate_markers([category], owner, unit_states=(False, False))
    actions = marker_actions(mission)
    assert actions
    assert all("[DESTROYED]" in str(action.text.id) for action in actions)
    allegiance = "ALLY" if owner.is_blue else "ENEMY"
    assert all(f"[{allegiance}]" in str(action.text.id) for action in actions)


@pytest.mark.parametrize("category", ["ammo", "armor", "aa"])
@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_partial_losses_do_not_label_the_whole_site_destroyed(
    category: str, owner: Player
) -> None:
    mission = generate_markers([category], owner, unit_states=(False, True))
    actions = marker_actions(mission)
    assert actions
    assert all("DESTROYED" not in str(action.text.id) for action in actions)


@pytest.mark.parametrize("category", ["armor", "aa"])
@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("cleared", [False, True])
def test_empty_military_sites_are_reported_as_destroyed(
    category: str, owner: Player, cleared: bool
) -> None:
    mission = generate_markers([category], owner, unit_states=(), cleared=cleared)
    action = marker_actions(mission)[0]
    allegiance = "ALLY" if owner.is_blue else "ENEMY"
    assert str(action.text.id).endswith(f"[{allegiance}] [DESTROYED]")
    assert len(list(mission.triggers.zones())) == 1


@pytest.mark.parametrize("category", ["ammo", "motorpool"])
def test_empty_non_military_sites_are_not_reported_as_destroyed(category: str) -> None:
    mission = generate_markers([category], unit_states=())
    if category == "motorpool":
        assert marker_actions(mission)
    assert all(
        "DESTROYED" not in str(action.text.id) for action in marker_actions(mission)
    )


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_empty_military_site_labels_are_written_to_the_miz(
    tmp_path: Path, owner: Player
) -> None:
    mission = generate_markers(["armor", "aa"], owner, cleared=True)
    output = tmp_path / "empty-sites.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        text = archive.read("mission").decode("utf-8")
    allegiance = "ALLY" if owner.is_blue else "ENEMY"
    assert f"BONGO 0 - RESERVE ARMOR GROUP [{allegiance}] [DESTROYED]" in text
    assert f"BONGO 1 - AA DEFENSE SITE [{allegiance}] [DESTROYED]" in text


def test_destroyed_building_markers_keep_their_actual_positions() -> None:
    mission = generate_markers(["ammo"], unit_states=(False, False))
    assert [zone.position.x for zone in mission.triggers.zones()] == [0, 10]
