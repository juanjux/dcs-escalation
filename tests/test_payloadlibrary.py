"""Library mutations preserve native payload metadata and loader precedence."""

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dcs import lua
from dcs.payloads import PayloadDirectories
from dcs.unittype import FlyingType

from game import payloadlibrary
from game.ato import loadouts
from game.dcs.payload_loading import install_resilient_payload_loading
from game.payloadlibrary import PayloadLibrary


def document(path: Path, aircraft: str, payloads: dict[int, Any]) -> None:
    path.write_text(
        "local unitPayloads = "
        + lua.dumps(
            {
                "name": "Library",
                "unitType": aircraft,
                "payloads": payloads,
                "extra": "preserve",
            }
        )
        + "\nreturn unitPayloads",
        encoding="utf-8",
    )


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    class LibraryPlane(FlyingType):
        id = "LibraryPlane"
        payloads = None

    custom = tmp_path / "custom"
    builtin = tmp_path / "builtin"
    custom.mkdir()
    builtin.mkdir()
    monkeypatch.setattr(payloadlibrary, "payloads_dir", lambda: custom)
    monkeypatch.setattr(loadouts, "payloads_dir", lambda: custom)
    monkeypatch.setattr(PayloadDirectories, "preferred", custom)
    monkeypatch.setattr(PayloadDirectories, "_user", custom)
    monkeypatch.setattr(PayloadDirectories, "fallback", builtin)
    monkeypatch.setattr(PayloadDirectories, "_dcs", [])
    monkeypatch.setattr(PayloadDirectories, "_mod", [])
    monkeypatch.setattr(FlyingType, "_payload_cache", {})
    raw = {
        "name": "Escalation CAS",
        "displayName": "Escalation CAS",
        "pylons": {
            4: {
                "num": 2,
                "CLSID": "unknown-mod-store",
                "settings": {1: {"laser": 1688}, "fuze": 12},
            }
        },
        "tasks": {3: 31, 7: 17},
        "ammo_type": 3,
        "custom_field": {9: "keep"},
    }
    document(builtin / "LibraryPlane.lua", LibraryPlane.id, {4: raw})
    install_resilient_payload_loading()
    return SimpleNamespace(
        lib=PayloadLibrary(),
        plane=LibraryPlane,
        custom=custom,
        builtin=builtin,
        raw=raw,
    )


def entry(
    library: Any, source: str = "Escalation", name: str = "Escalation CAS"
) -> Any:
    return next(
        e
        for e in library.lib.entries(library.plane.id)
        if e.source == source and e.name == name
    )


def test_builtin_edit_is_persistent_preserves_metadata_and_leaves_installation_untouched(
    library: Any,
) -> None:
    original = (library.builtin / "LibraryPlane.lua").read_bytes()
    raw = copy.deepcopy(library.raw)
    raw["ammo_type"] = 2
    library.lib.save(library.plane, raw, entry(library))
    assert (library.builtin / "LibraryPlane.lua").read_bytes() == original
    assert entry(library).payload == raw
    assert library.plane.load_payloads()[raw["name"]] == raw
    library.plane.payloads = None
    assert library.plane.load_payloads()[raw["name"]]["pylons"][4]["settings"][1] == {
        "laser": 1688
    }


def test_delete_builtin_stays_deleted_after_cache_reload_and_can_be_restored(
    library: Any,
) -> None:
    library.lib.delete(library.plane, entry(library))
    assert not library.lib.entries(library.plane.id)
    assert not library.plane.load_payloads()
    library.plane.payloads = None
    assert not library.plane.load_payloads()
    library.lib.restore_builtins(library.plane)
    assert library.plane.load_payloads()["Escalation CAS"] == library.raw


def test_builtin_rename_replaces_old_name_and_updates_default(library: Any) -> None:
    loadouts.set_default_loadout_override(
        library.plane.id, loadouts.FlightType.CAS, "Escalation CAS"
    )
    raw = copy.deepcopy(library.raw)
    raw["name"] = "Renamed"
    library.lib.save(library.plane, raw, entry(library))
    assert set(library.plane.load_payloads()) == {"Renamed"}
    assert (
        loadouts.get_default_loadout_override(library.plane.id, loadouts.FlightType.CAS)
        == "Renamed"
    )


def test_create_custom_update_delete_preserves_other_entries_and_backups(
    library: Any,
) -> None:
    path = library.custom / "LibraryPlane.lua"
    document(
        path, library.plane.id, {2: library.raw, 9: {**library.raw, "name": "Other"}}
    )
    raw = {**copy.deepcopy(library.raw), "name": "Custom new"}
    library.lib.save(library.plane, raw)
    assert set(payloadlibrary._read(path)["payloads"]) == {2, 9, 10}
    assert payloadlibrary._read(path)["extra"] == "preserve"
    custom = entry(library, "Custom", "Custom new")
    raw["ammo_type"] = 1
    library.lib.save(library.plane, raw, custom)
    assert library.plane.load_payloads()["Custom new"]["ammo_type"] == 1
    library.lib.delete(library.plane, entry(library, "Custom", "Custom new"))
    assert set(payloadlibrary._read(path)["payloads"]) == {2, 9}
    assert "Custom new" not in library.plane.load_payloads()
    assert path.with_suffix(".lua.bak").exists()


def test_custom_precedence_is_retained_when_editing_or_deleting_builtin(
    library: Any,
) -> None:
    custom = {**copy.deepcopy(library.raw), "ammo_type": 1}
    document(library.custom / "LibraryPlane.lua", library.plane.id, {1: custom})
    library.lib.save(library.plane, {**library.raw, "ammo_type": 2}, entry(library))
    assert library.plane.load_payloads()["Escalation CAS"]["ammo_type"] == 1
    library.lib.delete(library.plane, entry(library))
    assert library.plane.load_payloads()["Escalation CAS"]["ammo_type"] == 1


def test_edit_noncanonical_custom_file_and_duplicate_names_are_safe(
    library: Any,
) -> None:
    path = library.custom / "Alternate.lua"
    document(path, library.plane.id, {8: {**library.raw, "name": "Alt"}})
    library.lib.save(
        library.plane,
        {**library.raw, "name": "New alt"},
        entry(library, "Custom", "Alt"),
    )
    assert payloadlibrary._read(path)["payloads"][8]["name"] == "New alt"
    with pytest.raises(ValueError, match="already exists"):
        library.lib.save(library.plane, {**library.raw, "name": "New alt"})


def test_malformed_custom_file_is_not_overwritten(library: Any) -> None:
    path = library.custom / "LibraryPlane.lua"
    path.write_text("not a Lua payload!", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(Exception):
        library.lib.save(library.plane, library.raw)
    assert path.read_bytes() == before


def test_write_failure_keeps_file_and_cached_payloads_unchanged(
    library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    library.lib.save(library.plane, library.raw)
    cached = copy.deepcopy(library.plane.load_payloads())
    path = library.custom / "LibraryPlane.lua"
    before = path.read_bytes()

    def fail(*args: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(payloadlibrary, "atomic_write", fail)
    with pytest.raises(OSError):
        library.lib.save(
            library.plane, {**library.raw, "ammo_type": 1}, entry(library, "Custom")
        )
    assert path.read_bytes() == before
    assert library.plane.load_payloads() == cached


def test_stale_entry_is_rejected_without_overwriting_external_change(
    library: Any,
) -> None:
    path = library.custom / "LibraryPlane.lua"
    document(path, library.plane.id, {1: library.raw})
    old = entry(library, "Custom")
    document(path, library.plane.id, {1: {**library.raw, "name": "Externally changed"}})
    with pytest.raises(ValueError, match="changed on disk"):
        library.lib.save(library.plane, library.raw, old)
    assert payloadlibrary._read(path)["payloads"][1]["name"] == "Externally changed"


def test_delete_default_removes_dangling_reference(library: Any) -> None:
    loadouts.set_default_loadout_override(
        library.plane.id, loadouts.FlightType.CAS, "Escalation CAS"
    )
    library.lib.delete(library.plane, entry(library))
    assert (
        loadouts.get_default_loadout_override(library.plane.id, loadouts.FlightType.CAS)
        is None
    )


def test_broken_payload_for_other_aircraft_is_not_reported(library: Any) -> None:
    (library.builtin / "Other.lua").write_text(
        'local unitPayloads = {["unitType"] = "OtherPlane", broken!', encoding="utf-8"
    )
    assert library.lib.entries(library.plane.id)
    assert library.lib.errors == []
    assert library.lib.entries("OtherPlane") == []
    assert len(library.lib.errors) == 1


def test_same_name_external_edit_is_not_overwritten(library: Any) -> None:
    path = library.custom / "LibraryPlane.lua"
    document(path, library.plane.id, {1: library.raw})
    old = entry(library, "Custom")
    external = {**library.raw, "ammo_type": 2}
    document(path, library.plane.id, {1: external})
    with pytest.raises(ValueError, match="changed on disk"):
        library.lib.save(library.plane, library.raw, old)
    assert payloadlibrary._read(path)["payloads"][1] == external


def test_unicode_custom_name_loads_from_native_file(library: Any) -> None:
    name = "Ataque — precisión"
    library.lib.save(library.plane, {**library.raw, "name": name})
    assert library.plane.load_payloads()[name]["name"] == name
