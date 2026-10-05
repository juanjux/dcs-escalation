"""Keep mission-side exports and application-side discovery compatible."""

from pathlib import Path
from unittest.mock import patch

import pytest

from game.polldebriefingfilethread import _candidate_state_dirs, _candidate_state_files

SCRIPT = Path(__file__).parents[1] / "resources/plugins/base/dcs_retribution.lua"


def export_path(
    environment: dict[str, str],
    install: str,
    saved: str,
    blocked: list[str],
    sanitized: bool = False,
) -> str | None:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.globals().environment = lua.table_from(environment)
    lua.globals().blocked = lua.table_from(dict.fromkeys(blocked, True))
    lua.globals().install = install
    lua.globals().saved = saved
    lua.execute("""
        logger={info=function() end}
        os={getenv=function(key) return environment[key] end, time=function() return 42 end}
        io={open=function(path)
            if blocked[path] then return nil end
            return {close=function() end}
        end}
        lfs={writedir=function() return saved end}
        dcsRetribution={installPath=install}
    """)
    if sanitized:
        lua.execute("os=nil")
    source = SCRIPT.read_text(encoding="utf-8")
    ends_with = source[
        source.index("local function ends_with") : source.index(
            "local function messageAll"
        )
    ]
    discovery = source[
        source.index("local function canWrite") : source.index(
            "debriefing_file_location = discoverDebriefingFilePath()"
        )
    ]
    return lua.execute(ends_with + discovery + "\nreturn discoverDebriefingFilePath()")


@pytest.mark.parametrize("blocked_count", range(6))
def test_lua_and_python_share_discovery_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocked_count: int
) -> None:
    monkeypatch.chdir(tmp_path)
    environment = {
        "ESCALATION_EXPORT_DIR": str(tmp_path / "new"),
        "RETRIBUTION_EXPORT_DIR": str(tmp_path / "legacy"),
        "TEMP": str(tmp_path / "temp"),
        "TMP": str(tmp_path / "tmp"),
    }
    saved = tmp_path / "saved"
    expected = [
        tmp_path / p for p in ("new", "legacy", ".", "temp", "tmp", "saved/Missions")
    ]
    with patch.dict("os.environ", environment, clear=True), patch(
        "game.persistency.base_path", return_value=saved
    ):
        assert _candidate_state_dirs() == expected
        files = _candidate_state_files()
    blocked = [str(path / "state.json") for path in expected[:blocked_count]]
    selected = export_path(environment, str(tmp_path), str(saved) + "\\", blocked)
    assert selected == str(expected[blocked_count] / "state.json")
    assert Path(selected) in files


@pytest.mark.parametrize("prefix", ["ESCALATION", "RETRIBUTION"])
def test_export_aliases_and_timestamped_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    monkeypatch.chdir(tmp_path)
    export = tmp_path / "export"
    export.mkdir()
    stamped = export / "state-42.json"
    stamped.touch()
    environment = {
        f"{prefix}_EXPORT_DIR": str(export),
        f"{prefix}_EXPORT_STAMPED_STATE": "1",
    }
    selected = export_path(environment, str(tmp_path), str(tmp_path) + "\\", [])
    assert selected == str(stamped)
    with patch.dict("os.environ", environment, clear=True):
        assert stamped in _candidate_state_files()


def test_empty_new_variable_uses_legacy_and_duplicate_paths_are_removed(
    tmp_path: Path,
) -> None:
    environment = {"ESCALATION_EXPORT_DIR": "", "RETRIBUTION_EXPORT_DIR": str(tmp_path)}
    assert export_path(environment, "unused", "unused\\", []) == str(
        tmp_path / "state.json"
    )
    environment["ESCALATION_EXPORT_DIR"] = str(tmp_path)
    with patch.dict("os.environ", environment, clear=True):
        assert _candidate_state_dirs().count(tmp_path) == 1


def test_sanitized_environment_can_use_embedded_install_path(tmp_path: Path) -> None:
    assert export_path({}, str(tmp_path), "unused\\", [], sanitized=True) == str(
        tmp_path / "state.json"
    )


def test_unwritable_locations_return_no_export_path(tmp_path: Path) -> None:
    blocked = [str(tmp_path / "state.json"), str(tmp_path / "Missions" / "state.json")]
    assert export_path({}, str(tmp_path), str(tmp_path) + "\\", blocked) is None


def test_failure_message_uses_current_preferences_location() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Settings > General > Application preferences" in source
    assert "File/Preferences" not in source
    assert "Unable to write DCS Retribution state" not in source
