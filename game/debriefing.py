from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
    Union,
)
from uuid import UUID

from game.ato.starttype import StartType
from game.dcs.aircrafttype import AircraftType
from game.dcs.groundunittype import GroundUnitType
from game.squadrons.experience import PilotOutcomes
from game.theater import Airfield, ControlPoint, Player

if TYPE_CHECKING:
    from game import Game
    from game.ato.flight import Flight
    from game.sim.simulationresults import SimulationResults
    from game.transfers import CargoShip
    from game.unitmap import (
        AirliftUnits,
        ConvoyUnit,
        FlyingUnit,
        FrontLineUnit,
        TheaterUnitMapping,
        UnitMap,
        SceneryObjectMapping,
    )

DEBRIEFING_LOG_EXTENSION = "log"

#: A no-shooter air loss within this many seconds of a flightmate's confirmed
#: weapon-kill is treated as the same attack (an "indirect kill"), not a crash.
INDIRECT_KILL_WINDOW_S = 5.0


@dataclass(frozen=True)
class AirLosses:
    player: list[FlyingUnit]
    enemy: list[FlyingUnit]

    @property
    def losses(self) -> Iterator[FlyingUnit]:
        return itertools.chain(self.player, self.enemy)

    def by_type(self, player: Player) -> Dict[AircraftType, int]:
        losses_by_type: Dict[AircraftType, int] = defaultdict(int)
        losses = self.player if player.is_blue else self.enemy
        for loss in losses:
            losses_by_type[loss.flight.unit_type] += 1
        return losses_by_type

    def surviving_flight_members(self, flight: Flight) -> int:
        losses = 0
        for loss in self.losses:
            if loss.flight == flight:
                losses += 1
        return flight.count - losses


@dataclass
class GroundLosses:
    player_front_line: List[FrontLineUnit] = field(default_factory=list)
    enemy_front_line: List[FrontLineUnit] = field(default_factory=list)

    player_motorpool: List[FrontLineUnit] = field(default_factory=list)
    enemy_motorpool: List[FrontLineUnit] = field(default_factory=list)

    player_convoy: List[ConvoyUnit] = field(default_factory=list)
    enemy_convoy: List[ConvoyUnit] = field(default_factory=list)

    player_cargo_ships: List[CargoShip] = field(default_factory=list)
    enemy_cargo_ships: List[CargoShip] = field(default_factory=list)

    player_airlifts: List[AirliftUnits] = field(default_factory=list)
    enemy_airlifts: List[AirliftUnits] = field(default_factory=list)

    player_ground_objects: List[TheaterUnitMapping] = field(default_factory=list)
    enemy_ground_objects: List[TheaterUnitMapping] = field(default_factory=list)

    player_scenery: List[SceneryObjectMapping] = field(default_factory=list)
    enemy_scenery: List[SceneryObjectMapping] = field(default_factory=list)

    player_airfields: List[Airfield] = field(default_factory=list)
    enemy_airfields: List[Airfield] = field(default_factory=list)


@dataclass(frozen=True)
class BaseCaptureEvent:
    control_point: ControlPoint
    captured_by_player: Player


@dataclass(frozen=True)
class SideLossCounts:
    aircraft: int
    front_line: int
    motorpool: int
    convoy: int
    cargo_ships: int
    airlift_cargo: int
    ground_objects: int
    scenery: int
    bases_lost: int
    runways_destroyed: int


@dataclass(frozen=True)
class StateData:
    #: True if the mission ended. If False, the mission exited abnormally.
    mission_ended: bool

    #: Names of aircraft units that were killed during the mission.
    killed_aircraft: List[str]

    #: Names of vehicles, ships or buildings that were killed during the mission.
    killed_ground_units: List[str]

    #: List of descriptions of destroyed statics. Format of each element is a mapping of
    #: the coordinate type ("x", "y", "z", "type", "orientation") to the value.
    destroyed_statics: List[dict[str, Union[float, str]]]

    #: Mangled names of bases that were captured during the mission.
    base_capture_events: List[str]

    #: Structured S_EVENT_KILL records ({target, initiator, initiator_type,
    #: initiator_player, weapon}), used to attribute air losses in the UI feed.
    kill_details: List[Any] = field(default_factory=list)

    #: One record per attacking aircraft per target it hit, whether or not the
    #: target died. Written by the base plugin for pilot experience.
    hit_details: List[Any] = field(default_factory=list)

    #: DCS mission model time in seconds (timer.getTime()); None for older states.
    model_time: Optional[float] = None

    #: Unit names (DCS getName) that fired S_EVENT_TAKEOFF. A ground-start unit
    #: absent from this list was destroyed before it ever left the ground.
    took_off: List[str] = field(default_factory=list)

    #: Unit name -> first death-event mission time (s), for indirect-kill timing.
    death_times: Dict[str, float] = field(default_factory=dict)

    #: ``(ship_group_name, fired)`` per ship group that launched cruise missiles this
    #: mission, mirrored by the cruisemissiles plugin. reconcile_cruise_missiles debits
    #: the persisted campaign magazine by ``fired`` at the turn boundary -- the only
    #: debit site, so regenerating a mission never double-charges. Empty when the
    #: feature is off or the state file predates it.
    cruise_missiles_state: List[Tuple[str, int]] = field(default_factory=list)

    #: One flat record per event the Mission Log plugin saw -- kills, losses,
    #: crashes, interceptions, missiles defended against -- in the order they
    #: happened, each with its mission time.
    #: Empty when the plugin is off, and absent from every state file written
    #: before the feature, so it is parsed defensively like everything else here.
    mission_log_events: List[Dict[str, Any]] = field(default_factory=list)

    #: ``(naval_group_name, fired)`` per naval group that fired ANTI-SHIP missiles this
    #: mission, mirrored by the navalmagazines plugin. reconcile_naval_magazines debits
    #: the persisted campaign magazine by ``fired`` at the turn boundary -- the only
    #: debit site, so re-generating a mission never double-counts. The weapon set is
    #: disjoint from cruise_missiles_state's land-attack families, so a shot is never
    #: charged to both. Empty on pre-feature state files and when the feature is off.
    naval_magazines_state: List[Tuple[str, int]] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Dict[str, Any], unit_map: UnitMap) -> StateData:
        def clean_unit_list(unit_list: List[Any]) -> List[str]:
            # Cleans list of units in state.json by
            # - Removing duplicates. Airfields emit a new "dead" event every time a bomb
            #   is dropped on them when they've already dead.
            # - Normalise dead map objects (which are ints) to strings. The unit map
            #   only stores strings
            # dict.fromkeys dedups while preserving first-seen order, so the cumulative
            # state re-parsed every poll yields a stable append-only prefix (consumers
            # that diff by position, e.g. the mission panel event feed, rely on this).
            return list(dict.fromkeys(str(unit) for unit in unit_list))

        killed_aircraft = []
        killed_ground_units = []

        # Process killed units from S_EVENT_UNIT_LOST, S_EVENT_CRASH, S_EVENT_DEAD & S_EVENT_KILL
        # Try to process every event that could indicate a unit was killed, even if it is
        # inefficient and results in duplication as the logic DCS uses to trigger the various
        # event types is not clear and may change over time.
        killed_units = clean_unit_list(
            data.get("unit_lost_events", [])
            + data.get("kill_events", [])
            + data.get("crash_events", [])
            + data.get("dead_events", [])
        )
        for unit in killed_units:  # organize killed units into aircraft vs ground
            if unit_map.flight(unit) is not None:
                killed_aircraft.append(unit)
            else:
                killed_ground_units.append(unit)

        # Lua tables serialise as a JSON object, but an empty one encodes as [].
        raw_took_off = data.get("took_off", {})
        took_off = (
            list(raw_took_off.keys())
            if isinstance(raw_took_off, dict)
            else list(raw_took_off or [])
        )
        raw_death_times = data.get("death_time", {})
        death_times = raw_death_times if isinstance(raw_death_times, dict) else {}

        def parse_group_fired_state(raw: Any) -> List[Tuple[str, int]]:
            # The cruisemissiles and navalmagazines plugins both write
            # {group=, fired=} per launching group;
            # the Lua JSON encoder yields [] when there were none, and a state file
            # written before the feature omits the key entirely. Pull the pair
            # defensively: a malformed or unnamed entry must not break the debrief.
            if not isinstance(raw, list):
                return []
            out: List[Tuple[str, int]] = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                group = entry.get("group")
                fired = entry.get("fired")
                if isinstance(group, str) and group and isinstance(fired, (int, float)):
                    out.append((group, int(fired)))
            return out

        def parse_log_events(raw: Any) -> List[Dict[str, Any]]:
            # The Lua side writes a contiguous array of flat tables, which the
            # encoder yields as a list of objects -- and as [] when there were
            # none. Anything else is a state file this build does not
            # understand, and a log is never worth breaking a debrief for.
            if not isinstance(raw, list):
                return []
            return [entry for entry in raw if isinstance(entry, dict)]

        return cls(
            mission_ended=data.get("mission_ended", False),
            killed_aircraft=killed_aircraft,
            killed_ground_units=killed_ground_units,
            destroyed_statics=data.get("destroyed_objects_positions", []),
            base_capture_events=data.get("base_capture_events", []),
            kill_details=data.get("kill_details", []),
            hit_details=data.get("hit_details", []),
            model_time=data.get("model_time"),
            took_off=took_off,
            death_times=death_times,
            cruise_missiles_state=parse_group_fired_state(
                data.get("cruise_missiles_state", [])
            ),
            naval_magazines_state=parse_group_fired_state(
                data.get("naval_magazines_state", [])
            ),
            mission_log_events=parse_log_events(data.get("mission_log_events", [])),
        )


class Debriefing:
    def __init__(
        self, state_data: Dict[str, Any], game: Game, unit_map: UnitMap
    ) -> None:
        self.state_data = StateData.from_json(state_data, unit_map)
        self.game = game
        self.unit_map = unit_map

        self.player_country = game.blue.faction.country.name
        self.enemy_country = game.red.faction.country.name

        # id(loss) -> its DCS unit name, populated by dead_aircraft(); lets the
        # indirect-kill logic look up per-loss takeoff/death-time state.
        self._loss_name_by_id: Dict[int, str] = {}
        #: What became of the aircrew, filled in by the results processor as it
        #: commits losses and experience, and read by the debriefing window.
        self.pilot_outcomes = PilotOutcomes()
        self.air_losses = self.dead_aircraft()
        self.ground_losses = self.dead_ground_units()
        self.base_captures = self.base_capture_events()
        self.kill_info_by_unit_id = self._index_kill_details()
        # ids of air losses injected by the Escalation sim (no DCS kill record);
        # they are real combat losses, so is_non_combat_loss() must not refund them.
        self._sim_loss_ids: set[int] = set()
        # ids of air losses with no DCS shooter that are still combat kills:
        # destroyed parked (never took off) or downed in the same attack as a
        # confirmed weapon-kill flightmate. Counted, and shown as "indirect kill".
        self._indirect_loss_ids: set[int] = self._compute_indirect_loss_ids()

    def _index_kill_details(self) -> Dict[int, Dict[str, Any]]:
        """Map id(loss object) -> its S_EVENT_KILL detail (killer + weapon), for both
        air losses (FlyingUnit) and ground losses (FrontLineUnit/ConvoyUnit/...).

        Keyed by id() (not the object itself) because FlyingUnit holds a Pilot, an
        unhashable dataclass. The lookup side (the mission panel) keys by id(loss);
        those loss objects are the same instances unit_map resolves a name to, so
        identity matches. Wrapped defensively: this only feeds the UI feed, so a
        problem here must never break turn processing/debriefing construction.
        """
        index: Dict[int, Dict[str, Any]] = {}
        try:
            for detail in self.state_data.kill_details:
                if not isinstance(detail, dict):
                    continue
                name = detail.get("target")
                if not name:
                    continue
                obj = self._resolve_killed_object(str(name))
                if obj is not None:
                    index[id(obj)] = detail
        except Exception:
            logging.exception("Failed to index kill details; killer attribution off")
        return index

    def resolve_killed_object(self, name: str) -> Optional[Any]:
        """Public face of the name -> loss-object resolution, for callers that start
        from a kill detail rather than from a loss."""
        return self._resolve_killed_object(name)

    def _resolve_killed_object(self, name: str) -> Optional[Any]:
        """Resolve a killed unit name to its loss object, mirroring how
        dead_aircraft/dead_ground_units resolve names, so id() lines up."""
        um = self.unit_map
        obj: Optional[Any] = um.flight(name)
        if obj is not None:
            return obj
        obj = um.front_line_unit(name) or um.front_line_unit_from_tic_clone(name)
        if obj is not None:
            return obj
        for getter in (
            um.convoy_unit,
            um.cargo_ship,
            um.theater_units,
            um.scenery_object,
            um.motorpool_unit,
            um.airfield,
        ):
            obj = getter(name)
            if obj is not None:
                return obj
        # dead_ground_units retries statics under a " object" suffix; a kill detail for
        # one of those used to be resolved here as nothing and quietly dropped.
        if not name.endswith(" object"):
            return self._resolve_killed_object(f"{name} object")
        return None

    def _has_direct_shooter(self, loss: "FlyingUnit") -> bool:
        """True if DCS credited a weapon/SAM kill (not a collision) to this loss."""
        detail = self.kill_info_by_unit_id.get(id(loss))
        if not detail:
            return False
        initiator_type = detail.get("initiator_type")
        weapon = detail.get("weapon")
        has_shooter = bool(detail.get("initiator_player") or initiator_type)
        collision = bool(weapon and weapon == initiator_type)
        return has_shooter and not collision

    def _compute_indirect_loss_ids(self) -> set[int]:
        """Air losses with no DCS shooter that are still combat kills, not crashes.

        Both rules require corroborating combat nearby, so genuine AI crashes —
        including pre-takeoff ground mishaps (a rolling COLD/WARM/RUNWAY start can
        run off the end or clip another jet) — stay classified as crashes:

        1. Same attack: a loss within INDIRECT_KILL_WINDOW_S of a confirmed
           weapon-kill in its own flight. DCS dropped the kill attribution, which
           it does under heavy simultaneous-death load.
        2. Destroyed parked: a ground-start aircraft that never took off, lost
           while its own base was under attack (a confirmed weapon-kill from the
           same departure within the window). A never-took-off loss with no attack
           on its base is left as a crash.

        DCS-credited kills, and losses with no confirmed kill nearby, are untouched
        so the 'crashes don't count' doctrine still ignores genuine AI crashes.
        """
        indirect: set[int] = set()
        try:
            losses = list(self.air_losses.player) + list(self.air_losses.enemy)
            death_times = self.state_data.death_times or {}
            took_off = set(self.state_data.took_off or [])
            # Confirmed-weapon-kill death times, grouped by flight and by the base
            # they flew from, so a no-shooter loss can be tied to a real attack.
            direct_times_by_flight: Dict[int, List[float]] = defaultdict(list)
            direct_times_by_base: Dict[int, List[float]] = defaultdict(list)
            for loss in losses:
                if not self._has_direct_shooter(loss):
                    continue
                name = self._loss_name_by_id.get(id(loss))
                flight = getattr(loss, "flight", None)
                t = death_times.get(name) if name else None
                if t is None or flight is None:
                    continue
                direct_times_by_flight[id(flight)].append(t)
                departure = getattr(flight, "departure", None)
                if departure is not None:
                    direct_times_by_base[id(departure)].append(t)

            def near(t: Optional[float], times: List[float]) -> bool:
                return t is not None and any(
                    abs(t - mt) <= INDIRECT_KILL_WINDOW_S for mt in times
                )

            for loss in losses:
                if self._has_direct_shooter(loss):
                    continue
                name = self._loss_name_by_id.get(id(loss))
                flight = getattr(loss, "flight", None)
                if name is None or flight is None:
                    continue
                t = death_times.get(name)
                # 1. Same attack as a confirmed weapon-kill in its own flight.
                if near(t, direct_times_by_flight.get(id(flight), [])):
                    indirect.add(id(loss))
                    continue
                # 2. Destroyed parked while its base was under attack.
                start_type = getattr(flight, "start_type", None)
                departure = getattr(flight, "departure", None)
                if (
                    start_type is not None
                    and start_type is not StartType.IN_FLIGHT
                    and name not in took_off
                    and departure is not None
                    and near(t, direct_times_by_base.get(id(departure), []))
                ):
                    indirect.add(id(loss))
        except Exception:
            logging.exception("Failed to compute indirect-kill losses")
        return indirect

    def died_on_the_ground(self, loss: FlyingUnit) -> bool:
        """Whether the aircraft was destroyed before it took off: parked, or starting
        up on the ground. One lost in Escalation's own simulation of the air war never
        was, since it has no name to look up."""
        flight = loss.flight
        if getattr(flight, "parked_reserve", False):
            return True
        name = self._loss_name_by_id.get(id(loss))
        if name is None:
            return False
        return flight.start_type is not StartType.IN_FLIGHT and name not in set(
            self.state_data.took_off or []
        )

    def is_indirect_kill(self, flying_unit: "FlyingUnit") -> bool:
        """True if this loss is counted as combat via inference (no direct DCS
        shooter): destroyed parked, or the same attack as a confirmed kill."""
        return id(flying_unit) in self._indirect_loss_ids

    def merge_simulation_results(self, results: SimulationResults) -> None:
        for air_loss in results.air_losses:
            self._sim_loss_ids.add(id(air_loss))
            if air_loss.flight.squadron.player.is_blue:
                self.air_losses.player.append(air_loss)
            else:
                self.air_losses.enemy.append(air_loss)

    def is_non_combat_loss(self, flying_unit: "FlyingUnit") -> bool:
        """True if this air loss was a non-combat write-off: a crash, a collision,
        or a death with no shooter credited by DCS — as opposed to being shot down
        by a weapon or SAM. Escalation-sim combat losses (no DCS kill record) are
        NOT treated as crashes, nor are inferred 'indirect' kills (destroyed
        parked, or the same attack as a confirmed weapon-kill flightmate)."""
        if id(flying_unit) in self._sim_loss_ids:
            return False
        if id(flying_unit) in self._indirect_loss_ids:
            return False
        detail = self.kill_info_by_unit_id.get(id(flying_unit))
        if detail:
            initiator_type = detail.get("initiator_type")
            weapon = detail.get("weapon")
            has_shooter = bool(detail.get("initiator_player") or initiator_type)
            collision = bool(weapon and weapon == initiator_type)
            if has_shooter and not collision:
                return False  # shot down by a weapon / SAM
        return True

    @property
    def front_line_losses(self) -> Iterator[FrontLineUnit]:
        yield from self.ground_losses.player_front_line
        yield from self.ground_losses.enemy_front_line

    @property
    def motorpool_losses(self) -> Iterator[FrontLineUnit]:
        yield from self.ground_losses.player_motorpool
        yield from self.ground_losses.enemy_motorpool

    @property
    def convoy_losses(self) -> Iterator[ConvoyUnit]:
        yield from self.ground_losses.player_convoy
        yield from self.ground_losses.enemy_convoy

    @property
    def cargo_ship_losses(self) -> Iterator[CargoShip]:
        yield from self.ground_losses.player_cargo_ships
        yield from self.ground_losses.enemy_cargo_ships

    @property
    def airlift_losses(self) -> Iterator[AirliftUnits]:
        yield from self.ground_losses.player_airlifts
        yield from self.ground_losses.enemy_airlifts

    @property
    def ground_object_losses(self) -> Iterator[TheaterUnitMapping]:
        yield from self.ground_losses.player_ground_objects
        yield from self.ground_losses.enemy_ground_objects

    @property
    def scenery_object_losses(self) -> Iterator[SceneryObjectMapping]:
        yield from self.ground_losses.player_scenery
        yield from self.ground_losses.enemy_scenery

    @property
    def damaged_runways(self) -> Iterator[Airfield]:
        yield from self.ground_losses.player_airfields
        yield from self.ground_losses.enemy_airfields

    @cached_property
    def _casualties_by_origin(self) -> Dict[ControlPoint, int]:
        # commit_front_line_battle_impact() calls casualty_count() twice per
        # front-line pair; computing this once avoids re-scanning every
        # front-line loss on each call (O(pairs x losses), thousands per mission).
        counts: Dict[ControlPoint, int] = defaultdict(int)
        for loss in self.front_line_losses:
            counts[loss.origin] += 1
        return counts

    def casualty_count(self, control_point: ControlPoint) -> int:
        return self._casualties_by_origin.get(control_point, 0)

    def front_line_losses_by_type(self, player: Player) -> dict[GroundUnitType, int]:
        losses_by_type: dict[GroundUnitType, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_front_line
        else:
            losses = self.ground_losses.enemy_front_line
        for loss in losses:
            losses_by_type[loss.unit_type] += 1
        return losses_by_type

    def motorpool_losses_by_type(self, player: Player) -> dict[GroundUnitType, int]:
        losses_by_type: dict[GroundUnitType, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_motorpool
        else:
            losses = self.ground_losses.enemy_motorpool
        for loss in losses:
            losses_by_type[loss.unit_type] += 1
        return losses_by_type

    def convoy_losses_by_type(self, player: Player) -> dict[GroundUnitType, int]:
        losses_by_type: dict[GroundUnitType, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_convoy
        else:
            losses = self.ground_losses.enemy_convoy
        for loss in losses:
            losses_by_type[loss.unit_type] += 1
        return losses_by_type

    def cargo_ship_losses_by_type(self, player: Player) -> dict[GroundUnitType, int]:
        losses_by_type: dict[GroundUnitType, int] = defaultdict(int)
        if player.is_blue:
            ships = self.ground_losses.player_cargo_ships
        else:
            ships = self.ground_losses.enemy_cargo_ships
        for ship in ships:
            for unit_type, count in ship.units.items():
                losses_by_type[unit_type] += count
        return losses_by_type

    def airlift_losses_by_type(self, player: Player) -> dict[GroundUnitType, int]:
        losses_by_type: dict[GroundUnitType, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_airlifts
        else:
            losses = self.ground_losses.enemy_airlifts
        for loss in losses:
            for unit_type in loss.cargo:
                losses_by_type[unit_type] += 1
        return losses_by_type

    def ground_object_losses_by_type(self, player: Player) -> Dict[str, int]:
        losses_by_type: Dict[str, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_ground_objects
        else:
            losses = self.ground_losses.enemy_ground_objects
        for loss in losses:
            losses_by_type[loss.theater_unit.type.id] += 1
        return losses_by_type

    def scenery_losses_by_type(self, player: Player) -> Dict[str, int]:
        losses_by_type: Dict[str, int] = defaultdict(int)
        if player.is_blue:
            losses = self.ground_losses.player_scenery
        else:
            losses = self.ground_losses.enemy_scenery
        for loss in losses:
            losses_by_type[loss.trigger_zone.name] += 1
        return losses_by_type

    def loss_counts(self, player: Player) -> SideLossCounts:
        gl = self.ground_losses
        if player.is_blue:
            air = self.air_losses.player
            front_line = gl.player_front_line
            motorpool = gl.player_motorpool
            convoy = gl.player_convoy
            cargo_ships = gl.player_cargo_ships
            airlifts = gl.player_airlifts
            ground_objects = gl.player_ground_objects
            scenery = gl.player_scenery
            airfields = gl.player_airfields
        else:
            air = self.air_losses.enemy
            front_line = gl.enemy_front_line
            motorpool = gl.enemy_motorpool
            convoy = gl.enemy_convoy
            cargo_ships = gl.enemy_cargo_ships
            airlifts = gl.enemy_airlifts
            ground_objects = gl.enemy_ground_objects
            scenery = gl.enemy_scenery
            airfields = gl.enemy_airfields
        # Match the per-type casualty rows (and the campaign itself): when the
        # "crashes don't count" doctrine is on, non-combat write-offs are not
        # applied, so keep them out of the aircraft headline too.
        if getattr(self.game.settings, "ignore_non_combat_air_losses", False):
            aircraft_lost = sum(1 for loss in air if not self.is_non_combat_loss(loss))
        else:
            aircraft_lost = len(air)
        return SideLossCounts(
            aircraft=aircraft_lost,
            front_line=len(front_line),
            motorpool=len(motorpool),
            convoy=len(convoy),
            cargo_ships=len(cargo_ships),
            airlift_cargo=sum(len(loss.cargo) for loss in airlifts),
            ground_objects=len(ground_objects),
            scenery=len(scenery),
            bases_lost=sum(
                1
                for capture in self.base_captures
                if capture.captured_by_player == player.opponent
            ),
            runways_destroyed=len(airfields),
        )

    def dead_aircraft(self) -> AirLosses:
        player_losses = []
        enemy_losses = []
        for unit_name in self.state_data.killed_aircraft:
            aircraft = self.unit_map.flight(unit_name)
            if aircraft is None:
                logging.error(f"Could not find Flight matching {unit_name}")
                continue
            self._loss_name_by_id[id(aircraft)] = unit_name
            if aircraft.flight.departure.captured.is_blue:
                player_losses.append(aircraft)
            else:
                enemy_losses.append(aircraft)
        return AirLosses(player_losses, enemy_losses)

    def dead_ground_units(self) -> GroundLosses:
        losses = GroundLosses()
        untracked: List[str] = []
        for unit_name in self.state_data.killed_ground_units:
            front_line_unit = self.unit_map.front_line_unit(unit_name)
            if front_line_unit is None:
                # The TIC plugin respawns frontline units as renamed
                # single-unit clones; map clone deaths back to their group.
                front_line_unit = self.unit_map.front_line_unit_from_tic_clone(
                    unit_name
                )
            if front_line_unit is not None:
                if front_line_unit.origin.captured.is_blue:
                    losses.player_front_line.append(front_line_unit)
                else:
                    losses.enemy_front_line.append(front_line_unit)
                continue

            motorpool_unit = self.unit_map.motorpool_unit(unit_name)
            if motorpool_unit is not None:
                if motorpool_unit.origin.captured.is_blue:
                    losses.player_motorpool.append(motorpool_unit)
                else:
                    losses.enemy_motorpool.append(motorpool_unit)
                continue

            convoy_unit = self.unit_map.convoy_unit(unit_name)
            if convoy_unit is not None:
                if convoy_unit.convoy.player_owned.is_blue:
                    losses.player_convoy.append(convoy_unit)
                else:
                    losses.enemy_convoy.append(convoy_unit)
                continue

            cargo_ship = self.unit_map.cargo_ship(unit_name)
            if cargo_ship is not None:
                if cargo_ship.player_owned.is_blue:
                    losses.player_cargo_ships.append(cargo_ship)
                else:
                    losses.enemy_cargo_ships.append(cargo_ship)
                continue

            ground_object = self.unit_map.theater_units(unit_name)
            if ground_object is not None:
                if ground_object.theater_unit.ground_object.is_friendly(
                    to_player=Player.BLUE
                ):
                    losses.player_ground_objects.append(ground_object)
                else:
                    losses.enemy_ground_objects.append(ground_object)
                continue

            scenery_object = self.unit_map.scenery_object(unit_name)
            # Try appending object to the name, because we do this for building statics.
            if scenery_object is not None:
                if scenery_object.ground_unit.ground_object.is_friendly(
                    to_player=Player.BLUE
                ):
                    losses.player_scenery.append(scenery_object)
                else:
                    losses.enemy_scenery.append(scenery_object)
                continue

            airfield = self.unit_map.airfield(unit_name)
            if airfield is not None:
                if airfield.captured.is_blue:
                    losses.player_airfields.append(airfield)
                elif airfield.captured.is_red:
                    losses.enemy_airfields.append(airfield)
                continue

            # DCS appends " object" to static-object death names (e.g.
            # "1749 | X object"), but the unit map keys building statics without
            # it, so placed building statics (e.g. command centers) never matched
            # and their kills were silently dropped. Retry with the suffix
            # stripped so those objectives register.
            if unit_name.endswith(" object"):
                stripped = unit_name[: -len(" object")]
                theater_units = self.unit_map.theater_units(stripped)
                if theater_units is not None:
                    if theater_units.theater_unit.ground_object.is_friendly(
                        to_player=Player.BLUE
                    ):
                        losses.player_ground_objects.append(theater_units)
                    else:
                        losses.enemy_ground_objects.append(theater_units)
                    continue
                scenery_object = self.unit_map.scenery_object(stripped)
                if scenery_object is not None:
                    if scenery_object.ground_unit.ground_object.is_friendly(
                        to_player=Player.BLUE
                    ):
                        losses.player_scenery.append(scenery_object)
                    else:
                        losses.enemy_scenery.append(scenery_object)
                    continue

            # We don't track infantry or map/scenery objects, so a mission can
            # end with thousands of these unclaimed deaths. Collect them and log
            # one summary instead of a line each: per-unit logging here floods
            # the handlers (a file stat + flush per line, plus the log-window UI
            # hook) and froze the debrief for ~20s on busy missions.
            untracked.append(unit_name)

        if untracked:
            logging.debug(
                "%d untracked ground unit deaths had no effect (untracked "
                "infantry or map/scenery objects). First few: %s",
                len(untracked),
                ", ".join(untracked[:10]),
            )

        for unit_name in self.state_data.killed_aircraft:
            airlift_unit = self.unit_map.airlift_unit(unit_name)
            if airlift_unit is not None:
                if airlift_unit.transfer.player.is_blue:
                    losses.player_airlifts.append(airlift_unit)
                else:
                    losses.enemy_airlifts.append(airlift_unit)
                continue

        return losses

    def base_capture_events(self) -> List[BaseCaptureEvent]:
        """Keeps only the last instance of a base capture event for each base ID."""
        blue_coalition_id = 2
        seen = set()
        captures = []
        for capture in reversed(self.state_data.base_capture_events):
            # The ID string in the JSON file will be the UUID generated from escalation
            cp_id, new_owner_id_str, _name = capture.split("||")

            # Only the most recent capture event matters.
            if cp_id in seen:
                continue
            seen.add(cp_id)

            try:
                control_point = self.game.theater.find_control_point_by_id(UUID(cp_id))
            except (KeyError, ValueError):
                # Captured base is not a part of the campaign. This happens when neutral
                # bases are near the conflict. Nothing to do.
                continue
            if int(new_owner_id_str) == blue_coalition_id:
                captured_by_player = Player.BLUE
            else:
                captured_by_player = Player.RED
            if control_point.is_friendly(to_player=captured_by_player):
                # Base is currently friendly to the new owner. Was captured and
                # recaptured in the same mission. Nothing to do.
                continue

            captures.append(BaseCaptureEvent(control_point, captured_by_player))
        return captures
