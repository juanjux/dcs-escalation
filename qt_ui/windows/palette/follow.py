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
        from qt_ui.windows.palette.actions import action_at

        action = action_at(window.menuBar(), key)
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
            window.open_control_point_info_dialog(cp)
    elif kind == OBJECTIVE:
        tgo = game.db.tgos.get(UUID(key))
        window.open_tgo_info_dialog(tgo)
    elif kind == FLIGHT:
        flight = game.db.flights.get(UUID(key))
        window.on_select_flight(flight)
    elif kind == SQUADRON:
        squadron = _squadron(game, key)
        if squadron is not None:
            _open_squadron(window, squadron)
    elif kind == PILOT:
        # Until the pilot dialog exists, his squadron is the nearest thing to it.
        squadron = _squadron_of_pilot(game, key)
        if squadron is not None:
            _open_squadron(window, squadron)


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


def _squadron_of_pilot(game: Any, key: str) -> Optional[Any]:
    for coalition in game.coalitions:
        for squadron in coalition.air_wing.iter_squadrons():
            for group in (
                getattr(squadron, "active_pilots", ()),
                getattr(squadron, "pilot_pool", ()),
                getattr(squadron, "dead_pilots", ()),
            ):
                for pilot in group:
                    if str(pilot.id) == key:
                        return squadron
    return None


def _open_squadron(window: Any, squadron: Any) -> None:
    from qt_ui.models import SquadronModel
    from qt_ui.windows.SquadronDialog import SquadronDialog

    dialog = SquadronDialog(
        window.game_model.ato_model,
        SquadronModel(squadron),
        window.game_model.game.theater,
        window.game_model.sim_controller,
        window,
    )
    # Held, or Qt collects it the moment this returns.
    window.palette_child_dialogs.append(dialog)
    dialog.show()


def _open_setting(window: Any, key: str) -> None:
    """Open the settings dialog on the page this setting lives on, and flash it.

    The navigation is the dialog's own: go_to knows about pages, about sections
    behind a gear and about the plugins page, and none of that is worth a second
    copy. It takes the hit the settings search produces, so the key is searched for
    exactly to get one.
    """
    from game.settings.search import search
    from qt_ui.windows.settings.QSettingsWindow import QSettingsWindow

    game = window.game_model.game
    if game is None:
        return

    dialog = QSettingsWindow(game)
    window.palette_child_dialogs.append(dialog)
    dialog.show()

    for hit in search(key, game.settings):
        if hit.key == key:
            dialog.go_to(hit)
            return
