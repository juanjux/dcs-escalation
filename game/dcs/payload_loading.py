"""Resilient drop-in for pydcs' ``FlyingType.load_payloads``.

pydcs parses every payload ``.lua`` that belongs to an aircraft type and aborts
the *whole* type if any single file fails to parse: it only tolerates
``SyntaxError`` per file, so a malformed number (``ValueError: could not convert
string to float: ''``) or any other error propagates and the aircraft ends up
with no selectable payloads at all.

Third-party mods routinely ship hand-written payload files that use Lua locals,
block comments and variable references (e.g. ``["num"] = WTL`` instead of
``["num"] = 1``), which pydcs' minimal Lua reader cannot parse. One such file
then hides every other payload for that airframe -- including the user's own
payloads saved by the DCS Mission Editor, which parse fine.

This installs a replacement that parses each file independently and keeps every
payload it can read, skipping (and logging) only the files that fail. Behaviour
is otherwise identical to pydcs, including the decreasing-preference ordering of
the payload directories.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

logger = logging.getLogger(__name__)

_installed = False


def install_resilient_payload_loading() -> None:
    """Patch ``FlyingType.load_payloads`` to skip unparseable files per-file.

    Idempotent: safe to call more than once. Must run before payloads are first
    loaded (i.e. at startup) so every airframe benefits.
    """
    global _installed
    if _installed:
        return

    from dcs import lua
    from dcs.payloads import PayloadDirectories
    from dcs.unittype import FlyingType

    def load_payloads(cls: Any) -> Dict[str, Any]:
        if FlyingType._UnitPayloadGlobals is None:
            from dcs import task

            FlyingType._UnitPayloadGlobals = {
                v.internal_name: v.id for k, v in task.MainTask.map.items()
            }

        FlyingType.scan_payload_dir()
        if cls.payloads is not None:
            return cls.payloads
        cls.payloads = {}

        from game.payloadlibrary import builtin_changes, edited_builtin

        try:
            changes = builtin_changes(cls.id)
        except Exception:
            logger.warning("Could not read payload library edits", exc_info=True)
            changes = {}

        for payload_dir in PayloadDirectories.payload_dirs():
            if not payload_dir.exists():
                continue
            for payload_path in payload_dir.glob("*.lua"):
                # ``_payload_cache`` maps each file to the unit type it declares;
                # only parse files that belong to this airframe.
                if FlyingType._payload_cache.get(payload_path) != cls.id:
                    continue
                if not payload_path.exists():
                    continue
                try:
                    payload_main = lua.loads(
                        payload_path.read_text(encoding="utf-8-sig"),
                        # The pydcs stub types _UnitPayloadGlobals' keys as str | None;
                        # loads wants dict[str, Any]. Cast (a widening, never redundant).
                        _globals=cast("Dict[str, Any]", FlyingType._UnitPayloadGlobals),
                    )
                    pays = payload_main["unitPayloads"]
                    if pays["unitType"] != cls.id:
                        continue
                    # Directories are iterated in decreasing order of
                    # preference; keep the first occurrence of each name.
                    for load in pays["payloads"].values():
                        if PayloadDirectories.fallback == payload_dir:
                            load = edited_builtin(load, changes)
                            if load is None:
                                continue
                        name = load["name"]
                        if name not in cls.payloads:
                            cls.payloads[name] = load
                except Exception:
                    logger.warning(
                        "Skipping unparseable payload file %s for %s. This is "
                        "usually a hand-written third-party mod payload file "
                        "that pydcs cannot parse; its other payloads are kept.",
                        payload_path,
                        getattr(cls, "id", cls),
                        exc_info=True,
                    )
                    continue
        return cls.payloads

    FlyingType.load_payloads = classmethod(load_payloads)  # type: ignore[method-assign,assignment]
    _installed = True
