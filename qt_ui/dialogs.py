"""Application-wide dialog management."""

from typing import Any, Callable, Optional, TypeVar

import shiboken6
from PySide6.QtWidgets import QWidget

from game.ato.flight import Flight
from game.theater.missiontarget import MissionTarget
from .models import GameModel, PackageModel
from .windows.mission.QEditFlightDialog import QEditFlightDialog
from .windows.mission.QPackageDialog import (
    QEditPackageDialog,
    QNewPackageDialog,
)

#: Every window that is about one particular thing, by what it is about. A package,
#: a flight, a pilot, a squadron and the air wing are all windows a player reaches
#: from several places -- the map, the ATO list, the roster, the command palette --
#: and each of those used to build another one, so clicking the same package twice
#: left two identical windows stacked on each other.
_live: dict[str, QWidget] = {}

Window = TypeVar("Window", bound=QWidget)


def open_once(key: str, build: Callable[[], Window]) -> Window:
    """The window for this thing: the one already up, or a new one.

    A window that has been closed is rebuilt rather than shown again, so it never
    comes back with a turn-old view of the game.
    """
    existing = _live.get(key)
    if existing is not None:
        if shiboken6.isValid(existing) and existing.isVisible():
            if existing.isMinimized():
                existing.showNormal()
            existing.raise_()
            existing.activateWindow()
            return existing  # type: ignore[return-value]
        _forget_window(key, existing)
        if shiboken6.isValid(existing):
            existing.deleteLater()

    window = build()
    _live[key] = window
    # Qt deletes the C++ object when whatever it is parented to goes; holding the
    # Python wrapper after that and asking it anything raises.
    window.destroyed.connect(lambda *_: _forget_window(key, window))
    window.show()
    return window


def live_window(key: str) -> Optional[QWidget]:
    """Whatever window is up for this thing, if one is."""
    window = _live.get(key)
    if window is None or not shiboken6.isValid(window):
        return None
    return window


def _forget_window(key: str, window: QWidget) -> None:
    # By identity and without touching the object: it may be being destroyed, and a
    # newer window may already have taken its place.
    if _live.get(key) is window:
        del _live[key]


class Dialog:
    """Dialog management singleton.

    Opens dialogs and keeps references to dialog windows so that their creators
    do not need to worry about the lifetime of the dialog object, and can open
    dialogs without needing to have their own reference to common data like the
    game model.
    """

    #: The game model. Is only None before initialization, as the game model
    #: itself is responsible for handling the case where no game is loaded.
    game_model: Optional[GameModel] = None

    new_package_dialog: Optional[QNewPackageDialog] = None
    edit_package_dialog: Optional[QEditPackageDialog] = None
    edit_flight_dialog: Optional[QEditFlightDialog] = None

    @classmethod
    def set_game(cls, game_model: GameModel) -> None:
        """Sets the game model."""
        cls.game_model = game_model

    @classmethod
    def _remember(cls, name: str, dialog: QWidget) -> None:
        """Hold the dialog, and let go of it when Qt destroys it.

        These are parented to whatever opened them, so closing that window deletes
        the C++ object underneath while this class goes on holding the Python
        wrapper. Touching one of those afterwards raises, which is how a closed
        package dialog left the flight editor unopenable for the rest of the session.

        Which window it is comes from :func:`open_once`; this is the name the rest of
        the application reaches the most recent one by.
        """
        if getattr(cls, name, None) is dialog:
            return
        setattr(cls, name, dialog)
        dialog.destroyed.connect(lambda *_: cls._forget(name, dialog))

    @classmethod
    def _forget(cls, name: str, dialog: QWidget) -> None:
        # By identity, and without touching the object: it is being destroyed, and a
        # newer dialog may already have taken its place here.
        if getattr(cls, name, None) is dialog:
            setattr(cls, name, None)

    @classmethod
    def live_edit_flight_dialog(cls) -> Optional[QEditFlightDialog]:
        """The flight editor, if there is one and Qt has not deleted it."""
        dialog = cls.edit_flight_dialog
        if dialog is None:
            return None
        if not shiboken6.isValid(dialog):
            cls.edit_flight_dialog = None
            return None
        return dialog

    @classmethod
    def open_squadron_dialog(cls, squadron: Any, parent=None) -> None:
        """One squadron's roster, from wherever it was asked for.

        The pilot dialog, the command palette and the Air Wing list all want this and
        all have a different half of what it takes to build one; what they share is
        the game model, which is here.
        """
        from qt_ui.models import SquadronModel
        from qt_ui.windows.SquadronDialog import SquadronDialog

        model = cls.game_model
        if model is None or model.game is None:
            return
        open_once(
            f"squadron:{squadron.id}",
            lambda: SquadronDialog(
                model.ato_model,
                SquadronModel(squadron),
                model.game.theater,
                model.sim_controller,
                parent,
            ),
        )

    @classmethod
    def open_new_package_dialog(cls, mission_target: MissionTarget, parent=None):
        """Opens the dialog to create a new package with the given target."""
        dialog = open_once(
            f"new-package:{mission_target.name}",
            lambda: QNewPackageDialog(cls.game_model, mission_target, parent=parent),
        )
        cls._remember("new_package_dialog", dialog)

    @classmethod
    def open_edit_package_dialog(cls, package_model: PackageModel):
        """Opens the dialog to edit the given package."""
        dialog = open_once(
            f"package:{package_model.package.id}",
            lambda: QEditPackageDialog(cls.game_model, package_model),
        )
        cls._remember("edit_package_dialog", dialog)

    @classmethod
    def open_edit_flight_dialog(
        cls, package_model: PackageModel, flight: Flight, parent=None
    ) -> None:
        """Opens the dialog to edit the given flight."""
        dialog = open_once(
            f"flight:{flight.id}",
            lambda: QEditFlightDialog(
                cls.game_model, package_model, flight, parent=parent
            ),
        )
        cls._remember("edit_flight_dialog", dialog)
