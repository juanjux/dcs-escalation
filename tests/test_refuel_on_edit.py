"""The refuelling question, asked again after the player has edited the flight.

The planner asks it once, while it builds the plan. These cover the second asking:
what the verdict is for a flight the player has changed, and the deliberate gap
between the two thresholds.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.ato.flightplans import refueledit
from game.ato.flightplans.refueledit import RefuelVerdict, refuel_verdict
from game.utils import Mass, pounds


class _Layout:
    """Enough of a layout to have -- or not have -- a refuel slot."""

    def __init__(self, refuel: Any = None, has_slot: bool = True) -> None:
        if has_slot:
            self.refuel = refuel

    def delete_waypoint(self, waypoint: Any) -> bool:
        if getattr(self, "refuel", None) is waypoint:
            self.refuel = None
            return True
        return False


def _flight(
    *,
    refuel: Any = None,
    has_slot: bool = True,
    helo: bool = False,
    tankers: bool = True,
    refuel_point: Any = object(),
) -> Any:
    return SimpleNamespace(
        is_helo=helo,
        flight_plan=SimpleNamespace(layout=_Layout(refuel, has_slot)),
        coalition=SimpleNamespace(
            air_wing=SimpleNamespace(can_auto_plan=lambda _task: tankers),
        ),
        package=SimpleNamespace(refuel_point=refuel_point),
    )


def _estimate(required: float, carried: float) -> Any:
    return SimpleNamespace(
        required=pounds(required),
        carried=pounds(carried),
        enough=carried >= required,
    )


@pytest.fixture
def fuel(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Drive the verdict directly, rather than building a whole flight plan."""

    def set_to(required: float, carried: float) -> None:
        monkeypatch.setattr(
            refueledit, "estimate_fuel", lambda _flight: _estimate(required, carried)
        )

    return set_to


def test_a_flight_the_player_left_short_is_offered_a_tanker(fuel: Any) -> None:
    fuel(12000, 10000)
    assert refuel_verdict(_flight()) is RefuelVerdict.SHOULD_ADD


def test_a_flight_that_still_makes_it_is_left_alone(fuel: Any) -> None:
    fuel(9000, 10000)
    assert refuel_verdict(_flight()) is RefuelVerdict.NOTHING_TO_DO


def test_a_flight_with_fuel_to_spare_is_offered_its_detour_back(fuel: Any) -> None:
    """It has a waypoint it no longer needs -- the player put the tanks back on."""
    fuel(8000, 10000)  # a 25% surplus, past the comfortable margin
    assert refuel_verdict(_flight(refuel=object())) is RefuelVerdict.SHOULD_REMOVE


def test_a_flight_only_just_making_it_keeps_its_tanker(fuel: Any) -> None:
    """The band between the two thresholds, where nothing is offered.

    Being sent to a tanker it turns out not to need costs a flight a few minutes.
    Being sent home without one costs the aircraft, so the surplus has to be
    comfortable before the waypoint is taken away.
    """
    fuel(9500, 10000)
    assert refuel_verdict(_flight(refuel=object())) is RefuelVerdict.NOTHING_TO_DO


def test_a_flight_that_has_a_tanker_and_reads_short_is_left_alone(fuel: Any) -> None:
    """The estimate does not model taking fuel on, so a flight on its way to a tanker
    is expected to read short. That is not a reason to offer it a second one."""
    fuel(12000, 10000)
    assert refuel_verdict(_flight(refuel=object())) is RefuelVerdict.NOTHING_TO_DO


def test_a_helicopter_is_never_offered_one(fuel: Any) -> None:
    fuel(12000, 10000)
    assert refuel_verdict(_flight(helo=True)) is RefuelVerdict.NOTHING_TO_DO


def test_a_plan_with_nowhere_to_put_one_is_never_offered_one(fuel: Any) -> None:
    fuel(12000, 10000)
    assert refuel_verdict(_flight(has_slot=False)) is RefuelVerdict.NOTHING_TO_DO


def test_a_faction_with_no_tanker_is_never_offered_one(fuel: Any) -> None:
    fuel(12000, 10000)
    assert refuel_verdict(_flight(tankers=False)) is RefuelVerdict.NOTHING_TO_DO


def test_a_package_with_nowhere_to_meet_one_is_never_offered_one(fuel: Any) -> None:
    fuel(12000, 10000)
    assert refuel_verdict(_flight(refuel_point=None)) is RefuelVerdict.NOTHING_TO_DO


def test_a_flight_whose_plan_cannot_answer_is_left_alone(fuel: Any) -> None:
    fuel(12000, 10000)
    flight = _flight()

    class _Broken:
        @property
        def layout(self) -> Any:
            raise RuntimeError("no plan yet")

    flight.flight_plan = _Broken()
    assert refuel_verdict(flight) is RefuelVerdict.NOTHING_TO_DO


def test_removing_the_waypoint_goes_through_delete_waypoint() -> None:
    """By assignment it would leave the layout holding a reference, which is what
    breaks mission generation."""
    waypoint = object()
    flight = _flight(refuel=waypoint)
    assert refueledit.remove_refuel_waypoint(flight)
    assert flight.flight_plan.layout.refuel is None
    # Nothing to remove the second time.
    assert not refueledit.remove_refuel_waypoint(flight)


def test_nothing_is_added_when_there_is_nowhere_to_meet() -> None:
    flight = _flight(refuel_point=None)
    assert not refueledit.add_refuel_waypoint(flight)


def test_mass_helpers_are_the_ones_the_estimate_uses() -> None:
    """Guards the fixture: if FuelEstimate stops reporting pounds these tests would
    silently compare the wrong numbers."""
    assert isinstance(pounds(1000), Mass)


# --- offering a tanker to go with the waypoint ------------------------------


def _squadron(dcs_id: str, *, aircraft: int = 1, pilots: bool = True) -> Any:
    return SimpleNamespace(
        aircraft=SimpleNamespace(dcs_id=dcs_id),
        untasked_aircraft=aircraft,
        has_available_pilots=pilots,
        name="Test squadron",
        location="Nellis",
    )


def _flight_with_wing(squadrons: list[Any], *, threatened: bool = False) -> Any:
    flight = _flight(refuel=object())
    flight.coalition.air_wing.auto_assignable_for_task = lambda _task: iter(squadrons)
    flight.coalition.opponent = SimpleNamespace(
        threat_zone=SimpleNamespace(threatened_by_air_defense=lambda _point: threatened)
    )
    flight.package.flights = []
    return flight


def test_the_two_boom_only_tankers_are_named_as_such() -> None:
    """Everything else in the game trails a drogue. Getting this backwards sends a
    Hornet to a tanker it cannot use."""
    assert refueledit.refuelling_system(_squadron("KC-135")) == "boom"
    assert refueledit.refuelling_system(_squadron("KC_10_Extender")) == "boom"
    assert refueledit.refuelling_system(_squadron("KC135MPRS")) == "drogue"
    assert refueledit.refuelling_system(_squadron("KC_10_Extender_D")) == "drogue"
    assert refueledit.refuelling_system(_squadron("S-3B Tanker")) == "drogue"


def test_every_idle_tanker_is_offered_not_just_the_first() -> None:
    """Which one to send is the player's call: nothing in the data says whether the
    receiver has a probe."""
    boom = _squadron("KC-135")
    drogue = _squadron("KC135MPRS")
    flight = _flight_with_wing([boom, drogue])
    assert refueledit.can_offer_a_tanker(flight) == [boom, drogue]


def test_a_squadron_with_no_crew_is_not_offered() -> None:
    flight = _flight_with_wing([_squadron("KC135MPRS", pilots=False)])
    assert refueledit.can_offer_a_tanker(flight) == []


def test_a_squadron_with_no_airframe_is_not_offered() -> None:
    flight = _flight_with_wing([_squadron("KC135MPRS", aircraft=0)])
    assert refueledit.can_offer_a_tanker(flight) == []


def test_no_tanker_is_offered_into_a_threatened_orbit() -> None:
    """A tanker is large, slow, unarmed and flies in a straight line for an hour.
    Somewhere a SAM can reach is worse than nowhere."""
    flight = _flight_with_wing([_squadron("KC135MPRS")], threatened=True)
    assert refueledit.can_offer_a_tanker(flight) == []


def test_the_tanker_is_offered_before_the_waypoint_exists() -> None:
    """The dialog asks both questions at once -- waypoint only, or waypoint and
    tanker -- so it has to know whether a tanker is available before it has added
    anything. Requiring the waypoint first greyed the button out every time."""
    flight = _flight_with_wing([_squadron("KC135MPRS")])
    flight.flight_plan.layout.refuel = None
    assert len(refueledit.can_offer_a_tanker(flight)) == 1


def test_no_second_tanker_is_offered_to_a_package_that_has_one() -> None:
    from game.ato.flighttype import FlightType

    flight = _flight_with_wing([_squadron("KC135MPRS")])
    flight.package.flights = [SimpleNamespace(flight_type=FlightType.REFUELING)]
    assert refueledit.can_offer_a_tanker(flight) == []
