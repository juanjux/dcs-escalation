"""What every High Command objective is measured against, worked out once per list."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any, Iterator, Optional

from dcs import Point

from game.ato.flighttype import FlightType
from game.highcommand.approach import Approach, Release, Ring
from game.income import Income
from game.mfd import Band, band_of
from game.theater import Airfield, ControlPoint, Fob, Player
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.theatergroundobject import (
    MotorpoolGroundObject,
    TheaterGroundObject,
)
from game.utils import nautical_miles

if TYPE_CHECKING:
    from game import Game

#: What a site's ring weighs over the site itself. It falls off to nothing at the
#: edge of the ring. A long-range SAM is what decides whether a package needs SEAD
#: at all.
RING_WEIGHT = {Band.LONG: 4.0, Band.MEDIUM: 2.5, Band.SHORT: 1.0}

#: How close bombs, rockets and Mavericks have to be brought.
DIRECT_RELEASE = nautical_miles(10)

#: What needing a stand-off weapon adds to a route, in miles: fewer aircraft carry
#: one.
STANDOFF_PENALTY = 50.0

#: The anti-ship missiles, which have nothing to aim at on land, by weapon group name.
#: A SLAM reaches a ship as well as a building.
ANTI_SHIP = re.compile(
    r"^(8x)?AGM-84[AD]\b|Exocet|Sea Eagle|^Kh-(22|35|41)\b|^KSR-|^C-802AK$|^YJ-|"
    r"RBS-15|^RB-15|LRASM|Kormoran"
)
AGAINST_SHIPS_TOO = re.compile(r"SLAM|BrahMos")


class Campaign:
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
            and (ring := self.ring(tgo)) is not None
        ]
        self.our_bases = sorted(
            {
                s.location
                for s in game.coalition_for(player).air_wing.iter_squadrons()
                if s.owned_aircraft > 0
            },
            key=lambda cp: cp.name,
        )
        self.land_releases, self.sea_releases = releases(game, player)

        #: The enemy's aircraft by base: how many, how many of them fighters, in how
        #: many squadrons, and what they cost.
        self.aircraft: Counter[ControlPoint] = Counter()
        self.fighters: Counter[ControlPoint] = Counter()
        self.squadrons: Counter[ControlPoint] = Counter()
        self.aircraft_worth: defaultdict[ControlPoint, float] = defaultdict(float)
        for squadron in game.coalition_for(self.enemy).air_wing.iter_squadrons():
            if squadron.owned_aircraft <= 0:
                continue
            base = squadron.location
            self.aircraft[base] += squadron.owned_aircraft
            self.squadrons[base] += 1
            self.aircraft_worth[base] += (
                squadron.owned_aircraft * squadron.aircraft.price
            )
            if squadron.capable_of(FlightType.BARCAP):
                self.fighters[base] += squadron.owned_aircraft
        #: What our own aircraft at each of our bases cost.
        self.our_aircraft_worth: defaultdict[ControlPoint, float] = defaultdict(float)
        for squadron in game.coalition_for(player).air_wing.iter_squadrons():
            if squadron.owned_aircraft > 0:
                self.our_aircraft_worth[squadron.location] += (
                    squadron.owned_aircraft * squadron.aircraft.price
                )

        income = Income(game, self.enemy)
        self.income_multiplier = income.multiplier
        self.enemy_income = income.total
        self.approach: Optional[Approach] = None
        if self.our_bases:
            self.approach = Approach(
                self.rings,
                [(cp, cp.position) for cp in self.our_bases],
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

    def ring(self, tgo: TheaterGroundObject) -> Optional[Ring]:
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
                for cp in self.our_bases
                if cp.position.distance_to_point(position) <= reach
            ),
            key=lambda cp: cp.position.distance_to_point(position),
        )


def releases(game: Game, player: Player) -> tuple[list[Release], list[Release]]:
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

    def found(at_sea: bool) -> list[Release]:
        options = [Release(DIRECT_RELEASE.meters)]
        weapon = best.get(at_sea)
        if weapon is not None and _reach(weapon) > DIRECT_RELEASE.meters:
            options.append(Release(_reach(weapon), STANDOFF_PENALTY))
        return options

    return found(False), found(True)


def _reach(weapon: Any) -> float:
    reach = weapon.launch_range
    return reach.meters if reach is not None else 0.0
