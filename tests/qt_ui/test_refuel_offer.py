"""Which question a flight's fuel gets asked, and when.

The refuelling waypoint was meant to be an offer. The planner puts it in itself while
it builds the layout, so by the time anything could ask, the waypoint is already
there and the question -- waypoint, waypoint and a tanker, or neither -- can never
come up. A flight that has only just been planned therefore has it taken back off and
is asked properly.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Layout:
    def __init__(self, refuel: Any) -> None:
        self.refuel = refuel

    def delete_waypoint(self, waypoint: Any) -> bool:
        if self.refuel is waypoint:
            self.refuel = None
            return True
        return False


def _flight(
    *, refuel: Any = None, tanker_flying: bool = False, idle_tankers: bool = True
) -> Any:
    from game.ato.flighttype import FlightType

    squadron = SimpleNamespace(
        name="VS-35", untasked_aircraft=2, has_available_pilots=True
    )
    airborne = (
        [SimpleNamespace(flight_type=FlightType.REFUELING, callsign="TEXACO")]
        if tanker_flying
        else []
    )
    package = SimpleNamespace(refuel_point=object(), flights=[])
    return SimpleNamespace(
        is_helo=False,
        callsign="TARSIER",
        unit_type="AV-8B",
        flight_plan=SimpleNamespace(layout=_Layout(refuel)),
        coalition=SimpleNamespace(
            air_wing=SimpleNamespace(
                can_auto_plan=lambda _task: True,
                auto_assignable_for_task=lambda _task: (
                    [squadron] if idle_tankers else []
                ),
            ),
            ato=SimpleNamespace(packages=[SimpleNamespace(flights=airborne)]),
            opponent=SimpleNamespace(
                threat_zone=SimpleNamespace(
                    threatened_by_air_defense=lambda _point: False
                )
            ),
        ),
        package=package,
    )


def _offer(flight: Any, asked: list[str]) -> Any:
    """An offer that records which question it would have put, and asks nothing."""
    from qt_ui.windows.mission.refueloffer import RefuelOffer

    offer = RefuelOffer(cast(Any, flight), cast(Any, None), cast(Any, None))
    offer._ask_about_adding = lambda fresh=False: asked.append(  # type: ignore[method-assign]
        "add fresh" if fresh else "add"
    )
    offer._ask_about_the_tanker = lambda: asked.append("tanker")  # type: ignore[method-assign]
    offer._ask_about_removing = lambda: asked.append("remove")  # type: ignore[method-assign]
    return offer


@pytest.fixture
def fuel(monkeypatch: pytest.MonkeyPatch) -> Any:
    from game.ato.flightplans import refueledit
    from game.utils import pounds

    def set_to(required: float, carried: float) -> None:
        monkeypatch.setattr(
            refueledit,
            "estimate_fuel",
            lambda _flight: SimpleNamespace(
                required=pounds(required),
                carried=pounds(carried),
                enough=carried >= required,
            ),
        )

    return set_to


def test_a_planner_added_waypoint_is_taken_off_and_offered(
    qt_app: Any, fuel: Any
) -> None:
    from game.sim import GameUpdateEvents

    fuel(12000, 10000)
    waypoint = object()
    flight = _flight(refuel=waypoint)
    asked: list[str] = []

    _offer(flight, asked).ask(GameUpdateEvents(), fresh=True)

    assert asked == ["add fresh"]
    assert flight.flight_plan.layout.refuel is None


def test_the_estimate_is_not_consulted_again_for_a_fresh_flight(
    qt_app: Any, fuel: Any
) -> None:
    """Without the detour the route is shorter and may read as fine.

    Re-deriving the verdict after taking the waypoint off would then drop a waypoint
    the flight needs, so the planner having added one is taken as the judgement.
    """
    from game.sim import GameUpdateEvents

    fuel(8000, 10000)  # comfortably enough, which is a "remove it" verdict
    flight = _flight(refuel=object())
    asked: list[str] = []

    _offer(flight, asked).ask(GameUpdateEvents(), fresh=True)

    assert asked == ["add fresh"]


def test_an_edited_flight_is_asked_about_the_missing_tanker(
    qt_app: Any, fuel: Any
) -> None:
    from game.sim import GameUpdateEvents

    fuel(12000, 10000)
    flight = _flight(refuel=object(), tanker_flying=False)
    asked: list[str] = []

    _offer(flight, asked).ask(GameUpdateEvents())

    assert asked == ["tanker"]


def test_a_fresh_flight_with_no_waypoint_is_left_to_the_verdict(
    qt_app: Any, fuel: Any
) -> None:
    """The planner saw no problem, so nothing is asked unless the estimate disagrees."""
    from game.sim import GameUpdateEvents

    fuel(8000, 10000)
    flight = _flight(refuel=None)
    asked: list[str] = []

    _offer(flight, asked).ask(GameUpdateEvents(), fresh=True)

    assert asked == []


def test_the_question_reads_once(qt_app: Any) -> None:
    """It is built by implicit concatenation, where a slip duplicates a sentence."""
    from qt_ui.windows.mission.refueloffer import adding_message

    text = adding_message("TARSIER (AV-8B)", "A tanker can be sent with it.", True)
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]

    assert len(sentences) == len(set(sentences)), text
    assert "does not have the fuel" in text
    assert "no longer" not in text


# --- a second flight in a package already answered for ----------------------


def _package_model(flights: list[Any]) -> Any:
    from game.ato.flighttype import FlightType

    package = SimpleNamespace(flights=flights)
    for flight in flights:
        flight.package = package
        flight.flight_type = FlightType.BARCAP
    return SimpleNamespace(package=package)


def test_adding_a_flight_asks_about_that_flight_only(qt_app: Any, fuel: Any) -> None:
    """The report: a second BARCAP put the first one's question again, and the first
    one had already been given its waypoint."""
    from game.sim import GameUpdateEvents
    from qt_ui.windows.mission import refueloffer

    fuel(12000, 10000)
    answered = _flight(refuel=object())  # the player said "waypoint only" already
    added = _flight(refuel=object())
    asked: list[Any] = []

    class _Recording(refueloffer.RefuelOffer):
        def ask(self, events: Any, fresh: bool = False) -> Any:
            asked.append(self.flight)
            return events

    original = refueloffer.RefuelOffer
    refueloffer.RefuelOffer = _Recording  # type: ignore[misc]
    try:
        refueloffer.offer_for_package(
            cast(Any, _package_model([answered, added])),
            cast(Any, None),
            GameUpdateEvents(),
            only=[added],
        )
    finally:
        refueloffer.RefuelOffer = original  # type: ignore[misc]

    assert asked == [added]
    assert answered.flight_plan.layout.refuel is not None, "and its answer stands"


def test_a_whole_package_still_asks_about_all_of_it(qt_app: Any, fuel: Any) -> None:
    from game.sim import GameUpdateEvents
    from qt_ui.windows.mission import refueloffer

    fuel(12000, 10000)
    first = _flight(refuel=object())
    second = _flight(refuel=object())
    asked: list[Any] = []

    class _Recording(refueloffer.RefuelOffer):
        def ask(self, events: Any, fresh: bool = False) -> Any:
            asked.append(self.flight)
            return events

    original = refueloffer.RefuelOffer
    refueloffer.RefuelOffer = _Recording  # type: ignore[misc]
    try:
        refueloffer.offer_for_package(
            cast(Any, _package_model([first, second])),
            cast(Any, None),
            GameUpdateEvents(),
        )
    finally:
        refueloffer.RefuelOffer = original  # type: ignore[misc]

    assert asked == [first, second]
