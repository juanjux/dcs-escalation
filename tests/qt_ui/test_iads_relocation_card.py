"""A relocating site has a blue label, not an unpowered grey label."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from game.theater.iadsnetwork.iadsexplain import IadsPicture
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStatus
from qt_ui.windows.groundobject.iadscard import IadsCard, STATE_INK


def test_relocating_card_uses_blue_and_does_not_claim_to_be_dark() -> None:
    app = QApplication.instance() or QApplication([])
    status = IadsStatus(
        IadsState.RELOCATING,
        "Relocating: temporarily disconnected from the IADS network.",
        False,
    )
    card = IadsCard(IadsPicture(status))
    labels = card.findChildren(QLabel)
    verdict = next(label for label in labels if label.text() == "RELOCATING")
    assert STATE_INK[IadsState.RELOCATING] == "#46A0FF"
    assert "#46A0FF" in verdict.styleSheet()
    assert not any("DARK" in label.text() for label in labels)
    card.close()
    card.deleteLater()
    app.processEvents()
