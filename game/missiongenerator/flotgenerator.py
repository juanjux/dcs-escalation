from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, TYPE_CHECKING, Tuple

from dcs import Mission
from dcs.action import AITaskPush
from dcs.condition import GroupLifeLess, Or, TimeAfter, UnitDamaged
from dcs.country import Country
from dcs.mapping import Point, Vector2
from dcs.point import PointAction
from dcs.task import (
    AFAC,
    AttackGroup,
    ControlledTask,
    FAC,
    FireAtPoint,
    GoToWaypoint,
    Hold,
    OrbitAction,
    SetImmortalCommand,
    SetInvisibleCommand,
    OptAlarmState,
)
from dcs.triggers import Event, TriggerOnce
from dcs.unit import Skill, Vehicle

from game.dcs.skills import ground_skill
from dcs.unitgroup import VehicleGroup

from game.callsigns import callsign_for_support_unit
from game.data.units import UnitClass
from game.dcs.aircrafttype import AircraftType
from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import (
    CombatGroup,
    CombatGroupRole,
    DISTANCE_FROM_FRONTLINE,
)
from game.ground_forces.combat_stance import CombatStance
from game.naming import namegen
from game.plugins import LuaPluginManager
from game.radio.radios import RadioRegistry
from game.theater.controlpoint import ControlPoint, Player
from game.unitmap import UnitMap
from game.utils import Heading
from .aircraft.aircraftpainter import AircraftPainterJtac
from .frontlineconflictdescription import FrontLineConflictDescription
from .groundforcepainter import GroundForcePainter
from .missiondata import JtacInfo, MissionData, FrontlineUnitGroupsInfo
from .realisticcascampaign import suppress_legacy_jtac
from ..ato import FlightType

if TYPE_CHECKING:
    from game import Game

SPREAD_DISTANCE_FACTOR = 0.1, 0.3
SPREAD_DISTANCE_SIZE_FACTOR = 0.1

FRONTLINE_CAS_FIGHTS_COUNT = 16, 24
FRONTLINE_CAS_GROUP_MIN = 1, 2
FRONTLINE_CAS_PADDING = 12000

RETREAT_DISTANCE = 20000
BREAKTHROUGH_OFFENSIVE_DISTANCE = 35000
AGGRESIVE_MOVE_DISTANCE = 16000

FIGHT_DISTANCE = 3500

RANDOM_OFFSET_ATTACK = 250

INFANTRY_GROUP_SIZE = 5

# TIC-managed formations advance to this far short of the front-line trace
# (min, max meters). Attackers stopping one standoff from the trace leaves
# them inside TIC's ~2 NM targeting bubble, so opposing formations halt face
# to face and exchange fire instead of driving past each other to deep
# objectives.
TIC_CONTACT_STANDOFF = (600, 900)
# Defenders dig in a bound short of the trace rather than idling at their rear
# spawn (which could sit OUTSIDE the ~2 NM bubble, leaving an attacker pressing
# an empty line). Still well inside the bubble, just deeper than the attacker.
TIC_DEFENSIVE_STANDOFF = (900, 1400)
# Ambush is the most rearward/weapons-tight hold: further back than DEFENSIVE
# but still inside the bubble so the line engages once the attacker presses in.
TIC_AMBUSH_STANDOFF = (1400, 2200)
# Sideways movement along the front on a slide leg (min, max meters).
# Reshuffles the geometry so formations deadlocked behind LOS blockers (towns,
# ridges) pick up new sightlines and opponents.
TIC_LATERAL_SLIDE = (1500, 3000)
# How far past the front-line trace a press leg goes (min, max meters), before
# the per-stance depth scale. Pressing converges into close range, guaranteeing
# combat even where LOS was blocked at standoff.
TIC_PUSH_DEPTH = (400, 800)
# Per-group tempo multiplier (min, max) applied to every leg gap so formations
# don't all reach the firing line on the same beat. <1 = quicker mover.
TIC_GROUP_TEMPO = (0.7, 1.4)
# Floor for the step-off window (minutes) when boundPause is small.
TIC_STEP_OFF_FLOOR = 3
# BREAKTHROUGH presses much deeper than a measured AGGRESSIVE push.
TIC_BREAKTHROUGH_DEPTH_SCALE = 1.8
# Probability a dug-in DEFENSIVE group throws an occasional local counterattack
# leg, and how shallow that lunge is relative to a full press.
TIC_COUNTERATTACK_CHANCE = 0.25
TIC_COUNTERATTACK_DEPTH_SCALE = 0.6
# Fallback for the "tic.boundPause" plugin option (minutes between legs).
TIC_DEFAULT_BOUND_PAUSE = 25


@dataclass(frozen=True)
class TicStanceProfile:
    """Per-stance movement shape for a TIC-managed formation. Maps a campaign
    CombatStance onto a distinct firing-line posture so opposing sides don't run
    the same script and collide as a symmetric wall. See
    docs/dev/design/414th-tic-dynamic-fronts-notes.md."""

    # Distance band (m) to halt short of the trace for the opening bound.
    standoff: Tuple[int, int]
    # Number of slide/press assault cycles after the opening bound (attackers).
    assault_cycles: int
    # Whether each assault cycle slides laterally before pressing. Breakthrough
    # thrusts straight (no lateral dithering); aggressive/elimination slide to
    # break LOS deadlocks first.
    slide_before_press: bool
    # Multiplier on TIC_PUSH_DEPTH for press legs.
    push_depth_scale: float
    # Cadence multiplier on the leg gap (<1 = faster tempo, e.g. breakthrough).
    cadence_scale: float
    # Chance of an extra shallow forward counterattack leg (DEFENSIVE only).
    counter_chance: float


# AGGRESSIVE/BREAKTHROUGH/ELIMINATION attack; DEFENSIVE/AMBUSH hold a forward
# bound (and DEFENSIVE may occasionally counterattack). RETREAT is handled
# separately. Stances absent here fall back to the DEFENSIVE-style hold.
TIC_STANCE_PROFILES = {
    CombatStance.AGGRESSIVE: TicStanceProfile(
        standoff=TIC_CONTACT_STANDOFF,
        assault_cycles=1,
        slide_before_press=True,
        push_depth_scale=1.0,
        cadence_scale=1.0,
        counter_chance=0.0,
    ),
    CombatStance.BREAKTHROUGH: TicStanceProfile(
        standoff=TIC_CONTACT_STANDOFF,
        assault_cycles=1,
        slide_before_press=False,
        push_depth_scale=TIC_BREAKTHROUGH_DEPTH_SCALE,
        cadence_scale=0.7,
        counter_chance=0.0,
    ),
    CombatStance.ELIMINATION: TicStanceProfile(
        standoff=TIC_CONTACT_STANDOFF,
        assault_cycles=2,
        slide_before_press=True,
        push_depth_scale=1.0,
        cadence_scale=1.0,
        counter_chance=0.0,
    ),
    CombatStance.DEFENSIVE: TicStanceProfile(
        standoff=TIC_DEFENSIVE_STANDOFF,
        assault_cycles=0,
        slide_before_press=False,
        push_depth_scale=TIC_COUNTERATTACK_DEPTH_SCALE,
        cadence_scale=1.0,
        counter_chance=TIC_COUNTERATTACK_CHANCE,
    ),
    CombatStance.AMBUSH: TicStanceProfile(
        standoff=TIC_AMBUSH_STANDOFF,
        assault_cycles=0,
        slide_before_press=False,
        push_depth_scale=TIC_COUNTERATTACK_DEPTH_SCALE,
        cadence_scale=1.0,
        counter_chance=0.0,
    ),
}


class FlotGenerator:
    def __init__(
        self,
        mission: Mission,
        conflict: FrontLineConflictDescription,
        game: Game,
        player_planned_combat_groups: List[CombatGroup],
        enemy_planned_combat_groups: List[CombatGroup],
        player_stance: CombatStance,
        enemy_stance: CombatStance,
        unit_map: UnitMap,
        radio_registry: RadioRegistry,
        mission_data: MissionData,
    ) -> None:
        self.mission = mission
        self.conflict = conflict
        self.enemy_planned_combat_groups = enemy_planned_combat_groups
        self.player_planned_combat_groups = player_planned_combat_groups
        self.player_stance = player_stance
        self.enemy_stance = enemy_stance
        self.game = game
        self.unit_map = unit_map
        self.radio_registry = radio_registry
        self.mission_data = mission_data
        # When the TIC plugin is enabled, frontline maneuver units are handed
        # over to the Troops In Contact script (group/waypoint naming contract)
        # instead of receiving vanilla DCS combat tasking.
        self.tic_enabled = bool(self.game.settings.plugins.get("tic"))
        # Minutes between TIC advance legs, from the plugin settings UI.
        # Default 25 paces the battle arc across roughly 1.5-2 hours.
        self.tic_bound_pause = int(
            self.game.settings.plugins.get("tic.boundPause") or TIC_DEFAULT_BOUND_PAUSE
        )

    def generate(self) -> None:
        position = FrontLineConflictDescription.frontline_position(
            self.conflict.front_line, self.game.theater, self.game.settings
        )

        # Create player groups at random position
        player_groups = self._generate_groups(
            self.player_planned_combat_groups, is_player=Player.BLUE
        )

        # Create enemy groups at random position
        enemy_groups = self._generate_groups(
            self.enemy_planned_combat_groups, is_player=Player.RED
        )

        # TODO: Differentiate AirConflict and GroundConflict classes.
        if self.conflict.heading is None:
            raise RuntimeError(
                "Cannot generate ground units for non-ground conflict. Ground unit "
                "conflicts cannot have the heading `None`."
            )

        self.wpt_pointaction = (
            PointAction.OnRoad
            if self.game.settings.perf_frontline_units_prefer_roads
            else PointAction.OffRoad
        )

        # Plan combat actions for groups
        self.plan_action_for_groups(
            self.player_stance,
            player_groups,
            enemy_groups,
            self.conflict.heading.right,
            self.conflict.blue_cp,
            self.conflict.red_cp,
        )
        self.plan_action_for_groups(
            self.enemy_stance,
            enemy_groups,
            player_groups,
            self.conflict.heading.left,
            self.conflict.red_cp,
            self.conflict.blue_cp,
        )

        # Add JTAC
        if (
            self.game.settings.use_jtac
            and self.game.blue.faction.has_jtac
            and not suppress_legacy_jtac(LuaPluginManager.plugins())
        ):
            freq = self.radio_registry.alloc_uhf()
            # If the option fc3LaserCode is enabled, force all JTAC
            # laser codes to 1113 to allow lasing for Su-25 Frogfoots and A-10A Warthogs.
            # Otherwise use 1688 for the first JTAC, 1687 for the second etc.
            if self.game.settings.plugins.get("ctld.fc3LaserCode"):
                code = self.game.laser_code_registry.fc3_code
            else:
                code = self.conflict.front_line.laser_code

            utype = self.game.blue.faction.jtac_unit
            if utype is None:
                utype = AircraftType.named("MQ-9 Reaper")

            country = self.mission.country(self.game.blue.faction.country.name)
            jtac = self.mission.flight_group(
                country=country,
                name=namegen.next_jtac_name(),
                aircraft_type=utype.dcs_unit_type,
                position=position[0],
                airport=None,
                altitude=5000,
                maintask=AFAC,
            )
            AircraftPainterJtac(self.game.blue.faction, utype, jtac).apply_livery()
            cs = jtac.units[0].callsign_dict
            assert type(cs[1]) == int
            assert type(cs[2]) == int
            jtac.points[0].tasks.append(
                FAC(
                    callsign=cs[1],
                    number=cs[2],
                    frequency=int(freq.mhz),
                    modulation=freq.modulation,
                )
            )
            jtac.points[0].tasks.append(SetInvisibleCommand(True))
            jtac.points[0].tasks.append(SetImmortalCommand(True))
            jtac.points[0].tasks.append(
                OrbitAction(5000, 300, OrbitAction.OrbitPattern.Circle)
            )
            frontline = (
                f"Frontline {self.conflict.blue_cp.name}/{self.conflict.red_cp.name}"
            )
            # Note: Will need to change if we ever add ground based JTAC.
            callsign = callsign_for_support_unit(jtac)
            self.mission_data.jtacs.append(
                JtacInfo(
                    group_name=jtac.name,
                    unit_name=jtac.units[0].name,
                    callsign=callsign,
                    region=frontline,
                    code=str(code),
                    blue=Player.BLUE,
                    freq=freq,
                )
            )

        # Keep the existing frontline metadata even when only the JTAC is omitted.
        if self.game.blue.faction.has_jtac:
            for vehicle_group, combat_group in player_groups:
                self.mission_data.player_frontline_groups.append(
                    FrontlineUnitGroupsInfo(
                        group_name=vehicle_group.name, unit_type=combat_group.unit_type
                    )
                )

            for vehicle_group, combat_group in enemy_groups:
                self.mission_data.enemy_frontline_groups.append(
                    FrontlineUnitGroupsInfo(
                        group_name=vehicle_group.name, unit_type=combat_group.unit_type
                    )
                )

    @staticmethod
    def _tic_managed_role(role: CombatGroupRole) -> bool:
        """Roles handed over to the TIC script. Artillery keeps Escalation's
        fire-mission tasking; SHORAD/AAA keep vanilla air-defense AI."""
        return role in (
            CombatGroupRole.TANK,
            CombatGroupRole.IFV,
            CombatGroupRole.APC,
            CombatGroupRole.ATGM,
        )

    def gen_infantry_group_for_group(
        self,
        group: VehicleGroup,
        is_player: Player,
        side: Country,
        forward_heading: Heading,
        tic_formation: Optional[str] = None,
    ) -> None:
        infantry_position = self.conflict.find_ground_position(
            group.points[0].position.random_point_within(250, 50),
            500,
            forward_heading,
            self.conflict.theater,
        )

        faction = self.game.faction_for(is_player)

        def infantry_group_name(unit_type: GroundUnitType) -> str:
            name = namegen.next_infantry_name(side, unit_type)
            if tic_formation is not None:
                # Join the carrier group's TIC formation. The "#" bookend
                # keeps the DCS group name unique while TIC merges every
                # group sharing the formation name.
                return f"TIC:{tic_formation}#{name}"
            return name

        # Disable infantry unit gen if disabled
        if not self.game.settings.perf_infantry:
            if self.game.settings.manpads:
                # 50% of armored units protected by manpad
                if random.choice([True, False]):
                    manpads = list(faction.infantry_with_class(UnitClass.MANPAD))
                    if manpads:
                        u = random.choices(
                            manpads, weights=[m.spawn_weight for m in manpads]
                        )[0]
                        vg = self.mission.vehicle_group(
                            side,
                            namegen.next_infantry_name(side, u),
                            u.dcs_unit_type,
                            position=infantry_position,
                            group_size=1,
                            heading=forward_heading.degrees,
                            move_formation=PointAction.OffRoad,
                        )
                        vehicle = vg.units[0]
                        GroundForcePainter(faction, vehicle).apply_livery()
                        vg.hidden_on_mfd = True
            return

        possible_infantry_units = set(faction.infantry_with_class(UnitClass.INFANTRY))
        if self.game.settings.manpads:
            possible_infantry_units |= set(
                faction.infantry_with_class(UnitClass.MANPAD)
            )
        if not possible_infantry_units:
            return

        infantry_choices = list(possible_infantry_units)
        units = random.choices(
            infantry_choices,
            weights=[u.spawn_weight for u in infantry_choices],
            k=INFANTRY_GROUP_SIZE,
        )
        vg = self.mission.vehicle_group(
            side,
            infantry_group_name(units[0]),
            units[0].dcs_unit_type,
            position=infantry_position,
            group_size=1,
            heading=forward_heading.degrees,
            move_formation=PointAction.OffRoad,
        )
        vehicle = vg.units[0]
        GroundForcePainter(faction, vehicle).apply_livery()
        vg.hidden_on_mfd = True
        if tic_formation is not None:
            vg.late_activation = True

        for unit in units[1:]:
            position = infantry_position.random_point_within(55, 5)
            vg = self.mission.vehicle_group(
                side,
                infantry_group_name(unit),
                unit.dcs_unit_type,
                position=position,
                group_size=1,
                heading=forward_heading.degrees,
                move_formation=PointAction.OffRoad,
            )
            vehicle = vg.units[0]
            GroundForcePainter(faction, vehicle).apply_livery()
            vg.hidden_on_mfd = True
            if tic_formation is not None:
                vg.late_activation = True

    def _earliest_tot_on_flot(self, player: Player) -> timedelta:
        tots = [
            x.time_over_target
            for x in self.game.ato_for(player).packages
            if x.primary_task == FlightType.CAS
        ]
        return (
            timedelta(seconds=random.randint(150, 900))
            if len(tots) == 0
            else min(
                [
                    x.time_over_target - self.mission.start_time
                    for x in self.game.ato_for(player).packages
                    if x.primary_task == FlightType.CAS
                ]
            )
        )

    def _set_reform_waypoint(
        self,
        dcs_group: VehicleGroup,
        forward_heading: Heading,
        hold_duration: timedelta = timedelta(),
    ) -> None:
        """Setting a waypoint close to the spawn position allows the group to reform gracefully
        rather than spin
        """
        reform_point = dcs_group.position.point_from_heading(
            forward_heading.degrees, 50
        )
        rp = dcs_group.add_waypoint(reform_point)
        hold = ControlledTask(Hold())
        # total_seconds(), not seconds: timedelta normalises a negative delta to a
        # negative day plus a positive remainder, so a CAS package whose TOT lands
        # before the mission start turned a -60s hold into .seconds == 86340 -- very
        # nearly 24 hours, i.e. a group that never moves for the whole mission.
        hold.stop_after_duration(max(0, int(hold_duration.total_seconds())))
        rp.add_task(hold)

    def _plan_artillery_action(
        self,
        stance: CombatStance,
        gen_group: CombatGroup,
        dcs_group: VehicleGroup,
        forward_heading: Heading,
        target: Point,
    ) -> bool:
        """
        Handles adding the DCS tasks for artillery groups for all combat stances.
        Returns True if tasking was added, returns False if the stance was not a combat stance.
        """
        self._set_reform_waypoint(dcs_group, forward_heading)
        if stance != CombatStance.RETREAT:
            hold_task = Hold()
            hold_task.number = 1
            dcs_group.add_trigger_action(hold_task)

        # Artillery strike random start
        artillery_trigger = TriggerOnce(
            Event.NoEvent, "ArtilleryFireTask #" + str(dcs_group.id)
        )
        artillery_trigger.add_condition(TimeAfter(seconds=random.randint(1, 45) * 60))
        # TODO: Update to fire at group instead of point
        fire_task = FireAtPoint(target, gen_group.size * 10, 100)
        fire_task.number = 2 if stance != CombatStance.RETREAT else 1
        dcs_group.add_trigger_action(fire_task)
        artillery_trigger.add_action(AITaskPush(dcs_group.id, len(dcs_group.tasks)))
        self.mission.triggerrules.triggers.append(artillery_trigger)

        # Artillery will fall back when under attack
        if stance != CombatStance.RETREAT:
            # Hold position
            dcs_group.points[1].tasks.append(Hold())
            retreat = self.find_retreat_point(
                dcs_group, forward_heading, int(RETREAT_DISTANCE / 3)
            )
            dcs_group.add_waypoint(
                dcs_group.position.point_from_heading(forward_heading.degrees, 1),
                self.wpt_pointaction,
            )
            dcs_group.points[2].tasks.append(Hold())
            dcs_group.add_waypoint(retreat, self.wpt_pointaction)

            artillery_fallback = TriggerOnce(
                Event.NoEvent, "ArtilleryRetreat #" + str(dcs_group.id)
            )
            for i, u in enumerate(dcs_group.units):
                artillery_fallback.add_condition(UnitDamaged(u.id))
                if i < len(dcs_group.units) - 1:
                    artillery_fallback.add_condition(Or())

            hold_2 = Hold()
            hold_2.number = 3
            dcs_group.add_trigger_action(hold_2)

            retreat_task = GoToWaypoint(to_index=3)
            retreat_task.number = 4
            dcs_group.add_trigger_action(retreat_task)

            artillery_fallback.add_action(
                AITaskPush(dcs_group.id, len(dcs_group.tasks))
            )
            self.mission.triggerrules.triggers.append(artillery_fallback)

            for u in dcs_group.units:
                u.heading = (forward_heading + Heading.random(-5, 5)).degrees
            return True
        return False

    def _plan_tank_ifv_action(
        self,
        stance: CombatStance,
        enemy_groups: List[Tuple[VehicleGroup, CombatGroup]],
        dcs_group: VehicleGroup,
        forward_heading: Heading,
        to_cp: ControlPoint,
    ) -> bool:
        """
        Handles adding the DCS tasks for tank and IFV groups for all combat stances.
        Returns True if tasking was added, returns False if the stance was not a combat stance.
        """
        duration = timedelta()
        if stance == CombatStance.AGGRESSIVE:
            # Hold at the reform point until the enemy's first CAS package is due, so
            # an assault steps off with air support overhead. Only an attacker waits:
            # a DEFENSIVE group holding here spent that window unable to shoot back,
            # because Hold is a running task the AI will not abandon for a pushed one.
            duration = self._earliest_tot_on_flot(to_cp.coalition.player.opponent)
        self._set_reform_waypoint(dcs_group, forward_heading, duration)
        if stance == CombatStance.AGGRESSIVE:
            # Attack nearest enemy if any
            # Then move forward OR Attack enemy base if it is not too far away
            target = self.find_nearest_enemy_group(dcs_group, enemy_groups)
            if target is not None:
                rand_offset = Vector2(
                    random.randint(-RANDOM_OFFSET_ATTACK, RANDOM_OFFSET_ATTACK),
                    random.randint(-RANDOM_OFFSET_ATTACK, RANDOM_OFFSET_ATTACK),
                )
                target_point = self.conflict.theater.nearest_land_pos(
                    target.points[0].position + rand_offset
                )
                dcs_group.add_waypoint(target_point)
                dcs_group.points[2].tasks.append(AttackGroup(target.id))

            if (
                to_cp.position.distance_to_point(dcs_group.points[0].position)
                <= AGGRESIVE_MOVE_DISTANCE
            ):
                attack_point = self.conflict.theater.nearest_land_pos(
                    to_cp.position.random_point_within(500, 0)
                )
            else:
                # We use an offset heading here because DCS doesn't always
                # force vehicles to move if there's no heading change.
                offset_heading = forward_heading - Heading.from_degrees(2)
                attack_point = self.find_offensive_point(
                    dcs_group, offset_heading, AGGRESIVE_MOVE_DISTANCE
                )
            dcs_group.add_waypoint(attack_point, self.wpt_pointaction)
        elif stance == CombatStance.BREAKTHROUGH:
            # In breakthrough mode, the units will move forward
            # If the enemy base is close enough, the units will attack the base
            if (
                to_cp.position.distance_to_point(dcs_group.points[0].position)
                <= BREAKTHROUGH_OFFENSIVE_DISTANCE
            ):
                attack_point = self.conflict.theater.nearest_land_pos(
                    to_cp.position.random_point_within(500, 0)
                )
            else:
                # We use an offset heading here because DCS doesn't always
                # force vehicles to move if there's no heading change.
                offset_heading = forward_heading - Heading.from_degrees(1)
                attack_point = self.find_offensive_point(
                    dcs_group, offset_heading, BREAKTHROUGH_OFFENSIVE_DISTANCE
                )
            dcs_group.add_waypoint(attack_point, self.wpt_pointaction)
        elif stance == CombatStance.ELIMINATION:
            # In elimination mode, the units focus on destroying as much enemy groups as possible
            targets = self.find_n_nearest_enemy_groups(dcs_group, enemy_groups, 3)
            for i, target in enumerate(targets, start=1):
                rand_offset = Vector2(
                    random.randint(-RANDOM_OFFSET_ATTACK, RANDOM_OFFSET_ATTACK),
                    random.randint(-RANDOM_OFFSET_ATTACK, RANDOM_OFFSET_ATTACK),
                )
                target_point = self.conflict.theater.nearest_land_pos(
                    target.points[0].position + rand_offset
                )
                dcs_group.add_waypoint(target_point, self.wpt_pointaction)
                dcs_group.points[i + 1].tasks.append(AttackGroup(target.id))
            if (
                to_cp.position.distance_to_point(dcs_group.points[0].position)
                <= AGGRESIVE_MOVE_DISTANCE
            ):
                attack_point = self.conflict.theater.nearest_land_pos(
                    to_cp.position.random_point_within(500, 0)
                )
                dcs_group.add_waypoint(attack_point)

        if stance != CombatStance.RETREAT:
            self.add_morale_trigger(dcs_group, forward_heading)
            return True
        return False

    def _plan_apc_atgm_action(
        self,
        stance: CombatStance,
        dcs_group: VehicleGroup,
        forward_heading: Heading,
        to_cp: ControlPoint,
    ) -> bool:
        """
        Handles adding the DCS tasks for APC and ATGM groups for all combat stances.
        Returns True if tasking was added, returns False if the stance was not a combat stance.
        """
        duration = timedelta()
        if stance == CombatStance.AGGRESSIVE:
            # Hold at the reform point until the enemy's first CAS package is due, so
            # an assault steps off with air support overhead. Only an attacker waits:
            # a DEFENSIVE group holding here spent that window unable to shoot back,
            # because Hold is a running task the AI will not abandon for a pushed one.
            duration = self._earliest_tot_on_flot(to_cp.coalition.player.opponent)
        self._set_reform_waypoint(dcs_group, forward_heading, duration)
        if stance in [
            CombatStance.AGGRESSIVE,
            CombatStance.BREAKTHROUGH,
            CombatStance.ELIMINATION,
        ]:
            # APC & ATGM will never move too much forward, but will follow along any offensive
            if (
                to_cp.position.distance_to_point(dcs_group.points[0].position)
                <= AGGRESIVE_MOVE_DISTANCE
            ):
                attack_point = self.conflict.theater.nearest_land_pos(
                    to_cp.position.random_point_within(500, 0)
                )
            else:
                attack_point = self.find_offensive_point(
                    dcs_group, forward_heading, AGGRESIVE_MOVE_DISTANCE
                )
            dcs_group.add_waypoint(attack_point, self.wpt_pointaction)

        if stance != CombatStance.RETREAT:
            self.add_morale_trigger(dcs_group, forward_heading)
            return True
        return False

    def _tic_distance_to_front(
        self, dcs_group: VehicleGroup, forward_heading: Heading
    ) -> float:
        """Signed distance (m) from the group to the front-line trace, measured
        along the forward heading. Positive = the front is ahead."""
        pos = dcs_group.points[0].position
        probe = pos.point_from_heading(forward_heading.degrees, 1000.0)
        unit_x = (probe.x - pos.x) / 1000.0
        unit_y = (probe.y - pos.y) / 1000.0
        front = self.conflict.position
        return (front.x - pos.x) * unit_x + (front.y - pos.y) * unit_y

    def _tic_step_off(self) -> int:
        """Minutes before a group's opening bound steps off. Scaled to the
        battle tempo so the line doesn't move as one -- groups begin advancing
        across a wide window instead of together."""
        window = max(TIC_STEP_OFF_FLOOR, self.tic_bound_pause // 2)
        return random.randint(0, window)

    def _tic_jitter(self) -> int:
        """Minutes between TIC legs: boundPause +/- 45% (loosened from +/-25%
        so leg transitions don't re-cluster after the staggered step-off)."""
        pause = self.tic_bound_pause
        return random.randint(round(pause * 0.55), round(pause * 1.45))

    def _tic_leg_gap(self, tempo: float, cadence_scale: float) -> int:
        """Minutes to the next leg for one group: jitter scaled by the group's
        own tempo and the stance cadence (breakthrough presses faster). Floored
        at 1 so legs never collapse onto the same minute."""
        return max(1, round(self._tic_jitter() * tempo * cadence_scale))

    @staticmethod
    def _tic_stance_profile(stance: CombatStance) -> TicStanceProfile:
        """Movement shape for a stance. Unknown/unmapped stances fall back to a
        DEFENSIVE-style dug-in hold rather than a symmetric advance."""
        return TIC_STANCE_PROFILES.get(
            stance, TIC_STANCE_PROFILES[CombatStance.DEFENSIVE]
        )

    def _plan_tic_action(
        self,
        stance: CombatStance,
        dcs_group: VehicleGroup,
        forward_heading: Heading,
        from_cp: ControlPoint,
        to_cp: ControlPoint,
    ) -> bool:
        """
        Plans movement for a TIC-managed formation by encoding TIC commands in
        waypoint names ("t+N" = advance N minutes after activation, "hdg=" =
        formation facing). TIC ignores DCS tasks/triggers, so none are added.

        TIC runs the 414th's chosen "simulate" ROE: theatrical, mostly
        inaccurate fire that only happens while stationary. Movement is shaped
        per CombatStance (`_tic_stance_profile`) so opposing sides don't run the
        same script and collide as a symmetric wall. Every formation takes an
        opening bound to a fighting line short of the trace (inside TIC's ~2 NM
        bubble); attackers then run slide/press assault cycles past the trace,
        while DEFENSIVE/AMBUSH dig in there and only DEFENSIVE occasionally
        counterattacks. Cadence is staggered per group (`_tic_step_off`,
        `_tic_leg_gap`) so the line ripples instead of lurching. Leg pacing
        comes from the "tic.boundPause" plugin setting; players provide the real
        attrition. See docs/dev/design/414th-tic-dynamic-fronts-notes.md.

        Returns True if movement waypoints were added.
        """
        heading_cmd = f"hdg={int(forward_heading.degrees)}"
        if stance == CombatStance.RETREAT:
            if (
                from_cp.position.distance_to_point(dcs_group.points[0].position)
                <= RETREAT_DISTANCE
            ):
                retreat_point = self.conflict.theater.nearest_land_pos(
                    from_cp.position.random_point_within(500, 250)
                )
            else:
                retreat_point = self.find_retreat_point(dcs_group, forward_heading)
            wp = dcs_group.add_waypoint(retreat_point, self.wpt_pointaction)
            wp.name = f"t+0 {heading_cmd} roe=simulate"
            return True

        profile = self._tic_stance_profile(stance)
        tempo = random.uniform(*TIC_GROUP_TEMPO)
        leg_time = self._tic_step_off()
        added = False

        def emit(point: Point, when: int) -> None:
            nonlocal added
            wp = dcs_group.add_waypoint(point, self.wpt_pointaction)
            wp.name = f"t+{when} {heading_cmd} roe=simulate"
            added = True

        # Opening bound: advance to the fighting line short of the trace. For
        # attackers this is the contact standoff; for DEFENSIVE/AMBUSH it digs
        # them in well inside the bubble instead of idling at the rear spawn
        # (which could leave an attacker pressing an empty line).
        standoff = random.randint(*profile.standoff)
        travel = self._tic_distance_to_front(dcs_group, forward_heading) - standoff
        if travel > 100:
            firing_line = self.find_offensive_point(
                dcs_group, forward_heading, int(travel)
            )
            emit(firing_line, leg_time)
        else:
            # Already at (or past) the fighting line; slide and press from here.
            firing_line = dcs_group.points[0].position

        current = firing_line

        # Assault cycles (attackers): optionally slide to break an LOS deadlock,
        # then press just past the trace into close contact. ELIMINATION runs
        # two cycles to hunt sightlines; BREAKTHROUGH thrusts straight and deep.
        for _ in range(profile.assault_cycles):
            if profile.slide_before_press:
                slide_heading = random.choice(
                    [forward_heading.right, forward_heading.left]
                )
                current = self.conflict.theater.nearest_land_pos(
                    current.point_from_heading(
                        slide_heading.degrees, random.randint(*TIC_LATERAL_SLIDE)
                    )
                )
                leg_time += self._tic_leg_gap(tempo, profile.cadence_scale)
                emit(current, leg_time)

            press_depth = standoff + round(
                random.randint(*TIC_PUSH_DEPTH) * profile.push_depth_scale
            )
            current = self.conflict.theater.nearest_land_pos(
                current.point_from_heading(forward_heading.degrees, press_depth)
            )
            leg_time += self._tic_leg_gap(tempo, profile.cadence_scale)
            emit(current, leg_time)

        # DEFENSIVE: occasional local counterattack -- a single shallow lunge to
        # ~the trace, then it holds again. Keeps the dug-in line from being fully
        # predictable without committing it to a full assault.
        if profile.counter_chance and random.random() < profile.counter_chance:
            press_depth = standoff + round(
                random.randint(*TIC_PUSH_DEPTH) * profile.push_depth_scale
            )
            counter_point = self.conflict.theater.nearest_land_pos(
                current.point_from_heading(forward_heading.degrees, press_depth)
            )
            leg_time += self._tic_leg_gap(tempo, profile.cadence_scale)
            emit(counter_point, leg_time)

        return added

    def plan_action_for_groups(
        self,
        stance: CombatStance,
        ally_groups: List[Tuple[VehicleGroup, CombatGroup]],
        enemy_groups: List[Tuple[VehicleGroup, CombatGroup]],
        forward_heading: Heading,
        from_cp: ControlPoint,
        to_cp: ControlPoint,
    ) -> None:
        if not self.game.settings.perf_moving_units:
            return

        for dcs_group, group in ally_groups:
            if self.tic_enabled and self._tic_managed_role(group.role):
                # TIC-managed formations get their orders from waypoint names
                # (parsed by the TIC script), not from DCS AI tasks/triggers.
                self._plan_tic_action(
                    stance, dcs_group, forward_heading, from_cp, to_cp
                )
                continue

            if group.role == CombatGroupRole.ARTILLERY:
                if self.game.settings.perf_artillery:
                    target = self.get_artillery_target_in_range(
                        dcs_group, group, enemy_groups
                    )
                    if target is not None:
                        self._plan_artillery_action(
                            stance, group, dcs_group, forward_heading, target
                        )

            elif group.role in [CombatGroupRole.TANK, CombatGroupRole.IFV]:
                self._plan_tank_ifv_action(
                    stance, enemy_groups, dcs_group, forward_heading, to_cp
                )

            elif group.role in [CombatGroupRole.APC, CombatGroupRole.ATGM]:
                self._plan_apc_atgm_action(stance, dcs_group, forward_heading, to_cp)

            if stance == CombatStance.RETREAT:
                # In retreat mode, the units will fall back
                # If the allied base is close enough, the units will even regroup there
                if (
                    from_cp.position.distance_to_point(dcs_group.points[0].position)
                    <= RETREAT_DISTANCE
                ):
                    retreat_point = from_cp.position.random_point_within(500, 250)
                else:
                    retreat_point = self.find_retreat_point(dcs_group, forward_heading)
                reposition_point = retreat_point.point_from_heading(
                    forward_heading.degrees, 10
                )  # Another point to make the unit face the enemy
                dcs_group.add_waypoint(retreat_point, self.wpt_pointaction)
                dcs_group.add_waypoint(reposition_point, self.wpt_pointaction)

    def add_morale_trigger(
        self, dcs_group: VehicleGroup, forward_heading: Heading
    ) -> None:
        """
        This adds a trigger to manage units fleeing whenever their group is hit hard, or being engaged by CAS
        """

        if len(dcs_group.units) == 1:
            return

        # Units should hold position on last waypoint
        dcs_group.points[len(dcs_group.points) - 1].tasks.append(Hold())

        # Force unit heading
        for unit in dcs_group.units:
            unit.heading = forward_heading.degrees
        dcs_group.manualHeading = True

        # We add a new retreat waypoint
        dcs_group.add_waypoint(
            self.find_retreat_point(
                dcs_group, forward_heading, int(RETREAT_DISTANCE / 8)
            ),
            self.wpt_pointaction,
        )

        # Fallback task
        task = ControlledTask(GoToWaypoint(to_index=len(dcs_group.points)))
        task.enabled = False
        dcs_group.add_trigger_action(Hold())
        dcs_group.add_trigger_action(task)

        # Create trigger
        fallback = TriggerOnce(Event.NoEvent, "Morale manager #" + str(dcs_group.id))

        # Usually more than 50% casualties = RETREAT
        fallback.add_condition(GroupLifeLess(dcs_group.id, random.randint(51, 76)))

        # Do retreat to the configured retreat waypoint
        fallback.add_action(AITaskPush(dcs_group.id, len(dcs_group.tasks)))

        self.mission.triggerrules.triggers.append(fallback)

    def find_retreat_point(
        self,
        dcs_group: VehicleGroup,
        frontline_heading: Heading,
        distance: int = RETREAT_DISTANCE,
    ) -> Point:
        """
        Find a point to retreat to
        :param dcs_group: DCS mission group we are searching a retreat point for
        :param frontline_heading: Heading of the frontline
        :return: dcs.mapping.Point object with the desired position
        """
        desired_point = dcs_group.points[0].position.point_from_heading(
            frontline_heading.opposite.degrees, distance
        )
        if self.conflict.theater.is_on_land(desired_point):
            return desired_point
        return self.conflict.theater.nearest_land_pos(desired_point)

    def find_offensive_point(
        self, dcs_group: VehicleGroup, frontline_heading: Heading, distance: int
    ) -> Point:
        """
        Find a point to attack
        :param dcs_group:  DCS mission group we are searching an attack point for
        :param frontline_heading: Heading of the frontline
        :param distance: Distance of the offensive (how far unit should move)
        :return: dcs.mapping.Point object with the desired position
        """
        desired_point = dcs_group.points[0].position.point_from_heading(
            frontline_heading.degrees, distance
        )
        if self.conflict.theater.is_on_land(desired_point):
            return desired_point
        return self.conflict.theater.nearest_land_pos(desired_point)

    @staticmethod
    def find_n_nearest_enemy_groups(
        player_group: VehicleGroup,
        enemy_groups: List[Tuple[VehicleGroup, CombatGroup]],
        n: int,
    ) -> List[VehicleGroup]:
        """
        Return the nearest enemy group for the player group
        @param player_group Group for which we should find the nearest ennemies
        @param enemy_groups Potential enemy groups
        @param n number of nearby groups to take
        """
        targets = []  # type: List[VehicleGroup]
        sorted_list = sorted(
            enemy_groups,
            key=lambda group: player_group.points[0].position.distance_to_point(
                group[0].points[0].position
            ),
        )
        for i in range(n):
            # TODO: Is this supposed to return no groups if enemy_groups is less than n?
            if len(sorted_list) <= i:
                break
            else:
                targets.append(sorted_list[i][0])
        return targets

    @staticmethod
    def find_nearest_enemy_group(
        player_group: VehicleGroup, enemy_groups: List[Tuple[VehicleGroup, CombatGroup]]
    ) -> Optional[VehicleGroup]:
        """
        Search the enemy groups for a potential target suitable to armored assault
        @param player_group Group for which we should find the nearest ennemy
        @param enemy_groups Potential enemy groups
        """
        min_distance = math.inf
        target = None
        for dcs_group, _ in enemy_groups:
            dist = player_group.points[0].position.distance_to_point(
                dcs_group.points[0].position
            )
            if dist < min_distance:
                min_distance = dist
                target = dcs_group
        return target

    @staticmethod
    def get_artillery_target_in_range(
        dcs_group: VehicleGroup,
        group: CombatGroup,
        enemy_groups: List[Tuple[VehicleGroup, CombatGroup]],
    ) -> Optional[Point]:
        """
        Search the enemy groups for a potential target suitable to an artillery unit
        """
        # TODO: Update to return a list of groups instead of a single point
        rng = getattr(group.unit_type.dcs_unit_type, "threat_range", 0)
        if not enemy_groups:
            return None
        for _ in range(10):
            potential_target = random.choice(enemy_groups)[0]
            distance_to_target = dcs_group.points[0].position.distance_to_point(
                potential_target.points[0].position
            )
            if distance_to_target < rng:
                return potential_target.points[0].position
        return None

    @staticmethod
    def get_artilery_group_distance_from_frontline(group: CombatGroup) -> int:
        """
        For artillery group, decide the distance from frontline with the range of the unit
        """
        rg = group.unit_type.dcs_unit_type.threat_range - 7500
        if rg > DISTANCE_FROM_FRONTLINE[CombatGroupRole.ARTILLERY][1]:
            rg = random.randint(
                DISTANCE_FROM_FRONTLINE[CombatGroupRole.ARTILLERY][0],
                DISTANCE_FROM_FRONTLINE[CombatGroupRole.ARTILLERY][1],
            )
        elif rg < DISTANCE_FROM_FRONTLINE[CombatGroupRole.ARTILLERY][1]:
            rg = random.randint(
                DISTANCE_FROM_FRONTLINE[CombatGroupRole.TANK][0],
                DISTANCE_FROM_FRONTLINE[CombatGroupRole.TANK][1],
            )
        return rg

    def get_valid_position_for_group(
        self, distance_from_frontline: int, spawn_heading: Heading
    ) -> Point:
        assert self.conflict.heading is not None
        assert self.conflict.size is not None
        theater = self.conflict.theater
        # Pick a lateral position along the front. This point lies on the front
        # line itself (between the clipped left/right bounds), so it is valid land.
        shifted = self.conflict.position.point_from_heading(
            self.conflict.heading.degrees,
            random.randint(0, self.conflict.size),
        )
        if not theater.is_on_land(shifted):
            # Degenerate front (e.g. air-only campaign with an arbitrary route).
            # Fall back to the lateral search rather than risk an off-map spawn.
            desired_point = shifted.point_from_heading(
                spawn_heading.degrees, distance_from_frontline
            )
            return FrontLineConflictDescription.find_ground_position(
                desired_point,
                self.conflict.size,
                self.conflict.heading,
                theater,
            )
        # Step back from the front toward the requested depth, keeping the lateral
        # position fixed. The old code snapped the off-map point *along* the front
        # via find_ground_position, which collapsed every group whose depth ran
        # past the playable zone onto the same valid patch and stacked the units on
        # top of each other. Stepping perpendicular preserves the lateral spread.
        step = 250
        valid_point = shifted
        distance = step
        while distance <= distance_from_frontline:
            candidate = shifted.point_from_heading(spawn_heading.degrees, distance)
            if not theater.is_on_land(candidate):
                break
            valid_point = candidate
            distance += step
        return valid_point

    def _generate_groups(
        self, groups: list[CombatGroup], is_player: Player
    ) -> List[Tuple[VehicleGroup, CombatGroup]]:
        """Finds valid positions for planned groups and generates a pydcs group for them"""
        positioned_groups = []
        assert self.conflict.heading is not None
        spawn_heading = (
            self.conflict.heading.left
            if is_player.is_blue
            else self.conflict.heading.right
        )
        country = self.game.coalition_for(is_player).faction.country
        country = self.mission.country(country.name)
        for group in groups:
            if group.role == CombatGroupRole.ARTILLERY:
                distance_from_frontline = (
                    self.get_artilery_group_distance_from_frontline(group)
                )
            else:
                distance_from_frontline = random.randint(
                    DISTANCE_FROM_FRONTLINE[group.role][0],
                    DISTANCE_FROM_FRONTLINE[group.role][1],
                )

            final_position = self.get_valid_position_for_group(
                distance_from_frontline, spawn_heading
            )

            g = self._generate_group(
                is_player,
                country,
                group.unit_type,
                group.size,
                final_position,
                heading=spawn_heading.opposite,
                role=group.role,
            )
            if is_player == Player.BLUE:
                g.set_skill(ground_skill(Skill(self.game.settings.player_skill)))
            else:
                g.set_skill(ground_skill(Skill(self.game.settings.enemy_vehicle_skill)))
            positioned_groups.append((g, group))

            if group.role in [CombatGroupRole.APC, CombatGroupRole.IFV]:
                tic_formation = None
                group_name = str(g.name)
                if group_name.startswith("TIC:"):
                    # Infantry joins the carrier group's TIC formation so TIC
                    # auto-pairs it with the nearest carrier for mounting.
                    tic_formation = group_name[len("TIC:") :]
                self.gen_infantry_group_for_group(
                    g,
                    is_player,
                    country,
                    spawn_heading.opposite,
                    tic_formation=tic_formation,
                )

        return positioned_groups

    def _generate_group(
        self,
        player: Player,
        side: Country,
        unit_type: GroundUnitType,
        count: int,
        at: Point,
        heading: Heading,
        role: CombatGroupRole,
    ) -> VehicleGroup:
        cp = self.conflict.front_line.control_point_friendly_to(player)
        faction = self.game.faction_for(player)

        name = namegen.next_unit_name(side, unit_type)
        tic_managed = self.tic_enabled and self._tic_managed_role(role)
        if tic_managed:
            # TIC discovers groups by the "TIC:" prefix; each vehicle group is
            # its own formation (formation name = the unique generated name).
            name = f"TIC:{name}"

        group = self.mission.vehicle_group(
            side,
            name,
            unit_type.dcs_unit_type,
            position=at,
            group_size=count,
            heading=heading.degrees,
        )
        group.hidden_on_mfd = True
        if tic_managed:
            # TIC requires late-activated originals; it respawns its own
            # single-unit copies at mission start.
            group.late_activation = True
            self.mission_data.tic_groups.append(str(group.name))
        # Front-line units always come up RED, regardless of the perf toggle. A GREEN
        # ground unit does not search for targets and keeps its weapons stowed, so the
        # toggle -- offered as a performance option, and about SAM sites -- silently
        # disarmed the entire ground war: the FLOT would sit and watch the enemy drive
        # past. Same reasoning as the EWR exemption in tgogenerator.set_alarm_state.
        group.points[0].tasks.append(OptAlarmState(2))

        self.unit_map.add_front_line_units(group, cp, unit_type)

        for c in range(count):
            vehicle: Vehicle = group.units[c]
            vehicle.player_can_drive = True
            GroundForcePainter(faction, vehicle).apply_livery()

        return group
