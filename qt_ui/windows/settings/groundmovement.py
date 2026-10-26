"""Confirmation prompts for the Ground Movement / Motor Pool dependency."""

from PySide6.QtWidgets import QMessageBox, QWidget

from game.groundmovement import settings as movement
from game.settings import Settings


def change_movement(parent: QWidget, settings: Settings, value: bool) -> bool:
    if value and not settings.motorpool_enabled:
        answer = QMessageBox.question(
            parent,
            "Ground Movement requires Motor Pool",
            "Enable Motor Pool together with Ground Movement?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        movement.set_enabled(settings, True, enable_motorpool=True)
    else:
        movement.set_enabled(settings, value)
    return True


def change_motorpool(parent: QWidget, settings: Settings, value: bool) -> bool:
    if not value and movement.requested(settings):
        answer = QMessageBox.question(
            parent,
            "Disable Ground Movement too?",
            "Ground Movement requires Motor Pool. Disabling Motor Pool also disables "
            "Ground Movement. Existing movement orders will remain saved and paused. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        movement.disable_motorpool(settings)
    else:
        settings.motorpool_enabled = value
    return True
