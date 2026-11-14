from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import TYPE_CHECKING

from faker.providers.person.ja_JP import Provider as JapaneseNames
from text_unidecode import unidecode

if TYPE_CHECKING:
    from game.settings import Settings


def format_pilot_name(name: str, settings: Settings | None) -> str:
    """Render a pilot's name without changing the spelling stored in the roster."""
    if name.isascii() or not getattr(settings, "latin_pilot_names", False):
        return name
    return _romanize(name)


@lru_cache(maxsize=4096)
def _romanize(name: str) -> str:
    words = name.split()
    if len(words) == 2:
        family, given = words
        family_names, given_names = _japanese_readings()
        if family in family_names and given in given_names:
            return f"{family_names[family]} {given_names[given]}"

    parts: list[str] = []
    run: list[str] = []
    for char in name:
        category = unicodedata.category(char)
        if (
            category.startswith("L")
            and not unicodedata.name(char, "").startswith("LATIN ")
        ) or (run and category.startswith("M")):
            run.append(char)
            continue
        if run:
            parts.append(_romanize_run(run))
            run.clear()
        parts.append(char)
    if run:
        parts.append(_romanize_run(run))
    return "".join(parts)


def _romanize_run(run: list[str]) -> str:
    return " ".join(unidecode("".join(run)).replace("[?]", "?").split()) or "?"


@lru_cache(maxsize=1)
def _japanese_readings() -> tuple[dict[str, str], dict[str, str]]:
    # The same Faker provider that generates these names supplies their readings.
    return (
        dict(
            zip(
                JapaneseNames.last_names,
                JapaneseNames.last_romanized_names,
                strict=True,
            )
        ),
        dict(
            zip(
                JapaneseNames.first_names,
                JapaneseNames.first_romanized_names,
                strict=True,
            )
        ),
    )
