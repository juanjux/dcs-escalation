"""A squadron with aircraft on hand but none free must SAY so.

The payload omits zeros to stay small, which is right for a squadron with an empty
ramp and wrong for one holding a jet that is already tasked: the planner then reads
`owned: 1` with no availability field beside it, assumes the jet is free, and refuses
its own plan when the engine disagrees ("needs 1 aircraft but the most any candidate
squadron has free is 0"). Reported by the LLM planner as an air_wing/planner
inconsistency; the numbers were never inconsistent, the zero was just invisible.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.agent import views


def _squadron(
    owned: int, untasked: int, pilots: int = 10, pilot_limits: bool = True
) -> Any:
    return SimpleNamespace(
        id="sq-1",
        aircraft=SimpleNamespace(display_name="L-39ZA Albatros", price=10),
        location=SimpleNamespace(
            name="Rene Mouawad", captured=None, runway_is_operational=lambda: True
        ),
        owned_aircraft=owned,
        untasked_aircraft=untasked,
        pending_deliveries=0,
        number_of_available_pilots=pilots,
        pilot_limits_enabled=pilot_limits,
        max_size=22,
        settings=SimpleNamespace(enable_squadron_aircraft_limits=True),
    )


def test_a_fully_tasked_squadron_reports_zero_not_silence() -> None:
    view = views.build_squadron(_squadron(owned=1, untasked=0))

    assert view.owned == 1
    assert view.untasked == 0
    assert view.flyable == 0
    assert view.unflyable == "all 1 already tasked"


def test_zero_survives_serialisation() -> None:
    """The routes serialise with exclude_none, so a real 0 must not be a None."""
    payload = views.build_squadron(_squadron(owned=2, untasked=0)).model_dump(
        exclude_none=True
    )

    assert payload["untasked"] == 0
    assert payload["flyable"] == 0
    assert payload["unflyable"] == "all 2 already tasked"


def test_an_empty_squadron_stays_quiet() -> None:
    """Nothing on the ramp: the zeros are noise and are still omitted."""
    payload = views.build_squadron(_squadron(owned=0, untasked=0)).model_dump(
        exclude_none=True
    )

    assert "owned" not in payload
    assert "untasked" not in payload
    assert "flyable" not in payload
    assert "unflyable" not in payload


def test_aircraft_free_but_no_pilots_is_named() -> None:
    view = views.build_squadron(_squadron(owned=3, untasked=3, pilots=0))

    assert view.untasked == 3
    assert view.flyable == 0
    assert view.unflyable == "no available pilots"


def test_an_available_squadron_has_no_reason() -> None:
    view = views.build_squadron(_squadron(owned=4, untasked=2))

    assert (view.untasked, view.flyable) == (2, 2)
    assert view.unflyable is None


def test_sold_aircraft_are_not_reported_as_tasked() -> None:
    sq = _squadron(owned=4, untasked=0)
    sq.pending_deliveries = -4
    view = views.build_squadron(sq)
    assert view.pending_sales == 4
    assert view.pending == -4
    assert view.untasked == view.flyable == 0
    assert view.unflyable == "4 sold (already credited; inventory settles next turn)"


def test_sales_and_actual_tasking_are_distinguished() -> None:
    sq = _squadron(owned=4, untasked=0)
    sq.pending_deliveries = -2
    view = views.build_squadron(sq)
    assert view.pending_sales == 2
    assert view.unflyable == (
        "2 sold (already credited; inventory settles next turn); 2 already tasked"
    )


def test_sales_remain_visible_when_other_aircraft_are_available() -> None:
    sq = _squadron(owned=4, untasked=2)
    sq.pending_deliveries = -2
    view = views.build_squadron(sq)
    assert view.pending_sales == 2 and view.flyable == 2
    assert view.unflyable is None


def test_sales_workshop_and_tasking_do_not_double_count() -> None:
    sq = _squadron(owned=4, untasked=0)
    sq.pending_deliveries = -2
    sq.aircraft_repairs = [object()]
    view = views.build_squadron(sq)
    assert view.unflyable == (
        "2 sold (already credited; inventory settles next turn); "
        "1 in workshop; 1 already tasked"
    )


def test_no_sales_field_when_nothing_is_sold() -> None:
    payload = views.build_squadron(_squadron(owned=4, untasked=2)).model_dump(
        exclude_none=True
    )
    assert "pending_sales" not in payload


def test_the_real_squadron_has_the_attributes_this_reads() -> None:
    """Guard: the fakes above would happily validate a rename or a property/method mix-up."""
    from game.squadrons.squadron import Squadron

    for attr in (
        "owned_aircraft",
        "untasked_aircraft",
        "number_of_available_pilots",
        "pilot_limits_enabled",
        "pending_deliveries",
        "max_size",
    ):
        # max_size and friends are dataclass fields, so they live in the annotations
        # rather than on the class itself.
        assert hasattr(Squadron, attr) or attr in getattr(
            Squadron, "__annotations__", {}
        ), f"Squadron lost {attr}"
