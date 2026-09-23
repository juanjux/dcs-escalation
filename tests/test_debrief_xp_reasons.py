"""The debriefing says what a pilot was paid for, not only how much.

A total says a man gained 1,400 and nothing about whether that was two MiGs or a long
afternoon of trucks, and the multipliers -- morale, the company he flew in, the better
pilot who was teaching him -- do not show up in a total at all.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from game.squadrons.experience import (
    XP_AIR,
    XP_COMPANY,
    XP_GROUND,
    XP_HELD_BACK,
    XP_LEARNING,
    XP_MISSION,
    XP_MORALE,
    XP_REASON_ORDER,
    XpAward,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _award(**reasons: int) -> XpAward:
    award = XpAward("Raul", "VFA-113", before=1000, after=1000 + sum(reasons.values()))
    award.reasons = dict(reasons)
    return award


def test_the_reasons_read_in_a_fixed_order() -> None:
    """Collected in whatever order the passes ran; read in the order a person would."""
    award = _award(**{XP_COMPANY: 100, XP_AIR: 500, XP_MISSION: 500})
    assert [reason for reason, _ in award.ordered_reasons] == [
        XP_AIR,
        XP_MISSION,
        XP_COMPANY,
    ]


def test_a_reason_worth_nothing_is_not_a_reason() -> None:
    award = _award(**{XP_AIR: 500, XP_MORALE: 0})
    assert [reason for reason, _ in award.ordered_reasons] == [XP_AIR]


def test_adding_the_same_reason_twice_sums_it() -> None:
    award = XpAward("Raul", "VFA-113")
    award.add(XP_GROUND, 200)
    award.add(XP_GROUND, 400)
    assert award.reasons[XP_GROUND] == 600


def test_zero_is_never_recorded() -> None:
    award = XpAward("Raul", "VFA-113")
    award.add(XP_GROUND, 0)
    assert not award.reasons


def test_the_gain_is_the_difference_it_reports() -> None:
    award = _award(**{XP_AIR: 500, XP_MISSION: 500})
    assert award.gained == 1000


def test_a_penalty_reads_as_one() -> None:
    award = _award(**{XP_MISSION: 500, XP_MORALE: -150})
    assert dict(award.ordered_reasons)[XP_MORALE] == -150
    assert "-150" in award.summary


def test_every_label_has_a_place_in_the_order() -> None:
    """A new reason with no slot would be collected and silently never shown."""
    from game.squadrons import experience

    labels = {
        value
        for name, value in vars(experience).items()
        if name.startswith("XP_")
        and isinstance(value, str)
        and name != "XP_REASON_ORDER"
    }
    assert labels == set(XP_REASON_ORDER)


def test_a_held_back_promotion_is_shown_as_the_deduction_it_is() -> None:
    award = _award(**{XP_MISSION: 500, XP_HELD_BACK: -320})
    assert dict(award.ordered_reasons)[XP_HELD_BACK] == -320
    assert award.gained == 180


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_row_is_taller_than_a_two_line_one(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import (
        PILOT_ROW_HEIGHT,
        REASONS_ROW_HEIGHT,
        XpRow,
    )

    row = XpRow(_award(**{XP_AIR: 500}))
    assert REASONS_ROW_HEIGHT > PILOT_ROW_HEIGHT
    assert row.height() == REASONS_ROW_HEIGHT


def test_an_ordinary_row_keeps_its_height(qt_app: Any) -> None:
    from game.squadrons.experience import PilotPromotion
    from qt_ui.windows.QDebriefingWindow import PILOT_ROW_HEIGHT, PromotionRow

    row = PromotionRow(PilotPromotion("Raul", "VFA-113", "Lt", "Capt"))
    assert row.height() == PILOT_ROW_HEIGHT


def test_every_reason_has_a_colour(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import XP_REASON_COLOURS

    assert set(XP_REASON_COLOURS) == set(XP_REASON_ORDER)


def test_the_multiplier_is_split_into_the_three_things_that_moved_it() -> None:
    """And the three shares must add up to the change the total actually took."""
    from game.sim.missionresultsprocessor import MissionResultsProcessor, XpMultiplier

    processor = MissionResultsProcessor.__new__(MissionResultsProcessor)
    processor._xp_reasons = {}
    pilot = object()
    parts = XpMultiplier(morale=1.1, learning=0.15, company=0.05)
    base = 1000
    delta = round(base * parts.total) - base

    processor._note_multiplier(pilot, parts, base, delta)

    shares = processor._xp_reasons[id(pilot)]
    assert set(shares) == {XP_MORALE, XP_LEARNING, XP_COMPANY}
    assert sum(shares.values()) == delta


def test_a_rounding_remainder_does_not_go_missing() -> None:
    from game.sim.missionresultsprocessor import MissionResultsProcessor, XpMultiplier

    processor = MissionResultsProcessor.__new__(MissionResultsProcessor)
    processor._xp_reasons = {}
    pilot = object()
    # Three shares that each round down; the whole rounds up.
    parts = XpMultiplier(morale=1.0, learning=0.333, company=0.333)
    base = 999
    delta = round(base * parts.total) - base

    processor._note_multiplier(pilot, parts, base, delta)

    assert sum(processor._xp_reasons[id(pilot)].values()) == delta


def test_a_collapsed_multiplier_pays_nothing_at_all() -> None:
    """Morale low enough to zero the sortie is not then topped up by his friends."""
    from game.sim.missionresultsprocessor import XpMultiplier

    assert XpMultiplier(0.0, 0.0, 0.0).total == 0.0
