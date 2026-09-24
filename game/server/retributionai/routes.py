"""REST transport for the OPFOR-AI feature.

Thin shims over ``game.agent.service`` (the single source of truth). The MCP
transport (Phase 3) registers the same service calls, so behaviour never drifts.
Every route requires the per-process token (``?token=`` or ``X-API-Key``).
Per-turn reads serialise with ``exclude_none`` to stay token-frugal.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse

from game.agent import schemas, service, views
from game.server.security import ApiKeyManager


def _note_activity() -> None:
    """Light the toolbar robot on every API call (runs after auth passes)."""
    service.note_ai_activity()


router: APIRouter = APIRouter(
    prefix="/retribution-ai",
    dependencies=[Depends(ApiKeyManager.verify), Depends(_note_activity)],
)


@router.get(
    "/turn_context",
    operation_id="ai_turn_context",
    response_model=views.TurnContextView,
    response_model_exclude_none=True,
)
def turn_context(side: str = "red") -> views.TurnContextView:
    return service.turn_context(side)


@router.get(
    "/settings",
    operation_id="ai_settings",
    response_model=views.SettingsView,
)
def settings() -> views.SettingsView:
    return service.settings()


@router.get(
    "/packages",
    operation_id="ai_packages",
    response_model=list[views.PackageView],
    response_model_exclude_none=True,
)
def packages(side: str = "red") -> list[views.PackageView]:
    return service.get_packages(side)


@router.get(
    "/validate",
    operation_id="ai_validate",
    response_model=schemas.ValidateResult,
    response_model_exclude_none=True,
)
def validate_plan(side: str = "red") -> schemas.ValidateResult:
    return service.validate_plan(side)


@router.get("/map/image", operation_id="ai_map_image")
def map_image(side: str = "red", bbox: str | None = None) -> Response:
    """Rendered PNG strategic map for ``side`` (optional ``bbox`` = s,w,n,e)."""
    return Response(content=service.map_image(side, bbox), media_type="image/png")


@router.post("/flights/tot_offset", operation_id="ai_set_flight_tot_offset")
def set_flight_tot_offset(body: dict) -> schemas.OpResult:
    """`{side, flight_id, minutes}` — move ONE flight's time over target relative to
    its package's. Negative is ahead of the package, which is how an escort or a SEAD
    flight gets over the target before the strikers arrive.
    """
    return service.set_flight_tot_offset(
        body.get("side", "red"), body["flight_id"], float(body["minutes"])
    )


@router.get(
    "/ground/mine",
    operation_id="ai_my_ground_objects",
    response_model_exclude_none=True,
)
def my_ground_objects(side: str = "red") -> list[views.TargetView]:
    """YOUR own ground objects, with the ids ``ground/options`` and ``ground/rebuild`` need.

    ``turn_context.targets`` is always the ENEMY's, so this is the only place to get the
    id of one of your own sites -- and rebuilding is free on turn 0.
    """
    return service.my_ground_objects(side)


@router.get(
    "/iads",
    operation_id="ai_iads",
    response_model_exclude_none=True,
)
def iads(side: str = "red") -> views.IadsView:
    """Enemy IADS graph: each participating site, its role, and the sites feeding it.

    Striking a PowerSource or ConnectionNode takes down every node that depends on it
    without touching the launchers.
    """
    return service.iads(side)


@router.get("/aircraft/pylons", operation_id="ai_aircraft_pylons")
def aircraft_pylons(squadron_id: str, side: str = "red") -> dict:
    """Weapons each pylon of a squadron's airframe accepts (campaign-available)."""
    return service.aircraft_pylons(side, squadron_id)


@router.get("/aircraft/loadouts", operation_id="ai_aircraft_loadouts")
def aircraft_loadouts(squadron_id: str, side: str = "red") -> dict:
    """Named ready-made loadouts for a squadron's airframe."""
    return service.aircraft_loadouts(side, squadron_id)


@router.post("/payload/validate", operation_id="ai_validate_payload")
def validate_payload(body: schemas.ValidatePayloadRequest) -> dict:
    """Check a {pylon: clsid} payload against a squadron's airframe before using it."""
    return service.validate_payload(body.side, body.squadron_id, body.payload)


@router.get("/waypoints/{flight_id}", operation_id="ai_get_waypoints")
def get_waypoints(flight_id: str, side: str = "red") -> dict:
    """A flight's waypoints (idx, type, position, altitude) — read before /waypoints/edit."""
    return service.get_waypoints(side, flight_id)


@router.post("/waypoints/edit", operation_id="ai_edit_waypoint")
def edit_waypoint(body: schemas.WaypointEditRequest) -> schemas.OpResult:
    """Move/adjust a flight waypoint (position and/or altitude). Never deletes; waypoint
    0 (takeoff) is immovable."""
    return service.edit_waypoint(
        body.side, body.flight_id, body.waypoint_idx, body.lat, body.lng, body.alt_m
    )


@router.get("/high_command", operation_id="ai_high_command")
def high_command(side: str = "red", history: int = 20) -> dict:
    """Your High Command: the requests it has given you (what each asks, the target id
    to plan against, turns left, why, and the prize), your tickets with the picks each
    asks, the effects and loans running, and the latest history."""
    return service.high_command(side, history)


@router.post("/high_command/ticket_choices", operation_id="ai_ticket_choices")
def ticket_choices(body: schemas.TicketRequest) -> dict:
    """The next pick a ticket asks for, given the picks so far; or, with every step
    answered, what spending it gives."""
    return service.ticket_choices(body.side, body.ticket, body.picked)


@router.post("/high_command/spend", operation_id="ai_spend_ticket")
def spend_ticket(body: schemas.TicketRequest) -> schemas.OpResult:
    """Spend a ticket on the picks made. It is gone once spent; one that cannot be
    given now stays, with the reason."""
    return service.spend_ticket(body.side, body.ticket, body.picked)


@router.get("/squadrons/{squadron_id}/pilots", operation_id="ai_get_squadron_pilots")
def squadron_pilots(squadron_id: str, side: str = "red") -> dict:
    """A squadron's roster: each pilot's rank, experience, skill, wounds, and the flight
    he is already crewing. The ones without `assigned_to` are the ones you can task."""
    return service.squadron_pilots(side, squadron_id)


@router.get(
    "/squadrons/{squadron_id}/pilots/{pilot_name}/record",
    operation_id="ai_get_pilot_record",
)
def pilot_record(squadron_id: str, pilot_name: str, side: str = "red") -> dict:
    """Everything the campaign remembers about one pilot: every kill with its turn and
    weapon, what he has survived, how he died and who did it, everything that has moved
    his morale, and what he thinks of the men around him. The roster carries the counts;
    this is what they are made of."""
    return service.pilot_record(side, squadron_id, pilot_name)


@router.get("/flights/{flight_id}/crew", operation_id="ai_get_flight_crew")
def flight_crew(flight_id: str, side: str = "red") -> dict:
    """Who is in each seat of a flight, and which of the squadron's pilots are free."""
    return service.flight_crew(side, flight_id)


@router.post("/flights/crew", operation_id="ai_set_flight_crew")
def set_flight_crew(body: schemas.FlightCrewRequest) -> schemas.OpResult:
    """Put a named pilot in a seat, or empty it with a null name. Refuses a pilot who is
    dead, wounded, on leave or already flying: he can only be in one place."""
    return service.set_flight_crew(
        body.side, body.flight_id, body.seat, body.pilot_name
    )


@router.post("/pilots/leave", operation_id="ai_answer_leave_request")
def answer_leave_request(body: schemas.LeaveRequestAnswer) -> schemas.OpResult:
    """Say yes or no to a pilot listed in turn_context.leave_requests. Granting takes him
    off the roster for the turns you allow (never more than he asked) and brings him back
    steadier; refusing, or ignoring him, costs him morale."""
    return service.answer_leave_request(
        body.side, body.squadron_id, body.pilot_name, body.grant, body.turns
    )


@router.post("/pilots/leave/set", operation_id="ai_set_pilot_leave")
def set_pilot_leave(body: schemas.PilotLeaveRequest) -> schemas.PilotLeaveResult:
    """Rest a pilot who never asked for leave, or call one back early -- the Air Wing's
    leave button, which the player can press on anybody. turns=0 is open-ended; he stays
    out until you call him back, and calling him back early costs him morale."""
    return service.set_pilot_leave(
        body.side, body.squadron_id, body.pilot_name, body.on_leave, body.turns
    )


@router.post("/flights/loadout", operation_id="ai_set_flight_loadout")
def set_flight_loadout(body: schemas.FlightLoadoutRequest) -> schemas.OpResult:
    """Re-arm a flight that already exists, like the player's Payload tab. Takes a name
    from /aircraft/loadouts or a custom {pylon: clsid} map."""
    return service.set_flight_loadout(body.side, body.flight_id, body.loadout)


@router.get("/capabilities", operation_id="ai_capabilities")
def capabilities() -> dict:
    return service.capabilities()


@router.get("/start", operation_id="ai_start", response_class=PlainTextResponse)
def start(request: Request) -> PlainTextResponse:
    base_url = str(request.base_url).rstrip("/") + "/retribution-ai"
    return PlainTextResponse(service.start_doc(base_url), media_type="text/markdown")


@router.get("/howtoplay", operation_id="ai_howtoplay", response_class=PlainTextResponse)
def howtoplay() -> PlainTextResponse:
    return PlainTextResponse(service.howtoplay_doc(), media_type="text/markdown")


# --- write path ---


@router.post(
    "/packages",
    operation_id="ai_create_packages",
    response_model=list[schemas.CreateResult],
    response_model_exclude_none=True,
)
def create_packages(body: schemas.CreatePackagesRequest) -> list[schemas.CreateResult]:
    return service.create_packages(body.side, body.packages)


@router.post(
    "/packages/evaluate",
    operation_id="ai_evaluate_package",
    response_model=schemas.EvaluateResult,
    response_model_exclude_none=True,
)
def evaluate_package(body: schemas.EvaluatePackageRequest) -> schemas.EvaluateResult:
    return service.evaluate_package(body.side, body.package)


@router.delete(
    "/packages",
    operation_id="ai_clear_packages",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def clear_packages(side: str = "red") -> schemas.OpResult:
    return service.clear_packages(side)


@router.delete(
    "/packages/{index}",
    operation_id="ai_delete_package",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def delete_package(index: int, side: str = "red") -> schemas.OpResult:
    return service.delete_package(side, index)


@router.post(
    "/packages/{index}/tot",
    operation_id="ai_set_package_tot",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def set_package_tot(index: int, body: schemas.PackageTotRequest) -> schemas.OpResult:
    """Set/clear a committed package's Time-On-Target (minutes into the mission; null =
    ASAP). Stagger or synchronise packages to deconflict a multi-axis strike."""
    return service.set_package_tot(body.side, index, body.tot_minutes)


@router.post(
    "/buy/aircraft",
    operation_id="ai_buy_aircraft",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def buy_aircraft(body: schemas.BuyAircraftRequest) -> schemas.OpResult:
    return service.buy_aircraft(body.side, body.squadron_id, body.quantity)


@router.post(
    "/sell/aircraft",
    operation_id="ai_sell_aircraft",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def sell_aircraft(body: schemas.BuyAircraftRequest) -> schemas.OpResult:
    return service.sell_aircraft(body.side, body.squadron_id, body.quantity)


@router.post(
    "/buy/ground",
    operation_id="ai_buy_ground",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def buy_ground(body: schemas.BuyGroundRequest) -> schemas.OpResult:
    return service.buy_ground(body.side, body.cp_id, body.unit_name, body.quantity)


@router.get("/ground/options/{tgo_id}", operation_id="ai_ground_options")
def ground_options(tgo_id: str, side: str = "red") -> views.GroundObjectOptionsView:
    """What a SAM/EWR/armor/ship/missile/coastal site can be rebuilt into: force-groups,
    layouts, selectable unit types + counts, and the net cost (the old site is refunded).
    """
    return service.ground_object_options(side, tgo_id)


@router.post(
    "/ground/rebuild",
    operation_id="ai_rebuild_ground",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def rebuild_ground(body: schemas.RebuildGroundObjectRequest) -> schemas.OpResult:
    """Replace/upgrade a ground object with a chosen force-group + layout (optional
    per-group unit-type/count overrides). Refunds the old group; free on turn 0."""
    return service.rebuild_ground_object(
        body.side, body.tgo_id, body.force_group, body.layout, body.groups
    )


@router.post(
    "/stances",
    operation_id="ai_set_stance",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def set_stance(body: schemas.StanceRequest) -> schemas.OpResult:
    return service.set_stance(
        body.side, body.friendly_cp_id, body.enemy_cp_id, body.stance
    )


@router.post(
    "/squadron/relocate",
    operation_id="ai_relocate_squadron",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def relocate_squadron(body: schemas.RelocateSquadronRequest) -> schemas.OpResult:
    return service.relocate_squadron(body.side, body.squadron_id, body.dest_cp_id)


@router.post(
    "/ground/transfer",
    operation_id="ai_transfer_ground",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def transfer_ground(body: schemas.TransferGroundRequest) -> schemas.OpResult:
    return service.transfer_ground(
        body.side,
        body.origin_cp_id,
        body.dest_cp_id,
        body.unit_name,
        body.quantity,
        body.by_air,
    )


@router.post(
    "/naval/move",
    operation_id="ai_move_ship",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def move_ship(body: schemas.MoveShipRequest) -> schemas.OpResult:
    return service.move_ship(body.side, body.ship_id, body.lat, body.lng)


@router.post(
    "/repair",
    operation_id="ai_repair",
    response_model=schemas.OpResult,
    response_model_exclude_none=True,
)
def repair(body: schemas.RepairRequest) -> schemas.OpResult:
    return service.repair(body.side, body.id)


# --- session / Take-Off gate ---


@router.post("/ai/status", operation_id="ai_set_status")
def set_ai_status(text: str) -> dict:
    return service.set_ai_status(text)


@router.get("/turn_status", operation_id="ai_turn_status")
def turn_status() -> dict:
    return service.turn_status()


# --- memory ---


@router.get("/stored_context", operation_id="ai_get_stored_context")
def get_stored_context() -> dict:
    return service.get_stored_context()


@router.put("/stored_context", operation_id="ai_put_stored_context")
def put_stored_context(body: dict) -> dict:
    return service.put_stored_context(body)


@router.post("/stored_context", operation_id="ai_post_stored_context")
def post_stored_context(body: dict) -> dict:
    return service.post_stored_context(body)


@router.delete("/stored_context/{key}", operation_id="ai_delete_stored_context_key")
def delete_stored_context(key: str) -> dict:
    return service.delete_stored_context(key)


@router.delete("/stored_context", operation_id="ai_clear_stored_context")
def clear_stored_context() -> dict:
    return service.clear_stored_context()


@router.get("/human_notes", operation_id="ai_human_notes")
def human_notes() -> dict:
    return service.human_notes()


@router.get(
    "/prev_turns",
    operation_id="ai_prev_turns",
    response_model=list[views.TurnForcesView],
)
def prev_turns(n: int = 3) -> list[views.TurnForcesView]:
    return service.prev_turns(n)
