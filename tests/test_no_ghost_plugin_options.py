"""No code may make a RAISING read of a plugin that is not shipped.

Settings.plugin_option raises on a missing key, and a dropped plugin never gets its
defaults written, so one read of it takes down mission generation. The EW jamming
hooks are parked rather than deleted, waiting for the plugin to come back, so they
are allowed -- through plugin_option_or, which answers with a default instead.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The raising form only. plugin_option_or takes a default and cannot fail, which is
#: how parked code keeps its hooks; set_plugin_option only writes.
CALL = re.compile(r"""(?<![_\w])plugin_option\(\s*['"]([^'"]+)['"]""")


def _shipped_plugins() -> set[str]:
    return {p.name for p in (REPO / "resources/plugins").iterdir() if p.is_dir()}


def _sources() -> list[Path]:
    return [path for root in ("game", "qt_ui") for path in (REPO / root).rglob("*.py")]


def test_no_raising_read_of_a_plugin_that_is_not_shipped() -> None:
    shipped = _shipped_plugins()
    ghosts: dict[str, set[str]] = {}
    for path in _sources():
        for match in CALL.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            plugin = match.group(1).split(".")[0]
            if plugin not in shipped:
                ghosts.setdefault(plugin, set()).add(path.relative_to(REPO).as_posix())
    assert not ghosts, f"raising reads of plugins that are not shipped: {ghosts}"


def test_the_check_can_see_a_real_read() -> None:
    """Otherwise a broken pattern would pass by finding nothing at all."""
    found = {
        match.group(1).split(".")[0]
        for path in _sources()
        for match in CALL.finditer(path.read_text(encoding="utf-8", errors="ignore"))
    }
    assert found, "the pattern matched nothing anywhere, so it proves nothing"
