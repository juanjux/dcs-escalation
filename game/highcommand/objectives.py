"""The enemy objectives the High Command can order attacked, how hard each one is to
get at, and one line on why it is worth attacking.

What getting at an objective takes, its effort, adds up three things, each in points:

* the route, which weighs the most: the cheapest way from one of our bases to a point
  a weapon can reach the objective from, a mile inside an enemy ring costing more than
  a mile outside, and more the further that site reaches and the closer the route
  passes to it (``approach.py``). Our aircraft release bombs and Mavericks close in,
  and whatever longer-reaching weapon they carry from further out, so a battery on the
  coast is hit from outside its ring, and an objective behind two rings costs the
  detour or the rings;
* the enemy fighters based within reach of it;
* how much of it there is to destroy.

Difficulty, from 1 to 5, is where that effort falls among all of the enemy's
objectives, in fifths: 1 for the easiest fifth, 5 for the hardest. A campaign where a
long-range SAM covers everything would otherwise rate nearly everything the same; the
effort itself stays on the objective for whatever needs a number that means the same
in every campaign.

The line comes from the campaign: what the objective powers, covers, earns or carries.
One with nothing to say for itself gets COMICAL, for a later step to replace with a
humorous one.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Optional, Sequence

from dcs import Point

from game.ato.flighttype import FlightType
from game.config import REWARDS
from game.data.units import UnitClass
from game.highcommand.approach import Approach, Release, Ring
from game.income import Income
from game.mfd import GUN_CLASSES, Band, band_of
from game.theater import Airfield, ControlPoint, Fob, MissionTarget, Player
from game.theater.controlpoint import AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, covers, own_generator
from game.theater.theatergroundobject import (
    NAME_BY_CATEGORY,
    AirDefenceKind,
    BuildingGroundObject,
    CoastalSiteGroundObject,
    GenericCarrierGroundObject,
    IadsBuildingGroundObject,
    IadsGroundObject,
    MissileSiteGroundObject,
    MotorpoolGroundObject,
    NavalGroundObject,
    TheaterGroundObject,
    VehicleGroupGroundObject,
)
from game.utils import meters, nautical_miles

if TYPE_CHECKING:
    from game import Game
    from game.theater.iadsnetwork.iadsnetwork import IadsNetworkNode
    from game.theater.theatergroup import TheaterUnit

#: The justification of an objective nothing in the campaign speaks for.
COMICAL = "XXX comical"

#: What a site's ring weighs over the site itself. It falls off to nothing at the
#: edge of the ring. A long-range SAM is what decides whether a package needs SEAD
#: at all.
RING_WEIGHT = {Band.LONG: 4.0, Band.MEDIUM: 2.5, Band.SHORT: 1.0}

#: Miles of route, counted outside every ring, that make a point of effort. Low
#: enough for the route to outweigh the fighters and the size: how far an objective is
#: and what stands in the way decide most of how hard it is.
ROUTE_MILES_PER_POINT = 60.0

#: How close bombs, rockets and Mavericks have to be brought.
DIRECT_RELEASE = nautical_miles(10)

#: What needing a stand-off weapon adds to a route, in miles: fewer aircraft carry
#: one.
STANDOFF_PENALTY = 50.0

#: A ring adding less than this to a route, in miles, is not named among what makes an
#: objective hard.
NAMED_RING_COST = 50.0

#: A route shorter than this is not worth naming either.
NAMED_LENGTH = 100.0

#: Fighters based this close to an objective can be over it before a package is.
FIGHTER_REACH = nautical_miles(150)
FIGHTERS_PER_POINT = 12
MAX_FIGHTER_POINTS = 2.0

#: The anti-ship missiles, which have nothing to aim at on land, by weapon group name.
#: A SLAM reaches a ship as well as a building.
ANTI_SHIP = re.compile(
    r"^(8x)?AGM-84[AD]\b|Exocet|Sea Eagle|^Kh-(22|35|41)\b|^KSR-|^C-802AK$|^YJ-|"
    r"RBS-15|^RB-15|LRASM|Kormoran"
)
AGAINST_SHIPS_TOO = re.compile(r"SLAM|BrahMos")

#: What one flight takes care of, and how many units more make a point. A warship
#: counts as several.
FREE_UNITS = 4
UNITS_PER_POINT = 12
WARSHIP_UNITS = 3
MAX_SIZE_POINTS = 1.0

#: How many difficulties there are.
DIFFICULTIES = 5

#: A building earning less than this share of the enemy's income is not worth a
#: sortie on its own account.
MIN_INCOME_SHARE = 0.01

#: A warship this close to the enemy's carrier is part of its screen.
SCREEN_DISTANCE = nautical_miles(40)

#: How many names a line gives before it counts the rest.
NAMES_SHOWN = 2

UNIT_CLASSES_AT_SEA = frozenset(
    {
        UnitClass.AIRCRAFT_CARRIER,
        UnitClass.HELICOPTER_CARRIER,
        UnitClass.LANDING_SHIP,
        UnitClass.CRUISER,
        UnitClass.DESTROYER,
        UnitClass.FRIGATE,
        UnitClass.SUBMARINE,
    }
)


@dataclass(frozen=True)
class Effort:
    """What getting at an objective takes, in points."""

    route: float
    fighters: float
    size: float

    @property
    def total(self) -> float:
        return self.route + self.fighters + self.size


@dataclass(frozen=True)
class Objective:
    """One enemy objective the High Command can order attacked."""

    name: str
    #: What it is, as the map calls it.
    kind: str
    #: Its ground objects, or the base itself for an airfield.
    targets: tuple[MissionTarget, ...]
    effort: Effort
    #: Why it is worth attacking, in one line, or COMICAL.
    justification: str
    #: What makes it as hard as it is, the worst first.
    hazards: tuple[str, ...]
    #: From 1 to 5, against the rest of the enemy's objectives.
    difficulty: int = 0

    @property
    def position(self) -> Point:
        return self.targets[0].position


def enemy_objectives(game: Game, player: Player = Player.BLUE) -> list[Objective]:
    """Every objective of ``player``'s enemy still standing, easiest first."""
    campaign = _Campaign(game, player)
    found = [campaign.objective(name, tgos) for name, tgos in campaign.groups.items()]
    found.extend(campaign.base_objective(cp) for cp in campaign.enemy_bases())
    return sorted(ranked(found), key=lambda o: (o.effort.total, o.name))


def ranked(objectives: Sequence[Objective]) -> list[Objective]:
    """The objectives with their difficulty: the fifth their effort falls in.

    Equal efforts get the same difficulty, whichever side of a fifth they would
    otherwise straddle.
    """
    totals = sorted(o.effort.total for o in objectives)
    count = len(totals)
    return [
        replace(
            o,
            difficulty=1
            + min(
                DIFFICULTIES - 1,
                DIFFICULTIES * bisect_left(totals, o.effort.total) // count,
            ),
        )
        for o in objectives
    ]


class _Campaign:
    """What every objective is measured against, worked out once."""

    def __init__(self, game: Game, player: Player) -> None:
        self.game = game
        self.player = player
        self.enemy = player.opponent
        network = game.theater.iads_network
        self.network = network
        self.skynet = bool(game.settings.plugin_option("skynetiads")) and bool(
            network.nodes
        )
        #: Comms, power and command only count in the advanced network; the basic one
        #: runs on radars and batteries alone.
        self.advanced = self.skynet and network.advanced_iads
        self.groups = self._standing_objectives()
        self.rings = [
            ring
            for tgo in game.theater.ground_objects
            if tgo.control_point.captured == self.enemy
            and (ring := self._ring(tgo)) is not None
        ]
        our_squadrons = game.coalition_for(player).air_wing.iter_squadrons()
        self.bases = sorted(
            {s.location for s in our_squadrons if s.owned_aircraft > 0},
            key=lambda cp: cp.name,
        )
        self.land_releases, self.sea_releases = _releases(game, player)
        self.aircraft: Counter[ControlPoint] = Counter()
        self.fighters: Counter[ControlPoint] = Counter()
        for squadron in game.coalition_for(self.enemy).air_wing.iter_squadrons():
            if squadron.owned_aircraft <= 0:
                continue
            self.aircraft[squadron.location] += squadron.owned_aircraft
            if squadron.capable_of(FlightType.BARCAP):
                self.fighters[squadron.location] += squadron.owned_aircraft
        income = Income(game, self.enemy)
        self.income_multiplier = income.multiplier
        self.enemy_income = income.total
        self.approach: Optional[Approach] = None
        if self.bases:
            self.approach = Approach(
                self.rings,
                [(cp, cp.position) for cp in self.bases],
                [tgos[0].position for tgos in self.groups.values()]
                + [cp.position for cp in game.theater.controlpoints],
            )

    # ------------------------------------------------------------ what there is

    def _standing_objectives(self) -> dict[str, list[TheaterGroundObject]]:
        from game.commander.objectivefinder import ObjectiveFinder

        worth_striking = set(
            ObjectiveFinder(self.game, self.player).motorpool_targets()
        )
        groups: dict[str, list[TheaterGroundObject]] = defaultdict(list)
        for tgo in self.game.theater.ground_objects:
            if tgo.control_point.captured != self.enemy:
                continue
            if isinstance(tgo.control_point, Fob) and tgo.is_control_point:
                # A FOB's own structure: nothing can target it.
                continue
            if isinstance(tgo, MotorpoolGroundObject) and tgo not in worth_striking:
                continue
            groups[tgo.name].append(tgo)
        return {
            name: tgos
            for name, tgos in groups.items()
            if any(isinstance(t, MotorpoolGroundObject) for t in tgos)
            or not all(t.is_dead for t in tgos)
        }

    def _ring(self, tgo: TheaterGroundObject) -> Optional[Ring]:
        """The ring of a site that shoots, unless it is switched off or destroyed."""
        if tgo.is_dead:
            return None
        reach = tgo.max_threat_range().meters
        if reach <= 0:
            return None
        status = self.network.state_map.status_for(tgo)
        if status is not None and status.state in (
            IadsState.DARK,
            IadsState.DESTROYED,
        ):
            return None
        return Ring(
            site=tgo,
            x=tgo.position.x,
            y=tgo.position.y,
            reach=reach,
            weight=RING_WEIGHT[band_of(tgo)],
        )

    def enemy_bases(self) -> Iterator[ControlPoint]:
        """The enemy's airfields and FOBs with aircraft on them."""
        for cp in self.game.theater.controlpoints:
            if cp.captured != self.enemy or not isinstance(cp, (Airfield, Fob)):
                continue
            if self.aircraft[cp] > 0:
                yield cp

    def positions(self) -> Iterable[tuple[str, Point]]:
        for name, tgos in self.groups.items():
            yield name, tgos[0].position

    def objectives_within(
        self, position: Point, reach: float, excluding: str
    ) -> list[str]:
        return [
            name
            for name, where in self.positions()
            if name != excluding and where.distance_to_point(position) <= reach
        ]

    def enemy_bases_within(self, position: Point, reach: float) -> list[ControlPoint]:
        return sorted(
            (
                cp
                for cp in self.game.theater.controlpoints
                if cp.captured == self.enemy
                and cp.position.distance_to_point(position) <= reach
            ),
            key=lambda cp: cp.position.distance_to_point(position),
        )

    def our_bases_within(self, position: Point, reach: float) -> list[ControlPoint]:
        return sorted(
            (
                cp
                for cp in self.bases
                if cp.position.distance_to_point(position) <= reach
            ),
            key=lambda cp: cp.position.distance_to_point(position),
        )

    # ----------------------------------------------------------- the network

    def _enemy_nodes(self) -> list[IadsNetworkNode]:
        return [
            node
            for node in self.network.nodes
            if node.group.ground_object.control_point.captured == self.enemy
            and node.group.alive_units > 0
        ]

    def cued_by(self, tgo: TheaterGroundObject) -> list[str]:
        """The SAM sites inside this radar's cover, which it hands targets to."""
        radar = next(
            (n for n in self.network.nodes if n.group.ground_object is tgo), None
        )
        if radar is None:
            return []
        return _names(
            node
            for node in self._enemy_nodes()
            if node is not radar
            and node.group.iads_role in (IadsRole.SAM, IadsRole.SAM_AS_EWR)
            and covers(radar, node)
        )

    def held_up_by(
        self, tgos: Sequence[TheaterGroundObject], role: IadsRole
    ) -> list[IadsNetworkNode]:
        """The sites wired to this objective for power or for comms."""
        return [
            node
            for node in self._enemy_nodes()
            if any(
                group.iads_role is role and group.ground_object in tgos
                for group in node.connections.values()
            )
        ]

    def directed(self) -> tuple[list[str], int]:
        """The radars and batteries under command, and how many command centres."""
        nodes = self._enemy_nodes()
        sites = _names(
            node
            for node in nodes
            if node.group.iads_role in (IadsRole.SAM, IadsRole.SAM_AS_EWR, IadsRole.EWR)
        )
        centres = sum(
            1 for node in nodes if node.group.iads_role is IadsRole.COMMAND_CENTER
        )
        return sites, centres

    # ------------------------------------------------------------ the objective

    def objective(self, name: str, tgos: list[TheaterGroundObject]) -> Objective:
        position = tgos[0].position
        at_sea = isinstance(tgos[0], NavalGroundObject)
        effort, hazards = self._effort(name, position, _size(tgos), at_sea)
        return Objective(
            name=name,
            kind=_kind(tgos[0]),
            targets=tuple(tgos),
            effort=effort,
            justification=self._justify(tgos),
            hazards=hazards,
        )

    def base_objective(self, cp: ControlPoint) -> Objective:
        effort, hazards = self._effort(cp.name, cp.position, 0, at_sea=False)
        return Objective(
            name=cp.name,
            kind="Airfield" if isinstance(cp, Airfield) else "FOB",
            targets=(cp,),
            effort=effort,
            justification=self._aircraft_line("Home to", cp),
            hazards=hazards,
        )

    def _effort(
        self, name: str, position: Point, units: int, at_sea: bool
    ) -> tuple[Effort, tuple[str, ...]]:
        hazards: list[str] = []

        route_points = 0.0
        if self.approach is not None:
            route = self.approach.route(
                position, self.sea_releases if at_sea else self.land_releases
            )
            route_points = (route.cost + route.release.penalty) / ROUTE_MILES_PER_POINT
            for cost, ring in route.rings[:2]:
                if cost < NAMED_RING_COST:
                    break
                system = system_name(ring.site)
                site = ring.site.name
                hazards.append(
                    f"its own {system}" if site == name else f"{system} at {site}"
                )
            if route.base is not None and route.length >= NAMED_LENGTH:
                hazards.append(f"{route.length:.0f} nm from {route.base.name}")

        fighters = sum(
            count
            for cp, count in self.fighters.items()
            if cp.position.distance_to_point(position) <= FIGHTER_REACH.meters
        )
        if fighters:
            hazards.append(
                f"{fighters} fighters within {FIGHTER_REACH.nautical_miles:.0f} nm"
            )

        size_points = min(
            MAX_SIZE_POINTS, max(0.0, (units - FREE_UNITS) / UNITS_PER_POINT)
        )
        if size_points >= 0.5:
            hazards.append(f"{units} units to destroy")

        effort = Effort(
            route=route_points,
            fighters=min(MAX_FIGHTER_POINTS, fighters / FIGHTERS_PER_POINT),
            size=size_points,
        )
        return effort, tuple(hazards)

    # --------------------------------------------------------- the justification

    def _justify(self, tgos: Sequence[TheaterGroundObject]) -> str:
        tgo = tgos[0]
        if isinstance(tgo, GenericCarrierGroundObject) and (
            self.aircraft[tgo.control_point] > 0
        ):
            return self._aircraft_line("Carries", tgo.control_point)
        if isinstance(tgo, NavalGroundObject):
            return self._warships(tgos)
        if isinstance(tgo, IadsBuildingGroundObject):
            return self._infrastructure(tgos)
        if isinstance(tgo, IadsGroundObject):
            kind = tgo.air_defence_kind
            if kind is AirDefenceKind.JAMMER:
                return self._jammer(tgo)
            if kind is AirDefenceKind.RADAR:
                return self._radar(tgo)
            return self._battery(tgo)
        if isinstance(tgo, MotorpoolGroundObject):
            return self._motorpool(tgo)
        if isinstance(tgo, CoastalSiteGroundObject):
            return (
                f"Its {system_name(tgo)} launchers cover the sea off "
                f"{tgo.control_point.name}: our ships keep away."
            )
        if isinstance(tgo, MissileSiteGroundObject):
            return (
                f"Its {system_name(tgo)} launchers can fire on our positions from "
                f"{tgo.control_point.name}."
            )
        if isinstance(tgo, VehicleGroupGroundObject):
            return self._garrison(tgos)
        if isinstance(tgo, BuildingGroundObject):
            return self._building(tgos)
        return COMICAL

    def _battery(self, tgo: TheaterGroundObject) -> str:
        system = system_name(tgo)
        reach = tgo.max_threat_range().meters
        ours = self.our_bases_within(tgo.position, reach)
        if ours:
            return f"Its {system} reaches {_ours(ours[0])}."
        covered = self.objectives_within(tgo.position, reach, excluding=tgo.name)
        bases = self.enemy_bases_within(tgo.position, reach)
        places = [base.name for base in bases[:1]] + _objectives(covered)
        if not places:
            return COMICAL
        return f"Its {system} covers {_and(places)}."

    def _radar(self, tgo: TheaterGroundObject) -> str:
        cued = self.cued_by(tgo) if self.skynet else []
        if cued:
            return (
                f"Early warning for {_count(len(cued), 'SAM site')}: "
                f"{_listed(cued)}."
            )
        reach = tgo.max_detection_range().meters
        if reach <= 0:
            return COMICAL
        return f"Its radar sees our aircraft {meters(reach).nautical_miles:.0f} nm out."

    def _jammer(self, tgo: TheaterGroundObject) -> str:
        from game.gpsjamming import gps_jamming_enabled, jamming_reach_for

        if not gps_jamming_enabled(self.game):
            return COMICAL
        reach = jamming_reach_for(self.game, tgo)
        if reach is None:
            return COMICAL
        covered = self.objectives_within(tgo.position, reach.meters, excluding=tgo.name)
        bases = self.enemy_bases_within(tgo.position, reach.meters)
        if bases:
            return (
                f"Jams GPS within {reach.nautical_miles:.0f} nm of {bases[0].name}: "
                "our GPS weapons miss there."
            )
        if covered:
            return (
                f"Jams GPS over {_and(_objectives(covered))}: our GPS weapons miss "
                "there."
            )
        return COMICAL

    def _infrastructure(self, tgos: Sequence[TheaterGroundObject]) -> str:
        if not self.advanced:
            return COMICAL
        category = tgos[0].category
        if category == "power":
            powered = [
                node
                for node in self.held_up_by(tgos, IadsRole.POWER_SOURCE)
                if own_generator(node.group) is None
            ]
            if not powered:
                return COMICAL
            return f"Powers {_sites(_names(powered), 'go dark', 'goes dark')}."
        if category == "comms":
            names = _names(self.held_up_by(tgos, IadsRole.CONNECTION_NODE))
            if not names:
                return COMICAL
            return f"Connects {_sites(names, 'fight alone', 'fights alone')}."
        if category == "commandcenter":
            sites, centres = self.directed()
            if not sites:
                return COMICAL
            if centres <= 1:
                return f"Directs all {_sites(sites, 'fight alone', 'fights alone')}."
            return (
                f"One of {centres} command centres directing "
                f"{_count(len(sites), 'air defence site')}."
            )
        return COMICAL

    def _building(self, tgos: Sequence[TheaterGroundObject]) -> str:
        tgo = tgos[0]
        cp = tgo.control_point
        if tgo.category == "ammo" and cp.front_lines:
            return (
                f"Supplies the front at {cp.name}: "
                f"{AMMO_DEPOT_FRONTLINE_UNIT_CONTRIBUTION} more units in the line."
            )
        income = self.income_multiplier * sum(
            REWARDS.get(t.category, 0) * sum(1 for s in t.statics if s.alive)
            for t in tgos
        )
        if income <= 0 or self.enemy_income <= 0:
            return COMICAL
        share = income / self.enemy_income
        if share < MIN_INCOME_SHARE:
            return COMICAL
        return (
            f"Earns the enemy ${round(income, 1):g}M a turn, {share:.0%} of their "
            "income."
        )

    def _garrison(self, tgos: Sequence[TheaterGroundObject]) -> str:
        units = _alive(tgos)
        if not units:
            return COMICAL
        main, _ = Counter(_short_label(unit) for unit in units).most_common(1)[0]
        cp = tgos[0].control_point
        return (
            f"{len(units)} vehicles ({main}) garrisoning {cp.name}, in the way of any "
            "assault on it."
        )

    def _motorpool(self, tgo: MotorpoolGroundObject) -> str:
        from game.missiongenerator.motorpoolpopulator import (
            motorpool_rendered_unit_count,
        )

        settings = self.game.settings
        count = motorpool_rendered_unit_count(
            tgo, settings.motorpool_enabled, settings.motorpool_spawn_cap
        )
        if count <= 0:
            return COMICAL
        return (
            f"{count} reserve vehicles parked at {tgo.control_point.name}, waiting to "
            "reinforce it."
        )

    def _warships(self, tgos: Sequence[TheaterGroundObject]) -> str:
        ships = len(_alive(tgos))
        carriers = [
            tgo.control_point
            for tgo in self.game.theater.ground_objects
            if isinstance(tgo, GenericCarrierGroundObject)
            and tgo not in tgos
            and tgo.control_point.captured == self.enemy
            and not tgo.is_dead
            and tgo.position.distance_to_point(tgos[0].position)
            <= SCREEN_DISTANCE.meters
        ]
        if carriers:
            return f"{_count(ships, 'warship')} screening the {carriers[0].name}."
        reach = meters(max(t.max_threat_range().meters for t in tgos))
        if reach.meters > 0:
            return (
                f"{_count(ships, 'warship')} whose SAMs close "
                f"{reach.nautical_miles:.0f} nm of sea to our aircraft."
            )
        if ships:
            return (
                f"{_count(ships, 'warship')} holding the sea off "
                f"{tgos[0].control_point.name}."
            )
        return COMICAL

    def _aircraft_line(self, verb: str, cp: ControlPoint) -> str:
        aircraft = self.aircraft[cp]
        if not aircraft:
            return COMICAL
        fighters = self.fighters[cp]
        line = f"{verb} {aircraft} enemy aircraft"
        if fighters == aircraft:
            return f"{line}, all of them fighters."
        if fighters:
            return f"{line}, {fighters} of them fighters."
        return f"{line}."


# ------------------------------------------------------------------- helpers


def _releases(game: Game, player: Player) -> tuple[list[Release], list[Release]]:
    """How close our aircraft have to get to an objective on land, and to a ship.

    Close enough for bombs and Mavericks always, and, when one of our aircraft carries
    something that reaches further, as far out as the longest-reaching of those.
    """
    from game.data.weapons import Pylon, Weapon

    coalition = game.coalition_for(player)
    by_date = game.settings.restrict_weapons_by_date
    best: dict[bool, Weapon] = {}
    for aircraft in {
        s.aircraft for s in coalition.air_wing.iter_squadrons() if s.owned_aircraft
    }:
        for pylon in Pylon.iter_pylons(aircraft):
            weapons = (
                pylon.available_on(game.date, coalition.faction)
                if by_date
                else pylon.allowed
            )
            for weapon in weapons:
                reach = weapon.launch_range
                if reach is None:
                    continue
                name = weapon.weapon_group.name
                anti_ship = bool(ANTI_SHIP.search(name))
                for at_sea in (False, True):
                    if anti_ship != at_sea and not AGAINST_SHIPS_TOO.search(name):
                        continue
                    held = best.get(at_sea)
                    if held is None or reach.meters > _reach(held):
                        best[at_sea] = weapon

    def releases(at_sea: bool) -> list[Release]:
        found = [Release(DIRECT_RELEASE.meters)]
        weapon = best.get(at_sea)
        if weapon is not None and _reach(weapon) > DIRECT_RELEASE.meters:
            found.append(Release(_reach(weapon), STANDOFF_PENALTY))
        return found

    return releases(False), releases(True)


def _reach(weapon: Any) -> float:
    reach = weapon.launch_range
    return reach.meters if reach is not None else 0.0


#: The designations the unit names carry, SA-10 or HQ-7 or SS-N-2.
_DESIGNATION = re.compile(r"\b(SA-\d+[A-Z]?|HQ-\d+[A-Z]?|SS-[NC]-\d+)\b")

#: Systems known by name rather than by designation, as the unit names spell them.
_SYSTEMS = (
    "Patriot",
    "Hawk",
    "NASAMS",
    "Roland",
    "Rapier",
    "IRIS-T",
    "Crotale",
    "Chaparral",
    "Avenger",
    "Gepard",
    "Tunguska",
    "Pantsir",
    "SAMP/T",
    "Skyshield",
    "Silkworm",
    "Stinger",
    "Igla",
    "Vulcan",
    "Shilka",
    "ZSU-57",
    "ZU-23",
    "Bofors",
)


def system_name(tgo: TheaterGroundObject) -> str:
    """What the site's main weapon is called: its designation when it has one."""
    units = _alive([tgo])
    if not units:
        return "site"
    main = max(units, key=lambda unit: unit.threat_range.meters)
    if main.threat_range.meters <= 0:
        # Nothing here shoots at aircraft; a coastal battery's launcher is what it
        # is about.
        main = next(
            (
                unit
                for unit in units
                if getattr(unit.unit_type, "unit_class", None)
                in (UnitClass.ANTISHIP_MISSILE, UnitClass.MISSILE)
            ),
            main,
        )
    label = _unit_label(main)
    found = _DESIGNATION.search(label)
    if found:
        return found.group(1)
    for system in _SYSTEMS:
        if system in label:
            return system
    if getattr(main.unit_type, "unit_class", None) in GUN_CLASSES:
        return "guns"
    return label


def _unit_label(unit: TheaterUnit) -> str:
    return str(unit.unit_type) if unit.unit_type is not None else unit.type.id


def _short_label(unit: TheaterUnit) -> str:
    """The unit's name without the other designation some carry in brackets."""
    return re.sub(r"\s*\(.*\)$", "", _unit_label(unit))


def _alive(tgos: Iterable[TheaterGroundObject]) -> list[TheaterUnit]:
    return [unit for tgo in tgos for unit in tgo.units if unit.alive]


def _size(tgos: Sequence[TheaterGroundObject]) -> int:
    """How many things there are to destroy, a warship counting as several."""
    return sum(
        (
            WARSHIP_UNITS
            if getattr(unit.unit_type, "unit_class", None) in UNIT_CLASSES_AT_SEA
            else 1
        )
        for unit in _alive(tgos)
    )


def _kind(tgo: TheaterGroundObject) -> str:
    if isinstance(tgo, GenericCarrierGroundObject):
        return "Carrier group"
    if isinstance(tgo, IadsGroundObject):
        kind = tgo.air_defence_kind
        if kind is AirDefenceKind.JAMMER:
            return "GPS jammer"
        if kind is AirDefenceKind.RADAR:
            return NAME_BY_CATEGORY["ewr"]
        return NAME_BY_CATEGORY["aa"]
    return NAME_BY_CATEGORY.get(tgo.category, tgo.category)


def _names(nodes: Iterable[IadsNetworkNode]) -> list[str]:
    return sorted({str(node.group.ground_object.name) for node in nodes})


def _objectives(names: Sequence[str]) -> list[str]:
    """A couple of objectives by name, more of them by number."""
    if len(names) <= NAMES_SHOWN:
        return sorted(names)
    return [_count(len(names), "objective")]


def _and(items: Sequence[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _sites(names: Sequence[str], they: str, it: str) -> str:
    """The air defence sites something holds up, and what they do without it."""
    if len(names) == 1:
        return f"the air defence site {names[0]}, which {it} without it"
    return (
        f"{_count(len(names), 'air defence site')} ({_listed(names)}), which {they} "
        "without it"
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _listed(names: Sequence[str], most: int = NAMES_SHOWN) -> str:
    """Up to ``most`` names, and how many more there are."""
    if len(names) <= most:
        return " and ".join(names)
    return f"{', '.join(names[:most])} and {len(names) - most} more"


def _ours(base: ControlPoint) -> str:
    return f"the {base.name}" if base.is_fleet else f"our base at {base.name}"
