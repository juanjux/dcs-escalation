"""A dialog that Qt has deleted must not be handed back out.

The flight editor is parented to whatever opened it, so closing that window deletes
the C++ object while this class goes on holding the Python wrapper. Reading one of
those raises RuntimeError from shiboken, and because the read happened on the click
that would have opened a new editor, the reference was never replaced: one closed
package dialog left every flight editor in the session unopenable.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SLOT = "edit_flight_dialog"


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    app = QApplication.instance() or QApplication([])
    yield app


def test_a_destroyed_dialog_is_let_go_of(qt_app: Any) -> None:
    import shiboken6
    from PySide6.QtWidgets import QDialog, QWidget

    from qt_ui.dialogs import Dialog

    parent = QWidget()
    dialog = QDialog(parent)
    Dialog._remember(SLOT, dialog)
    assert getattr(Dialog, SLOT) is dialog

    # What closing the window does to the children: the C++ object goes, the Python
    # wrapper stays behind.
    shiboken6.delete(parent)
    qt_app.processEvents()

    assert not shiboken6.isValid(dialog)
    # Let go of by the destroyed signal, not merely hidden by the validity check.
    assert getattr(Dialog, SLOT) is None
    assert Dialog.live_edit_flight_dialog() is None


def test_a_newer_dialog_survives_the_older_one_being_destroyed(qt_app: Any) -> None:
    """The old one's destroyed signal must not clear the reference to its replacement."""
    from PySide6.QtWidgets import QDialog, QWidget

    from qt_ui.dialogs import Dialog

    parent = QWidget()
    old = QDialog(parent)
    Dialog._remember(SLOT, old)
    newer = QDialog()
    Dialog._remember(SLOT, newer)

    import shiboken6

    shiboken6.delete(parent)
    qt_app.processEvents()

    assert getattr(Dialog, SLOT) is newer
    setattr(Dialog, SLOT, None)
