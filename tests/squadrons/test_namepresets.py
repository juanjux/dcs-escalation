from __future__ import annotations

import json
from pathlib import Path
import pickle
from unittest.mock import patch

import pytest

from game.squadrons.namepresets import (
    NameCategory,
    NameLibrary,
    autofill,
    clean_name,
    rename_pilot,
)
from game.squadrons.pilot import Pilot, PilotStatus


def test_builtin_categories_are_populated_and_ordered(tmp_path: Path) -> None:
    library = NameLibrary.load(tmp_path / "names.json")
    assert len(library.categories) == 13
    assert all(len(c.names) >= 14 for c in library.categories.values())
    assert library.categories["star-wars"].names[:2] == (
        "Luke Skywalker",
        "Darth Vader",
    )
    assert library.categories["top-gun"].names[0] == 'Pete "Maverick" Mitchell'
    for category in library.categories.values():
        assert len({n.casefold() for n in category.names}) == len(category.names)
    assert not library.path.exists()


def test_custom_categories_unicode_and_priority_survive_reload(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    library = NameLibrary.load(path)
    custom = library.put(
        None, "Colegas Multiplayer", ["Álex", "Zoë", "Commander Éowyn"]
    )
    library.save()
    reloaded = NameLibrary.load(path)
    assert reloaded.categories[custom.id] == custom
    assert list(reloaded.categories)[-1] == custom.id
    assert json.loads(path.read_text("utf-8"))["categories"] == [custom.to_data()]


def test_builtin_edits_and_deletions_persist_without_editing_defaults(
    tmp_path: Path,
) -> None:
    library = NameLibrary.load(tmp_path / "names.json")
    original = library.defaults["star-wars"]
    library.put("star-wars", "My Star Wars", ["Darth Vader", "Luke Skywalker"])
    del library.categories["top-gun"]
    library.save()
    reloaded = NameLibrary.load(library.path)
    assert reloaded.defaults["star-wars"] == original
    assert reloaded.categories["star-wars"].names == ("Darth Vader", "Luke Skywalker")
    assert reloaded.categories["star-wars"].name == "My Star Wars"
    assert "top-gun" not in reloaded.categories


def test_new_defaults_appear_after_upgrade_while_user_edits_are_kept(
    tmp_path: Path,
) -> None:
    library = NameLibrary.load(tmp_path / "names.json")
    library.put("star-wars", "Star Wars", ["Luke", "Vader"])
    library.save()
    defaults = tmp_path / "new-defaults.json"
    data = json.loads(Path("resources/pilot_names.json").read_text("utf-8"))
    data["categories"].append({"id": "new-lore", "name": "New lore", "names": ["Hero"]})
    defaults.write_text(json.dumps(data), "utf-8")
    reloaded = NameLibrary.load(library.path, defaults)
    assert reloaded.categories["new-lore"].names == ("Hero",)
    assert reloaded.categories["star-wars"].names == ("Luke", "Vader")


@pytest.mark.parametrize("value", ["", "  ", "A\nB", "A\x00B", "A" * 121])
def test_invalid_names_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        clean_name(value)


def test_duplicate_category_titles_are_rejected_case_insensitively(
    tmp_path: Path,
) -> None:
    library = NameLibrary.load(tmp_path / "names.json")
    with pytest.raises(ValueError, match="already exists"):
        library.put(None, "  star WARS  ", [])
    assert len(library.categories) == 13


@pytest.mark.parametrize(
    "data", ["not json", "[]", '{"version":2}', '{"version":1,"categories":[{}]}']
)
def test_corrupt_user_library_is_not_overwritten(tmp_path: Path, data: str) -> None:
    path = tmp_path / "names.json"
    path.write_text(data, "utf-8")
    with pytest.raises(ValueError):
        NameLibrary.load(path)
    assert path.read_text("utf-8") == data


def test_atomic_write_failure_preserves_previous_file_and_cleans_temporary(
    tmp_path: Path,
) -> None:
    library = NameLibrary.load(tmp_path / "names.json")
    library.save()
    previous = library.path.read_bytes()
    library.put(None, "Friends", ["Alice"])
    with patch(
        "game.squadrons.namepresets.os.replace", side_effect=OSError("Disk full")
    ):
        with pytest.raises(OSError, match="Disk full"):
            library.save()
    assert library.path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [library.path]


def test_rename_keeps_identity_record_state_and_shared_flight_seats() -> None:
    pilot = Pilot("Old name", player=True, status=PilotStatus.Wounded)
    pilot.record.xp = 700
    pilot.morale = 65
    pilot.wounded_turns = 2
    pilot.friendships[Pilot("Friend").id] = 8
    pilot.aircraft_notes["A-10C_2"] = "My cockpit"
    before = dict(pilot.__dict__)
    record = pilot.record
    seat = [pilot]
    rename_pilot(pilot, "  Luke Skywalker  ")
    assert pilot.name == "Luke Skywalker"
    assert seat[0] is pilot and pilot.record is record
    assert {k: v for k, v in pilot.__dict__.items() if k != "name"} == {
        k: v for k, v in before.items() if k != "name"
    }
    restored = pickle.loads(pickle.dumps([pilot, seat]))
    assert restored[0] is restored[1][0]
    assert restored[0].name == pilot.name and restored[0].id == pilot.id


@pytest.mark.parametrize(
    "count,names,expected",
    [
        (4, ["Luke", "Vader"], ["Luke", "Vader", "Pilot 2", "Pilot 3"]),
        (2, ["Luke", "Vader", "Leia"], ["Luke", "Vader"]),
        (2, [], ["Pilot 0", "Pilot 1"]),
        (0, ["Luke"], []),
    ],
)
def test_autofill_uses_prefix_and_never_cycles_or_creates_pilots(
    count: int, names: list[str], expected: list[str]
) -> None:
    pilots = [Pilot(f"Pilot {i}") for i in range(count)]
    identities = [id(pilot) for pilot in pilots]
    assert autofill(pilots, names) == min(count, len(names))
    assert [p.name for p in pilots] == expected
    assert [id(pilot) for pilot in pilots] == identities


def test_autofill_validates_all_used_names_before_changing_any_pilot() -> None:
    pilots = [Pilot("One"), Pilot("Two")]
    with pytest.raises(ValueError):
        autofill(pilots, ["Luke", ""])
    assert [p.name for p in pilots] == ["One", "Two"]
