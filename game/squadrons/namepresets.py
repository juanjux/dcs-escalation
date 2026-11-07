"""Ordered pilot-name libraries, shared by the user's campaigns."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
from uuid import uuid4

from game.squadrons.pilot import Pilot

DEFAULTS_PATH = Path("resources/pilot_names.json")
MAX_NAME_LENGTH = 120


def clean_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > MAX_NAME_LENGTH or not name.isprintable():
        raise ValueError(
            f"Names must contain 1–{MAX_NAME_LENGTH} printable characters."
        )
    return name


@dataclass(frozen=True)
class NameCategory:
    id: str
    name: str
    names: tuple[str, ...]

    @classmethod
    def from_data(cls, data: Any) -> NameCategory:
        if not isinstance(data, dict):
            raise ValueError("Invalid name category.")
        if not isinstance(data.get("id"), str) or not data["id"]:
            raise ValueError("A name category needs an identifier.")
        if not isinstance(data.get("name"), str):
            raise ValueError("A name category needs a title.")
        names = data.get("names")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError("Category names must be a list of text entries.")
        return cls(
            data["id"], clean_name(data["name"]), tuple(clean_name(n) for n in names)
        )

    def to_data(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "names": list(self.names)}


def _categories(data: Any) -> dict[str, NameCategory]:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported pilot-name library format.")
    entries = data.get("categories")
    if not isinstance(entries, list):
        raise ValueError("The pilot-name library needs a category list.")
    result: dict[str, NameCategory] = {}
    for entry in entries:
        category = NameCategory.from_data(entry)
        if category.id in result:
            raise ValueError("Duplicate name category identifier.")
        result[category.id] = category
    if len({c.name.casefold() for c in result.values()}) != len(result):
        raise ValueError("Category titles must be unique.")
    return result


class NameLibrary:
    def __init__(self, path: Path, defaults: dict[str, NameCategory]) -> None:
        self.path = path
        self.defaults = defaults
        self.categories = dict(defaults)

    @classmethod
    def load(cls, path: Path, defaults_path: Path = DEFAULTS_PATH) -> NameLibrary:
        defaults = _categories(json.loads(defaults_path.read_text("utf-8")))
        library = cls(path, defaults)
        if path.exists():
            data = json.loads(path.read_text("utf-8"))
            overrides = _categories(data)
            deleted = data.get("deleted_defaults", [])
            if not isinstance(deleted, list) or not all(
                isinstance(k, str) for k in deleted
            ):
                raise ValueError("Invalid removed-category list.")
            for key in deleted:
                library.categories.pop(key, None)
            library.categories.update(overrides)
            titles = [c.name.casefold() for c in library.categories.values()]
            if len(set(titles)) != len(titles):
                raise ValueError("Category titles must be unique.")
        return library

    def put(
        self, category_id: str | None, name: str, names: Iterable[str]
    ) -> NameCategory:
        category = NameCategory(
            category_id or str(uuid4()),
            clean_name(name),
            tuple(clean_name(n) for n in names),
        )
        if any(
            c.id != category.id and c.name.casefold() == category.name.casefold()
            for c in self.categories.values()
        ):
            raise ValueError("A category with that title already exists.")
        self.categories[category.id] = category
        return category

    def save(self) -> None:
        """Write only overrides so later releases can add built-in lists."""
        data = {
            "version": 1,
            "categories": [
                c.to_data()
                for c in self.categories.values()
                if self.defaults.get(c.id) != c
            ],
            "deleted_defaults": [
                key for key in self.defaults if key not in self.categories
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def rename_pilot(pilot: Pilot, name: str) -> None:
    """Keep the same pilot object, including UUID, roster seats and record."""
    pilot.name = clean_name(name)


def autofill(pilots: Iterable[Pilot], names: Iterable[str]) -> int:
    pairs = [(pilot, clean_name(name)) for pilot, name in zip(pilots, names)]
    for pilot, name in pairs:
        pilot.name = name
    return len(pairs)
