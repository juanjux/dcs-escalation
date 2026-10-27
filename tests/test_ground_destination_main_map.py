"""Destination selection temporarily borrows the existing campaign map."""

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMainWindow, QPushButton, QVBoxLayout, QWidget
import pytest

from qt_ui.widgets.map.grounddestination import (
    GroundDestinationBridge,
    GroundDestinationPicker,
)
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_ground_destination_picker import at


@pytest.mark.parametrize(
    "finish",
    ["pick", "cancel", "campaign", "orders", "owner-close", "window-close", "timeout"],
)
def test_existing_map_restores_dialogs_controls_and_focus(
    world: Any, controls: Any, finish: str
) -> None:
    errors: list[BaseException] = []
    bridges: list[GroundDestinationBridge] = []

    class CampaignMap(QWidget):
        def begin_ground_selection(self, bridge: GroundDestinationBridge) -> None:
            bridges.append(bridge)
            bridge.ready()

            def interact() -> None:
                try:
                    assert not dialog.isVisible() and not base_dialog.isVisible()
                    assert not normal.isEnabled() and not action.isEnabled()
                    assert self.isEnabled() and self.isVisible()
                    if finish == "pick":
                        picker.choose(at(world))
                    elif finish == "campaign":
                        controls.signal.gameupdated.emit(None)
                    elif finish == "orders":
                        controls.signal.ground_movements_changed.emit()
                    elif finish == "owner-close":
                        dialog.close()
                    elif finish == "window-close":
                        window.close()
                    elif finish == "timeout":
                        picker.connection_failed()
                    else:
                        bridge.dismiss()
                except BaseException as exc:
                    errors.append(exc)
                    picker.reject()

            QTimer.singleShot(0, interact)

        def end_ground_selection(self, bridge: GroundDestinationBridge) -> None:
            assert bridge is bridges[-1] and bridge.closed

    window = QMainWindow()
    central = QWidget(window)
    layout = QVBoxLayout(central)
    window.setCentralWidget(central)
    window.liberation_map = CampaignMap(central)  # type: ignore[attr-defined]
    normal = QPushButton("Campaign controls", central)
    already_disabled = QPushButton("Unavailable", central)
    already_disabled.setEnabled(False)
    layout.addWidget(normal)
    layout.addWidget(already_disabled)
    layout.addWidget(window.liberation_map)  # type: ignore[attr-defined]
    action = QAction("Campaign action", window)
    window.addAction(action)
    disabled_action = QAction("Unavailable action", window)
    disabled_action.setEnabled(False)
    window.addAction(disabled_action)
    base_dialog = QDialog(window)
    dialog = QDialog(base_dialog)
    dialog_layout = QVBoxLayout(dialog)
    previous_focus = QPushButton("Choose on map", dialog)
    dialog_layout.addWidget(previous_focus)
    window.show()
    base_dialog.show()
    dialog.show()
    previous_focus.setFocus()
    controls.app.processEvents()
    picker = GroundDestinationPicker(
        controls.model,
        world.source.position,
        world.source.name,
        lambda _: None,  # type: ignore[arg-type, return-value]
        dialog,
    )
    try:
        if finish == "timeout":
            with pytest.raises(RuntimeError, match="main map did not respond"):
                picker.exec()
        else:
            result = picker.exec()
            assert result == (
                QDialog.DialogCode.Accepted
                if finish == "pick"
                else QDialog.DialogCode.Rejected
            )
        assert not errors
        assert normal.isEnabled() and action.isEnabled()
        assert not already_disabled.isEnabled() and not disabled_action.isEnabled()
        if finish not in ("window-close", "owner-close"):
            assert dialog.isVisible() and base_dialog.isVisible()
            assert dialog.focusWidget() is previous_focus
        elif finish == "owner-close":
            assert not dialog.isVisible() and base_dialog.isVisible()
        else:
            assert not dialog.isVisible() and not base_dialog.isVisible()
        assert len(bridges) == 1 and picker.bridge.closed
        assert not controls.sent
    finally:
        picker.deleteLater()
        window.close()
        window.deleteLater()


def test_missing_main_map_is_reported_without_opening_another_map(
    world: Any, controls: Any
) -> None:
    dialog = QDialog()
    with pytest.raises(RuntimeError, match="main campaign map is unavailable"):
        GroundDestinationPicker(
            controls.model, world.source.position, world.source.name, lambda _: None, dialog  # type: ignore[arg-type, return-value]
        )
    dialog.deleteLater()
