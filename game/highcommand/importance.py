"""What losing an objective costs the enemy, and so how much it matters.

Everything is counted in millions, the game's own money. What an objective is worth
by itself adds up:

* rebuild: what rebuilding what stands there costs. Ground units at their price,
  buildings at the game's repair price for each structure, an airfield's runway at
  its repair price. Warships cannot be bought or repaired, so they count by class.
* income: what it earns a turn, over INCOME_TURNS turns, and what rebuilding it costs,
  which the game prices off that income.
* front: the units an ammo depot keeps in the line of a front, at what the base's
  armour costs.
* aircraft: a share of what the enemy aircraft based there cost; for a carrier, a sum
  for each squadron sinking it grounds as well.
* runway: what repairing an airfield's runway costs, and a sum for each squadron a
  cratered runway grounds.
* capture: what the base earns, with its buildings, over INCOME_TURNS turns, and what
  the sites around it are worth, since taking a base clears all but its buildings.
* reserve: what the vehicles parked in a motorpool cost.
* garrison: what an armour group costs, and more the closer it stands to its base,
  which it holds against any assault; more again when that base is on a front.
* threat: a share of what it can hit of ours: our base inside a SAM's ring, our ships
  in range of a coastal battery, our sites in range of a missile site.

Two more come from what it does for the rest, and are worked out after, from what the
rest is worth by itself:

* cover: a share of what its ring protects, split with the other rings over the same
  objective by what each weighs there; GPS jamming the same way over what it jams.
* network: what destroying it would do to the air defence network, worked out by the
  rules that decide each site's state. Each site left to fight alone counts for a
  share of its whole worth, and each switched off for more.

Importance, from 1 to 5, is where the total falls among all of the enemy's objectives,
in fifths, the same as difficulty.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from game.config import REWARDS, RUNWAY_REPAIR_COST
from game.data.units import UnitClass
from game.highcommand.approach import Ring
from game.highcommand.campaign import RING_WEIGHT, Campaign, Task
from game.highcommand.wording import (
    LAUNCHER_CLASSES,
    NAMES_SHOWN,
    alive,
    counted,
    listed,
    money,
    short,
    sites,
    system_name,
    unit_class,
    unit_label,
    unit_system,
)
from game.mfd import Band
from game.theater import Airfield, ControlPoint
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStateMap
from game.theater.theatergroundobject import (
    AirDefenceKind,
    BuildingGroundObject,
    CoastalSiteGroundObject,
    GenericCarrierGroundObject,
    IadsGroundObject,
    MissileSiteGroundObject,
    MotorpoolGroundObject,
    NavalGroundObject,
    TheaterGroundObject,
    VehicleGroupGroundObject,
)
from game.utils import meters, nautical_miles

if TYPE_CHECKING:
    from game.highcommand.objectives import Objective
    from game.theater.theatergroup import TheaterUnit

#: Turns of income an income building counts for.
INCOME_TURNS = 4

#: Warships by class. None of them can be bought or repaired, so sinking one takes it
#: out of the campaign. An SA-20 battery, for scale, costs about $380M.
WARSHIP_WORTH = {
    UnitClass.AIRCRAFT_CARRIER: 500.0,
    UnitClass.HELICOPTER_CARRIER: 250.0,
    UnitClass.CRUISER: 300.0,
    UnitClass.DESTROYER: 200.0,
    UnitClass.FRIGATE: 120.0,
    UnitClass.SUBMARINE: 150.0,
    UnitClass.LANDING_SHIP: 100.0,
}

#: Any other ship: a boat, a tanker, a cargo ship.
OTHER_SHIP_WORTH = 10.0

#: The share of what the aircraft at a base cost that an attack on it puts at stake,
#: and what grounding one squadron is worth.
AIRCRAFT_SHARE = 0.5
SQUADRON_WORTH = 25.0

#: An armour group adds up to this share of its price when it stands within
#: GARRISON_CLOSE of its base, falling to nothing at GARRISON_REACH, and FRONT_FACTOR
#: times that when the base is on a front.
GARRISON_SHARE = 0.5
GARRISON_CLOSE = nautical_miles(3)
GARRISON_REACH = nautical_miles(15)
FRONT_FACTOR = 2.0

#: The share of what a site can hit of ours that it counts for.
THREAT_SHARE = 0.25

#: The share of an objective's worth its air defence stands for, split between the
#: rings over it by what each weighs there, and all of it once they weigh as much as
#: the centre of a long-range SAM.
COVER_SHARE = 0.5
FULL_COVER = RING_WEIGHT[Band.LONG]

#: The same for GPS jamming, split evenly between the jammers over an objective. Less
#: than a ring's: it only stops the weapons that steer by GPS.
JAMMING_SHARE = 0.1

#: The share of a site's worth an objective holds up by keeping it in the network,
#: and by keeping it switched on.
AUTONOMOUS_SHARE = 0.25
DARK_SHARE = 0.5

#: A covered objective adding less than this share of what the first one adds is not
#: named in the line.
NAMED_SHARE = 0.05

#: The reasons that come from what an objective does for the rest.
SHARED = frozenset({"cover", "jamming", "network"})


@dataclass(frozen=True)
class Reason:
    """One thing that makes an objective worth attacking."""

    #: One of rebuild, income, front, aircraft, runway, capture, reserve, garrison,
    #: threat, cover, jamming and network.
    kind: str
    #: In millions.
    worth: float
    #: What it is, in a line for the player.
    line: str
    #: What the worth adds up from, when it says more than the kind: (what, millions).
    parts: tuple[tuple[str, float], ...] = ()


def by_worth(reasons: Iterable[Reason]) -> tuple[Reason, ...]:
    return tuple(sorted(reasons, key=lambda reason: -reason.worth))


def own_worth(objective: Objective) -> float:
    """What the objective is worth by itself, without what it does for the rest."""
    return sum(r.worth for r in objective.reasons if r.kind not in SHARED)


class Worth:
    """The reasons of every objective: its own first, then what it does for the rest."""

    def __init__(self, campaign: Campaign) -> None:
        self.campaign = campaign
        self.game = campaign.game

    # ------------------------------------------------------------------ its own

    def own(self, tgos: Sequence[TheaterGroundObject]) -> tuple[Reason, ...]:
        tgo = tgos[0]
        found: list[Optional[Reason]] = []
        income = self._income(tgos)
        if income is not None:
            found.append(income)
        elif isinstance(tgo, VehicleGroupGroundObject):
            found.append(self._garrison(tgos))
        else:
            found.append(self._rebuild(tgos))
        found.append(self._front(tgos))
        if isinstance(tgo, MotorpoolGroundObject):
            found.append(self._reserve(tgo))
        if isinstance(tgo, GenericCarrierGroundObject):
            found.append(self._aircraft("Carries", tgo.control_point, grounds=True))
        found.append(self._threat(tgos))
        return _kept(found)

    def own_base(self, cp: ControlPoint, task: Task) -> tuple[Reason, ...]:
        """What the task asked of a base costs the enemy."""
        if task is Task.AIRCRAFT:
            return _kept([self._aircraft("Home to", cp, grounds=False)])
        if task is Task.RUNWAY:
            return _kept([self._runway(cp)])
        return _kept([self._capture(cp)])

    def _capture(self, cp: ControlPoint) -> Optional[Reason]:
        buildings = [
            t for t in cp.ground_objects if isinstance(t, BuildingGroundObject)
        ]
        income = self.campaign.income_multiplier * (
            cp.income_per_turn
            + sum(
                REWARDS.get(t.category, 0) * sum(1 for s in t.statics if s.alive)
                for t in buildings
            )
        )
        cleared = [
            t
            for t in cp.ground_objects
            if not isinstance(t, BuildingGroundObject) and not t.is_dead
        ]
        earned = income * INCOME_TURNS
        sites = sum(rebuild_worth([t]) for t in cleared)
        worth = earned + sites
        if worth <= 0:
            return None
        line = f"Taking it costs the enemy {money(income)} a turn"
        if cleared:
            line += f" and {counted(len(cleared), 'site')} around it"
        parts = [(_turns_of(income), earned)]
        if sites > 0:
            parts.append((f"rebuild, {counted(len(cleared), 'site')} around it", sites))
        return Reason("capture", worth, line + ".", tuple(parts))

    def _runway(self, cp: ControlPoint) -> Optional[Reason]:
        squadrons = self.campaign.squadrons[cp]
        if not squadrons:
            return None
        return Reason(
            "runway",
            RUNWAY_REPAIR_COST + SQUADRON_WORTH * squadrons,
            f"Cratering its runway grounds {counted(squadrons, 'squadron')} until the "
            f"enemy pays {money(RUNWAY_REPAIR_COST)} to repair it.",
        )

    def _rebuild(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        units = alive(tgos)
        ships = [unit for unit in units if unit.is_ship]
        worth = rebuild_worth(tgos)
        if worth <= 0:
            return None
        tgo = tgos[0]
        if isinstance(tgo, GenericCarrierGroundObject) and ships:
            escorts = counted(len(ships) - 1, "escort")
            line = (
                f"The {tgo.control_point.name} and {escorts}, which the enemy cannot "
                "replace."
            )
        elif ships:
            line = (
                f"{counted(len(ships), 'warship')} ({_most_common(ships)}) the enemy "
                "cannot replace."
            )
        elif isinstance(tgo, IadsGroundObject):
            line = f"Its {system_name(tgo)} costs the enemy {money(worth)} to rebuild."
        else:
            line = f"Costs the enemy {money(worth)} to rebuild."
        return Reason("rebuild", worth, line)

    def _income(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        income = self.campaign.income_multiplier * sum(
            REWARDS.get(t.category, 0) * sum(1 for s in t.statics if s.alive)
            for t in tgos
        )
        if income <= 0:
            return None
        total = self.campaign.enemy_income
        share = income / total if total > 0 else 0.0
        rebuild = rebuild_worth(tgos)
        parts = [(_turns_of(income), income * INCOME_TURNS)]
        if rebuild > 0:
            parts.append((f"rebuild, {_buildings(tgos)}", rebuild))
        return Reason(
            "income",
            income * INCOME_TURNS + rebuild,
            f"Earns the enemy {money(income)} a turn, {share:.0%} of their income.",
            tuple(parts),
        )

    def _front(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        depots = [t for t in tgos if t.is_ammo_depot]
        if not depots:
            return None
        cp = depots[0].control_point
        if not cp.front_lines:
            return None
        standing = sum(t.alive_unit_count for t in depots)
        lost = cp.deployable_front_line_units - cp.deployable_front_line_units_with(
            max(0, cp.active_ammo_depots_count - standing)
        )
        armour = cp.base.armor
        vehicles = sum(armour.values())
        if lost <= 0 or vehicles <= 0:
            return None
        price = sum(t.price * n for t, n in armour.items()) / vehicles
        return Reason(
            "front",
            lost * price,
            f"Supplies the front at {cp.name}: {lost} more units in the line.",
        )

    def _aircraft(self, verb: str, cp: ControlPoint, grounds: bool) -> Optional[Reason]:
        campaign = self.campaign
        aircraft = campaign.aircraft[cp]
        if not aircraft:
            return None
        squadrons = campaign.squadrons[cp]
        fighters = campaign.fighters[cp]
        line = f"{verb} {counted(squadrons, 'squadron')}: {aircraft} aircraft"
        if fighters == aircraft:
            line += ", all of them fighters"
        elif fighters:
            line += f", {fighters} of them fighters"
        worth = AIRCRAFT_SHARE * campaign.aircraft_worth[cp]
        if grounds:
            worth += SQUADRON_WORTH * squadrons
        return Reason("aircraft", worth, line + ".")

    def _reserve(self, tgo: MotorpoolGroundObject) -> Optional[Reason]:
        from game.missiongenerator.motorpoolpopulator import motorpool_rendered_units

        settings = self.game.settings
        units = motorpool_rendered_units(
            tgo, settings.motorpool_enabled, settings.motorpool_spawn_cap
        )
        if not units:
            return None
        main, _ = Counter(short(str(unit)) for unit in units).most_common(1)[0]
        return Reason(
            "reserve",
            float(sum(unit.price for unit in units)),
            f"{len(units)} reserve vehicles ({main}) parked at "
            f"{tgo.control_point.name}, waiting to reinforce it.",
        )

    def _garrison(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        units = alive(tgos)
        price = sum(u.unit_type.price for u in units if u.unit_type is not None)
        if price <= 0:
            return None
        cp = tgos[0].control_point
        distance = tgos[0].position.distance_to_point(cp.position)
        closeness = min(
            1.0,
            max(
                0.0,
                (GARRISON_REACH.meters - distance)
                / (GARRISON_REACH.meters - GARRISON_CLOSE.meters),
            ),
        )
        extra = GARRISON_SHARE * closeness
        if cp.front_lines:
            extra *= FRONT_FACTOR
        armour = [u for u in units if not u.is_anti_air] or units
        anti_air = sorted({_anti_air_name(u) for u in units if u.is_anti_air})
        what = ", ".join([_most_common(armour), *anti_air])
        return Reason(
            "garrison",
            price * (1 + extra),
            f"{len(units)} vehicles ({what}) garrisoning {cp.name}, in the way of any "
            "assault on it.",
        )

    def _threat(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        tgo = tgos[0]
        if isinstance(tgo, CoastalSiteGroundObject):
            return self._threat_to_ships(tgos)
        if isinstance(tgo, MissileSiteGroundObject):
            return self._threat_to_sites(tgos)
        reach = max(t.max_threat_range().meters for t in tgos)
        if reach <= 0:
            return None
        ours = self.campaign.our_bases_within(tgo.position, reach)
        if not ours:
            return None
        worth = THREAT_SHARE * sum(self.campaign.our_aircraft_worth[cp] for cp in ours)
        return Reason(
            "threat", worth, f"Its {system_name(tgo)} reaches {_ours(ours[0])}."
        )

    def _threat_to_ships(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        reach = _launcher_reach(tgos)
        position = tgos[0].position
        ships = [
            t
            for t in self._ours()
            if isinstance(t, NavalGroundObject)
            and t.position.distance_to_point(position) <= reach
        ]
        if not ships:
            return None
        worth = THREAT_SHARE * sum(
            rebuild_worth([t])
            + (
                self.campaign.our_aircraft_worth[t.control_point]
                if isinstance(t, GenericCarrierGroundObject)
                else 0.0
            )
            for t in ships
        )
        nearest = min(ships, key=lambda t: t.position.distance_to_point(position))
        target = (
            f"the {nearest.control_point.name}"
            if isinstance(nearest, GenericCarrierGroundObject)
            else f"our ships at {nearest.name}"
        )
        return Reason(
            "threat",
            worth,
            f"Its {system_name(tgos[0])} launchers reach {target}.",
        )

    def _threat_to_sites(self, tgos: Sequence[TheaterGroundObject]) -> Optional[Reason]:
        reach = _launcher_reach(tgos)
        position = tgos[0].position
        targets = [
            t
            for t in self._ours()
            if not isinstance(t, NavalGroundObject)
            and t.position.distance_to_point(position) <= reach
        ]
        if not targets:
            return None
        # It fires at one of them a mission: the best it could pick is what is at
        # stake.
        best = max(targets, key=lambda t: rebuild_worth([t]))
        return Reason(
            "threat",
            THREAT_SHARE * rebuild_worth([best]),
            f"Its {system_name(tgos[0])} launchers can hit "
            f"{counted(len(targets), 'of our sites')}, {best.name} among them.",
        )

    def _ours(self) -> list[TheaterGroundObject]:
        player = self.campaign.player
        return [
            t
            for t in self.game.theater.ground_objects
            if t.control_point.captured == player and not t.is_dead
        ]

    # -------------------------------------------------------- for the rest

    def shared(self, objectives: Sequence[Objective]) -> dict[str, list[Reason]]:
        """What each objective does for the rest: the cover it gives, the GPS it jams,
        and what it holds up in the air defence network."""
        own = {o.name: own_worth(o) for o in objectives}
        found: dict[str, list[Reason]] = defaultdict(list)
        for name, reason in self._cover(objectives, own):
            found[name].append(reason)
        for name, reason in self._jamming(objectives, own):
            found[name].append(reason)
        whole = {
            o.name: own[o.name] + sum(r.worth for r in found[o.name])
            for o in objectives
        }
        for name, reason in self._network(objectives, whole):
            found[name].append(reason)
        return found

    def _cover(
        self, objectives: Sequence[Objective], own: dict[str, float]
    ) -> Iterable[tuple[str, Reason]]:
        rings: dict[str, list[Ring]] = defaultdict(list)
        for ring in self.campaign.rings:
            rings[ring.site.name].append(ring)
        if not rings:
            return
        # What every ring but its own weighs over each objective.
        over: dict[str, float] = {
            o.name: sum(
                ring.weight_at(o.position.x, o.position.y)
                for ring in self.campaign.rings
                if ring.site.name != o.name
            )
            for o in objectives
        }
        for coverer in objectives:
            if coverer.name not in rings:
                continue
            credits: list[tuple[float, Objective]] = []
            for o in objectives:
                if o.name == coverer.name or own[o.name] <= 0:
                    continue
                weight = sum(
                    ring.weight_at(o.position.x, o.position.y)
                    for ring in rings[coverer.name]
                )
                if weight <= 0:
                    continue
                credits.append(
                    (
                        COVER_SHARE
                        * own[o.name]
                        * weight
                        / max(over[o.name], FULL_COVER),
                        o,
                    )
                )
            if credits:
                credits.sort(key=lambda pair: -pair[0])
                yield coverer.name, Reason(
                    "cover",
                    sum(credit for credit, _ in credits),
                    _cover_line(coverer, credits),
                )

    def _jamming(
        self, objectives: Sequence[Objective], own: dict[str, float]
    ) -> Iterable[tuple[str, Reason]]:
        from game.gpsjamming import gps_jamming_enabled, jamming_reach_for

        if not gps_jamming_enabled(self.game):
            return
        jammers: list[tuple[Objective, float]] = []
        for o in objectives:
            tgo = o.targets[0]
            if (
                isinstance(tgo, IadsGroundObject)
                and tgo.air_defence_kind is AirDefenceKind.JAMMER
                and (bubble := jamming_reach_for(self.game, tgo)) is not None
            ):
                jammers.append((o, bubble.meters))
        jammed: Counter[str] = Counter()
        for jammer, reach in jammers:
            for o in objectives:
                if o.position.distance_to_point(jammer.position) <= reach:
                    jammed[o.name] += 1
        for jammer, reach in jammers:
            covered = [
                o
                for o in objectives
                if o.name != jammer.name
                and o.position.distance_to_point(jammer.position) <= reach
            ]
            worth = sum(JAMMING_SHARE * own[o.name] / jammed[o.name] for o in covered)
            if worth <= 0:
                continue
            bases = self.campaign.enemy_bases_within(jammer.position, reach)
            if bases:
                line = (
                    f"Jams GPS within {meters(reach).nautical_miles:.0f} nm of "
                    f"{bases[0].name}: our GPS weapons miss there."
                )
            else:
                names = [o.name for o in sorted(covered, key=lambda o: -own[o.name])]
                line = f"Jams GPS over {listed(names)}: our GPS weapons miss there."
            yield jammer.name, Reason("jamming", worth, line)

    def _network(
        self, objectives: Sequence[Objective], whole: dict[str, float]
    ) -> Iterable[tuple[str, Reason]]:
        campaign = self.campaign
        if not campaign.skynet:
            return
        network = campaign.network
        now = network.state_map
        by_name = {o.name: o for o in objectives}
        enemy_sites = [
            (tgo, status)
            for tgo, status in now
            if tgo.control_point.captured == campaign.enemy
        ]
        # Every ground object the network knows, as a site or as what one hangs on.
        in_network = {node.group.ground_object for node in network.nodes} | {
            group.ground_object
            for node in network.nodes
            for group in node.connections.values()
        }
        for o in objectives:
            tgos = [t for t in ground_objects(o) if t in in_network]
            if not tgos:
                continue
            what_if = IadsStateMap(network, destroyed=tgos)
            dark: dict[str, float] = {}
            loose: dict[str, float] = {}
            for tgo, before in enemy_sites:
                site = by_name.get(tgo.name)
                after = what_if.status_for(tgo)
                if site is None or site is o or after is None:
                    continue
                if after.state is IadsState.DARK and before.state not in (
                    IadsState.DARK,
                    IadsState.DESTROYED,
                ):
                    dark[site.name] = whole[site.name]
                elif (
                    after.state is IadsState.AUTONOMOUS
                    and before.state is IadsState.NETWORKED
                ):
                    loose[site.name] = whole[site.name]
            for name in dark:
                loose.pop(name, None)
            worth = DARK_SHARE * sum(dark.values()) + AUTONOMOUS_SHARE * sum(
                loose.values()
            )
            if worth > 0:
                yield o.name, Reason("network", worth, _network_line(o, dark, loose))


# ------------------------------------------------------------------- helpers


def rebuild_worth(tgos: Iterable[TheaterGroundObject]) -> float:
    """What rebuilding what stands there costs; warships, which cannot be rebuilt, by
    class."""
    tgos = list(tgos)
    worth = 0.0
    for unit in alive(tgos):
        if unit.is_ship:
            kind = unit_class(unit)
            worth += (
                WARSHIP_WORTH.get(kind, OTHER_SHIP_WORTH)
                if kind is not None
                else OTHER_SHIP_WORTH
            )
        elif unit.unit_type is not None:
            worth += unit.unit_type.price
    for tgo in tgos:
        if isinstance(tgo, BuildingGroundObject):
            worth += tgo.repair_cost() * sum(1 for s in tgo.statics if s.alive)
    return worth


def _turns_of(income: float) -> str:
    return f"lost income, {INCOME_TURNS} turns of {money(income)}"


def _buildings(tgos: Sequence[TheaterGroundObject]) -> str:
    """What rebuilding means here: so many buildings at so much each, when they all
    cost the same."""
    buildings = [t for t in tgos if isinstance(t, BuildingGroundObject)]
    costs = {t.repair_cost() for t in buildings}
    standing = sum(1 for t in buildings for s in t.statics if s.alive)
    if len(buildings) != len(tgos) or len(costs) != 1 or not standing:
        return "what stands there"
    return f"{counted(standing, 'building')} at {money(costs.pop())}"


def _kept(found: Iterable[Optional[Reason]]) -> tuple[Reason, ...]:
    return by_worth(r for r in found if r is not None and r.worth > 0)


def _most_common(units: Sequence[TheaterUnit]) -> str:
    return Counter(short(unit_label(unit)) for unit in units).most_common(1)[0][0]


def _anti_air_name(unit: TheaterUnit) -> str:
    system = unit_system(unit)
    return "AA guns" if system == "guns" else system


def _launcher_reach(tgos: Sequence[TheaterGroundObject]) -> float:
    """How far the launchers of a coastal battery or a missile site reach, which is
    not what they reach against aircraft."""
    return max(
        (
            float(getattr(unit.type, "threat_range", 0) or 0)
            for unit in alive(tgos)
            if unit_class(unit) in LAUNCHER_CLASSES
        ),
        default=0.0,
    )


def _ours(base: ControlPoint) -> str:
    return f"the {base.name}" if base.is_fleet else f"our base at {base.name}"


def _cover_line(coverer: Objective, credits: Sequence[tuple[float, Objective]]) -> str:
    top = credits[0][0]
    named = [o for credit, o in credits if credit >= NAMED_SHARE * top]
    names = [o.name for o in named]
    tgos = ground_objects(coverer)
    if not tgos:
        return f"Covers {listed(names)}."
    if isinstance(tgos[0], NavalGroundObject):
        ships = counted(sum(1 for u in alive(tgos) if u.is_ship), "warship")
        for o in named[:NAMES_SHOWN]:
            carrier = o.targets[0]
            if isinstance(carrier, GenericCarrierGroundObject):
                return f"{ships} screening the {carrier.control_point.name}."
        return f"{ships} covering {listed(names)}."
    return f"Its {system_name(tgos[0])} covers {listed(names)}."


def ground_objects(objective: Objective) -> list[TheaterGroundObject]:
    """The objective's ground objects; none for a base."""
    return [t for t in objective.targets if isinstance(t, TheaterGroundObject)]


def _network_line(
    objective: Objective, dark: dict[str, float], loose: dict[str, float]
) -> str:
    def ranked(found: dict[str, float]) -> list[str]:
        return sorted(found, key=lambda name: (-found[name], name))

    if dark:
        held = sites(ranked(dark), "go dark", "goes dark")
    else:
        held = sites(ranked(loose), "fight alone", "fights alone")
    tgo = objective.targets[0]
    category = getattr(tgo, "category", "")
    if category == "power":
        return f"Powers {held}."
    if category == "comms":
        return f"Connects {held}."
    if category == "commandcenter":
        return f"Directs {held}."
    return f"Early warning for {held}."
