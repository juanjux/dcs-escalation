"""A debriefing is pickled into the save, so it has to load from before its own fields.

Pickle rebuilds an object's ``__dict__`` exactly as it was written. A field added to one
of these records after a save was made is simply absent from the object that comes back,
and the first thing that reads it raises AttributeError -- opening the debriefing of a
turn played before the experience awards existed did exactly that.
"""

from __future__ import annotations

import pickle
from typing import Any

import pytest

from game.squadrons.experience import (
    MoraleShift,
    PilotDeath,
    PilotOutcomes,
    PilotPromotion,
    PilotWound,
    XpAward,
)


def _as_written_before(obj: Any, *missing: str) -> Any:
    """Round-trip through pickle with some fields stripped from the stored state."""

    class _Stripped:
        def __reduce__(self) -> Any:
            state = {k: v for k, v in obj.__dict__.items() if k not in missing}
            return (_rebuild, (type(obj), state))

    return pickle.loads(pickle.dumps(_Stripped()))


def _rebuild(cls: type, state: dict[str, Any]) -> Any:
    obj: Any = object.__new__(cls)
    obj.__setstate__(state)
    return obj


def test_an_old_debriefing_gets_an_empty_list_of_awards() -> None:
    restored = _as_written_before(PilotOutcomes(), "xp_awards")
    assert restored.xp_awards == []


def test_an_old_debriefing_can_still_say_whether_it_is_empty() -> None:
    """`empty` is the first thing the debriefing window reads, and it reads every list."""
    restored = _as_written_before(PilotOutcomes(), "xp_awards")
    assert restored.empty


def test_what_the_save_did_carry_is_kept() -> None:
    outcomes = PilotOutcomes()
    outcomes.promotions.append(PilotPromotion("Raul", "VFA-113", "Lt", "Capt"))
    restored = _as_written_before(outcomes, "xp_awards")
    assert [p.pilot_name for p in restored.promotions] == ["Raul"]


def test_each_old_debriefing_gets_its_own_list() -> None:
    """A default factory, not a shared default: one debriefing's awards are not another's."""
    first = _as_written_before(PilotOutcomes(), "xp_awards")
    second = _as_written_before(PilotOutcomes(), "xp_awards")
    first.xp_awards.append("x")
    assert second.xp_awards == []


@pytest.mark.parametrize(
    "record,field_name,expected",
    [
        (PilotDeath("Raul", "VFA-113", "F/A-18C"), "friendly_fire", False),
        (PilotWound("Raul", "VFA-113", 2), "killed_by", None),
        (PilotPromotion("Raul", "VFA-113", "Lt", "Capt"), "to_rank_full", ""),
        (MoraleShift("Raul", "VFA-113", 5, 3, []), "after_state", ""),
        (XpAward("Raul", "VFA-113"), "reasons", {}),
    ],
)
def test_every_record_fills_a_field_its_save_lacked(
    record: Any, field_name: str, expected: Any
) -> None:
    """Every record in the module is pickled with the debriefing, so all of them heal."""
    restored = _as_written_before(record, field_name)
    assert getattr(restored, field_name) == expected


def test_a_full_round_trip_is_unchanged() -> None:
    outcomes = PilotOutcomes()
    outcomes.xp_awards.append(XpAward("Raul", "VFA-113", before=100, after=600))
    restored = pickle.loads(pickle.dumps(outcomes))
    assert restored.xp_awards[0].gained == 500


def test_pickle_itself_heals_it() -> None:
    """No helper in the way: the object is saved without the field and loaded back."""
    outcomes = PilotOutcomes()
    del outcomes.__dict__["xp_awards"]
    restored = pickle.loads(pickle.dumps(outcomes))
    assert restored.xp_awards == []
    assert restored.empty
