"""Doing whatever the chosen entry says to do.

The index is built in ``game`` and has no business opening a dialog, so an entry
carries a pair of strings and this turns the pair back into the thing. Anything it
cannot find -- a flight that was deleted between the search and the Enter, a menu
that has changed shape -- is a no-op rather than a traceback: the palette is a
shortcut, and a shortcut that crashes is worse than one that does nothing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from game.search.index import Follow
from game.search.providers import (
    ACTION,
    BASE,
    FLIGHT,
    OBJECTIVE,
    PILOT,
    SETTING,
    SQUADRON,
)


def follow(window: Any, follow_this: Follow) -> None:
    """Open, trigger or select whatever the entry stands for."""
    try:
        _follow(window, follow_this)
    except Exception:
        logging.exception(f"Could not follow {follow_this}")


def _follow(window: Any, target: Follow) -> None:
    kind, key = target.kind, target.key
    if kind == ACTION:
        from qt_ui.windows.palette.actions import action_at, menu_bar_of

        action = action_at(menu_bar_of(window), key)
        if action is not None:
            action.trigger()
        return

    if kind == SETTING:
        _open_setting(window, key)
        return

    game = window.game_model.game
    if game is None:
        return

    if kind == BASE:
        cp = _control_point(game, key)
        if cp is not None:
            _look_at(cp.position)
            window.open_control_point_info_dialog(cp)
    elif kind == OBJECTIVE:
        tgo = game.db.tgos.get(UUID(key))
        _look_at(tgo.position)
        window.open_tgo_info_dialog(tgo)
    elif kind == FLIGHT:
        flight = game.db.flights.get(UUID(key))
        window.on_select_flight(flight)
    elif kind == SQUADRON:
        squadron = _squadron(game, key)
        if squadron is not None:
            _open_squadron(window, squadron)
    elif kind == PILOT:
        _open_pilot(window, *_pilot_and_squadron(game, key))


def _look_at(position: Any) -> None:
    """Put the map on it as well as opening its dialog, at the zoom the player left
    it at, as the map search does.

    Half of what a player wants from finding a place is to see where it is, and the
    map search on the other side of the window has always done this.
    """
    from game.server import EventStream
    from game.sim import GameUpdateEvents

    EventStream.put_nowait(GameUpdateEvents().look_at(position.latlng()))


def _control_point(game: Any, key: str) -> Optional[Any]:
    for cp in game.theater.controlpoints:
        if str(cp.id) == key:
            return cp
    return None


def _squadron(game: Any, key: str) -> Optional[Any]:
    for coalition in game.coalitions:
        for squadron in coalition.air_wing.iter_squadrons():
            if str(squadron.id) == key:
                return squadron
    return None


def _pilot_and_squadron(game: Any, key: str) -> tuple[Optional[Any], Optional[Any]]:
    """The man the row is about, and whose roster he is on.

    The whole roster, the way the index is built from it: looking only at the men fit
    to fly this minute found no one who was wounded, on leave or gone, so those rows
    were in the palette and did nothing when chosen.
    """
    for coalition in game.coalitions:
        for squadron in coalition.air_wing.iter_squadrons():
            for group in (
                getattr(squadron, "current_roster", ()),
                getattr(squadron, "pilot_pool", ()),
            ):
                for pilot in group:
                    if str(pilot.id) == key:
                        return pilot, squadron
    return None, None


def _open_pilot(window: Any, pilot: Optional[Any], squadron: Optional[Any]) -> None:
    """His own dialog, and his squadron's when the window has none to offer.

    Asked of the window rather than imported: the pilot dialog is a separate change,
    and until it is in the same tree the nearest thing to a man's record is the roster
    he is on.
    """
    if pilot is None:
        return
    opens_pilots = getattr(window, "open_pilot_dialog", None)
    if opens_pilots is not None:
        opens_pilots(pilot)
    elif squadron is not None:
        _open_squadron(window, squadron)


def _open_squadron(window: Any, squadron: Any) -> None:
    """His squadron's roster, the same window the pilot dialog and the Air Wing open."""
    from qt_ui.dialogs import Dialog

    Dialog.open_squadron_dialog(squadron, window)


def _open_setting(window: Any, key: str) -> None:
    """Open the settings dialog on the page this setting lives on, and flash it.

    The navigation is the dialog's own: go_to knows about pages, about sections
    behind a gear and about the plugins page, and none of that is worth a second copy.
    What it needs is the settings dialog's own description of the option, which is
    looked up rather than searched for -- searching for an option by its own key finds
    nothing at all for every Skynet option and a third of Splash Damage's.
    """
    from game.search.providers import setting_hit
    from qt_ui.windows.settings.QSettingsWindow import QSettingsWindow

    game = window.game_model.game
    if game is None:
        return

    dialog = QSettingsWindow(game)
    window.palette_child_dialogs.append(dialog)
    dialog.show()

    hit = setting_hit(game.settings, key)
    if hit is not None:
        # On the widget inside the window, not on the window: QSettingsWindow is a
        # dialog wrapped round a QSettingsWidget, and that is where the pages, the
        # index and go_to all live.
        dialog.settings_widget.go_to(hit)
