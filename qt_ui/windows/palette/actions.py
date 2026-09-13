"""The menu bar, as things that can be found by typing.

Walked rather than listed: a menu entry added later is in the palette the moment it is
in the menu, and nothing has to remember to register it.
"""

from __future__ import annotations

from typing import Iterator, Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar

from game.search.index import Entry, Follow
from game.search.providers import ACTION


def clean(text: str) -> str:
    """A menu label without its keyboard mnemonic: "&Save As" is "Save As"."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()


def action_entries(menubar: Optional[QMenuBar]) -> Iterator[Entry]:
    if menubar is None:
        return
    for action in menubar.actions():
        yield from _walk(action, trail=())


def _walk(action: QAction, trail: tuple[str, ...]) -> Iterator[Entry]:
    label = clean(action.text())
    menu: Optional[QMenu] = action.menu()
    if menu is not None:
        for child in menu.actions():
            yield from _walk(child, trail + (label,))
        return

    if action.isSeparator() or not label:
        return

    shortcut = action.shortcut().toString()
    where = " › ".join(trail)
    yield Entry(
        label=label,
        detail=f"{where} · {shortcut}" if shortcut else where,
        follow=Follow(ACTION, _address(action, trail, label)),
        keywords=" ".join([*trail, "menu command", shortcut]),
    )


def _address(action: QAction, trail: tuple[str, ...], label: str) -> str:
    """Where the action is, as a string a Follow can carry back.

    The object's name when it has one, and its place in the menus when it does not:
    most of these are built without names, and a trail is stable enough to find the
    same row again next time the palette opens.
    """
    return action.objectName() or " › ".join([*trail, label])


def action_at(menubar: Optional[QMenuBar], address: str) -> Optional[QAction]:
    """The action a Follow addresses, or None if the menus have changed under it."""
    if menubar is None:
        return None
    for action in menubar.actions():
        found = _find(action, trail=(), address=address)
        if found is not None:
            return found
    return None


def _find(action: QAction, trail: tuple[str, ...], address: str) -> Optional[QAction]:
    label = clean(action.text())
    menu: Optional[QMenu] = action.menu()
    if menu is not None:
        for child in menu.actions():
            found = _find(child, trail + (label,), address)
            if found is not None:
                return found
        return None
    if action.isSeparator() or not label:
        return None
    return action if _address(action, trail, label) == address else None
