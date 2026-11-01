"""Persistent payload editing without modifying the installed preset files."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import tempfile
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dcs import lua, task
from dcs.payloads import PayloadDirectories
from dcs.unittype import FlyingType

from game.persistency import payloads_dir

STATE_FILE = "escalation_payload_library.json"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return copy.deepcopy(_parse(path, stat.st_mtime_ns, stat.st_size))


@lru_cache(maxsize=2048)
def _parse(path: Path, modified: int, size: int) -> dict[str, Any]:
    globals_ = {str(v.internal_name): v.id for v in task.MainTask.map.values()}
    document = lua.loads(path.read_text(encoding="utf-8-sig"), _globals=globals_)[
        "unitPayloads"
    ]
    if not isinstance(document, dict) or not isinstance(document.get("payloads"), dict):
        raise ValueError(f"Invalid payload document: {path}")
    return document


@lru_cache(maxsize=2048)
def _declared_aircraft(path: Path, modified: int, size: int) -> str | None:
    # Check the header before parsing: a broken preset for an unrelated mod
    # must not produce an error for every aircraft in the editor.
    match = re.search(
        r'\["unitType"\]\s*=\s*"([^"\n]+)"', path.read_text(encoding="utf-8-sig")
    )
    return match.group(1) if match else None


def _state() -> dict[str, Any]:
    path = payloads_dir() / STATE_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid payload library state: {path}")
    for changes in data.values():
        if (
            not isinstance(changes, dict)
            or not isinstance(changes.get("overrides", {}), dict)
            or not isinstance(changes.get("deleted", []), list)
        ):
            raise ValueError(f"Invalid payload library state: {path}")
    return data


def builtin_changes(aircraft_id: str) -> dict[str, Any]:
    return _state().get(aircraft_id, {})


def edited_builtin(
    payload: dict[str, Any], changes: dict[str, Any]
) -> dict[str, Any] | None:
    name = payload["name"]
    if name in changes.get("deleted", []):
        return None
    replacement = changes.get("overrides", {}).get(name)
    if replacement is None:
        return payload
    # Lua preserves numeric table keys in nested settings, unlike JSON objects.
    return lua.loads("payload = " + replacement)["payload"]


@dataclass
class PayloadEntry:
    source: Literal["Escalation", "Custom"]
    path: Path
    key: Any
    original_name: str
    payload: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.payload["name"])


class PayloadLibrary:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def entries(self, aircraft_id: str) -> list[PayloadEntry]:
        self.errors = []
        entries = []
        custom = payloads_dir()
        folders = [("Custom", custom), ("Escalation", PayloadDirectories.fallback)]
        changes = builtin_changes(aircraft_id)
        # The same built-in name can occur in more than one installed file.
        seen_builtin: set[str] = set()
        for source, folder in folders:
            if folder is None:
                continue
            for path in sorted(folder.glob("*.lua")):
                try:
                    stat = path.stat()
                    declared = _declared_aircraft(path, stat.st_mtime_ns, stat.st_size)
                    if declared is not None and declared != aircraft_id:
                        continue
                    document = _read(path)
                    if document.get("unitType") != aircraft_id:
                        continue
                    for key, raw in document["payloads"].items():
                        if not isinstance(raw, dict) or not isinstance(
                            raw.get("name"), str
                        ):
                            raise ValueError(f"Invalid payload entry in {path}")
                        if source == "Escalation":
                            if raw["name"] in seen_builtin:
                                continue
                            seen_builtin.add(raw["name"])
                            payload = edited_builtin(raw, changes)
                        else:
                            payload = raw
                        if payload is not None:
                            entries.append(
                                PayloadEntry(
                                    "Custom" if source == "Custom" else "Escalation",
                                    path,
                                    key,
                                    raw["name"],
                                    copy.deepcopy(payload),
                                )
                            )
                except Exception as error:
                    self.errors.append(f"{path.name}: {error}")
                    logging.warning(
                        "Could not read payload file %s", path, exc_info=True
                    )
        return sorted(entries, key=lambda e: (e.source, e.name.casefold(), str(e.path)))

    @staticmethod
    def _write(path: Path, text: str) -> None:
        if path.exists():
            # Keep the previous file recoverable, including user-created metadata.
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        atomic_write(path, text)

    @staticmethod
    def _invalidate(aircraft: type[FlyingType]) -> None:
        aircraft.payloads = None
        if FlyingType._payload_cache is not None:
            FlyingType._payload_cache.clear()

    def _save_state(self, aircraft: type[FlyingType], changes: dict[str, Any]) -> None:
        data = _state()
        data[aircraft.id] = changes
        self._write(payloads_dir() / STATE_FILE, json.dumps(data, indent=2))
        self._invalidate(aircraft)

    @staticmethod
    def _document(entry: PayloadEntry, aircraft_id: str) -> dict[str, Any]:
        root = payloads_dir().resolve()
        if entry.path.resolve().parent != root:
            raise ValueError("Custom payload is outside the user payload directory")
        document = _read(entry.path)
        if document.get("unitType") != aircraft_id:
            raise ValueError("The payload file now belongs to another aircraft")
        raw = document["payloads"].get(entry.key)
        if not raw or raw.get("name") != entry.original_name or raw != entry.payload:
            raise ValueError("The payload changed on disk. Reopen it before saving.")
        return document

    def save(
        self,
        aircraft: type[FlyingType],
        payload: dict[str, Any],
        entry: PayloadEntry | None = None,
    ) -> None:
        payload = copy.deepcopy(payload)
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Enter a payload name")
        payload["name"] = name
        payload["displayName"] = name
        source = entry.source if entry else "Custom"
        for other in self.entries(aircraft.id):
            if (
                other.source == source
                and other.name == name
                and (
                    entry is None or (other.path, other.key) != (entry.path, entry.key)
                )
            ):
                raise ValueError(f'A {source} payload named "{name}" already exists')
        if source == "Escalation" and entry is not None:
            changes = copy.deepcopy(builtin_changes(aircraft.id))
            changes.setdefault("overrides", {})[entry.original_name] = lua.dumps(
                payload
            )
            changes["deleted"] = [
                n for n in changes.get("deleted", []) if n != entry.original_name
            ]
            self._save_state(aircraft, changes)
        else:
            if entry is not None:
                path = entry.path
                document = self._document(entry, aircraft.id)
                key = entry.key
            else:
                path = payloads_dir() / f"{aircraft.id}.lua"
                if path.resolve().parent != payloads_dir().resolve():
                    raise ValueError("Invalid aircraft payload filename")
                document = (
                    _read(path)
                    if path.exists()
                    else {"unitType": aircraft.id, "name": aircraft.id, "payloads": {}}
                )
                if document.get("unitType") != aircraft.id:
                    raise ValueError("The payload file belongs to another aircraft")
                key = (
                    max(
                        (k for k in document["payloads"] if isinstance(k, int)),
                        default=0,
                    )
                    + 1
                )
            document["payloads"][key] = payload
            self._write(
                path,
                "local unitPayloads = "
                + lua.dumps(document)
                + "\nreturn unitPayloads\n",
            )
            self._invalidate(aircraft)
        if entry is not None and entry.name != name:
            self._update_defaults(aircraft, entry.name, name)

    def delete(self, aircraft: type[FlyingType], entry: PayloadEntry) -> None:
        if entry.source == "Escalation":
            changes = copy.deepcopy(builtin_changes(aircraft.id))
            changes["deleted"] = sorted(
                set(changes.get("deleted", [])) | {entry.original_name}
            )
            changes.setdefault("overrides", {}).pop(entry.original_name, None)
            self._save_state(aircraft, changes)
        else:
            document = self._document(entry, aircraft.id)
            del document["payloads"][entry.key]
            self._write(
                entry.path,
                "local unitPayloads = "
                + lua.dumps(document)
                + "\nreturn unitPayloads\n",
            )
            self._invalidate(aircraft)
        self._update_defaults(aircraft, entry.name, None)

    def restore_builtins(self, aircraft: type[FlyingType]) -> None:
        self._save_state(aircraft, {})

    @staticmethod
    def _update_defaults(aircraft: type[FlyingType], old: str, new: str | None) -> None:
        from game.ato.loadouts import (
            _write_default_loadout_overrides,
            load_default_loadout_overrides,
        )

        try:
            if old in aircraft.load_payloads():
                return  # Another source still supplies this named preset.
            defaults = load_default_loadout_overrides()
            for role, name in list(defaults.get(aircraft.id, {}).items()):
                if name == old:
                    if new is None:
                        del defaults[aircraft.id][role]
                    else:
                        defaults[aircraft.id][role] = new
            _write_default_loadout_overrides(defaults)
        except Exception:
            logging.exception("Could not update payload default references")
