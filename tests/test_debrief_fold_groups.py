"""The debriefing's gains fold, and start folded; the dead and the wounded do not."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from game.squadrons.experience import (
    PilotDeath,
    PilotOutcomes,
    PilotPromotion,
    XpAward,
    XP_MISSION,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _report() -> Any:
    outcomes = PilotOutcomes()
    outcomes.deaths.append(PilotDeath("Raul", "VFA-113", "F/A-18C"))
    outcomes.promotions.append(PilotPromotion("Ana", "VFA-113", "Lt", "Capt"))
    award = XpAward("Ana", "VFA-113", before=100, after=600)
    award.reasons = {XP_MISSION: 500}
    outcomes.xp_awards.append(award)
    return SimpleNamespace(
        game=SimpleNamespace(settings=SimpleNamespace(live_pilots_debrief_enemy=False)),
        pilot_outcomes=outcomes,
    )


def _groups(card: Any) -> dict[str, tuple[Any, list[Any]]]:
    from qt_ui.windows.QDebriefingWindow import GroupHeader

    layout = card.layout()
    groups: dict[str, tuple[Any, list[Any]]] = {}
    current = ""
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, GroupHeader):
            current = widget.title
            groups[current] = (widget, [])
        else:
            groups[current][1].append(widget)
    return groups


def test_the_gains_start_folded_and_the_dead_do_not(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import QDebriefingWindow

    shell = SimpleNamespace(_section=lambda caption, hint, card: card)
    card = QDebriefingWindow._pilots_section(shell, _report())  # type: ignore[arg-type]

    groups = _groups(card)
    dead_header, dead = groups["KILLED IN ACTION"]
    assert not dead_header.foldable and not any(row.isHidden() for row in dead)
    for title in ("PROMOTIONS", "EXPERIENCE"):
        header, rows = groups[title]
        assert header.foldable and header.folded
        assert all(row.isHidden() for row in rows)


def test_a_click_opens_a_folded_group(qt_app: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from qt_ui.windows.QDebriefingWindow import QDebriefingWindow

    shell = SimpleNamespace(_section=lambda caption, hint, card: card)
    card = QDebriefingWindow._pilots_section(shell, _report())  # type: ignore[arg-type]
    header, rows = _groups(card)["EXPERIENCE"]

    QTest.mouseClick(header, Qt.MouseButton.LeftButton)

    assert not header.folded
    assert not any(row.isHidden() for row in rows)
