"""The pilot list is readable whatever the names in it are.

A QComboBox measures itself once, at its first show, and its popup inherits that
width. These selectors are rebuilt whenever another one changes, so a longer name
arriving afterwards was elided in the box AND in the list -- and widening the dialog
did nothing, because the box asks for no more than its own idea of enough.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:  # pragma: no cover - no display of any kind
            pytest.skip(f"no Qt platform available: {exc}")
    return app


def _selector(qt_app: Any, names: list[str]) -> Any:
    from dcs.unit import Skill

    from game.settings import Settings
    from game.squadrons.pilot import Pilot
    from qt_ui.windows.mission.flight.settings.QFlightSlotEditor import PilotSelector

    settings = Settings()
    settings.live_pilots_enabled = True
    pilots = []
    for index, name in enumerate(names):
        pilot = Pilot(name)
        pilot.morale = 10 + index * 15
        pilots.append(pilot)
    squadron: Any = SimpleNamespace(
        available_pilots=pilots,
        settings=settings,
        morale_in_play=True,
        pilot_rank=lambda _p: SimpleNamespace(abbreviation="1stLt"),
        pilot_skill=lambda _p: Skill.Good,
        rank_order=lambda _p: (0,),
    )
    roster: Any = SimpleNamespace(max_size=4, pilot_at=lambda _i: None)
    return PilotSelector(squadron, roster, 0)


LONG = "Аксенов Всеволод Ярославович"


def test_the_list_is_never_narrower_than_its_widest_row(qt_app: Any) -> None:
    selector = _selector(qt_app, ["Smith", LONG, "Moore"])
    metrics = selector.fontMetrics()
    widest = max(
        metrics.horizontalAdvance(selector.itemText(i)) for i in range(selector.count())
    )
    assert selector.view().minimumWidth() >= widest


def test_a_longer_name_widens_the_box_too(qt_app: Any) -> None:
    """AdjustToContentsOnFirstShow is what froze it at the short one."""
    short = _selector(qt_app, ["Smith", "Moore"]).sizeHint().width()
    long = _selector(qt_app, ["Smith", LONG]).sizeHint().width()
    assert long > short
