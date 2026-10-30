"""Read estimated layer bounds from the installed cloud preset, without executing Lua."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from dcs import lua

from game.weather.clouds import Clouds


@dataclass(frozen=True)
class CloudLayer:
    base: int
    top: int


def _table(text: str, start: int) -> str | None:
    """Extract a balanced Lua table, ignoring quoted strings and comments."""
    tokens = re.finditer(
        r"--\[\[.*?\]\]|--[^\n]*|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|[{}]",
        text[start:],
        re.S,
    )
    depth = 0
    for token in tokens:
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return text[start : start + token.end()]
    return None


def _name(text: str) -> str:
    return re.sub(r"\s*\[ED\]$", "", text).strip()


@lru_cache(maxsize=8)
def _read(
    path: Path, modified: int, size: int, name: str, ui_name: str
) -> tuple[CloudLayer, ...]:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(r"^\s*" + re.escape(name) + r"\s*=\s*(\{)", text, re.M)
    if match is None:
        return ()
    preset = _table(text, match.start(1))
    if preset is None:
        return ()
    native_name = re.search(r"readableNameShort\s*=\s*_?\(?\s*['\"]([^'\"]+)", preset)
    # Preset identifiers are reused by different packs. Never mix their geometry.
    if native_name is None or _name(native_name[1]) != _name(ui_name):
        return ()
    layers = re.search(r"\blayers\s*=\s*(\{)", preset)
    if layers is None:
        return ()
    table = _table(preset, layers.start(1))
    if table is None:
        return ()
    # pydcs's data-only parser expects bracketed keys inside tables.
    table = re.sub(r"\b([A-Za-z_]\w*)\s*=", r'["\1"] =', table)
    decoded = lua.loads("layers = " + table)["layers"]
    entries = list(decoded.values()) if isinstance(decoded, dict) else list(decoded)
    result = []
    for entry in entries:
        if entry["density"] > 0 and entry["coverage"] > 0:
            base, top = entry["altitudeMin"], entry["altitudeMax"]
            if top <= base:
                return ()
            result.append(CloudLayer(round(base), round(top)))
    return tuple(result)


def estimated_layers(clouds: Clouds, install: Path) -> list[CloudLayer]:
    """Translate preset geometry to the selected base, as an explicitly labelled estimate.

    DCS's editor defaults its base to the first layer's altitudeMin. Native rendering
    and local cloud edges are not exported by the mission, so these are not measured
    cloud boundaries. Missing or mismatched installations provide no estimate.
    """
    if clouds.preset is None:
        return []
    path = install / "Config" / "Effects" / "clouds.lua"
    try:
        stat = path.stat()
        if stat.st_size > 4_000_000:
            return []
        layers = _read(
            path,
            stat.st_mtime_ns,
            stat.st_size,
            clouds.preset.name,
            clouds.preset.ui_name,
        )
        if not layers:
            return []
        offset = clouds.base - layers[0].base
        return [CloudLayer(layer.base + offset, layer.top + offset) for layer in layers]
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        SyntaxError,
    ):
        return []
