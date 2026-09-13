"""FastMCP tools for the OPFOR-AI feature.

Every tool delegates to ``game.agent.service`` — the SAME functions the REST routes
call — so the two transports never diverge. Mounted at ``/mcp`` by
``game/server/app.py``. Reads return frugal dicts (``exclude_none``) for token economy.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from game.agent import service

mcp = FastMCP(
    "DCS Retribution OPFOR AI",
    instructions=(
        "Plan the enemy (red/OPFOR) turn of a DCS Retribution campaign. Call "
        "`start` then `howtoplay` once, then on each 'your turn': read "
        "turn_context/get_packages, create_packages / buy / stances. The toolbar "
        "robot lights up on its own with every call — nothing to toggle on/off."
    ),
    stateless_http=True,
    json_response=True,
    # The sub-app's own route lives at "/"; app.py mounts it at "/mcp", so the
    # connector URL is http://host:port/mcp (not /mcp/mcp).
    streamable_http_path="/",
    # Single-user tool with user-controlled exposure: don't reject by Host header
    # so a tunnel (an MCP connector) reaches it. The localhost bind and the
    # user's own tunnel are the boundary — add token auth + a host allowlist before
    # exposing more widely.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _dump(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return obj


def _tool(*args: Any, **kwargs: Any) -> Callable[[Callable], Any]:
    """Like ``@_tool()`` but marks AI activity (lights the toolbar robot) on every
    call. There is no manual on/off — any tool the LLM calls counts as activity, so the
    robot lights up for a few seconds each call. ``functools.wraps`` keeps the wrapped
    function's signature/annotations so FastMCP still builds the correct tool schema."""

    def decorator(fn: Callable) -> Any:
        @functools.wraps(fn)
        def wrapper(*a: Any, **kw: Any) -> Any:
            service.note_ai_activity()
            return fn(*a, **kw)

        return mcp.tool(*args, **kwargs)(wrapper)

    return decorator


# --- reads ---


@_tool()
def turn_context(side: str = "red") -> dict:
    """Operational picture: situation, economy, control points, air wing, targets,
    threats (blue's air-defense umbrellas ranked by reach — incl. SAM-armed ships),
    naval (YOUR movable ship groups and carriers — reposition them with move_ship), and
    repairs (YOUR damaged assets you can pay to fix with repair)."""
    return _dump(service.turn_context(side))


@_tool()
def settings() -> dict:
    """Campaign settings the planner reads (aggressiveness, fog, mission window)."""
    return _dump(service.settings())


@_tool()
def map_image(side: str = "red", bbox: str | None = None) -> Image:
    """Rendered PNG strategic map for `side` (control points, front lines, threat
    umbrellas, your naval) for visual analysis. Optional `bbox` = "s,w,n,e" (lat/lng
    south,west,north,east) zooms in."""
    return Image(data=service.map_image(side, bbox), format="png")


@_tool()
def aircraft_pylons(squadron_id: str, side: str = "red") -> dict:
    """Weapons each pylon of a squadron's airframe accepts (only weapons available this
    campaign), so you can build a valid custom payload. Returns
    {aircraft, pylons: {pylon_num: [clsids]}, weapons: {clsid: human name}}."""
    return service.aircraft_pylons(side, squadron_id)


@_tool()
def aircraft_loadouts(squadron_id: str, side: str = "red") -> dict:
    """Named ready-made loadouts for a squadron's airframe (pick one by name in a flight,
    or build a custom payload from aircraft_pylons)."""
    return service.aircraft_loadouts(side, squadron_id)


@_tool()
def validate_payload(
    squadron_id: str, payload: dict[int, str], side: str = "red"
) -> dict:
    """Check a {pylon: clsid} payload against a squadron's airframe before putting it on a
    flight. Returns {ok, aircraft, errors: {pylon: reason}} — errors omitted when valid.
    """
    return service.validate_payload(side, squadron_id, payload)


@_tool()
def squadron_pilots(squadron_id: str, side: str = "red") -> dict:
    """A squadron's roster: each pilot's rank, experience, skill, wounds and the flight he
    is already crewing. Pilots without `assigned_to` are the ones free to task. Squadron
    ids come from turn_context."""
    return service.squadron_pilots(side, squadron_id)


@_tool()
def pilot_record(squadron_id: str, pilot_name: str, side: str = "red") -> dict:
    """Everything the campaign remembers about one pilot: every kill with its turn and
    weapon, what he has survived, how he died and who did it, his whole morale log, and
    what he thinks of the men around him. squadron_pilots carries the counts; this is
    what they are made of. Names come from squadron_pilots."""
    return service.pilot_record(side, squadron_id, pilot_name)


@_tool()
def flight_crew(flight_id: str, side: str = "red") -> dict:
    """Who is in each seat of a flight, and which of the squadron's pilots are still free.
    Seat numbers are what set_flight_crew expects."""
    return service.flight_crew(side, flight_id)


@_tool()
def set_flight_crew(
    flight_id: str, seat: int, pilot_name: str | None = None, side: str = "red"
) -> dict:
    """Put a named pilot in a seat of a flight, or empty it by leaving pilot_name out.
    Refuses anyone dead, wounded, on leave or already flying -- a pilot can only be in one
    place. Read flight_crew first for the seat numbers and the free pilots."""
    return service.set_flight_crew(side, flight_id, seat, pilot_name).model_dump()


@_tool()
def answer_leave_request(
    squadron_id: str,
    pilot_name: str,
    grant: bool,
    turns: int = 0,
    side: str = "red",
) -> dict:
    """Say yes or no to a pilot listed in turn_context.leave_requests. Granting takes him
    off the roster for the turns you allow -- never more than he asked, and 0 means all of
    them -- and he comes back steadier. Refusing him, or ignoring the request, costs him
    morale."""
    return service.answer_leave_request(
        side, squadron_id, pilot_name, grant, turns
    ).model_dump()


@_tool()
def set_pilot_leave(
    squadron_id: str,
    pilot_name: str,
    on_leave: bool = True,
    turns: int = 0,
    side: str = "red",
) -> dict:
    """Rest a pilot who never asked for leave, or call one back early -- the Air Wing's
    leave button, which the player can press on anybody. answer_leave_request only
    reaches a man who put his hand up, and the ones worth resting often do not. turns=0
    is open-ended: he stays out until you call him back. Calling him back early costs him
    morale; leave that ran out on its own does not."""
    return service.set_pilot_leave(
        side, squadron_id, pilot_name, on_leave, turns
    ).model_dump()


@_tool()
def get_waypoints(flight_id: str, side: str = "red") -> dict:
    """A flight's waypoints (idx, type, pos [lat,lng], alt_m) — read them before editing a
    route with edit_waypoint. Waypoint 0 is takeoff (immovable); none can be deleted."""
    return service.get_waypoints(side, flight_id)


@_tool()
def edit_waypoint(
    flight_id: str,
    waypoint_idx: int,
    lat: float | None = None,
    lng: float | None = None,
    alt_m: float | None = None,
    side: str = "red",
) -> dict:
    """Move/adjust a flight's waypoint (position lat/lng and/or altitude alt_m), like the
    player dragging it on the map. Waypoint 0 (takeoff) is immovable and waypoints can
    NEVER be deleted (that crashes DCS). Returns {ok, detail/error}."""
    return _dump(service.edit_waypoint(side, flight_id, waypoint_idx, lat, lng, alt_m))


@_tool()
def set_flight_loadout(
    flight_id: str, loadout: str | dict[int, str], side: str = "red"
) -> dict:
    """Re-arm a flight that already exists, like the player's Payload tab. `loadout` is a
    name from aircraft_loadouts, or a custom {pylon: clsid} map. Use it on flights the
    engine created for you rather than you: a squadron relocation launches its ferry
    flights EMPTY. Returns {ok, detail/error}."""
    return _dump(service.set_flight_loadout(side, flight_id, loadout))


@_tool()
def get_packages(side: str = "red") -> list:
    """Current ATO for a side — packages and flights with stable ids."""
    return _dump(service.get_packages(side))


@_tool()
def validate_plan(side: str = "red") -> dict:
    """Health-check the committed plan: each package's TOT vs the mission window and any
    uncrewed flights. ok=true means every package is crewed and on time (no changes made).
    Leftover crewed aircraft on the ramp are reported as a soft `issues` warning (they don't
    flip ok — you may be holding them back on purpose)."""
    return _dump(service.validate_plan(side))


@_tool()
def capabilities() -> dict:
    """A manifest of the reads/writes this OPFOR-AI API offers (see howtoplay for detail)."""
    return service.capabilities()


@_tool()
def start() -> str:
    """Start-here briefing: role, per-turn workflow, the tool catalog."""
    return service.start_doc("")


@_tool()
def howtoplay() -> str:
    """The OPFOR commander's full briefing (packages, fair play, doctrine)."""
    return service.howtoplay_doc()


@_tool()
def turn_status() -> dict:
    """AI-session snapshot (active/status/cancelled) plus the current turn number."""
    return service.turn_status()


# --- writes ---


@_tool()
def create_packages(side: str, packages: list[dict]) -> list:
    """Plan packages: each spec is target_id + flights[{task,count,escort?}] + rationale.
    Optional per-package ignore_range:true sends a capable airframe even past the
    auto-planner's range limit (parity with the human's manual planner; accept the risk).
    PARTIAL by default: flights that can't be filled are dropped and returned in the result's
    `dropped:[{flight,reason}]` — ALWAYS check it (a strike may have lost its SEAD/escort or be
    under-strength). ok:false only when nothing could be filled. The result's
    `idle_flyable_remaining` is how many crewed aircraft are still on the ramp — keep tasking
    until it's 0."""
    return _dump(service.create_packages(side, packages))


@_tool()
def evaluate_package(side: str, package: dict) -> dict:
    """Dry-run ONE package spec (target_id + flights[{task,count,escort?}]) to see its
    time-over-target and whether it fits the mission window — WITHOUT committing it.
    Use this to check a strike's feasibility/timing before create_packages."""
    return _dump(service.evaluate_package(side, package))


@_tool()
def delete_package(side: str, index: int) -> dict:
    """Remove a package by its index (frees its aircraft/pilots)."""
    return _dump(service.delete_package(side, index))


@_tool()
def set_package_tot(side: str, index: int, tot_minutes: int | None = None) -> dict:
    """Set/clear a committed package's Time-On-Target. tot_minutes = minutes into the
    mission (0 = mission start); None resets to ASAP. Stagger or synchronise packages to
    deconflict a multi-axis strike (parity with the player's TOT/ASAP controls)."""
    return _dump(service.set_package_tot(side, index, tot_minutes))


@_tool()
def clear_packages(side: str) -> dict:
    """Remove all of a side's packages (start the turn over)."""
    return _dump(service.clear_packages(side))


@_tool()
def buy_aircraft(side: str, squadron_id: str, quantity: int = 1) -> dict:
    """Order aircraft into a squadron (arrive next turn; spends budget)."""
    return _dump(service.buy_aircraft(side, squadron_id, quantity))


@_tool()
def sell_aircraft(side: str, squadron_id: str, quantity: int = 1) -> dict:
    """Sell untasked aircraft from a squadron (refunds budget)."""
    return _dump(service.sell_aircraft(side, squadron_id, quantity))


@_tool()
def buy_ground(side: str, cp_id: str, unit_name: str, quantity: int = 1) -> dict:
    """Order ground units of a type (from turn_context.buyable_ground) at your base."""
    return _dump(service.buy_ground(side, cp_id, unit_name, quantity))


@_tool()
def ground_object_options(tgo_id: str, side: str = "red") -> dict:
    """What one of YOUR ground objects (a SAM/EWR/armor/ship/missile/coastal site — a tgo
    id from turn_context.targets or your own sites) can be REBUILT into: the force-groups,
    layouts, and per-group selectable unit types + counts, with the default price and the
    `refund` (the old site's value, credited back). Read this before rebuild_ground_object.
    Returns {tgo_id, name, role, refund, budget, options:[{force_group, layout, price,
    groups:[{group_name, optional, default_count, max_count, unit_types:[{name, price}]}]}]}.
    """
    return _dump(service.ground_object_options(side, tgo_id))


@_tool()
def rebuild_ground_object(
    tgo_id: str,
    force_group: str,
    layout: str,
    groups: list[dict] | None = None,
    side: str = "red",
) -> dict:
    """Replace/UPGRADE one of your ground objects (SAM/EWR/armor/ship/missile/coastal) with a
    chosen `force_group` + `layout` (names from ground_object_options) — e.g. swap an SA-3
    for an SA-10, or add TELs by raising a group's count. Optional `groups` overrides each
    group: a list of {group_name, unit_type?, count?, enabled?} (group_name/unit_type from
    ground_object_options; enabled turns an optional group off). Refunds the old group's
    value and charges the net; free on turn 0; respects the campaign repair-delay (rebuilt
    units arrive over the repair turns). Returns {ok, detail/error}."""
    return _dump(
        service.rebuild_ground_object(side, tgo_id, force_group, layout, groups)
    )


@_tool()
def set_stance(side: str, friendly_cp_id: str, enemy_cp_id: str, stance: str) -> dict:
    """Set the ground stance at the front between two control points."""
    return _dump(service.set_stance(side, friendly_cp_id, enemy_cp_id, stance))


@_tool()
def move_ship(
    side: str, ship_id: str, lat: float | None = None, lng: float | None = None
) -> dict:
    """Reposition one of YOUR movable naval groups — a ship group OR a carrier/LHA (an id
    from turn_context.naval) — to [lat, lng], up to ~80 nm over water per turn (no land
    between). Omit lat/lng to cancel a pending move. The move applies at turn end."""
    return _dump(service.move_ship(side, ship_id, lat, lng))


@_tool()
def repair(side: str, id: str) -> dict:
    """Pay to repair one of YOUR damaged assets (an id from turn_context.repairs) — a dead
    SAM/EWR/armor unit group, a building, or a cratered runway. Instant or over a few turns
    per campaign settings; debits your budget. (Leftover budget also auto-repairs at turn end.)
    """
    return _dump(service.repair(side, id))


@_tool()
def relocate_squadron(side: str, squadron_id: str, dest_cp_id: str) -> dict:
    """Relocate a squadron to another of your bases (arrives over time, not instant)."""
    return _dump(service.relocate_squadron(side, squadron_id, dest_cp_id))


@_tool()
def transfer_ground(
    side: str,
    origin_cp_id: str,
    dest_cp_id: str,
    unit_name: str,
    quantity: int = 1,
    by_air: bool = False,
) -> dict:
    """Transfer existing ground units between two of your bases (land, or by_air to airlift)."""
    return _dump(
        service.transfer_ground(
            side, origin_cp_id, dest_cp_id, unit_name, quantity, by_air
        )
    )


@_tool()
def set_ai_status(text: str) -> dict:
    """Set the one-line status shown in the robot info window (optional flavor; the robot
    lights up on its own with every call, so you don't need to toggle anything)."""
    return service.set_ai_status(text)


# --- memory ---


@_tool()
def get_stored_context() -> dict:
    """Your saved per-campaign strategy notes (key -> value), persisted in the save."""
    return service.get_stored_context()


@_tool()
def put_stored_context(data: dict) -> dict:
    """Replace ALL your stored notes with `data` (a key->value object)."""
    return service.put_stored_context(data)


@_tool()
def post_stored_context(data: dict) -> dict:
    """Merge `data` into your stored notes (add/update keys; keeps the rest)."""
    return service.post_stored_context(data)


@_tool()
def delete_stored_context(key: str) -> dict:
    """Remove one note key from stored_context."""
    return service.delete_stored_context(key)


@_tool()
def human_notes() -> dict:
    """The player's campaign notes — guidance for you to read (read-only)."""
    return service.human_notes()


@_tool()
def prev_turns(n: int = 3) -> list:
    """Force totals over the last n turns — the attrition trend to react to."""
    return _dump(service.prev_turns(n))
