"""The debriefing says what moved a pilot's morale and by how much, on a line of its
own, the way it says what his experience was paid for."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.unit import Skill

from game.settings import Settings
from game.squadrons import morale as morale_rules
from game.squadrons.experience import MoraleShift, PilotOutcomes
from game.squadrons.pilot import Pilot

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _shift(amounts: dict[str, int]) -> MoraleShift:
    return MoraleShift(
        "Raul",
        "VFA-113",
        before=90,
        after=90 + sum(amounts.values()),
        reasons=sorted(amounts),
        amounts=dict(amounts),
    )


def test_the_biggest_move_comes_first() -> None:
    shift = _shift(
        {
            "flew the mission": 10,
            "lost a squadron mate": -40,
            "a man in his flight was hit": -1,
        }
    )
    assert list(shift.ordered_reasons) == [
        ("lost a squadron mate", -40),
        ("flew the mission", 10),
        ("a man in his flight was hit", -1),
    ]


def test_a_reason_that_moved_nothing_is_left_out() -> None:
    shift = _shift({"flew the mission": 10, "promoted": 0})
    assert list(shift.ordered_reasons) == [("flew the mission", 10)]


def test_an_older_record_has_its_reasons_without_amounts() -> None:
    shift = MoraleShift(
        "Raul",
        "VFA-113",
        90,
        50,
        ["lost a squadron mate", "lost a squadron mate", "came home empty"],
    )
    assert list(shift.ordered_reasons) == [
        ("lost a squadron mate x2", None),
        ("came home empty", None),
    ]


def test_what_each_reason_moved_adds_up_to_the_change() -> None:
    from game.sim.missionresultsprocessor import MissionResultsProcessor

    settings = Settings()
    settings.live_pilots_enabled = True
    settings.morale_enabled = True
    pilot = Pilot("Raul", morale=90)
    squadron = SimpleNamespace(
        current_roster=[pilot],
        pilot_skill=lambda _: Skill.Good,
        pilot_rank=lambda _: None,
        player=SimpleNamespace(is_blue=True),
        aircraft="F/A-18C",
    )
    processor: Any = MissionResultsProcessor.__new__(MissionResultsProcessor)
    processor.game = SimpleNamespace(
        settings=settings,
        turn=3,
        blue=SimpleNamespace(
            air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron])
        ),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: [])),
    )
    processor._xp_log = SimpleNamespace(morale=lambda *_: None)
    processor._morale_events = {
        id(pilot): [
            morale_rules.MISSION_COMPLETE,
            morale_rules.SQUADRON_DEATH,
            morale_rules.SQUADRON_DEATH,
            morale_rules.FLIGHT_WOUND,
        ]
    }
    debriefing: Any = SimpleNamespace(pilot_outcomes=PilotOutcomes())

    processor._commit_morale(debriefing)

    [shift] = debriefing.pilot_outcomes.morale_shifts
    assert set(shift.amounts) == {
        morale_rules.MISSION_COMPLETE.reason,
        morale_rules.SQUADRON_DEATH.reason,
        morale_rules.FLIGHT_WOUND.reason,
    }
    assert sum(shift.amounts.values()) == shift.after - shift.before


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_row_is_as_tall_as_the_experience_one(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import REASONS_ROW_HEIGHT, MoraleRow

    row = MoraleRow(_shift({"flew the mission": 10}))
    assert row.height() == REASONS_ROW_HEIGHT


@pytest.mark.parametrize(
    "shift",
    [
        _shift({"lost a squadron mate": -40, "flew the mission": 10}),
        MoraleShift("Raul", "VFA-113", 20, -5, ["came home empty"]),
    ],
    ids=["with amounts", "an older record, refusing to fly"],
)
def test_the_row_paints(qt_app: Any, shift: MoraleShift) -> None:
    """Called directly: an exception inside paintEvent is printed by Qt, not raised."""
    from PySide6.QtGui import QPainter, QPixmap

    from qt_ui.windows.QDebriefingWindow import MoraleRow

    row = MoraleRow(shift)
    row.resize(900, row.height())
    pixmap = QPixmap(row.size())
    painter = QPainter(pixmap)
    row.paint_detail(painter, 520)
    row.paint_outcome(painter, 886)
    row._paint_reasons(painter)
    painter.end()
