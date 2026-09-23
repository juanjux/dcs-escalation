from __future__ import annotations

import itertools
import logging
import math
import secrets
from collections.abc import Iterator
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Callable, List, Optional, TYPE_CHECKING, Union, cast
from uuid import UUID

from dcs.countries import (
    Switzerland,
    USAFAggressors,
    UnitedNationsPeacekeepers,
    country_dict,
)
from dcs.country import Country
from dcs.mapping import Point
from dcs.task import CAP, CAS, PinpointStrike
from dcs.vehicles import AirDefence

from game.ato.closestairfields import ObjectiveDistanceCache
from game.dcs.skills import experience_for_skill
from game.ground_forces.ai_ground_planner import GroundPlanner
from game.mfd import remember_positions
from game.models.game_stats import GameStats
from game.plugins import LuaPluginManager
from game.utils import Distance
from . import naming, persistency
from .ato import Flight
from .ato.flighttype import FlightType
from .campaignloader import CampaignAirWingConfig
from .coalition import Coalition
from .db.gamedb import GameDb
from .dcs.countries import country_with_name
from .highcommand.orders import HighCommand
from .infos.information import Information
from .lasercodes.lasercoderegistry import LaserCodeRegistry
from .profiling import logged_duration
from .settings import Settings
from .spatialindex import LiveUnitIndex
from .theater import ConflictTheater, Player
from .theater.bullseye import Bullseye
from .theater.theatergroundobject import (
    EwrGroundObject,
    SamGroundObject,
    TheaterGroundObject,
)
from .theater.transitnetwork import TransitNetwork, TransitNetworkBuilder
from .timeofday import TimeOfDay
from .weather.conditions import Conditions

if TYPE_CHECKING:
    from .ato.airtaaskingorder import AirTaskingOrder
    from .debriefingreport import DebriefingReport
    from .factions.faction import Faction
    from .navmesh import NavMesh
    from .sim import GameUpdateEvents
    from .squadrons import AirWing
    from .transfers import MultiGroupTransport
    from .threatzones import ThreatZones

COMMISION_UNIT_VARIETY = 4
COMMISION_LIMITS_SCALE = 1.5
COMMISION_LIMITS_FACTORS = {
    PinpointStrike: 10,
    CAS: 5,
    CAP: 8,
    AirDefence: 8,
}

COMMISION_AMOUNTS_SCALE = 1.5
COMMISION_AMOUNTS_FACTORS = {
    PinpointStrike: 3,
    CAS: 1,
    CAP: 2,
    AirDefence: 0.8,
}

PLAYER_INTERCEPT_GLOBAL_PROBABILITY_BASE = 30
PLAYER_INTERCEPT_GLOBAL_PROBABILITY_LOG = 2
PLAYER_BASEATTACK_THRESHOLD = 0.4

# amount of strength player bases recover for the turn
PLAYER_BASE_STRENGTH_RECOVERY = 0.2

# amount of strength enemy bases recover for the turn
ENEMY_BASE_STRENGTH_RECOVERY = 0.05

# cost of AWACS for single operation
AWACS_BUDGET_COST = 4

# Bonus multiplier logarithm base
PLAYER_BUDGET_IMPORTANCE_LOG = 2


class TurnState(Enum):
    WIN = 0
    LOSS = 1
    CONTINUE = 2


def time_of_day_offset(
    theater: ConflictTheater, start_date: datetime, start_time: time | None
) -> int:
    """Which turn slot a campaign beginning at this date and time starts in.

    The date and the time are two values and are not interchangeable: the slots
    themselves are computed from the sun, so the map is chosen by the date, and the
    time of day is then looked up inside it. Only one shipped campaign carries a time
    in its start date, so confusing the two crashed exactly that campaign and nothing
    else.
    """
    if start_time is None:
        return list(TimeOfDay).index(TimeOfDay.Day)
    return list(TimeOfDay).index(
        theater.daytime_map_for(start_date.date()).best_guess_time_of_day_at(start_time)
    )


class Game:
    scenery_clear_zones: List[Point]

    def __init__(
        self,
        player_faction: Faction,
        enemy_faction: Faction,
        theater: ConflictTheater,
        air_wing_config: CampaignAirWingConfig,
        start_date: datetime,
        start_time: time | None,
        settings: Settings,
        player_budget: float,
        enemy_budget: float,
        campaign_name: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.theater = theater
        self.campaign_name = campaign_name
        self.turn = 0
        # NB: This is the *start* date. It is never updated.
        self.date = date(start_date.year, start_date.month, start_date.day)
        self.game_stats = GameStats()
        self.notes = ""
        # Free-form scratchpad for the OPFOR-AI commander (persisted per campaign).
        self.stored_context: dict[str, str] = {}
        # Per-turn loss summaries for the OPFOR-AI prev_turns after-action.
        self.debrief_history: list[dict[str, int]] = []
        # The last debriefing, as data. The window used to be the only place the report
        # lived, so it was gone the moment Escalation was closed; kept here it can be
        # reopened from the Misc bar in a later session.
        self.last_debriefing_report: Optional[DebriefingReport] = None
        # Opaque JSON blob with the web client's map-layer panel state (which layers
        # are visible, base map, which groups are open). The client owns the
        # (de)serialization; the game just stores it so the choices travel with the
        # save instead of being lost on reload.
        self.client_map_layers: Optional[str] = None
        # The objectives the High Command has ordered taken, with their prizes.
        self.high_command = HighCommand()
        # OPFOR-AI API token, persisted so a campaign keeps the same connect URL across
        # restarts of this save (an LLM reconnects without a new token each session).
        self.opfor_ai_token: str = secrets.token_urlsafe()
        # Missiles left per cruise-missile ship group, keyed by TheaterGroup.group_name.
        # Only groups that have fired appear here; game.cruise_raids reads the stock of
        # the rest from their living hulls. Written solely at the turn boundary, so
        # regenerating a mission can never charge for the same salvo twice.
        self.cruise_missile_magazines: dict[str, int] = {}
        # Each naval group's remaining ANTI-SHIP missile stock, keyed by the same
        # stable group name. Seeded on first sight and debited only at the turn
        # boundary from what the plugin reports fired, never at generation, so
        # re-generating a mission cannot charge for the same salvo twice. A disjoint
        # weapon set from the cruise-missile magazine above, so the two never
        # double-charge the same shot. There is no rearm.
        self.naval_magazines: dict[str, int] = {}
        self.ground_planners: dict[UUID, GroundPlanner] = {}
        self.informations: list[Information] = []
        self.message("Game Start", "-" * 40)
        # Culling Zones are for areas around points of interest that contain things we may not wish to cull.
        self.__culling_zones: List[Point] = []
        self.__destroyed_units: list[dict[str, Union[float, str]]] = []
        self.savepath = ""
        self.current_unit_id = 0
        self.current_group_id = 0
        self.name_generator = naming.namegen
        self.laser_code_registry = LaserCodeRegistry()

        self.db = GameDb()

        self.time_of_day_offset_for_start_time = time_of_day_offset(
            self.theater, start_date, start_time
        )
        self.conditions = self.generate_conditions(forced_time=start_time)

        self.sanitize_sides(player_faction, enemy_faction)
        self.blue = Coalition(self, player_faction, player_budget, player=Player.BLUE)
        self.red = Coalition(self, enemy_faction, enemy_budget, player=Player.RED)
        neutral_faction = deepcopy(player_faction)
        neutral_faction.country = self.neutral_country
        self.neutral = Coalition(self, neutral_faction, 0, player=Player.NEUTRAL)
        self.blue.set_opponent(self.red)
        self.red.set_opponent(self.blue)

        for control_point in self.theater.controlpoints:
            control_point.finish_init(self)

        self.blue.configure_default_air_wing(air_wing_config)
        self.red.configure_default_air_wing(air_wing_config)

        self.on_load(game_still_initializing=True)

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        # Heal carcass lists bloated by old saves. Guarded like laser_code_registry
        # below: __destroyed_units postdates the oldest saves, so a pre-2020 save
        # arrives without it and must not AttributeError here.
        if hasattr(self, "_Game__destroyed_units"):
            self._dedup_destroyed_units()
        if not hasattr(self, "laser_code_registry"):
            self.laser_code_registry = LaserCodeRegistry()
            for front_line in self.theater.conflicts():
                front_line.laser_code = self.laser_code_registry.alloc_laser_code()
        if not hasattr(self, "stored_context"):
            self.stored_context = {}
        if not hasattr(self, "debrief_history"):
            self.debrief_history = []
        if not hasattr(self, "last_debriefing_report"):
            self.last_debriefing_report = None
        if not hasattr(self, "client_map_layers"):
            self.client_map_layers = None
        if not hasattr(self, "high_command"):
            self.high_command = HighCommand()
        if not hasattr(self, "cruise_missile_magazines"):
            self.cruise_missile_magazines = {}
        if not hasattr(self, "naval_magazines"):
            self.naval_magazines = {}
        if not getattr(self, "opfor_ai_token", None):
            # Pre-feature save: mint a token now; it sticks once this save is written.
            self.opfor_ai_token = secrets.token_urlsafe()
        # Regenerate any state that was not persisted.
        self.on_load()

    def record_debrief(self, debriefing: Any) -> None:
        """Capture a concise per-turn loss summary (counts + who-killed-what) for the
        OPFOR-AI prev_turns after-action (best-effort; must never break the commit)."""
        from collections import Counter
        from game.theater.player import Player

        if not hasattr(self, "debrief_history"):
            self.debrief_history = []

        # Keep the report the debriefing window shows, so it can be reopened in a later
        # session. This runs while the results are being committed, before the turn is
        # passed, so self.turn is the turn the mission was flown in. Best-effort like
        # the summary below: failing here must never cost the player the turn.
        try:
            from game.debriefingreport import DebriefingReport

            self.last_debriefing_report = DebriefingReport.from_debriefing(
                debriefing, self.turn
            )
        except Exception:
            logging.exception("Failed to record the debriefing report")

        def lost_by_type(player: Player) -> dict[str, int]:
            """What died, by airframe. "30 aircraft" does not tell a planner whether it
            lost its Hinds or its Frogfoots; this does, in about twenty keys."""
            try:
                return {
                    unit_type.name: count
                    for unit_type, count in debriefing.air_losses.by_type(
                        player
                    ).items()
                }
            except Exception:
                return {}

        def kills_by_weapon(losses: Any) -> dict[str, int]:
            """What did the killing, by weapon. Deliberately the weapon alone, unlike
            `killers` below, which falls back from the shooter to the weapon and so
            mixes the two in one dict -- a loadout cannot be judged from a number that
            might be an airframe."""
            try:
                index = getattr(debriefing, "kill_info_by_unit_id", {}) or {}
                counts: Counter[str] = Counter()
                for loss in losses:
                    detail = index.get(id(loss))
                    weapon = detail.get("weapon") if detail else None
                    if weapon:
                        counts[str(weapon)] += 1
                return dict(counts)
            except Exception:
                return {}

        def kills_by_victim(losses: Any) -> dict[str, dict[str, int]]:
            """Which airframe killed which, one nesting deep: {victim: {killer: n}}.
            Aggregated, so it grows with the number of TYPES in the fight rather than
            with the number of kills."""
            try:
                index = getattr(debriefing, "kill_info_by_unit_id", {}) or {}
                out: dict[str, Counter[str]] = {}
                for loss in losses:
                    detail = index.get(id(loss))
                    killer = detail.get("initiator_type") if detail else None
                    if not killer:
                        continue
                    victim = getattr(
                        getattr(getattr(loss, "flight", None), "unit_type", None),
                        "name",
                        None,
                    )
                    if not victim:
                        continue
                    out.setdefault(str(victim), Counter())[str(killer)] += 1
                return {victim: dict(c) for victim, c in out.items()}
            except Exception:
                return {}

        def killers(losses: Any) -> dict[str, int]:
            try:
                index = getattr(debriefing, "kill_info_by_unit_id", {}) or {}
                counts: Counter[str] = Counter()
                for loss in losses:
                    detail = index.get(id(loss))
                    if detail:
                        who = detail.get("initiator_type") or detail.get("weapon")
                        if who:
                            counts[str(who)] += 1
                return dict(counts)
            except Exception:
                return {}

        try:
            summary = {
                "turn": self.turn,
                "blue_air_lost": len(debriefing.air_losses.player),
                "red_air_lost": len(debriefing.air_losses.enemy),
                "blue_air_crashed": sum(
                    debriefing.is_non_combat_loss(u)
                    for u in debriefing.air_losses.player
                ),
                "red_air_crashed": sum(
                    debriefing.is_non_combat_loss(u)
                    for u in debriefing.air_losses.enemy
                ),
                "blue_ground_lost": sum(
                    debriefing.front_line_losses_by_type(Player.BLUE).values()
                ),
                "red_ground_lost": sum(
                    debriefing.front_line_losses_by_type(Player.RED).values()
                ),
                "red_air_killers": killers(debriefing.air_losses.enemy),
                "blue_air_killers": killers(debriefing.air_losses.player),
                # The three that let a planner judge an airframe and a loadout rather
                # than a headline number. All aggregates, so they scale with the number
                # of types in the fight, not with the number of events.
                "red_air_lost_by_type": lost_by_type(Player.RED),
                "blue_air_lost_by_type": lost_by_type(Player.BLUE),
                # A side's KILLS come from the OTHER side's losses. air_losses.player is
                # blue and .enemy is red, so red's kills are read off blue's losses --
                # getting this backwards hands a planner the enemy's weapons when it asks
                # which of its own are working.
                "red_air_kills_by_weapon": kills_by_weapon(
                    debriefing.air_losses.player
                ),
                "blue_air_kills_by_weapon": kills_by_weapon(
                    debriefing.air_losses.enemy
                ),
                "red_air_kills_by_victim": kills_by_victim(
                    debriefing.air_losses.player
                ),
                "blue_air_kills_by_victim": kills_by_victim(
                    debriefing.air_losses.enemy
                ),
                # Per-type site/naval unit losses this turn (ships by class, SAM
                # launchers/radars, etc.) — the concrete result of each side's strikes:
                # what actually died, not just "target damaged". e.g. {"Type_052C": 1}.
                "blue_sites_lost": dict(
                    debriefing.ground_object_losses_by_type(Player.BLUE)
                ),
                "red_sites_lost": dict(
                    debriefing.ground_object_losses_by_type(Player.RED)
                ),
            }
        except Exception:
            logging.exception("OPFOR-AI: failed to record debrief summary")
            return
        self.debrief_history.append(summary)
        if len(self.debrief_history) > 20:
            self.debrief_history = self.debrief_history[-20:]

    @property
    def coalitions(self) -> Iterator[Coalition]:
        yield self.blue
        yield self.red

    def point_in_world(self, x: float, y: float) -> Point:
        return Point(x, y, self.theater.terrain)

    def ato_for(self, player: Player) -> AirTaskingOrder:
        return self.coalition_for(player).ato

    def transit_network_for(self, player: Player) -> TransitNetwork:
        return self.coalition_for(player).transit_network

    def generate_conditions(self, forced_time: time | None = None) -> Conditions:
        return Conditions.generate(
            self.theater,
            self.current_day,
            self.current_turn_time_of_day,
            self.settings,
            forced_time=forced_time,
        )

    @staticmethod
    def sanitize_sides(player_faction: Faction, enemy_faction: Faction) -> None:
        """
        Make sure the opposing factions are using different countries
        :return:
        """
        # TODO: This should just be rejected and sent back to the user to fix.
        # This isn't always something that the original faction can support.
        if player_faction.country == enemy_faction.country:
            if player_faction.country.name == "USA":
                enemy_faction.country = country_with_name("USAF Aggressors")
            elif player_faction.country.name == "Russia":
                enemy_faction.country = country_with_name("USSR")
            else:
                enemy_faction.country = country_with_name("Russia")

    def faction_for(self, player: Player) -> Faction:
        return self.coalition_for(player).faction

    def air_wing_for(self, player: Player) -> AirWing:
        return self.coalition_for(player).air_wing

    @property
    def neutral_country(self) -> Country:
        """Return the best fitting country to use for the neutral coalition.

        Returns the first candidate whose id is not already claimed by a
        belligerent. The in-use set spans every squadron's own country (#627
        per-squadron countries), not just the two faction primaries, so a CJTF
        side that fields e.g. a Swiss or UN squadron does not also hand that
        nation to the neutral coalition -- which would place one country on two
        coalitions (an unloadable .miz) and misfile neutral statics / break DCS
        capture triggers keyed on neutral membership. Membership is tested by id,
        which is pydcs's own equality key for ``Country`` (``Country.__eq__`` and
        ``__hash__`` are by ``id``).
        """
        ids_in_use = {self.red.faction.country.id, self.blue.faction.country.id}
        for coalition in (self.blue, self.red):
            for squadron in coalition.air_wing.iter_squadrons():
                ids_in_use.add(squadron.country.id)
        for candidate in (UnitedNationsPeacekeepers, Switzerland, USAFAggressors):
            if candidate.id not in ids_in_use:
                return candidate()
        # Every preferred neutral is claimed by a belligerent (e.g. a USAF
        # Aggressors red faction against a blue CJTF fielding UN and Swiss
        # squadrons). Returning a claimed country would place one nation on two
        # coalitions -- the unloadable .miz this property exists to prevent -- so
        # scan the full pydcs country list for any unclaimed nation instead.
        for country_id in sorted(country_dict):
            if country_id not in ids_in_use:
                return country_dict[country_id]()
        raise RuntimeError(
            "No neutral country available: every pydcs country is claimed by a "
            "belligerent"
        )

    def coalition_for(self, player: Player) -> Coalition:
        if player.is_neutral:
            return self.neutral
        elif player.is_blue:
            return self.blue
        else:
            return self.red

    def adjust_budget(self, amount: float, player: Player) -> None:
        self.coalition_for(player).adjust_budget(amount)

    def on_load(self, game_still_initializing: bool = False) -> None:
        from .sim import GameUpdateEvents

        if not hasattr(self, "name_generator"):
            self.name_generator = naming.namegen
        # This was meant to carry the name generator's state across a save, and cannot:
        # what the save holds is the generator itself, and it is a class, which pickle
        # stores by reference -- the counters on it are not in the save at all. So the
        # line below hands back the same class this process started with, counting from
        # zero, and the transports already on the road are named from the last one.
        naming.namegen = self.name_generator
        self._resume_transport_names()
        # A campaign that has never had a turn pass still has a picture of itself:
        # what is standing when it starts is what a satellite would have found.
        remember_positions(
            tgo
            for cp in self.theater.controlpoints
            for tgo in cp.connected_objectives
            if getattr(tgo, "mfd_seen_at", None) is None
        )
        LuaPluginManager.load_settings(self.settings)
        ObjectiveDistanceCache.set_theater(self.theater)
        self.compute_unculled_zones(GameUpdateEvents())
        # Apply mod settings again so mod properties get injected again,
        # in case mods like CJS F/A-18E/F/G or IDF F-16I are selected by the player
        self.blue.faction.apply_mod_settings()
        self.red.faction.apply_mod_settings()
        if not game_still_initializing:
            # We don't need to push events that happen during load. The UI will fully
            # reset when we're done.
            self.compute_threat_zones(GameUpdateEvents())

    def _resume_transport_names(self) -> None:
        """Number the next convoy and cargo ship after the ones already travelling.

        A transport is a campaign object, not a mission one: it keeps its name for as
        long as it is on the road, and that name is how the debrief credits what was
        killed on it. Its number comes from a counter no save carries, so a campaign
        loaded with a convoy in transit would mint the same name a second time. A save
        that already holds such a pair is healed here -- the later one is renamed --
        rather than left with two columns answering to one name.
        """
        travelling: list[tuple[MultiGroupTransport, Callable[[], str]]] = []
        for coalition in (self.blue, self.red):
            transfers = getattr(coalition, "transfers", None)
            if transfers is None:
                continue
            travelling.extend(
                (transport, minter)
                for transports, minter in (
                    (transfers.convoys, naming.namegen.next_convoy_name),
                    (transfers.cargo_ships, naming.namegen.next_cargo_ship_name),
                )
                for transport in transports
            )

        naming.namegen.resume_after(transport.name for transport, _ in travelling)

        taken: set[str] = set()
        for transport, next_name in travelling:
            if transport.name in taken:
                was = transport.name
                transport.name = next_name()
                logging.info(f"Renamed a second {was} in transit to {transport.name}")
            taken.add(transport.name)

    def finish_turn(self, events: GameUpdateEvents, skipped: bool = False) -> None:
        """Finalizes the current turn and advances to the next turn.

        This handles the turn-end portion of passing a turn. Initialization of the next
        turn is handled by `initialize_turn`. These are separate processes because while
        turns may be initialized more than once under some circumstances (see the
        documentation for `initialize_turn`), `finish_turn` performs the work that
        should be guaranteed to happen only once per turn:

        * Turn counter increment.
        * Delivering units ordered the previous turn.
        * Transfer progress.
        * Squadron replenishment.
        * Income distribution.
        * Base strength (front line position) adjustment.
        * Weather/time-of-day generation.

        Some actions (like transit network assembly) will happen both here and in
        `initialize_turn`. We need the network to be up to date so we can account for
        base captures when processing the transfers that occurred last turn, but we also
        need it to be up to date in the case of a re-initialization in `initialize_turn`
        (such as to account for a cheat base capture) so that orders are only placed
        where a supply route exists to the destination. This is a relatively cheap
        operation so duplicating the effort is not a problem.

        Args:
            skipped: True if the turn was skipped.
        """
        self.message("End of turn #" + str(self.turn), "-" * 40)
        self.turn += 1

        # The coalition-specific turn finalization *must* happen before unit deliveries,
        # since the coalition-specific finalization handles transit network updates and
        # transfer processing. If in the other order, units may be delivered to captured
        # bases, and freshly delivered units will spawn one leg through their journey.
        self.blue.end_turn(events)
        self.red.end_turn(events)

        for control_point in self.theater.controlpoints:
            control_point.process_turn(self, events)

        # Movable ship TGOs snap to their destination and re-parent to the
        # nearest friendly CP. Runs after captures are committed (process_results
        # precedes pass_turn -> finish_turn), so re-parenting sees post-capture
        # ownership.
        from game.theater.shipmovement import move_and_reparent_ships

        move_and_reparent_ships(self.theater.controlpoints)

        if not skipped:
            for cp in self.theater.player_points():
                for front_line in cp.front_lines.values():
                    front_line.update_position()
                    events.update_front_line(front_line)
                cp.base.affect_strength(+PLAYER_BASE_STRENGTH_RECOVERY)

        # We don't actually advance time or change the conditions between turn 0 and
        # turn 1.
        if self.turn > 1:
            self.conditions = self.generate_conditions()

    def begin_turn_0(self, squadrons_start_full: bool) -> None:
        """Initialization for the first turn of the game."""
        from .sim import GameUpdateEvents

        # Build the IADS Network
        with logged_duration("Generate IADS Network"):
            self.theater.iads_network.initialize_network(self.theater.ground_objects)

        for control_point in self.theater.controlpoints:
            control_point.initialize_turn_0(self.laser_code_registry)
            for tgo in control_point.connected_objectives:
                self.db.tgos.add(tgo.id, tgo)

        # Correct the heading of specifc TGOs, can only be done after init turn 0
        for tgo in self.theater.ground_objects:
            # If heading is 0 then we change the orientation to head towards the
            # closest conflict. Heading of 0 means that the campaign designer wants
            # to determine the heading automatically by liberation. Values other
            # than 0 mean it is custom defined.
            if tgo.should_head_to_conflict and tgo.heading.degrees == 0:
                # Calculate the heading to conflict
                heading = self.theater.heading_to_conflict_from(tgo.position)
                # Rotate the whole TGO with the new heading
                tgo.rotate(heading or tgo.heading)

        self.blue.preinit_turn_0(squadrons_start_full)
        self.red.preinit_turn_0(squadrons_start_full)
        # TODO: Check for overfull bases.
        # We don't need to actually stream events for turn zero because we haven't given
        # *any* state to the UI yet, so it will need to do a full draw once we do.
        self.initialize_turn(
            GameUpdateEvents(), squadrons_start_full=squadrons_start_full
        )
        self.refresh_high_command()

    def pass_turn(self, no_action: bool = False) -> None:
        """Ends the current turn and initializes the new turn.

        Called both when skipping a turn or by ending the turn as the result of combat.

        Args:
            no_action: True if the turn was skipped.
        """
        from .server import EventStream
        from .sim import GameUpdateEvents

        events = GameUpdateEvents()

        logging.info("Pass turn")
        with logged_duration("Turn finalization"):
            self.finish_turn(events, no_action)
            # What a satellite would have found as the new turn begins. A site put
            # up or moved later in the turn is not in the picture.
            remember_positions(
                tgo
                for cp in self.theater.controlpoints
                for tgo in cp.connected_objectives
            )

        with logged_duration("Turn initialization"):
            self.initialize_turn(events)
        self.refresh_high_command()

        EventStream.put_nowait(events)

        # Autosave progress
        persistency.autosave(self)

    def refresh_high_command(self) -> None:
        """Close the High Command's orders that are over, pay the prizes of those
        achieved, and make new ones. Only at the start of a turn: a turn re-initialised
        for a purchase is the same turn.

        A fault here must not stop the turn, so it is logged and the orders wait for
        the next one.
        """
        if self.check_win_loss() is not TurnState.CONTINUE:
            return
        try:
            with logged_duration("High Command orders"):
                closed = self.high_command.refresh(self)
                for line in self.high_command.pay(self, closed):
                    self.message("High Command", line)
        except Exception:
            logging.exception("Could not refresh the High Command's orders")

    def check_win_loss(self) -> TurnState:
        if not self.theater.player_points(state_check=True):
            return TurnState.LOSS

        if not self.theater.enemy_points(state_check=True):
            return TurnState.WIN

        return TurnState.CONTINUE

    def set_bullseye(self) -> None:
        player_cp, enemy_cp = self.theater.closest_opposing_control_points()
        self.blue.bullseye = Bullseye(enemy_cp.position)
        self.red.bullseye = Bullseye(player_cp.position)

    def begin_live_pilots(self) -> None:
        """Start the career ladder, once, when Live Pilots is switched on.

        Every pilot already in the campaign keeps the rank he has, seeded with what
        that rank costs. Nobody is demoted and nobody gets a windfall; the next
        promotion is paid for in full.

        The rank is read from the difficulty page rather than from what the pilot
        currently flies at, because the moment the feature is switched on the floor
        under him is the bottom rung. Seeding from the floor instead would hand
        every wing whose coalition was already at Cadet a career starting from zero
        while the other side kept its rank -- which is what it did.
        """
        if getattr(self, "live_pilots_initialized", False):
            return
        for coalition in (self.blue, self.red):
            for squadron in coalition.air_wing.iter_squadrons():
                earned = experience_for_skill(squadron.difficulty_skill, self.settings)
                for pilot in list(squadron.pilot_pool) + list(squadron.current_roster):
                    pilot.record.xp = max(pilot.record.xp, earned)
        self.live_pilots_initialized = True
        logging.info("Live Pilots started: every pilot seeded with his rank")

    def plan_ground_war(self) -> None:
        """Decide which of each base's vehicles deploy to which front.

        Planned from ``base.armor`` as it stands *now*, and deliberately not cached
        across the turn: ordering a transfer debits the origin the moment it is
        created, so a plan made at the start of the turn deploys units the campaign
        no longer owns. That is not a cosmetic disagreement -- the front line battle
        is resolved from the books, so a player who moved his army mid-turn watched
        it hold the line on the map and lose the ground war for being absent.
        """
        self.ground_planners = {}
        for cp in self.theater.controlpoints:
            if cp.has_frontline:
                gplanner = GroundPlanner(cp, self)
                gplanner.plan_groundwar()
                self.ground_planners[cp.id] = gplanner

    def initialize_turn(
        self,
        events: GameUpdateEvents,
        for_red: bool = True,
        for_blue: bool = True,
        squadrons_start_full: bool = False,
    ) -> None:
        """Performs turn initialization for the specified players.

        Turn initialization performs all of the beginning-of-turn actions. *End-of-turn*
        processing happens in `pass_turn` (despite the name, it's called both for
        skipping the turn and ending the turn after combat).

        Special care needs to be taken here because initialization can occur more than
        once per turn. A number of events can require re-initializing a turn:

        * Cheat capture. Bases changing hands invalidates many missions in both ATOs,
          purchase orders, threat zones, transit networks, etc. Practically speaking,
          after a base capture the turn needs to be treated as fully new. The game might
          even be over after a capture.
        * Cheat front line position. CAS missions are no longer in the correct location,
          and the ground planner may also need changes.
        * Selling/buying units at TGOs. Selling a TGO might leave missions in the ATO
          with invalid targets. Buying a new SAM (or even replacing some units in a SAM)
          potentially changes the threat zone and may alter mission priorities and
          flight planning.

        Most of the work is delegated to initialize_turn_for, which handles the
        coalition-specific turn initialization. In some cases only one coalition will be
        (re-) initialized. This is the case when buying or selling TGO units, since we
        don't want to force the player to redo all their planning just because they
        repaired a SAM, but should replan opfor when that happens. On the other hand,
        base captures are significant enough (and likely enough to be the first thing
        the player does in a turn) that we replan blue as well. Front lines are less
        impactful but also likely to be early, so they also cause a blue replan.

        Args:
            events: Game update event container for turn initialization.
            for_red: True if opfor should be re-initialized.
            for_blue: True if the player coalition should be re-initialized.
            squadrons_start_full: True if generator setting was checked.
        """
        # Check for win or loss condition FIRST!
        turn_state = self.check_win_loss()
        if turn_state in (TurnState.LOSS, TurnState.WIN):
            return self.process_win_loss(turn_state)

        # Update bullseye positions for blue & red
        self.set_bullseye()

        # Update statistics
        self.game_stats.update(self)

        # Plan flights & combat for next turn
        with logged_duration("Threat zone computation"):
            self.compute_threat_zones(events)

        # Plan Coalition specific turn
        if for_blue:
            self.blue.initialize_turn(self.turn == 0 and squadrons_start_full, events)
        if for_red:
            self.red.initialize_turn(self.turn == 0 and squadrons_start_full, events)

        self.plan_ground_war()

        # Update cull zones
        with logged_duration("Computing culling positions"):
            self.compute_unculled_zones(events)

        events.begin_new_turn()

    def message(self, title: str, text: str = "") -> None:
        self.informations.append(Information(title, text, turn=self.turn))

    @property
    def current_turn_time_of_day(self) -> TimeOfDay:
        tod_turn = max(0, self.turn - 1) + self.time_of_day_offset_for_start_time
        return list(TimeOfDay)[tod_turn % 4]

    @property
    def current_day(self) -> date:
        return self.date + timedelta(days=self.turn // 4)

    def next_unit_id(self) -> int:
        """
        Next unit id for pre-generated units
        """
        self.current_unit_id += 1
        return self.current_unit_id

    def next_group_id(self) -> int:
        """
        Next unit id for pre-generated units
        """
        self.current_group_id += 1
        return self.current_group_id

    def compute_transit_network_for(self, player: Player) -> TransitNetwork:
        return TransitNetworkBuilder(self.theater, player).build()

    def compute_threat_zones(self, events: GameUpdateEvents) -> None:
        self.blue.compute_threat_zones(events)
        self.red.compute_threat_zones(events)
        self.blue.compute_nav_meshes(events)
        self.red.compute_nav_meshes(events)

    def threat_zone_for(self, player: Player) -> ThreatZones:
        return self.coalition_for(player).threat_zone

    def navmesh_for(self, player: Player) -> NavMesh:
        return self.coalition_for(player).nav_mesh

    def compute_unculled_zones(self, events: GameUpdateEvents) -> None:
        """
        Compute the current conflict position(s) used for culling calculation
        """
        from game.missiongenerator.frontlineconflictdescription import (
            FrontLineConflictDescription,
        )

        zones = []

        # By default, use the existing frontline conflict position
        for front_line in self.theater.conflicts():
            position = FrontLineConflictDescription.frontline_position(
                front_line, self.theater, self.settings
            )
            zones.append(position[0])
            zones.append(front_line.blue_cp.position)
            zones.append(front_line.red_cp.position)

        for cp in self.theater.controlpoints:
            # If do_not_cull_carrier is enabled, add carriers as culling point
            if self.settings.perf_do_not_cull_carrier:
                if cp.is_carrier or cp.is_lha:
                    zones.append(cp.position)

        # If there is no conflict take the center point between the two nearest opposing bases
        if len(zones) == 0:
            cpoint = None
            min_distance = math.inf
            for cp in self.theater.player_points():
                for cp2 in self.theater.enemy_points():
                    d = cp.position.distance_to_point(cp2.position)
                    if d < min_distance:
                        min_distance = d
                        cpoint = cp.position.midpoint(cp2.position)
                        zones.append(cp.position)
                        zones.append(cp2.position)
                        break
                if cpoint is not None:
                    break
            if cpoint is not None:
                zones.append(cpoint)

        packages = itertools.chain(self.blue.ato.packages, self.red.ato.packages)
        for package in packages:
            if package.primary_task in [
                FlightType.BARCAP,
                FlightType.TRANSPORT,
                FlightType.AEWC,
                FlightType.REFUELING,
                FlightType.RECOVERY,
            ]:
                # BARCAPs will be planned at most locations on smaller theaters,
                # rendering culling fairly useless. BARCAP packages don't really
                # need the ground detail since they're defensive. SAMs nearby
                # are only interesting if there are enemies in the area, and if
                # there are they won't be culled because of the enemy's mission.

                # Don't create culling exclusion zones around FlightType.TRANSPORT,
                # FlightType.AEWC & FlightType.REFUELING mission targets.
                continue
            zones.append(package.target.position)

        # A cruise missile raid hits whatever the planner picked, which is usually a
        # rear-area object no package is fragged against, so nothing else keeps it out
        # of the cull. Culled, the target TGO is never generated and the missiles
        # visibly demolish the map's bare scenery at those coordinates while the
        # campaign records nothing at all. Un-cull every planned raid target, and every
        # launching ship group so a standalone shooter is there for the F10
        # call-for-fire (carrier groups are already covered above).
        if self.settings.plugin_option_or("cruisemissiles", False):
            from game.cruise_raids import lacm_ships, plan_cruise_raids

            for raid in plan_cruise_raids(self):
                zones.append(Point(raid.target_x, raid.target_y, self.theater.terrain))
            for lacm_ship in lacm_ships(self):
                zones.append(lacm_ship.position)

        self.__culling_zones = zones
        events.update_unculled_zones(zones)

    @staticmethod
    def _carcass_key(data: dict[str, Union[float, str]]) -> tuple[str, int, int]:
        # (type, x, z) quantized to 1 m identifies one carcass. Statics that
        # Escalation respawns ALIVE each mission (FARP fuel/ammo depots,
        # motorpool Garage_A) fire a fresh S_EVENT_DEAD at the same deterministic
        # spot every time they are bombed; keying on this collapses them to a
        # single wreck. Type is in the key so adjacent different-type statics
        # (FARP fuel vs ammo) never merge; 1 m rounding absorbs Lua->JSON float
        # jitter (distinct same-type statics are always spaced well over a metre).
        # Precondition: data must carry "x" and "z" (raises KeyError otherwise).
        # For entries of unknown provenance use _safe_carcass_key instead.
        return (
            str(data.get("type", "")),
            round(cast(float, data["x"])),
            round(cast(float, data["z"])),
        )

    @staticmethod
    def _safe_carcass_key(
        data: dict[str, Union[float, str]],
    ) -> tuple[str, int, int] | None:
        # None for an unkeyable legacy entry (missing/garbled coords). Callers
        # treat None as "no match", so such entries are never merged nor crash
        # the dedup scan — matching _dedup's keep-them-untouched behaviour.
        # OverflowError: round(±inf); ValueError: round(nan); KeyError: no x/z;
        # TypeError: non-float coord.
        try:
            return Game._carcass_key(data)
        except (KeyError, TypeError, ValueError, OverflowError):
            return None

    def add_destroyed_units(self, data: dict[str, Union[float, str]]) -> None:
        pos = Point(
            cast(float, data["x"]), cast(float, data["z"]), self.theater.terrain
        )
        if not self.theater.is_on_land(pos):
            return
        # Bound to one carcass per (type, cell): a respawned-alive static bombed
        # every mission would otherwise stack a new hidden wreck each turn.
        # _safe_carcass_key throughout so a garbled coord (missing/inf/nan) never
        # crashes turn commit; an unkeyable entry (key None) can't be deduped, so
        # it's just recorded — mirroring _dedup's keep-them-untouched behaviour.
        key = self._safe_carcass_key(data)
        if key is not None and any(
            self._safe_carcass_key(d) == key for d in self.__destroyed_units
        ):
            return
        self.__destroyed_units.append(data)

    def get_destroyed_units(self) -> list[dict[str, Union[float, str]]]:
        return self.__destroyed_units

    def _dedup_destroyed_units(self) -> None:
        # Heal saves written before the insert-path dedup existed: collapse
        # stacked carcasses to one per (type, cell). First occurrence wins,
        # order preserved.
        seen: set[tuple[str, int, int]] = set()
        deduped: list[dict[str, Union[float, str]]] = []
        for d in self.__destroyed_units:
            key = self._safe_carcass_key(d)
            if key is None:
                deduped.append(d)  # unkeyable legacy entry: keep it, never dedup
                continue
            if key not in seen:
                seen.add(key)
                deduped.append(d)
        self.__destroyed_units = deduped

    def prune_destroyed_units(self, index: LiveUnitIndex) -> None:
        # Drop any carcass a live unit now occupies: once something alive stands at
        # a cell, its old wreck-history there is stale (the list is cosmetic-only).
        # Deleting (vs keeping-hidden) avoids two-husk stacking when a site is
        # rebuilt as a different type and re-killed. Garbled-coord entries can't be
        # matched, so they're kept — consistent with _safe_carcass_key.
        kept: list[dict[str, Union[float, str]]] = []
        for d in self.__destroyed_units:
            try:
                x = cast(float, d["x"])
                z = cast(float, d["z"])
                occupied = index.occupied(float(x), float(z))
            except (KeyError, TypeError, ValueError):
                # Missing x/z (KeyError) or a non-numeric coord (TypeError/
                # ValueError) -> unmatchable, keep the entry. Non-finite coords
                # don't reach here: LiveUnitIndex.occupied is total over floats.
                kept.append(d)
                continue
            if not occupied:
                kept.append(d)
        self.__destroyed_units = kept

    def position_culled(self, pos: Point) -> bool:
        """
        Check if unit can be generated at given position depending on culling performance settings
        :param pos: Position you are tryng to spawn stuff at
        :return: True if units can not be added at given position
        """
        if not self.settings.perf_culling:
            return False
        for z in self.__culling_zones:
            if z.distance_to_point(pos) < self.settings.perf_culling_distance * 1000:
                return False
        return True

    def skynet_culled(self, tgo: TheaterGroundObject) -> bool:
        """True if this object should be left out of the Skynet IADS.

        A different question from iads_considerate_culling, which asks whether the
        object is generated at all. What is culled here is still in the mission and
        still fights: it is simply not handed to Skynet, so it never goes dark, never
        shares a contact and never reacts to a HARM. tgogenerator forces it to red
        alert to match, because a site nobody wakes would otherwise sit at green.

        Independent of perf_culling on purpose -- that one defaults to off, which is
        why Skynet is handed the whole map today.
        """
        radius = self.settings.plugin_option_or("skynetiads.radiusKm", 0)
        if radius <= 0:
            return False
        if not self.__culling_zones:
            # No conflict located yet. Culling everything would hand Skynet nothing.
            return False
        if not isinstance(tgo, (SamGroundObject, EwrGroundObject)):
            # Only radars cost Skynet anything, and only radars can be left out
            # safely. Skynet reads an absent dependency as a working one --
            # genericCheckOneObjectIsAlive starts at `#objects == 0` and
            # isCommandCenterUsable returns true on an empty list -- so dropping a
            # command centre, comms tower or power station does not quieten the
            # network, it tells the network everything is fine. A bombed power
            # station outside the radius would switch its SAMs back on, and a
            # coalition whose last command centre fell outside would regain command
            # by having it culled. They stay in: they are cheap, and their absence
            # is a lie.
            return False
        limit = radius * 1000
        return not any(
            zone.distance_to_point(tgo.position) < limit
            for zone in self.__culling_zones
        )

    def iads_considerate_culling(self, tgo: TheaterGroundObject) -> bool:
        if not self.settings.perf_do_not_cull_threatening_iads:
            return self.position_culled(tgo.position)
        else:
            if self.settings.perf_culling:
                if isinstance(tgo, EwrGroundObject):
                    max_detection_range = tgo.max_detection_range().meters
                    for z in self.__culling_zones:
                        seperation = z.distance_to_point(tgo.position)
                        # Don't cull EWR if in detection range.
                        if seperation < max_detection_range:
                            return False
                if isinstance(tgo, SamGroundObject):
                    max_threat_range = tgo.max_threat_range().meters
                    for z in self.__culling_zones:
                        seperation = z.distance_to_point(tgo.position)
                        # Create a 12nm buffer around nearby SAMs.
                        respect_bubble = (
                            max_threat_range + Distance.from_nautical_miles(12).meters
                        )
                        if seperation < respect_bubble:
                            return False
            return self.position_culled(tgo.position)

    def get_culling_zones(self) -> list[Point]:
        """
        Check culling points
        :return: List of culling zones
        """
        return self.__culling_zones

    def process_win_loss(self, turn_state: TurnState) -> None:
        if turn_state is TurnState.WIN:
            self.message(
                "Congratulations, you are victorious! Start a new campaign to continue."
            )
        elif turn_state is TurnState.LOSS:
            self.message("Game Over, you lose. Start a new campaign to continue.")

    def ato_has_clients(self) -> bool:
        for package in self.blue.ato.packages:
            for flight in package.flights:
                if flight.client_count > 0:
                    return True
        return False
