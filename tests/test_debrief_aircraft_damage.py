"""Friendly aircraft damage is grouped separately from permanent losses."""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from game.debriefingreport import DebriefingReport


def test_damage_card_groups_models_and_does_not_reveal_enemy_returns(
    tmp_path: Path,
) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
    from qt_ui.windows.QDebriefingWindow import QDebriefingWindow

    app = QApplication.instance() or QApplication([])
    report = DebriefingReport(
        damaged_aircraft={
            True: [
                ("AH-1W SuperCobra", 2, "Recovered for repair"),
                ("A-10C II", 1, "Recovered for repair"),
            ],
            False: [("Mi-24P", 3, "Recovered for repair")],
        }
    )
    section_owner: Any = SimpleNamespace(_section=QDebriefingWindow._section)
    section = QDebriefingWindow._damage_section(section_owner, report)
    assert section is not None
    widget = QWidget()
    widget.setStyleSheet("background: #2D3E50;")
    widget.setLayout(section)
    text = [label.text() for label in widget.findChildren(QLabel)]
    assert "DAMAGED AIRCRAFT" in text
    assert "AH-1W SuperCobra" in text and "A-10C II" in text
    assert "2" in text and "1" in text
    assert "Mi-24P" not in text
    widget.resize(900, 160)
    widget.show()
    app.processEvents()
    assert widget.grab().save(str(tmp_path / "aircraft-damage-debrief.png"))
    widget.close()


def test_damage_section_is_absent_for_empty_or_legacy_reports() -> None:
    from qt_ui.windows.QDebriefingWindow import QDebriefingWindow

    section_owner: Any = SimpleNamespace()
    assert QDebriefingWindow._damage_section(section_owner, DebriefingReport()) is None
