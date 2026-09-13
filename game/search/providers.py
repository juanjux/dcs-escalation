"""Where the findable things come from.

One provider per kind. Each yields entries and knows nothing about how they are shown
or what happens when one is chosen -- that is the ``Follow`` pair, resolved by the
user interface.

Keywords are the point of several of these. An objective is called MINK and holds a
Patriot; a player looking for the Patriot does not know it is called MINK, which is
the whole reason the map search indexes what is parked inside a site as well as its
name. The same trick is worth having here for squadrons and flights.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional

from game.search.index import Entry, Follow

#: Kinds, so the rows can be chipped and the Follow resolved. Strings rather than an
#: enum: they cross into the user interface and into a QSettings history, and a
#: renamed enum member is a broken history.
ACTION = "action"
SETTING = "setting"
BASE = "base"
OBJECTIVE = "objective"
SQUADRON = "squadron"
PILOT = "pilot"
FLIGHT = "flight"

#: Said on every pilot row until the pilot dialog exists.
PILOT_NOTE = "opens the squadron for now"


def entries_for(game: Optional[Any]) -> Iterator[Entry]:
    """Everything there is to find. Settings exist without a campaign; nothing else."""
    yield from settings_entries(game)
    if game is None:
        return
    yield from base_entries(game)
    yield from objective_entries(game)
    yield from squadron_entries(game)
    yield from pilot_entries(game)
    yield from flight_entries(game)


# -- settings ---------------------------------------------------------------------


def settings_entries(game: Optional[Any]) -> Iterator[Entry]:
    """Every setting, and every section, as the settings dialog's own search finds them.

    Reached through that search rather than through Settings directly: it already
    knows which options a campaign is not offering, and which of them live behind a
    plugin's gear.
    """
    settings = getattr(game, "settings", None) if game is not None else None
    for hit in _all_settings(settings):
        yield Entry(
            label=hit.label,
            detail=hit.where,
            follow=Follow(SETTING, hit.key),
            keywords=f"{hit.page} {hit.section} {hit.subsection or ''}",
            key=hit.key,
        )


def _all_settings(settings: Optional[Any]) -> Iterable[Any]:
    """Every setting there is, as SettingHits, without searching for anything.

    The dialog's search answers a query; the palette wants the population, so this
    walks the same sources and builds the same hit for each.
    """
    from game.plugins import LuaPluginManager
    from game.settings import Settings
    from game.settings.search import PLUGINS_PAGE, SettingHit

    for key, description in Settings.all_fields():
        if (
            settings is not None
            and description.visible_when is not None
            and not description.visible_when(settings)
        ):
            continue
        yield SettingHit(
            key=key,
            label=description.text,
            page=description.page,
            section=description.section,
            subsection=description.subsection,
            score=0,
        )

    for plugin in LuaPluginManager.plugins():
        if not plugin.show_in_ui:
            continue
        for option in plugin.options:
            yield SettingHit(
                key=option.identifier,
                label=option.name,
                page=PLUGINS_PAGE,
                section=plugin.name,
                subsection=None,
                score=0,
                plugin=plugin.identifier,
            )


# -- the theatre ------------------------------------------------------------------


def base_entries(game: Any) -> Iterator[Entry]:
    for cp in game.theater.controlpoints:
        owner = "blue" if cp.captured.is_blue else "red"
        yield Entry(
            label=cp.name,
            detail=f"{_kind_of(cp)} · {owner}",
            follow=Follow(BASE, str(cp.id)),
            keywords=f"base airfield {owner} {_kind_of(cp)}",
        )


def _kind_of(cp: Any) -> str:
    """The same words the base menu's header puts on its chip."""
    try:
        from qt_ui.windows.basemenu.header import kind_of

        return kind_of(cp).title()
    except Exception:
        # game must not depend on qt_ui; this is a nicety, not a requirement.
        return "Base"


def objective_entries(game: Any) -> Iterator[Entry]:
    """Every objective, findable by its code name or by what is standing in it."""
    seen: set[int] = set()
    for cp in game.theater.controlpoints:
        for tgo in cp.connected_objectives:
            if id(tgo) in seen:
                continue
            seen.add(id(tgo))
            owner = "blue" if tgo.control_point.captured.is_blue else "red"
            state = "destroyed" if tgo.is_dead else ""
            yield Entry(
                label=tgo.obj_name,
                detail=f"{str(tgo)} · {tgo.control_point.name} · {owner}",
                follow=Follow(OBJECTIVE, str(tgo.id)),
                keywords=" ".join(
                    [tgo.category, owner, state, *_units_in(tgo)],
                ),
            )


def _units_in(tgo: Any) -> Iterator[str]:
    """What is standing in it, so "patriot" finds the site that holds one."""
    named: set[str] = set()
    for unit in tgo.units:
        unit_type = getattr(unit, "unit_type", None)
        name = getattr(unit_type, "display_name", None)
        if name and name not in named:
            named.add(name)
            yield name


# -- the air wing -----------------------------------------------------------------


def squadron_entries(game: Any) -> Iterator[Entry]:
    for coalition in game.coalitions:
        owner = "blue" if coalition.player else "red"
        for squadron in coalition.air_wing.iter_squadrons():
            yield Entry(
                label=str(squadron),
                detail=(
                    f"{squadron.aircraft.display_name} · {squadron.location.name}"
                    f" · {squadron.owned_aircraft} aircraft"
                ),
                follow=Follow(SQUADRON, str(squadron.id)),
                keywords=" ".join(
                    [
                        "squadron",
                        owner,
                        squadron.aircraft.display_name,
                        squadron.location.name,
                        str(squadron.primary_task.value),
                        squadron.nickname or "",
                    ]
                ),
            )


def pilot_entries(game: Any) -> Iterator[Entry]:
    """Every pilot a squadron has, living or not.

    The dead are worth finding: half of what a player wants a pilot's name for is to
    read what happened to him.
    """
    for coalition in game.coalitions:
        owner = "blue" if coalition.player else "red"
        for squadron in coalition.air_wing.iter_squadrons():
            for pilot in _pilots_of(squadron):
                # None while Live Pilots is off, when everyone is just a name.
                rank = squadron.pilot_rank(pilot)
                abbreviation = rank.abbreviation if rank is not None else ""
                yield Entry(
                    label=f"{abbreviation} {pilot.name}".strip(),
                    detail=f"{squadron} · {pilot.status.value}",
                    follow=Follow(PILOT, str(pilot.id)),
                    keywords=" ".join(
                        [
                            "pilot",
                            owner,
                            abbreviation,
                            rank.name if rank is not None else "",
                            squadron.aircraft.display_name,
                            str(squadron),
                        ]
                    ),
                    note=PILOT_NOTE,
                )


def _pilots_of(squadron: Any) -> Iterator[Any]:
    seen: set[int] = set()
    for group in (
        getattr(squadron, "active_pilots", ()),
        getattr(squadron, "pilot_pool", ()),
        getattr(squadron, "dead_pilots", ()),
    ):
        for pilot in group:
            if id(pilot) not in seen:
                seen.add(id(pilot))
                yield pilot


def flight_entries(game: Any) -> Iterator[Entry]:
    """What is fragged this turn. Gone next turn, which is why the index is rebuilt."""
    for coalition in game.coalitions:
        owner = "blue" if coalition.player else "red"
        for package in coalition.ato.packages:
            for flight in package.flights:
                # Most flights have no name of their own; what identifies those is
                # what they are doing and what they are doing it in.
                named = flight.custom_name or flight.unit_type.display_name
                yield Entry(
                    label=f"{flight.flight_type.value} · {named}",
                    detail=(
                        f"{flight.count}x {flight.unit_type.display_name}"
                        f" · {flight.departure.name} → {package.target.name}"
                    ),
                    follow=Follow(FLIGHT, str(flight.id)),
                    keywords=" ".join(
                        [
                            "flight package mission",
                            owner,
                            flight.unit_type.display_name,
                            flight.departure.name,
                            package.target.name,
                        ]
                    ),
                )
