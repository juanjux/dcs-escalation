from __future__ import annotations

import logging
import typing
from datetime import timedelta
from itertools import chain
from typing import TYPE_CHECKING, Any

from dcs.countries import countries_by_name
from dcs.terrain import Airport, Terrain

from game.ato import FlightType
from game.ato.flightplans.formation import FormationLayout
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.ato.packagewaypoints import PackageWaypoints
from game.data.doctrine import MODERN_DOCTRINE, COLDWAR_DOCTRINE, WWII_DOCTRINE
from game.squadrons import morale
from game.theater import ParkingType, SeasonalConditions, Airfield
from game.theater.player import Player
from game.theater.theatergroundobject import ShipGroundObject, TheaterGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight


def try_set_attr(obj: Any, attr_name: str, val: Any = None) -> None:
    if not hasattr(obj, attr_name):
        setattr(obj, attr_name, val)


class Migrator:
    def __init__(self, game: Game, is_liberation: bool):
        self.game = game
        self.is_liberation = is_liberation
        self._migrate_game()

    def _migrate_game(self) -> None:
        self._update_doctrine()
        self._update_control_points()
        self._update_packagewaypoints()
        self._update_package_attributes()
        self._update_factions()
        self._update_flights()
        self._update_squadrons()
        self._update_transfers()
        self._release_untasked_flights()
        self._reconcile_available_pilots()
        self._clear_leave_requests_from_the_wounded()
        self._restate_the_morale_numbers()
        self._collapse_the_tanker_options()
        self._update_weather()
        self._update_tgos()
        self._restore_pruned_iads_nodes()
        self._relabel_formation_waypoints()
        try_set_attr(self.game.settings, "motorpool_enabled", True)
        try_set_attr(self.game.settings, "motorpool_spawn_cap", 10)
        self._ensure_motorpool_tgos()
        self._register_new_tgos()
        self._reload_terrain()
        self._update_theater()
        self._update_campaign_name()

        # TODO: remove in due time as this is supposedly fixed
        self.game.settings.nevatim_parking_fix = False

        from game.missiongenerator.motorpoolpopulator import MotorpoolPopulator

        # Re-home only. Upstream #960 made the motorpool groups ephemeral on purpose:
        # they are filled at mission generation (and on demand by the serializer), not
        # written into the save, so populating here would persist them.
        MotorpoolPopulator(self.game)._rehome_motorpools()

    def _update_doctrine(self) -> None:
        doctrines = [
            MODERN_DOCTRINE,
            COLDWAR_DOCTRINE,
            WWII_DOCTRINE,
        ]
        for c in self.game.coalitions:
            if c.faction.doctrine.__dict__ in [d.__dict__ for d in doctrines]:
                continue
            found = False
            for d in doctrines:
                if c.faction.doctrine.max_patrol_altitude == d.max_patrol_altitude:
                    c.faction.doctrine = d
                    found = True
                    break
            if not found:
                c.faction.doctrine = MODERN_DOCTRINE

    def _update_packagewaypoints(self) -> None:
        for c in self.game.coalitions:
            for p in c.ato.packages:
                if p.waypoints and not hasattr(p.waypoints, "initial"):
                    p.waypoints = PackageWaypoints.create(p, c, False)
                if p.waypoints:
                    try_set_attr(p.waypoints, "standoff_range")

    def _update_package_attributes(self) -> None:
        for c in self.game.coalitions:
            for p in c.ato.packages:
                try_set_attr(p, "custom_name")
                try_set_attr(p, "frequency")
                if isinstance(p.time_over_target, timedelta):  # type: ignore
                    p.time_over_target = (  # type: ignore
                        p.time_over_target + self.game.conditions.start_time
                    )

    def _update_control_points(self) -> None:
        is_sinai = self.game.theater.terrain.name == "SinaiMap"
        for cp in self.game.theater.controlpoints:
            cp.release_parking_slots()
            is_carrier = cp.is_carrier
            is_lha = cp.is_lha
            is_fob = cp.category == "fob"
            radio_configurable = is_carrier or is_lha or is_fob
            if radio_configurable:
                try_set_attr(cp, "frequency")
            if is_carrier or is_lha:
                try_set_attr(cp, "tacan")
                try_set_attr(cp, "tcn_name")
                try_set_attr(cp, "icls_channel")
                try_set_attr(cp, "icls_name")
                try_set_attr(cp, "link4")
            try_set_attr(cp, "convoy_spawns", {})
            try_set_attr(cp, "ground_spawns", [])
            try_set_attr(cp, "ground_spawns_roadbase", [])
            try_set_attr(cp, "helipads_quad", [])
            try_set_attr(cp, "helipads_invisible", [])
            try_set_attr(cp, "ground_spawns_large", [])
            try_set_attr(cp.preset_locations, "motorpools", [])
            if (
                cp.dcs_airport and is_sinai and cp.dcs_airport.id == 20
            ):  # fix for Hatzor
                beacons = cp.dcs_airport.beacons
                faulty_beacon = [x for x in beacons if x.id == "airfield20_0"]
                if faulty_beacon:
                    beacons.remove([x for x in beacons if x.id == "airfield20_0"][0])
            if isinstance(cp, Airfield) and issubclass(cp.airport.__class__, Airport):
                cp.airport = cp.airport.__class__(self.game.theater.terrain)  # type: ignore

    def _update_flight_plan(self, f: Flight) -> None:
        layout = f.flight_plan.layout
        try_set_attr(layout, "nav_to", [])
        try_set_attr(layout, "nav_from", [])
        try_set_attr(layout, "custom_waypoints", [])
        if f.flight_type == FlightType.CAS:
            try_set_attr(layout, "ingress", None)
        if isinstance(layout, FormationLayout):
            if not layout.join and f.package.waypoints:
                builder = WaypointBuilder(f, [])
                layout.join = builder.join(f.package.waypoints.join)

    def _update_flights(self) -> None:
        to_remove = []
        for f in self.game.db.flights.objects.values():
            try_set_attr(f, "frequency")
            try_set_attr(f, "tacan")
            try_set_attr(f, "tcn_name")
            try_set_attr(f, "fuel", f.unit_type.max_fuel)
            try_set_attr(f, "plane_altitude_offset", 0)
            try_set_attr(f, "use_same_livery_for_all_members", True)
            if f.package in f.squadron.coalition.ato.packages:
                self._update_flight_plan(f)
            else:
                to_remove.append(f.id)
            for m in f.roster.members:
                try_set_attr(m, "livery", None)
        for fid in to_remove:
            self.game.db.flights.remove(fid)

    def _release_untasked_flights(self) -> None:
        for cp in self.game.theater.controlpoints:
            for s in cp.squadrons:
                count = 0
                for f in s.flight_db.objects.values():
                    if f.squadron == s:
                        count += f.count
                s.return_all_pilots_and_aircraft()
                new_claim = min(count, s.untasked_aircraft)
                s.claim_inventory(new_claim)
                for i in range(new_claim):
                    s.claim_available_pilot()

    def _restate_the_morale_numbers(self) -> None:
        """Move a campaign in progress onto the re-weighed morale figures.

        The event sizes are settings, and settings ride inside the save, so a
        campaign started before they were re-weighed would keep playing by the old ones
        for ever. Only the ones still sitting on the previous default are moved: a
        figure the player set himself is his.
        """
        settings = self.game.settings
        moved = []
        for event in morale.MORALE_EVENTS:
            olds = morale.PREVIOUS_DEFAULTS.get(event.key, ())
            held = getattr(settings, event.key, event.default)
            if held == event.default or held not in olds:
                continue  # already current, or he set it himself
            setattr(settings, event.key, event.default)
            moved.append(f"{event.key} {held} -> {event.default}")
        if moved:
            logging.info("Morale event sizes brought up to date: %s", "; ".join(moved))

    #: The three per-task tanker options this replaced.
    TANKER_OPTIONS = (
        "autoplan_tankers_for_strike",
        "autoplan_tankers_for_oca",
        "autoplan_tankers_for_dead",
    )

    def _collapse_the_tanker_options(self) -> None:
        """One option where there were three, honouring a campaign that said no.

        The three never did anything -- the fulfiller pruned the tanker they asked
        for -- but a player who turned them all off said what he wanted, so the one
        that replaces them starts off for him. Any of them still on reads as
        "tankers, yes", which is the new option's default anyway.
        """
        settings = self.game.settings
        held = [getattr(settings, name, None) for name in self.TANKER_OPTIONS]
        for name in self.TANKER_OPTIONS:
            if hasattr(settings, name):
                delattr(settings, name)
        if held and all(value is False for value in held):
            settings.plan_refuelling_when_needed = False
            logging.info("Tanker auto-planning was off in all three tasks; kept off")

    def _clear_leave_requests_from_the_wounded(self) -> None:
        """A pilot cannot be asking for leave from a hospital bed.

        Being wounded clears the request now, and the turn's housekeeping will not let a
        wounded man ask -- but saves made before both still carry the flag, and it showed
        as "Requests leave" on the row of a man who was plainly out of action.
        """
        for coalition in (self.game.blue, self.game.red):
            for squadron in coalition.air_wing.iter_squadrons():
                for pilot in squadron.current_roster:
                    if pilot.wounded and pilot.wants_leave:
                        logging.info(
                            f"{pilot.name} of {squadron} was asking for leave while "
                            "wounded; request dropped"
                        )
                        pilot.wants_leave = False
                        pilot.leave_turns_requested = 0

    def _reconcile_available_pilots(self) -> None:
        """The pool of pilots on offer, made to agree with the roster and the ATO.

        It is a stored list, rebuilt from the roster only between turns, so anything
        that moved a man during one used to leave it wrong in one of two ways.

        Too many: clearing a roster handed its crew back without letting go of them, so
        a pilot sat in a flight and in the pool at once -- the Edit Flight dropdown
        listed him twice and the next flight could claim him again, and the same man
        flew two missions in one turn.

        Too few: sending a man on leave did not take him out of the pool and bringing
        him back did not return him, so every claim after that spent somebody else's
        place. A squadron rested down to four pilots ended the turn offering none of
        them, and the two who were fit to fly could not be picked for anything.

        The pool is simply what it should be: active, not refusing to fly, not already
        in a cockpit. Order is preserved for the ones that were already right.
        """
        for coalition in (self.game.blue, self.game.red):
            assigned = {
                id(pilot)
                for package in coalition.ato.packages
                for flight in package.flights
                for pilot in flight.roster.iter_pilots()
                if pilot is not None
            }
            for squadron in coalition.air_wing.iter_squadrons():
                should_be = [
                    pilot
                    for pilot in squadron.active_pilots
                    if id(pilot) not in assigned
                    and not (squadron.morale_in_play and pilot.refuses_to_fly)
                ]
                wanted = {id(pilot) for pilot in should_be}
                seen: set[int] = set()
                # Keep whoever was already listed in the order they were listed in,
                # then append the ones that went missing.
                pool = []
                for pilot in squadron.available_pilots:
                    if id(pilot) in wanted and id(pilot) not in seen:
                        seen.add(id(pilot))
                        pool.append(pilot)
                missing = [p for p in should_be if id(p) not in seen]
                pool.extend(missing)
                if len(pool) != len(squadron.available_pilots) or missing:
                    dropped = len(squadron.available_pilots) - (
                        len(pool) - len(missing)
                    )
                    if dropped:
                        logging.info(
                            f"{squadron}: {dropped} pilot(s) were available and unable "
                            "to fly at the same time; corrected"
                        )
                    if missing:
                        logging.info(
                            f"{squadron}: {len(missing)} fit pilot(s) had gone missing "
                            f"from the pool ({', '.join(p.name for p in missing)}); "
                            "returned"
                        )
                    squadron.available_pilots = pool

    def _update_squadrons(self) -> None:
        country_dict = {
            "Netherlands": "The Netherlands",
            "CHN": "China",
        }
        # Squadrons
        for cp in self.game.theater.controlpoints:
            for s in cp.squadrons:
                preferred_task = max(
                    s.aircraft.task_priorities,
                    key=lambda x: s.aircraft.task_priorities[x],
                )
                try_set_attr(s, "primary_task", preferred_task)
                try_set_attr(s, "max_size", 12)
                try_set_attr(s, "radio_presets", {})
                try_set_attr(s, "livery_set", [])
                try_set_attr(s, "_livery_pool", [])
                if isinstance(s.country, str):
                    c = country_dict.get(s.country, s.country)
                    s.country = countries_by_name[c]()

                # code below is used to fix corruptions wrt overpopulation
                parking_type = ParkingType().from_squadron(s)
                if (
                    s.owned_aircraft < 0
                    or s.location.unclaimed_parking(parking_type) < 0
                ):
                    # unclaimed_parking + owned is the capacity available to this
                    # squadron alone; clamp an overfull squadron down to it. The
                    # min() guards the negative-owned case: a negative count must
                    # collapse to 0, not balloon up to the whole airfield.
                    s.owned_aircraft = max(
                        0,
                        min(
                            s.owned_aircraft,
                            s.location.unclaimed_parking(parking_type)
                            + s.owned_aircraft,
                        ),
                    )

                if self.is_liberation:
                    s.set_auto_assignable_mission_types(s.auto_assignable_mission_types)
        # SquadronDefs
        for coa in self.game.coalitions:
            for ac, sdefs in coa.air_wing.squadron_defs.items():
                for sdef in sdefs:
                    try_set_attr(sdef, "radio_presets", {})

    def _update_transfers(self) -> None:
        # Track transfers across all coalitions to detect the same object in
        # more than one coalition's containers.
        global_seen: set[int] = set()
        for coalition in self.game.coalitions:
            self._normalize_transfers_for_coalition(coalition, global_seen)

    def _normalize_transfers_for_coalition(
        self, coalition: Any, global_seen: set[int]
    ) -> None:
        """Normalize transfer player ownership for a coalition's transfers.

        Traverses the pending list plus convoy/cargo aliases, deduplicating
        transfer objects by identity. Missing and legacy-boolean owners are set
        from the containing coalition. An existing enum owner that conflicts
        with its sole container, or the same transfer reachable from more than
        one coalition, fails with a diagnostic.
        """
        transfers = coalition.transfers
        aliased = chain.from_iterable(c.transfers for c in transfers.convoys)
        shipped = chain.from_iterable(c.transfers for c in transfers.cargo_ships)
        seen: set[int] = set()
        all_transfers: list[Any] = []
        for transfer in chain(transfers.pending_transfers, aliased, shipped):
            if id(transfer) not in seen:
                seen.add(id(transfer))
                all_transfers.append(transfer)

        for transfer in all_transfers:
            if id(transfer) in global_seen:
                raise RuntimeError(
                    f"Transfer {transfer} is reachable from more than one coalition"
                )
            global_seen.add(id(transfer))

        for transfer in all_transfers:
            self._normalize_single_transfer_player(transfer, coalition)

    @staticmethod
    def _normalize_single_transfer_player(transfer: Any, coalition: Any) -> None:
        owner = getattr(transfer, "player", None)
        if owner is None or isinstance(owner, bool):
            transfer.player = coalition.player
        elif owner != coalition.player:
            raise RuntimeError(
                f"Transfer {transfer} has owner {owner} but is in the "
                f"{coalition.player} coalition"
            )

    @typing.no_type_check
    def _update_factions(self) -> None:
        for c in self.game.coalitions:
            if isinstance(c.faction.country, str):
                c.faction.country = countries_by_name[c.faction.country]()
            if getattr(c.faction, "aircraft", None) and isinstance(
                c.faction.aircraft, list
            ):
                c.faction.aircraft = set(c.faction.aircraft)
            elif getattr(c.faction, "aircrafts", None) and isinstance(
                c.faction.aircrafts, list
            ):
                c.faction.aircraft = set(c.faction.aircrafts)
            if isinstance(c.faction.awacs, list):
                c.faction.awacs = set(c.faction.awacs)
            if isinstance(c.faction.tankers, list):
                c.faction.tankers = set(c.faction.tankers)
            if isinstance(c.faction.frontline_units, list):
                c.faction.frontline_units = set(c.faction.frontline_units)
            if isinstance(c.faction.artillery_units, list):
                c.faction.artillery_units = set(c.faction.artillery_units)
            if isinstance(c.faction.infantry_units, list):
                c.faction.infantry_units = set(c.faction.infantry_units)
            if isinstance(c.faction.logistics_units, list):
                c.faction.logistics_units = set(c.faction.logistics_units)
            if isinstance(c.faction.air_defense_units, list):
                c.faction.air_defense_units = set(c.faction.air_defense_units)
            if isinstance(c.faction.missiles, list):
                c.faction.missiles = set(c.faction.missiles)
            if isinstance(c.faction.naval_units, list):
                c.faction.naval_units = set(c.faction.naval_units)
            if isinstance(c.faction.building_set, list):
                c.faction.building_set = set(c.faction.building_set)

    def _update_weather(self) -> None:
        a = self.game.conditions.weather.atmospheric
        try_set_attr(a, "turbulence_per_10cm", 0.1)
        sc = self.game.theater.seasonal_conditions
        if not hasattr(
            self.game.theater.seasonal_conditions, "high_avg_yearly_turbulence_per_10cm"
        ):
            self.game.theater.seasonal_conditions = SeasonalConditions(
                summer_avg_pressure=sc.summer_avg_pressure,
                winter_avg_pressure=sc.winter_avg_pressure,
                summer_avg_temperature=sc.summer_avg_temperature,
                winter_avg_temperature=sc.winter_avg_temperature,
                temperature_day_night_difference=sc.temperature_day_night_difference,
                high_avg_yearly_turbulence_per_10cm=1.2,
                low_avg_yearly_turbulence_per_10cm=0.1,
                solar_noon_turbulence_per_10cm=0.8,
                midnight_turbulence_per_10cm=0.4,
                weather_type_chances=sc.weather_type_chances,
            )

    def _update_tgos(self) -> None:
        for go in self.game.theater.ground_objects:
            try_set_attr(go, "task", None)
            try_set_attr(go, "hide_on_mfd", False)
            # Movable-ship state added after some saves were written; pickle
            # bypasses __init__, so back-fill it or finish_turn's movement pass
            # raises AttributeError on pre-feature saves.
            if isinstance(go, ShipGroundObject):
                try_set_attr(go, "target_position", None)

    def _restore_pruned_iads_nodes(self) -> None:
        """Put back the IADS nodes a destroyed site used to be dropped from.

        A site with nothing alive was taken out of the network altogether, and its
        links went off the map with it -- so in a campaign that has been fought in, the
        breaks you most want to see are the ones that are missing. The code no longer
        prunes, but the damage is already in the save: the nodes and their connection
        ids are gone, and nothing recreates them.

        So the network is rebuilt once, from the campaign's own configuration and the
        objectives as they stand, which is exactly what happens when a campaign starts.
        Once is enough -- it cannot be pruned again -- and the flag says it has been
        done, so a save that has already been through here keeps the network it has.
        """
        network = self.game.theater.iads_network
        if getattr(network, "keeps_destroyed_nodes", False):
            return
        network.keeps_destroyed_nodes = True
        before = len(network.nodes)
        network.nodes = []
        network.ground_objects = {}
        network.initialize_network(iter(self.game.theater.ground_objects))
        logging.info(
            "IADS network rebuilt to restore pruned nodes: "
            f"{before} -> {len(network.nodes)} nodes"
        )

    def _relabel_formation_waypoints(self) -> None:
        """Join and split are the package's, not the flight's.

        A flight that is the whole package has nobody to meet, so those two waypoints
        read as nav points now. Flight plans are saved with the game, so the ones
        already built carry the old names until they are rebuilt.
        """
        for coalition in (self.game.blue, self.game.red):
            for package in coalition.ato.packages:
                package.label_formation_waypoints()

    def _ensure_motorpool_tgos(self) -> None:
        from game.data.groups import GroupTask
        from game.naming import namegen
        from game.theater.controlpoint import warn_if_motorpool_inside_capture_zone
        from game.theater.theatergroundobject import MotorpoolGroundObject

        if not self.game.settings.motorpool_enabled:
            return
        control_points = self.game.theater.controlpoints
        from game.missiongenerator.motorpoolpopulator import motorpool_identity

        authored = {
            motorpool_identity(location.original_name, location)
            for cp in control_points
            for location in getattr(cp.preset_locations, "motorpools", [])
        }
        existing: dict[tuple[str, float, float, float], MotorpoolGroundObject] = {}
        identity: tuple[str, float, float, float]
        for cp in control_points:
            for tgo in cp.ground_objects:
                if not isinstance(tgo, MotorpoolGroundObject):
                    continue
                identity = (
                    tgo.original_name,
                    tgo.position.x,
                    tgo.position.y,
                    tgo.heading.degrees,
                )
                if identity in authored:
                    existing.setdefault(identity, tgo)

        # Remove stale and duplicate persisted references before ensuring every
        # current authored marker has exactly one surviving TGO.
        seen: set[MotorpoolGroundObject] = set()
        for cp in control_points:
            retained: list[TheaterGroundObject] = []
            for tgo in cp.connected_objectives:
                if not isinstance(tgo, MotorpoolGroundObject):
                    retained.append(tgo)
                    continue
                identity = (
                    tgo.original_name,
                    tgo.position.x,
                    tgo.position.y,
                    tgo.heading.degrees,
                )
                if existing.get(identity) is tgo and tgo not in seen:
                    retained.append(tgo)
                    seen.add(tgo)
            cp.connected_objectives[:] = retained

        for cp in control_points:
            for location in getattr(cp.preset_locations, "motorpools", []):
                identity = motorpool_identity(location.original_name, location)
                if identity in existing:
                    continue
                name = namegen.random_objective_name()
                warn_if_motorpool_inside_capture_zone(name, location, cp)
                tgo = MotorpoolGroundObject(
                    # Codename like every other TGO; the "motorpool" category
                    # label already says what it is.
                    name,
                    location,
                    cp,
                    GroupTask.MOTORPOOL,
                )
                cp.connected_objectives.append(tgo)
                existing[identity] = tgo

    def _register_new_tgos(self) -> None:
        """Put every objective in the lookup the map and the API read.

        db.tgos is filled once, at turn 0, so an objective added to a campaign already
        under way -- a motorpool the step above just created, anything a later
        migration adds -- was never in it. Clicking one asked the server for a UUID it
        did not know and the info window never opened. Last of the migration steps, so
        it catches whatever the others made.
        """
        for cp in self.game.theater.controlpoints:
            for tgo in cp.connected_objectives:
                if tgo.id not in self.game.db.tgos.objects:
                    self.game.db.tgos.add(tgo.id, tgo)

    def _reload_terrain(self) -> None:
        t = self.game.theater.terrain
        if issubclass(t.__class__, Terrain):
            self.game.theater.terrain = type(t)()  # type: ignore

    def _update_theater(self) -> None:
        if not hasattr(self.game.theater, "rebel_zones"):
            self.game.theater.rebel_zones = []

    def _update_campaign_name(self) -> None:
        if not hasattr(self.game, "campaign_name"):
            self.game.campaign_name = None
