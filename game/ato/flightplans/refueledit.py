"""Re-deciding the refuelling waypoint after the player has edited a flight.

The planner decides this once, while it builds the plan, from the plan it is building.
That is the right moment for a flight nobody touches, but it is the only moment: take
the drop tanks off, or take the route down to eight thousand feet, and nothing asks the
question again. The flight is short of fuel and the plan still says it is fine.

So the flight editor asks again on the way out, the same way it already asks whether the
ingress point should move when the stand-off weapons changed. The measure is
:func:`estimate_fuel`, which walks the route the flight actually has rather than the one
the planner would have built, so it sees the edits.

Nothing here changes a plan on its own -- it reports a verdict, and the dialog asks.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

from game.ato.fuelestimate import estimate_fuel
from .refuelneed import can_carry_a_refuel_waypoint, has_refuel_waypoint
from .waypointbuilder import WaypointBuilder

if TYPE_CHECKING:
    from game.squadrons import Squadron

    from ..flight import Flight


#: How much fuel to spare before offering to take the waypoint back off. A flight that
#: is barely making it is one bad vector from not making it, and being sent to a tanker
#: it turns out not to need costs it a few minutes; being sent home with the tanker
#: removed costs it the aircraft. So the two thresholds are deliberately not the same
#: number, and nothing is offered in the band between them.
COMFORTABLE_MARGIN = 1.15


class RefuelVerdict(Enum):
    """What the edited flight now says about meeting a tanker."""

    #: It is short of fuel and has nowhere to take any on.
    SHOULD_ADD = auto()
    #: It is carrying comfortably more than the route asks for and still has one.
    SHOULD_REMOVE = auto()
    #: Leave it alone.
    NOTHING_TO_DO = auto()


def refuel_verdict(flight: Flight) -> RefuelVerdict:
    """Whether the flight as the player left it wants its waypoint added or removed."""
    if not _could_meet_a_tanker(flight):
        return RefuelVerdict.NOTHING_TO_DO

    estimate = estimate_fuel(flight)
    if estimate is None:
        return RefuelVerdict.NOTHING_TO_DO

    if has_refuel_waypoint(flight):
        # The estimate does not model taking fuel on, so a flight that has a tanker to
        # meet is *expected* to read short. Only a comfortable surplus means the
        # detour has stopped being worth flying.
        if estimate.carried.pounds >= estimate.required.pounds * COMFORTABLE_MARGIN:
            return RefuelVerdict.SHOULD_REMOVE
        return RefuelVerdict.NOTHING_TO_DO

    if not estimate.enough:
        return RefuelVerdict.SHOULD_ADD
    return RefuelVerdict.NOTHING_TO_DO


def _could_meet_a_tanker(flight: Flight) -> bool:
    """Whether there is any point asking the question at all."""
    from game.ato.flighttype import FlightType

    if flight.is_helo:
        return False
    if not can_carry_a_refuel_waypoint(flight):
        return False
    if not flight.coalition.air_wing.can_auto_plan(FlightType.REFUELING):
        return False
    return flight.package.refuel_point is not None


def add_refuel_waypoint(flight: Flight) -> bool:
    """Put the waypoint in without rebuilding the plan.

    Rebuilding is what the player is trying to avoid: it would throw away the very
    edits that made the flight short. The layout has a slot for this waypoint and
    yields it in the right place -- after the target, or after the last lap -- so
    filling the slot is the whole change.
    """
    point = flight.package.refuel_point
    if point is None:
        return False
    try:
        layout = flight.flight_plan.layout
    except Exception:
        logging.debug("No usable flight plan for %s", flight, exc_info=True)
        return False
    if not hasattr(layout, "refuel"):
        return False
    layout.refuel = WaypointBuilder(flight).refuel(point)
    return True


def remove_refuel_waypoint(flight: Flight) -> bool:
    """Take it back off, the same way deleting it from the route table does."""
    try:
        layout = flight.flight_plan.layout
    except Exception:
        logging.debug("No usable flight plan for %s", flight, exc_info=True)
        return False
    existing = getattr(layout, "refuel", None)
    if existing is None:
        return False
    # Through delete_waypoint rather than by assignment: that is the path the route
    # table uses, and a waypoint the layout still holds a reference to is what breaks
    # mission generation.
    return bool(layout.delete_waypoint(existing))


def planned_tanker_name(flight: Flight) -> Optional[str]:
    """A tanker this flight could actually reach, or None if none is flying.

    The waypoint on its own is not a promise of fuel: the AI goes looking for a tanker
    of its own coalition and, if the turn has none in the air, finds nothing. Worth
    saying out loud when we offer to add one.
    """
    from game.ato.flighttype import FlightType

    for package in flight.coalition.ato.packages:
        for other in package.flights:
            if other.flight_type is FlightType.REFUELING:
                return str(other.callsign or other.unit_type)
    return None


def package_has_tanker(flight: Flight) -> bool:
    """Whether this flight's own package already brings its own fuel."""
    from game.ato.flighttype import FlightType

    return any(
        other.flight_type is FlightType.REFUELING for other in flight.package.flights
    )


def refuel_point_is_safe(flight: Flight) -> bool:
    """Whether the meeting point is outside the enemy's air defences.

    A tanker is a large, slow, unarmed aircraft that flies in a straight line for an
    hour. Sending one somewhere a SAM can reach is worse than sending none, so the
    offer is not made when the point is inside the opponent's air-defence zone.
    Upstream places the point three quarters of the way from the package's home field
    towards the join, with a TODO about avoiding threatened areas, so this can and
    does happen.
    """
    point = flight.package.refuel_point
    if point is None:
        return False
    try:
        threats = flight.coalition.opponent.threat_zone
    except AttributeError:
        # No opponent zone to consult is not a reason to refuse.
        return True
    return not threats.threatened_by_air_defense(point)


#: The tankers that offer a boom and nothing else. Every other tanker in the game --
#: the MPRS, the KC-10 Drogue, the KC-130s, the S-3B, the IL-78, the buddy stores --
#: trails a drogue, so a probe-equipped receiver can use it.
#:
#: Nothing in the unit data models this, in the fork or in pydcs, so it is a list
#: rather than a field. It is short and it does not move: naming the two exceptions is
#: honest, where a table of which of several hundred receivers has a probe would not
#: be. The player is told which system the tanker offers and decides.
BOOM_ONLY_TANKERS = frozenset({"KC-135", "KC_10_Extender"})


def refuelling_system(squadron: "Squadron") -> str:
    """ "boom" or "drogue", for telling the player what they are being offered."""
    return "boom" if squadron.aircraft.dcs_id in BOOM_ONLY_TANKERS else "drogue"


def idle_tanker_squadrons(flight: Flight) -> list["Squadron"]:
    """Every squadron with a tanker on the ground and a crew for it.

    The same two questions the commander asks before it plans one: is there an
    airframe not already tasked, and is there somebody to fly it. All of them rather
    than the first, because which one to send is a question only the player can
    answer -- a Hornet cannot take fuel from a boom.
    """
    from game.ato.flighttype import FlightType

    return [
        squadron
        for squadron in flight.coalition.air_wing.auto_assignable_for_task(
            FlightType.REFUELING
        )
        if squadron.untasked_aircraft >= 1 and squadron.has_available_pilots
    ]


def can_offer_a_tanker(flight: Flight) -> list["Squadron"]:
    """The squadrons worth offering, or an empty list if offering makes no sense.

    Deliberately does NOT require the flight to have its refuelling waypoint yet: the
    dialog asks both questions at once -- waypoint only, or waypoint and tanker -- so
    it has to know the answer to this one before it has added anything.
    """
    if package_has_tanker(flight):
        return []
    if not refuel_point_is_safe(flight):
        return []
    return idle_tanker_squadrons(flight)


def plan_tanker_for(flight: Flight, squadron: "Squadron") -> "Flight":
    """Put a tanker in the package, orbiting where the flight will look for it.

    Its plan is the standard package-refuelling one, which builds its racetrack around
    ``Package.refuel_point`` -- the same point the refuelling waypoint was put at, so
    the two cannot end up in different places.
    """
    from game.ato.flight import Flight as AtoFlight
    from game.ato.flighttype import FlightType

    settings = flight.coalition.game.settings
    return AtoFlight(
        flight.package,
        squadron,
        1,
        FlightType.REFUELING,
        settings.default_start_type,
        divert=None,
    )
