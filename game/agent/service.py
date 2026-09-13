"""Service layer for the OPFOR-AI feature — the single source of truth.

Both transports (REST routers in ``game/server/retributionai/`` and the MCP tools in
``game/mcp/``) call these functions, so all behaviour lives here and never drifts
between transports. Functions resolve the live game lazily via ``GameContext`` so the
module stays importable without a running server (and without Qt).
"""

from __future__ import annotations

import functools
import inspect
import re
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from game.agent import views

if TYPE_CHECKING:
    from game import Game


#: The coalition this API commands. The planner is OPFOR: it plans RED's turn and
#: reads RED's picture, including whatever RED has detected of BLUE. It must never be
#: served BLUE's own view — that is the human's private side of the board, and unlike
#: every other asymmetry the player has no way to tell it is being read.
OPFOR_SIDE = "red"


class SideNotAllowedError(PermissionError):
    """Raised when the planner asks for a side it does not command."""


def opfor_only(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Refuse any call for a side other than OPFOR.

    Applied to every service function that takes ``side``. The guard lives here, not in
    the routers, so the REST and MCP transports cannot diverge on it: a rule enforced in
    one transport and forgotten in the other is not a rule.
    """
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        side = str(bound.arguments.get("side", OPFOR_SIDE)).lower()
        if side != OPFOR_SIDE:
            raise SideNotAllowedError(
                f"this API commands {OPFOR_SIDE} only; {side!r} is the human "
                f"player's own view and is not readable through it"
            )
        return fn(*args, **kwargs)

    return wrapper


def _require_game() -> Game:
    # Lazy import keeps game/agent importable without the server/Qt stack.
    from game.server import GameContext

    return GameContext.require()


@opfor_only
def turn_context(side: str = "red") -> views.TurnContextView:
    """Operational picture for ``side`` (red/blue) from the live game."""
    return views.build_turn_context(_require_game(), side)


def settings() -> views.SettingsView:
    """Campaign settings the planner reads (aggressiveness, fog, mission window)."""
    return views.build_settings(_require_game())


@opfor_only
def map_image(side: str = "red", bbox: str | None = None) -> bytes:
    """PNG strategic map for ``side``, drawn from the same intel as turn_context
    (plus this side's own SAM umbrellas, which the text context omits)."""
    from game.agent import mapimage

    game = _require_game()
    return mapimage.render(
        views.build_turn_context(game, side),
        bbox,
        own_sams=views.build_own_sams(game, side),
    )


@opfor_only
def my_ground_objects(side: str = "red") -> list[views.TargetView]:
    """``side``'s own ground objects and their ids -- what ground/options needs."""
    return views.build_own_ground_objects(_require_game(), side)


@opfor_only
def iads(side: str = "red") -> views.IadsView:
    """The enemy IADS as a graph: participating sites and what feeds each one."""
    return views.build_iads(_require_game(), side)


@opfor_only
def aircraft_pylons(side: str = "red", squadron_id: str = "") -> dict:
    """Every weapon each pylon of a squadron's airframe accepts, so the LLM can build a
    valid custom payload. Lists ALL loadable weapons (matches what /payload/validate
    accepts and what named loadouts can carry — NOT filtered by campaign availability).
    ``pylons``: pylon number -> [clsids it accepts]; ``weapons``: clsid -> name (deduped).
    """
    from game.agent import planner
    from game.data.weapons import Pylon

    game = _require_game()
    squadron = planner._resolve_squadron(game, side, squadron_id)
    aircraft = squadron.aircraft
    pylons: dict[int, list[str]] = {}
    weapons: dict[str, str] = {}
    for pylon in Pylon.iter_pylons(aircraft):
        clsids = []
        for weapon in sorted(pylon.allowed, key=lambda w: w.name):
            clsids.append(weapon.clsid)
            weapons[weapon.clsid] = weapon.name
        if clsids:
            pylons[pylon.number] = clsids
    return {"aircraft": aircraft.display_name, "pylons": pylons, "weapons": weapons}


@opfor_only
def aircraft_loadouts(side: str = "red", squadron_id: str = "") -> dict:
    """Named ready-made loadouts for a squadron's airframe — pick one by name in a
    FlightSpec, or build a custom payload from ``aircraft_pylons``."""
    from game.agent import planner
    from game.ato.loadouts import Loadout

    game = _require_game()
    squadron = planner._resolve_squadron(game, side, squadron_id)
    aircraft = squadron.aircraft
    names = sorted({loadout.name for loadout in Loadout.iter_for_aircraft(aircraft)})
    return {"aircraft": aircraft.display_name, "loadouts": names}


@opfor_only
def validate_payload(
    side: str = "red", squadron_id: str = "", payload: dict | None = None
) -> dict:
    """Check a proposed ``{pylon: clsid}`` payload against a squadron's airframe: is each
    weapon real and accepted on that pylon? Returns ``{ok, aircraft, errors:{pylon: msg}}``
    (errors omitted when valid)."""
    from game.agent import planner
    from game.data.weapons import Pylon, Weapon

    game = _require_game()
    squadron = planner._resolve_squadron(game, side, squadron_id)
    aircraft = squadron.aircraft
    pylons = {pylon.number: pylon for pylon in Pylon.iter_pylons(aircraft)}
    errors: dict[int, str] = {}
    for raw_num, clsid in (payload or {}).items():
        num = int(raw_num)
        weapon = Weapon.with_clsid(clsid)
        if weapon is None:
            errors[num] = f"unknown weapon clsid {clsid!r}"
        elif num not in pylons:
            errors[num] = f"airframe has no pylon {num}"
        elif not pylons[num].can_equip(weapon):
            errors[num] = f"pylon {num} does not accept {weapon.name}"
    return {
        "ok": not errors,
        "aircraft": aircraft.display_name,
        "errors": errors or None,
    }


@opfor_only
def get_packages(side: str = "red") -> list[views.PackageView]:
    """Current ATO for ``side`` — packages and their flights (with stable ids)."""
    return views.build_packages(_require_game(), side)


@opfor_only
def validate_plan(side: str = "red"):
    """Health-check the committed plan: per-package TOT vs the mission window + any
    uncrewed flights (no changes made)."""
    from game.agent import planner

    return planner.validate_plan(_require_game(), side)


def capabilities() -> dict:
    """A small machine-readable manifest of what this OPFOR-AI API offers (so a client
    can discover the endpoints without guessing). Full prose is in /howtoplay."""
    return {
        "name": "DCS Retribution OPFOR-AI",
        "side": "red",
        "docs": "GET /retribution-ai/start and /howtoplay (full briefing)",
        "reads": [
            "turn_context",
            "settings",
            "packages",
            "map/image (rendered PNG strategic map — both sides' SAM/naval umbrellas)",
            "iads (enemy IADS graph: each site's role and what feeds it)",
            "aircraft/pylons (weapons each pylon accepts, to build a custom payload)",
            "aircraft/loadouts (named ready-made loadouts for an airframe)",
            "waypoints/{flight_id} (a flight's waypoints, to adjust its route)",
            "squadrons/{squadron_id}/pilots (rank, experience, skill, wounds, who is"
            " already flying, and who gets on with whom)",
            "flights/{flight_id}/crew (who is in each seat, which pilots are free, and"
            " how well the crew flies together)",
            "ground/mine (YOUR OWN ground objects with their ids -- turn_context.targets is the enemy's, so this is the only place to get an id to rebuild/upgrade one of yours)",
            "ground/options/{tgo_id} (what a SAM/EWR/armor/ship site can be rebuilt into + costs)",
            "validate",
            "prev_turns",
            "turn_status",
            "stored_context",
            "human_notes",
        ],
        "writes": [
            "packages (create; each flight may set squadron_id + loadout; package may set tot_minutes)",
            "packages/evaluate (dry-run a package's TOT, no commit)",
            "payload/validate (check a {pylon: clsid} loadout is valid for an airframe)",
            "waypoints/edit (move/adjust a flight waypoint — never deletes)",
            "flights/crew (put a named pilot in a seat, or empty it)",
            "pilots/leave (answer a pilot listed in turn_context.leave_requests)",
            "pilots/leave/set (rest a pilot who never asked, or call one back early)",
            "flights/loadout (re-arm a flight that already exists — ferries launch empty)",
            "flights/tot_offset (shift ONE flight's TOT off its package's — negative puts escorts over the target ahead of the strikers)",
            "packages/{index} (delete)",
            "packages/{index}/tot (set/clear a committed package's TOT — stagger multi-axis strikes)",
            "buy/aircraft",
            "sell/aircraft",
            "buy/ground",
            "ground/rebuild (replace/upgrade a SAM/EWR/armor/ship site: pick force-group + layout, override unit type/count; refunds the old group)",
            "stances",
            "squadron/relocate",
            "ground/transfer",
            "naval/move (reposition one of your ship groups or carriers, <=80nm over water)",
            "repair (pay to repair a damaged SAM/EWR unit, building, or runway)",
            "ai/status",
        ],
    }


@opfor_only
def create_packages(side, specs):
    """Plan packages from the LLM's specs (reusing the engine). Lazy-imports the
    write path so the read service stays light."""
    from game.agent import planner

    return planner.create_packages(_require_game(), side, specs)


@opfor_only
def evaluate_package(side, spec):
    """Dry-run a single package (plan + TOT + window fit) without committing it."""
    from game.agent import planner

    return planner.evaluate_package(_require_game(), side, spec)


@opfor_only
def edit_waypoint(side, flight_id, waypoint_idx, lat=None, lng=None, alt_m=None):
    """Move/adjust a flight waypoint (position and/or altitude). Never deletes."""
    from game.agent import planner

    return planner.edit_waypoint(
        _require_game(), side, flight_id, waypoint_idx, lat, lng, alt_m
    )


@opfor_only
def squadron_pilots(side: str, squadron_id: str) -> dict:
    """A squadron's roster: rank, experience, skill, and who is already flying."""
    from game.agent import planner

    return planner.squadron_pilots(_require_game(), side, squadron_id)


@opfor_only
def pilot_record(side: str, squadron_id: str, pilot_name: str) -> dict:
    """Everything the campaign remembers about one pilot."""
    from game.agent import planner

    return planner.pilot_record(_require_game(), side, squadron_id, pilot_name)


@opfor_only
def flight_crew(side: str, flight_id: str) -> dict:
    """Who is in each seat of a flight, and which pilots are still free."""
    from game.agent import planner

    return planner.flight_crew(_require_game(), side, flight_id)


@opfor_only
def answer_leave_request(
    side: str, squadron_id: str, pilot_name: str, grant: bool, turns: int = 0
):
    """Say yes or no to a pilot who asked for leave."""
    from game.agent import planner

    return planner.answer_leave_request(
        _require_game(), side, squadron_id, pilot_name, grant, turns
    )


@opfor_only
def set_pilot_leave(
    side: str,
    squadron_id: str,
    pilot_name: str,
    on_leave: bool = True,
    turns: int = 0,
):
    """Rest a pilot who never asked, or call one back early."""
    from game.agent import planner

    return planner.set_pilot_leave(
        _require_game(), side, squadron_id, pilot_name, on_leave, turns
    )


@opfor_only
def set_flight_crew(side: str, flight_id: str, seat: int, pilot_name):
    """Put a named pilot in a seat, or empty it."""
    from game.agent import planner

    return planner.set_flight_crew(_require_game(), side, flight_id, seat, pilot_name)


@opfor_only
def set_flight_loadout(side, flight_id, loadout):
    """Re-arm an existing flight (named loadout or {pylon: clsid})."""
    from game.agent import planner

    return planner.set_flight_loadout(_require_game(), side, flight_id, loadout)


@opfor_only
def get_waypoints(side: str = "red", flight_id: str = "") -> dict:
    """A flight's waypoints so the LLM can adjust its route with /waypoints/edit. Returns
    ``{flight_id, waypoints:[{idx, type, pos:[lat,lng], name?, alt_m?}]}``. Waypoint 0 is
    takeoff (immovable); waypoints can never be deleted."""
    from dcs.mapping import Point as DcsPoint

    from game.agent import planner

    game = _require_game()
    # Scoped to the commanded side: db.flights is global, so an id alone would reach
    # the human player's flights and expose the route they are about to fly.
    flight = planner.flight_for_side(game, side, flight_id)
    if flight is None:
        raise ValueError(f"no flight with id {flight_id!r}")
    terrain = game.theater.terrain

    def to_ll(pos) -> list[float]:
        latlng = DcsPoint(pos.x, pos.y, terrain).latlng()
        return [round(latlng.lat, 5), round(latlng.lng, 5)]

    waypoints: list[dict] = [
        {"idx": 0, "type": "TAKEOFF", "pos": to_ll(flight.departure.position)}
    ]
    for index, waypoint in enumerate(flight.flight_plan.waypoints, 1):
        entry: dict = {
            "idx": index,
            "type": waypoint.waypoint_type.name,
            "pos": to_ll(waypoint.position),
        }
        if waypoint.name:
            entry["name"] = waypoint.name
        alt = getattr(waypoint, "alt", None)
        if alt is not None:
            entry["alt_m"] = round(alt.meters)
        waypoints.append(entry)
    return {"flight_id": str(flight_id), "waypoints": waypoints}


@opfor_only
def delete_package(side, index):
    from game.agent import planner

    return planner.delete_package(_require_game(), side, index)


@opfor_only
def set_package_tot(side, index, tot_minutes):
    """Set/clear a committed package's Time-On-Target (minutes into the mission; None = ASAP)."""
    from game.agent import planner

    return planner.set_package_tot(_require_game(), side, index, tot_minutes)


@opfor_only
def clear_packages(side):
    from game.agent import planner

    return planner.clear_packages(_require_game(), side)


@opfor_only
def buy_aircraft(side, squadron_id, quantity=1):
    from game.agent import planner

    return planner.buy_aircraft(_require_game(), side, squadron_id, quantity)


@opfor_only
def sell_aircraft(side, squadron_id, quantity=1):
    from game.agent import planner

    return planner.sell_aircraft(_require_game(), side, squadron_id, quantity)


@opfor_only
def buy_ground(side, cp_id, unit_name, quantity=1):
    from game.agent import planner

    return planner.buy_ground(_require_game(), side, cp_id, unit_name, quantity)


@opfor_only
def set_stance(side, friendly_cp_id, enemy_cp_id, stance):
    from game.agent import planner

    return planner.set_stance(
        _require_game(), side, friendly_cp_id, enemy_cp_id, stance
    )


@opfor_only
def move_ship(side, ship_id, lat=None, lng=None):
    from game.agent import planner

    return planner.move_ship(_require_game(), side, ship_id, lat, lng)


@opfor_only
def repair(side, asset_id):
    from game.agent import planner

    return planner.repair(_require_game(), side, asset_id)


@opfor_only
def relocate_squadron(side, squadron_id, dest_cp_id):
    from game.agent import planner

    return planner.relocate_squadron(_require_game(), side, squadron_id, dest_cp_id)


@opfor_only
def transfer_ground(
    side, origin_cp_id, dest_cp_id, unit_name, quantity=1, by_air=False
):
    from game.agent import planner

    return planner.transfer_ground(
        _require_game(), side, origin_cp_id, dest_cp_id, unit_name, quantity, by_air
    )


@opfor_only
def ground_object_options(side, tgo_id):
    from game.agent import views

    return views.build_ground_object_options(_require_game(), side, tgo_id)


@opfor_only
def set_flight_tot_offset(side, flight_id, minutes):
    """Shift one flight's TOT relative to its package's (negative = ahead)."""
    from game.agent import planner

    return planner.set_flight_tot_offset(_require_game(), side, flight_id, minutes)


@opfor_only
def rebuild_ground_object(side, tgo_id, force_group, layout, groups=None):
    from game.agent import planner

    return planner.rebuild_ground_object(
        _require_game(), side, tgo_id, force_group, layout, groups
    )


# --- session / Take-Off gate ---


def note_ai_activity() -> None:
    """Mark AI activity so the toolbar robot lights up. Called by every transport on
    every API call (there is no manual on/off) — the robot reads active for a few
    seconds after each call, and Take Off is gated while active."""
    from game.agent.session import AI_SESSION

    AI_SESSION.touch()


def set_ai_status(text: str) -> dict:
    """Set the one-line status shown in the robot info window."""
    from game.agent.session import AI_SESSION

    AI_SESSION.set_status(text)
    return AI_SESSION.snapshot()


def turn_status() -> dict:
    """AI-session snapshot plus the current turn number."""
    from game.agent.session import AI_SESSION

    snap = AI_SESSION.snapshot()
    try:
        from game.server import GameContext

        game = GameContext.get()
    except Exception:
        game = None
    snap["turn"] = game.turn if game is not None else None
    return snap


# --- memory (persisted in the save) ---


def get_stored_context() -> dict:
    """The AI's saved per-campaign strategy notes (key -> value)."""
    return dict(_require_game().stored_context)


def put_stored_context(data: dict) -> dict:
    """Replace the whole stored_context with ``data``."""
    game = _require_game()
    game.stored_context = {str(k): str(v) for k, v in dict(data).items()}
    return dict(game.stored_context)


def post_stored_context(data: dict) -> dict:
    """Merge ``data`` into stored_context (add/update keys)."""
    game = _require_game()
    game.stored_context.update({str(k): str(v) for k, v in dict(data).items()})
    return dict(game.stored_context)


def delete_stored_context(key: str) -> dict:
    """Remove one key from stored_context."""
    game = _require_game()
    game.stored_context.pop(key, None)
    return dict(game.stored_context)


def clear_stored_context() -> dict:
    """Empty the stored_context."""
    game = _require_game()
    game.stored_context.clear()
    return dict(game.stored_context)


def human_notes() -> dict:
    """The player's campaign notes — guidance the AI reads (read-only)."""
    return {"notes": getattr(_require_game(), "notes", "") or ""}


def prev_turns(n: int = 3) -> list:
    """Force totals over the last ``n`` turns (the attrition trend)."""
    return views.build_prev_turns(_require_game(), n)


# --- autonomous wiring / scripted fallback ---


def run_opfor_fallback_if_needed() -> dict:
    """If OPFOR-AI is on but red's ATO is empty (the LLM never played), run the
    scripted commander so the turn is never empty. Called at Take Off."""
    game = _require_game()
    if not getattr(game.settings, "opfor_ai_enabled", False):
        return {"ran": False, "reason": "opfor_ai disabled"}
    red = game.red
    if red.ato.packages:
        return {
            "ran": False,
            "reason": "AI already planned",
            "packages": len(red.ato.packages),
        }
    red.plan_missions(game.conditions.start_time)
    return {"ran": True, "packages": len(red.ato.packages)}


def _server_base() -> str:
    from game.server.settings import ServerSettings

    s = ServerSettings.get()
    host = str(s.server_bind_address)
    # Show "localhost" for any loopback/any-interface bind instead of a raw address:
    # the default "::1" renders as "[::1]", which reads as broken and trips up clients
    # that assume IPv4. localhost resolves to whatever loopback the server is on.
    if host in ("::1", "::", "0.0.0.0", "127.0.0.1", ""):
        host_disp = "localhost"
    else:
        host_disp = f"[{host}]" if ":" in host else host
    return f"http://{host_disp}:{s.server_port}"


def connect_url() -> str:
    """Ready-to-paste REST connect URL+token (GET /start) — for any HTTP/REST client or curl."""
    from game.server.security import ApiKeyManager

    return f"{_server_base()}/retribution-ai/start?token={ApiKeyManager.current_key()}"


def mcp_url() -> str:
    """Ready-to-paste MCP connector URL+token (/mcp) — for any MCP-compatible client."""
    from game.server.security import ApiKeyManager

    return f"{_server_base()}/mcp?token={ApiKeyManager.current_key()}"


_DOCS_DIR = Path(__file__).parent / "docs"
_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)


def _render_doc(name: str, subs: dict[str, str]) -> str:
    text = (_DOCS_DIR / name).read_text(encoding="utf-8")
    text = _LEADING_COMMENT.sub("", text, count=1)  # drop the editorial header
    for key, value in subs.items():
        text = text.replace("{" + key + "}", value)
    return text


def start_doc(base_url: str) -> str:
    """The /start welcome doc, with {BASE_URL} filled in (read once per session)."""
    return _render_doc("start.md", {"BASE_URL": base_url.rstrip("/")})


def howtoplay_doc() -> str:
    """The OPFOR briefing; fills in the red faction when a game is loaded."""
    subs: dict[str, str] = {}
    try:
        from game.server import GameContext

        game = GameContext.get()
    except Exception:
        game = None
    if game is not None:
        faction = game.red.faction
        subs["RED_FACTION"] = faction.name or "the RED faction"
        subs["RED_COUNTRY"] = faction.country.name
    return _render_doc("howtoplay.md", subs)
