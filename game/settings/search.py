"""Finding a setting by typing part of what it is called.

There are two hundred-odd of them across six pages and twenty sections, and the name
a player remembers is rarely the one on the label. The matching itself is
:mod:`game.search.matcher`, shared with everything else that is searched by typing;
what is here is where a setting lives and how to get to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional

from game.search.matcher import (
    SCORE_DETAIL,
    SCORE_KEY,
    SCORE_LABEL,
    SCORE_LABEL_WORD_START,
    SCORE_SUBSEQUENCE,
    SUBSEQUENCE_MINIMUM,
    SUBSEQUENCE_SLACK,
    fold,
    is_subsequence,
    score_all,
    score_one,
    tokens_of,
)

__all__ = [
    "PLUGINS_PAGE",
    "SCORE_DETAIL",
    "SCORE_KEY",
    "SCORE_LABEL",
    "SCORE_LABEL_WORD_START",
    "SCORE_SECTION",
    "SCORE_SUBSEQUENCE",
    "SUBSEQUENCE_MINIMUM",
    "SUBSEQUENCE_SLACK",
    "SettingHit",
    "fold",
    "is_subsequence",
    "score_one",
    "search",
]

#: A section whose name matches is offered as one row, not as every setting inside it:
#: "rank" used to answer with fifteen rows called Cadet, Good and High, which is the
#: section's name showing through each of its members.
SCORE_SECTION = 50


@dataclass(frozen=True)
class SettingHit:
    """One setting a query found, and where the player has to go to reach it."""

    key: str
    label: str
    page: str
    section: str
    subsection: Optional[str]
    score: int
    #: The hit is the section itself rather than a setting in it, so following it
    #: means opening that section and stopping there.
    is_section: bool = False
    #: Set when the hit is a plugin's option rather than a setting of the game's, in
    #: which case reaching it means opening that plugin's gear.
    plugin: Optional[str] = None

    @property
    def where(self) -> str:
        parts = [self.page, self.section]
        if self.subsection:
            parts.append(self.subsection)
        return " › ".join(parts)


def search(query: str, settings: Any = None, limit: int = 40) -> list[SettingHit]:
    """Every setting that matches all of the words typed, best first.

    ``settings`` is only read to skip the options a campaign is not offering right
    now, so a search never sends anyone to a row that is not there.
    """
    from game.settings import Settings

    tokens = tokens_of(query)
    if not tokens:
        return []

    hits: list[SettingHit] = []
    for key, description in Settings.all_fields():
        if (
            settings is not None
            and description.visible_when is not None
            and not description.visible_when(settings)
        ):
            continue
        label = fold(description.text)
        detail = fold(description.detail or "")
        subsection = description.subsection
        folded_key = fold(key)

        total = score_all(tokens, label, detail, folded_key)
        if not total:
            continue
        # A short label matching is a better answer than a long one saying the same
        # thing further in.
        total = total * 100 - len(description.text)
        hits.append(
            SettingHit(
                key=key,
                label=description.text,
                page=description.page,
                section=description.section,
                subsection=subsection,
                score=total,
            )
        )

    hits.extend(_section_hits(tokens))
    hits.extend(_plugin_hits(tokens))
    hits.sort(key=lambda hit: (-hit.score, hit.label))
    return hits[:limit]


def _section_hits(tokens: list[str]) -> Iterator[SettingHit]:
    """One row per section whose name matches, instead of all of its contents."""
    from game.settings import Settings

    for page in Settings.pages():
        for section in Settings.sections(page):
            places = [(section, None)] + [
                (box, box) for box in Settings.subsections(page, section)
            ]
            for name, subsection in places:
                where = fold(f"{page} {section} {subsection or ''}")
                if not all(token in where for token in tokens):
                    continue
                yield SettingHit(
                    key="",
                    label=name,
                    page=page,
                    section=section,
                    subsection=subsection,
                    score=SCORE_SECTION * len(tokens) * 100 - len(name),
                    is_section=True,
                )


#: What the plugin page is called in the dialog's own list.
PLUGINS_PAGE = "Mission Plugins"


def _plugin_hits(tokens: list[str]) -> Iterator[SettingHit]:
    """The options behind the gears, which are options too.

    Splash Damage alone has sixty-five of them, and they are the ones hardest to
    find by clicking: nothing on the page says the word "napalm" until you have
    opened the right plugin.
    """
    from game.plugins import LuaPluginManager

    for plugin in LuaPluginManager.plugins():
        if not plugin.show_in_ui:
            continue
        for option in plugin.options:
            label = fold(option.name)
            key = fold(option.identifier)
            total = score_all(tokens, label, "", key)
            if not total:
                continue
            yield SettingHit(
                key=option.identifier,
                label=option.name,
                page=PLUGINS_PAGE,
                section=plugin.name,
                subsection=None,
                score=total * 100 - len(option.name),
                plugin=plugin.identifier,
            )
