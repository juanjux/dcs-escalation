"""Read DTOs for the OPFOR-AI feature.

Pure functions over a ``Game`` (no ``GameContext``, no Qt) so they are unit-testable
and importable without PySide6. ``service.py`` wires these to the live game.

Token economy: these payloads go to the LLM **every turn**, so they are frugal —
numbers are rounded,
coordinates are bare ``[lat, lng]`` pairs, TOT is ``HH:MM``, and "boring" fields
(zero counts, empty strings) are left ``None`` so the transport drops them with
``exclude_none``. Convention, stated once in ``/howtoplay``: an absent numeric field
means 0. The one-time docs (start/howtoplay) are exempt — only per-turn data is.
"""

from __future__ import annotations

import math
from typing import Any, TYPE_CHECKING

from dcs.mapping import Point as DcsPoint
from dcs.weather import Weather as PydcsWeather, Wind
from pydantic import BaseModel, Field

from game.income import Income
from game.theater.iadsnetwork.iadsstate import IadsStatus
from game.theater.player import Player
from game.utils import meters, mps

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.squadrons.squadron import Squadron
    from game.theater import ControlPoint
    from game.weather.clouds import Clouds


_SIDE_TO_PLAYER = {"red": Player.RED, "blue": Player.BLUE}

# game.check_win_loss() is blue-centric (WIN == the human/blue won). Re-express it
# from RED's point of view, which is who the OPFOR planner is.
_CAMPAIGN_STATE_FROM_RED = {
    "CONTINUE": "ongoing",
    "WIN": "red_losing",  # blue reached a winning condition
    "LOSS": "red_winning",  # blue lost all its points
}


def player_for_side(side: str) -> Player:
    try:
        return _SIDE_TO_PLAYER[side.lower()]
    except KeyError:
        raise ValueError(f"side must be 'red' or 'blue', got {side!r}")


def coalition_for_side(game: Game, side: str) -> Coalition:
    return game.coalition_for(player_for_side(side))


def _r(value: float, ndigits: int = 5) -> float:
    return round(float(value), ndigits)


def _enum_str(value: object) -> str | None:
    if value is None:
        return None
    member_value = getattr(value, "value", None)
    if member_value is not None:
        return str(member_value)
    return getattr(value, "name", None) or str(value)


# --- DTOs (omitted-when-None fields carry their "boring" default implicitly) ---


class WeatherView(BaseModel):
    """The turn's weather, in the terms it changes decisions.

    Kept to what alters a plan: a ceiling rules out laser guidance from altitude,
    precipitation and low visibility blunt sensors, and wind sets the carrier's course.
    QNH is deliberately absent -- it is a cockpit number, not a planning one.
    """

    # "clear", a coverage code ("SCT", "OVC"), or a preset's name when the campaign
    # uses one ("Three Layer Overcast").
    clouds: str
    base_ft: int | None = None  # cloud base, omitted when clear
    precip: str | None = None  # "rain" / "thunderstorm", omitted when none
    vis_nm: int | None = None  # omitted unless something actually limits visibility
    wind_gl: str  # "dir/kts" at ground level
    wind_fl26: str | None = None  # omitted when it matches the surface wind
    temp_c: int


class SituationView(BaseModel):
    turn: int
    date: str
    time_of_day: str
    weather: WeatherView
    campaign_state: str | None = None  # set only when not "ongoing"


class EconomyView(BaseModel):
    budget: int
    income_next_turn: int


class ControlPointView(BaseModel):
    id: str
    name: str
    type: str
    owner: str  # red / blue / neutral
    pos: list[float]  # [lat, lng]
    sqns: int | None = None  # based-squadron count (omitted when 0)
    parking_free: int | None = None  # free aircraft slots (room to buy/station here)
    parking_total: int | None = None  # total aircraft slots
    can_recruit_ground: bool | None = None  # has a factory/front — buy ground here
    factories: dict[str, str] | None = (
        None  # the factories standing at this base, by name -> "alive" / "repairing" /
        # "destroyed". Only bases that have one carry this. A base recruits ground units
        # only while one of its factories is alive, so this is the *why* behind
        # can_recruit_ground: a dead factory is a repair worth paying for, and on the
        # enemy's side it is the strike that stops their army being replaced.
    )
    links: list[str] | None = None  # adjacent control-point ids (land moves / fronts)
    ground: dict[str, int] | None = None  # armor on hand here (unit name -> count)
    ground_pending_transfer: int | None = (
        None  # vehicles ordered away from here that have found no transport yet.
        # They are INCLUDED in ground above: still parked here, still deployable to
        # the front, still counted in the ground war. They leave only when a lift
        # turns up, so a big number here is an army you have decided to move and
        # cannot
    )
    ground_transferring_out: int | None = (
        None  # vehicles that left here under a transport this turn. NOT included
        # in ground above -- they are on the road or in the air and will not defend
        # this base or its front
    )
    pending_ground: dict[str, int] | None = (
        None  # armor ORDERED here, arriving next turn (unit name -> count). Aircraft
        # have `pending` on the squadron; ground had nothing, so a planner that bought
        # armor saw no change anywhere and bought it again. YOUR bases only -- what the
        # enemy ordered is not visible to the human either.
    )
    air: dict[str, dict[str, int]] | None = (
        None  # aircraft based here, grouped by role: {"CAP": {"F-16CM …": 7}, …}. The
        # same breakdown the human reads on a base's Intel tab, for both sides — on an
        # enemy field it is what tells an OCA/Aircraft strike apart from a waste of a
        # package: seven fighters is worth hitting, two transports is not. Counts are
        # aircraft PRESENT (not ordered or in transit). Omitted when the base is empty.
    )
    motorpool: int | None = (
        None  # vehicles of this base's UNDEPLOYED reserve that spawn in a strikeable
        # motorpool depot — what an enemy BAI strike here can destroy (and what you
        # lose the purchase price of). Omitted when the base has no motorpool or
        # nothing in reserve. Yours: deploy it or defend it. Enemy: a fat number is a
        # cheap attrition target (see also targets[] kind:motorpool)
    )
    can_launch: bool | None = (
        None  # False = this base CANNOT launch aircraft this turn; omitted when it can.
        # Do NOT plan flights from a base with can_launch:false. WHY it cannot is in
        # no_launch_reason, and the three reasons call for three different responses.
    )
    no_launch_reason: str | None = (
        None  # why can_launch is false, omitted when it can launch:
        # "runway_damaged" — cratered or under repair. Repairable, and worth CRATERING
        #   on an enemy field: see runway_repair_turns_remaining. A base being repaired
        #   does NOT appear in turn_context.repairs (already paid for) yet still cannot
        #   sortie until that counter hits 0.
        # "hull_sunk" — a carrier/LHA whose hull is dead. Nothing to repair.
        # "no_launch_facilities" — a FOB with no helipads or ground spawns. It has no
        #   runway at all: there is NOTHING to crater here, an OCA/Runway package
        #   against it is wasted, and no repair will ever change it.
    )
    runway_repair_turns_remaining: int | None = (
        None  # turns until a repairing runway is operational again (omitted when the base
        # can launch, or when the runway is damaged-but-unpaid — that shows in repairs)
    )


class SquadronView(BaseModel):
    id: str
    name: str
    aircraft: str
    base: str
    owned: int | None = None  # aircraft on hand (omitted when 0)
    untasked: int | None = (
        None  # available to task; a literal 0 whenever the squadron owns aircraft,
        # omitted only when it owns none (see `unflyable`)
    )
    flyable: int | None = (
        None  # aircraft you can actually LAUNCH now = min(untasked, pilots), 0 if grounded —
        # the real number to plan with (untasked can exceed available pilots); a literal 0
        # whenever the squadron owns aircraft, omitted only when it owns none
    )
    pending: int | None = None  # arriving next turn (omitted when 0)
    pilots: int
    price: int  # cost of ONE aircraft, so budget / price = how many you can afford
    max_ac: int | None = (
        None  # squadron airframe cap: buy/aircraft refuses once owned+pending reaches
        # it (a cap of 1 marks an irreplaceable airframe, e.g. a lone AWACS); omitted
        # when the campaign disables per-squadron aircraft limits
    )
    grounded: bool | None = (
        None  # can't sortie this turn: base enemy-held OR runway cratered / hull sunk
        # (else omitted). flyable is 0 while grounded.
    )
    unflyable: str | None = (
        None  # why a squadron that HAS aircraft can launch none of them right now
        # ("all 2 already tasked" / "no available pilots" / "grounded"); omitted whenever
        # flyable > 0, so its presence alone means "do not plan with this squadron"
    )


class FlightView(BaseModel):
    id: str
    task: str | None
    aircraft: str
    count: int
    squadron: str
    start: str | None = None
    dep: str | None = None
    clients: int | None = None  # player-controlled seats (omitted when 0)
    uncrewed: int | None = None  # missing pilots — present only when >0 (an alert)
    loadout: str | None = None  # payload name ("Retribution Anti-ship" / "Custom (AI)")
    weapons: dict[int, str] | None = (
        None  # pylon number -> weapon clsid — what this flight actually carries
    )
    startup_min: int | None = (
        None  # minutes from MISSION START to this flight's engine start -- the "Departing
        # At" the player reads in Edit Flight, in the same unit the planner sets TOTs in.
        # It is derived: TOT, minus the flight's own offset, minus the time to fly the
        # route, minus startup and taxi. A NEGATIVE value means the flight would have had
        # to start before the mission does, so it CANNOT make its TOT -- push the TOT
        # later or fly it from a closer base.
    )
    tot_offset_min: float | None = (
        None  # this flight's time over target relative to the PACKAGE's, in minutes.
        # NEGATIVE = ahead of the package (what escorts and SEAD want: be there before
        # the strikers arrive), positive = behind it. Omitted when the flight arrives
        # with the package. Some tasks default to a non-zero offset -- SEAD leads,
        # sweeps lead further -- so an absent value is a deliberate "on time", not
        # "unset". Set it with POST /flights/tot_offset, or up front in a FlightSpec.
    )


class PackageView(BaseModel):
    index: int  # position in the ATO (stable within a turn snapshot)
    target: str
    task: str | None
    tot: str | None  # time over target, HH:MM
    desc: str | None = None
    flights: list[FlightView]


class RebuildView(BaseModel):
    """Work in progress on a site: what is coming back, and when."""

    force_group: str  # what it is being rebuilt into
    turns_remaining: int  # turns until the last of it comes alive
    units_repairing: int = 0  # dead units with a countdown on them
    units_alive: int = 0  # units already standing. 0 = the whole site is down and is
    # being rebuilt; anything else = it is fighting now and getting stronger, which is
    # a different thing to plan against


class TargetView(BaseModel):
    id: str
    name: str
    kind: str  # sam / ship / building / motorpool / front / convoy / cargo_ship
    suggested_task: str  # DEAD / ANTISHIP / STRIKE / BAI / CAS
    pos: list[float]  # [lat, lng]
    category: str | None = (
        None  # buildings only: which kind of building, since "building" covers every
        # fixed target that is not a SAM. factory / ware / fuel / oil / derrick / ammo /
        # power / comms / commandcenter / village / farp / fob / allycamp / ww2bunker.
        # Worth reading: a factory is what lets its base recruit ground units, oil and
        # derricks are income, ammo and fuel are what the garrison fights on.
    )
    base: str | None = (
        None  # the control point this sits at. Which base loses the factory, or which
        # airfield the SAM is defending, without matching coordinates by hand.
    )
    threat_nm: int | None = (
        None  # air-defense umbrella radius (nm) — danger to ANY flight transiting it,
        # not only the attacker; ships carry it too (naval SAMs like SM-6 reach far)
    )
    detection_nm: int | None = (
        None  # how far the site SEES (nm). A radar site -- an EWR, or a GPS jamming
        # site -- has this and no threat_nm: it cannot shoot you, it tells the SAMs
        # where you are. Killing one blinds the network over that radius.
    )
    friendly_cp_id: str | None = None  # fronts only: your control point (for stances)
    enemy_cp_id: str | None = None  # fronts only: the enemy control point
    group_id: str | None = (
        None  # ships: their naval-group control-point id (concentrate)
    )
    #: Set only while the site is being rebuilt: what it will become and how many
    #: turns until its units come alive. Without it a site under construction is
    #: indistinguishable from a destroyed one -- the player sees the works on the map.
    rebuild: RebuildView | None = None
    iads_role: str | None = (
        None  # what this site is to the enemy IADS, when it is part of one: PowerSource /
        # ConnectionNode / CommandCenter / Ewr / Sam / SamAsEwr. Tells a code-named
        # building apart from a generic one — a "PowerSource" is a radar's mains supply,
        # not a warehouse. Omitted for anything outside the IADS. See GET /iads for the
        # links (which node each one feeds).
    )
    composition: dict[str, int] | None = (
        None  # ships: alive-hull count per class, e.g. {"Constellation": 2} — so you can
        # spot Aegis escorts (Constellation/Ticonderoga) and count hulls before an ANTISHIP
        # strike, instead of seeing only the group's aggregate threat
    )
    origin: str | None = (
        None  # convoys/cargo ships: the base it left. Killing one denies the
        # DESTINATION its reinforcements, so a convoy is worth more the closer the
        # front it feeds is to falling.
    )
    destination: str | None = None  # convoys/cargo ships: the base it is reinforcing
    route: list[list[float]] | None = (
        None  # convoys/cargo ships: [[lat,lng] start, [lat,lng] end] of the leg it is
        # driving/sailing. It is MOVING: plan the intercept along this line, not at pos.
    )
    damage: str | None = None  # 'lightly/heavily damaged' (omitted at full strength)
    iads_state: str | None = (
        None  # "autonomous" (cut off from its network: it engages only what its own
        # radar finds) or "dark" (no power: the radar never comes up, so it will not
        # shoot at all this mission). OMITTED when the site is working normally, which
        # is the usual case. iads_reason says why.
    )
    iads_reason: str | None = None  # one line: why it is autonomous or dark
    iads_blind: bool | None = (
        None  # true when nothing it has left can find a target for itself -- its search
        # radar is gone. A networked site can still be handed targets; an autonomous
        # blind one is harmless until repaired. Omitted when false.
    )


class ThreatView(BaseModel):
    """An enemy air-defense umbrella ranked by reach — the route-shaping threats to
    avoid or suppress. The list is COMPLETE, not a top-N sample. Same ``id`` as the
    matching target, so you can DEAD/ANTISHIP it directly."""

    id: str  # same id as the target in targets[] — task DEAD (sam) / ANTISHIP (ship) on it
    name: str
    kind: str  # sam / ship (ships project naval-SAM umbrellas — SM-6 etc.)
    threat_nm: int  # umbrella radius (nm): your flights are engaged within it
    pos: list[float]  # [lat, lng]
    iads_state: str | None = (
        None  # "autonomous" or "dark" -- this umbrella is not what its radius says. A
        # dark site does not shoot this mission at all; an autonomous one engages only
        # what its own radar finds. Omitted when the site is working normally.
    )
    iads_reason: str | None = None  # one line: why
    iads_blind: bool | None = None  # nothing left that can find a target for itself


class IadsNodeView(BaseModel):
    """One site in an IADS, with what it depends on."""

    id: str  # same id as in targets[] — plan DEAD or STRIKE against it directly
    name: str
    role: str  # Sam / SamAsEwr / Ewr / CommandCenter / PowerSource / ConnectionNode
    alive: bool  # false = already destroyed; its dependants are already degraded
    depends_on: list[str] | None = (
        None  # ids of the sites feeding this one (power, comms, command). Kill one of
        # these and this node goes down without touching the node itself — that is the
        # whole point of striking the network instead of the launchers.
    )
    state: str | None = (
        None  # what this site will actually do next mission: "autonomous" (cut off from
        # the network, engaging only what its own radar finds) or "dark" (no power, so
        # the radar never comes up and it does not shoot at all). OMITTED when the site
        # is networked and working, which is the usual case -- so a node WITH a state is
        # a node whose dependencies you have already broken.
    )
    state_reason: str | None = None  # one line: which dependency did it
    blind: bool | None = (
        None  # nothing left that can find a target for itself. Omitted when false.
    )
    repair_turns: int | None = (
        None  # turns until the work on this site finishes. Present whenever ANYTHING
        # on it is being repaired, whether it is a wreck being rebuilt or a live site
        # getting a launcher back -- so a node you flattened last turn is not a free
        # corridor. Omitted when nothing is under repair. `alive` says which of the two
        # it is; targets[] carries the same countdown with the unit counts.
    )


class IadsView(BaseModel):
    """The enemy IADS as a graph. Empty when the campaign runs no advanced IADS."""

    advanced: bool  # false = Skynet is not wiring power/comms, so only the sites matter
    nodes: list[IadsNodeView]


class NavalView(BaseModel):
    """One of YOUR movable naval groups — reposition it with move_ship."""

    id: str  # group id — pass to move_ship (ships: a tgo id; carriers: a control-point id)
    name: str
    kind: str  # ship (combatant group) / carrier (CV/LHA control point)
    pos: list[float]  # [lat, lng]
    move_range_nm: int  # max reposition per turn (great-circle, over water)
    destination: list[float] | None = (
        None  # pending move target [lat, lng] (omitted when holding)
    )
    threat_nm: int | None = (
        None  # its own air-defense umbrella reach — position it to cover what matters
    )
    damage: str | None = None  # 'lightly/heavily damaged' (omitted at full strength)
    composition: dict[str, int] | None = (
        None  # alive hull count per class, e.g. {"Type 052C": 1, "Type 054A": 2}; lets
        # you see which hulls are still up (not just the aggregate damage %)
    )
    cruise_missiles_remaining: int | None = (
        None  # land-attack cruise missiles this group has left FOR THE WHOLE CAMPAIGN.
        # Never regenerates, cannot be bought or resupplied, and sinks with the hull —
        # spend it on targets aircraft would pay dearly to reach. Omitted when the group
        # carries none or the campaign has cruise missile strikes switched off.
    )


class RepairView(BaseModel):
    """One of YOUR damaged assets you can pay to repair — dead SAM/EWR units, a building,
    or a cratered runway. The fix is instant or takes a few turns, per campaign settings.
    """

    id: str  # repair target id: a ground-object/building tgo id, or a control-point id (runway)
    name: str
    kind: str  # aa / ewr / oil / factory / ammo / runway / ... (what's damaged; economy
    # buildings use their category, so 'oil'/'factory' flag an income asset worth restoring)
    cost: int  # budget to repair it (sum of its dead units, or the flat runway/building cost)
    dead_units: int | None = (
        None  # dead units it would bring back (omitted for a runway)
    )
    income_per_turn: int | None = (
        None  # economy buildings only: the income this asset restores each turn once
        # repaired — prioritise a dead oil/factory over cosmetic damage (a strangled
        # budget is usually a dead income building you can rebuild here)
    )


class GroundUnitView(BaseModel):
    name: str
    price: int
    kind: str  # front (tanks/IFVs) / artillery


class TurnForcesView(BaseModel):
    """Force totals at a past turn — the attrition trend the planner reacts to.

    Loss fields are present only for turns whose mission was flown + debriefed.
    """

    turn: int
    blue_aircraft: int
    blue_vehicles: int
    red_aircraft: int
    red_vehicles: int
    blue_air_lost: int | None = None
    red_air_lost: int | None = None
    blue_air_crashed: int | None = (
        None  # of blue_air_lost, how many were non-combat (crash/collision, no shooter)
    )
    red_air_crashed: int | None = (
        None  # of red_air_lost, how many were non-combat (crash/collision, no shooter)
    )
    blue_ground_lost: int | None = None
    red_ground_lost: int | None = None
    #: What died, by airframe: {"Mi-24P": 8, "Su-25": 6}. A headline count does not
    #: say whether a side lost its Hinds or its Frogfoots, and the two mean different
    #: things for the next turn.
    red_air_lost_by_type: dict[str, int] | None = None
    blue_air_lost_by_type: dict[str, int] | None = None
    #: What did the killing, by WEAPON alone: {"R-37M": 20}. Judge a loadout from this
    #: rather than from *_air_killers below, which falls back from the shooter to the
    #: weapon and so mixes airframes and missiles in one dict.
    red_air_kills_by_weapon: dict[str, int] | None = None
    blue_air_kills_by_weapon: dict[str, int] | None = None
    #: Which airframe killed which: {"Su-57": {"F-16C_50": 9, "F15EX": 4}} reads "red's
    #: Su-57s were shot down 9 times by F-16Cs and 4 by F-15EXs". One nesting deep, and
    #: aggregated, so it grows with the number of TYPES in the fight, not with kills.
    red_air_kills_by_victim: dict[str, dict[str, int]] | None = None
    blue_air_kills_by_victim: dict[str, dict[str, int]] | None = None
    red_air_killers: dict[str, int] | None = None  # what killed red's aircraft
    blue_air_killers: dict[str, int] | None = None  # what killed blue's aircraft
    blue_air_combat: int | None = (
        None  # of blue_air_lost, how many were SHOT DOWN (= lost - crashed); the
    )
    # weapon breakdown is blue_air_killers, the remainder are non-combat blue_air_crashed
    red_air_combat: int | None = None  # of red_air_lost, how many were shot down
    blue_sites_lost: dict[str, int] | None = (
        None  # blue site/naval UNITS destroyed this turn, per unit-type id — ships by
    )
    # class ({"Type_052C": 1}) + SAM launchers/radars: the concrete result of RED's strikes
    red_sites_lost: dict[str, int] | None = (
        None  # red site/naval units destroyed this turn — the result of BLUE's strikes
    )


class LeaveRequestView(BaseModel):
    """A pilot asking for a rest, and what saying yes would cost you.

    Answer with ``answer_leave_request``. Saying nothing is saying no, and a refusal
    costs him morale -- so is worth doing on purpose rather than by omission.
    """

    squadron_id: str  # pass this back to answer_leave_request
    squadron: str
    pilot_name: str  # and this
    rank: str
    morale: int  # -30 to 100; below zero is Broken and takes turns to climb out of
    state: str  # the word for it: Shaken, Shattered, Broken...
    asked_turns: int  # what HE asked for; you may grant fewer
    spare_pilots: int  # pilots still available in his squadron if you say yes
    aircraft: int  # airframes it owns -- fewer spare pilots than these means idle jets


class TurnContextView(BaseModel):
    side: str
    situation: SituationView
    economy: EconomyView
    control_points: list[ControlPointView]
    air_wing: list[SquadronView]
    idle_flyable: (
        int  # total aircraft you can LAUNCH right now that are still untasked (sum of
    )
    # each squadron's `flyable`). Standing reminder — if this is >0 when you finish the turn you
    # left force on the ramp: task it (more/bigger/staggered BARCAPs, a probe, extra saturation)
    # or hold it on purpose. DRIVE IT TOWARD 0. (0 shown as confirmation.)
    targets: list[TargetView]  # enemy objects this side can strike (aim by id)
    threats: list[ThreatView]  # blue's strongest air-defense umbrellas, ranked by reach
    naval: list[NavalView]  # YOUR movable ship groups (reposition with move_ship)
    repairs: list[
        RepairView
    ]  # YOUR damaged assets you can pay to repair (with `repair`)
    buyable_ground: list[GroundUnitView]  # ground units this faction can buy
    leave_requests: list[LeaveRequestView] = (
        []
    )  # pilots asking for leave this turn; empty most turns. Answer them with
    # answer_leave_request -- ignoring one refuses it, and a refusal costs him morale.


class SettingsView(BaseModel):
    """The campaign settings the OPFOR planner reads (and never changes)."""

    opfor_aggressiveness_pct: int  # risk-tolerance hint the player set for red
    map_coalition_visibility: str  # fog-of-war level (drives the intel filter)
    desired_player_mission_duration_min: int  # TOT window the player flies within
    player_income_multiplier: float
    enemy_income_multiplier: float
    crashes_dont_count: (
        bool  # if True, a non-combat air loss (crash/collision, no credited
    )
    # shooter) does NOT deplete the squadron or kill the pilot — see *_air_crashed in prev_turns
    pilot_replenishment_per_squadron: int | None = (
        None  # new pilots each squadron regains per turn (up to the limit); omitted = no pilot limits (unlimited)
    )
    squadron_pilot_limit: int | None = (
        None  # max active pilots per squadron (omitted = no limit)
    )
    runway_repair_turns: int = (
        4  # turns a cratered runway takes to repair; a base's
        # runway_repair_turns_remaining (in control_points) counts down from this
    )
    cruise_missile_strikes: bool = (
        False  # ships with land-attack cruise missiles can hit shore targets. When
        # False, `cruise_missiles_remaining` never appears in naval[] and no raid flies
    )
    cruise_missile_auto_raids: bool = (
        False  # each turn, both sides automatically commit one cruise missile raid at
        # their best reachable enemy ground object. Spends YOUR magazine without asking
    )
    all_settings: list[SettingView] = Field(default_factory=list)
    # Every setting on the campaign's settings pages, in the order they appear there,
    # with the label and explanation the player reads. The named fields above are the
    # ones worth planning around and are repeated here; everything else -- mission
    # durations, doctrine distances, difficulty, the lot -- is only here. Read it once
    # at the start of a campaign rather than every turn: it is long.


class SettingView(BaseModel):
    """One setting exactly as the player sees it on the settings page."""

    key: str  # what it is called in the code, e.g. desired_tarcap_mission_duration
    page: str
    section: str
    label: str  # the text beside the box
    value: Any  # its current value, as a number, a bool or a string
    detail: str | None = None  # the explanation under the box, when it has one


class UnitTypeOption(BaseModel):
    name: str
    price: int


class GroupSlotView(BaseModel):
    group_name: str
    optional: bool
    default_count: int
    max_count: int
    unit_types: list[UnitTypeOption]


class LayoutOption(BaseModel):
    force_group: str
    layout: str
    price: int  # INDICATIVE: every group at its first unit type and its default count.
    # A layout whose groups declare a unit-count RANGE rolls a size each time it is
    # asked, so what ground/rebuild charges can differ from this quote. Pin
    # `groups[].count` on the rebuild to pay exactly what you planned for.
    groups: list[GroupSlotView]


class GroundObjectOptionsView(BaseModel):
    tgo_id: str
    name: str
    role: str  # "air_defense" | "ground_force" | "naval" | "defenses"
    refund: int  # tgo.value, refunded when rebuilding
    budget: int
    options: list[LayoutOption]


# --- builders ---


_CLOUD_COVERAGE = ((1, "FEW"), (4, "SCT"), (7, "BKN"), (11, "OVC"))


def _cloud_summary(clouds: Clouds) -> str:
    """What the sky looks like, in a couple of words."""
    if clouds.preset is not None:
        # A preset's description is two lines: a name after "##", then a METAR-style
        # layer breakdown. The name alone is what a planner needs.
        return clouds.preset.description.splitlines()[0].split("##")[-1].strip()
    for limit, name in _CLOUD_COVERAGE:
        if clouds.density < limit:
            return name
    return "OVC"


def _wind(wind: Wind) -> str:
    return (
        f"{str(wind.direction or 0).rjust(3, '0')}/{round(mps(wind.speed or 0).knots)}"
    )


def build_weather(game: Game) -> WeatherView:
    weather = game.conditions.weather
    clouds = weather.clouds

    precip = None
    if (
        clouds is not None
        and clouds.precipitation is not PydcsWeather.Preceptions.None_
    ):
        precip = clouds.precipitation.name.lower()

    vis_nm = None
    if weather.fog is not None:
        vis_nm = round(weather.fog.visibility.nautical_miles)

    surface = _wind(weather.wind.at_0m)
    high = _wind(weather.wind.at_8000m)
    return WeatherView(
        clouds="clear" if clouds is None else _cloud_summary(clouds),
        base_ft=None if clouds is None else round(meters(clouds.base).feet),
        precip=precip,
        vis_nm=vis_nm,
        wind_gl=surface,
        wind_fl26=None if high == surface else high,
        temp_c=round(weather.atmospheric.temperature_celsius),
    )


def build_situation(game: Game) -> SituationView:
    state = _CAMPAIGN_STATE_FROM_RED.get(game.check_win_loss().name, "ongoing")
    return SituationView(
        turn=game.turn,
        date=game.current_day.isoformat(),
        time_of_day=game.current_turn_time_of_day.name,
        weather=build_weather(game),
        campaign_state=None if state == "ongoing" else state,
    )


def build_economy(game: Game, side: str) -> EconomyView:
    player = player_for_side(side)
    return EconomyView(
        budget=round(game.coalition_for(player).budget),
        income_next_turn=round(Income(game, player).total),
    )


def _parking(cp) -> tuple[int, int] | None:
    """(used, total) aircraft-parking slots at a base, or None if it has none."""
    from game.theater import ParkingType

    try:
        pt = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
        total = cp.total_aircraft_parking(pt)
        if total <= 0:
            return None
        return total - cp.unclaimed_parking(pt), total
    except Exception:
        return None


def _motorpool_exposed(game: Game, cp: ControlPoint) -> int | None:
    """Vehicles of this base's undeployed reserve that render in a strikeable
    motorpool, i.e. what an enemy BAI strike here could actually destroy.

    None (omitted) unless the base has an authored motorpool and something in
    reserve. The spawn cap is per control point — its motorpools share one reserve
    pool (MotorpoolPopulator._populate_cp) — so the exposure is capped once here.
    """
    try:
        from game.ground_forces.ai_ground_planner import reserve_armor_for
        from game.theater.theatergroundobject import MotorpoolGroundObject

        cap = game.settings.motorpool_spawn_cap
        if not game.settings.motorpool_enabled or cap <= 0:
            return None
        if not any(isinstance(tgo, MotorpoolGroundObject) for tgo in cp.ground_objects):
            return None
        return min(sum(reserve_armor_for(cp).values()), cap) or None
    except Exception:
        return None


def _pending_ground(cp: ControlPoint) -> dict[str, int]:
    """Ground units ordered at this base and arriving next turn."""
    try:
        orders = cp.ground_unit_orders.units
    except AttributeError:  # pragma: no cover - carriers and off-map points
        return {}
    return {ut.display_name: n for ut, n in orders.items() if n}


def build_control_point(
    game: Game, cp: ControlPoint, viewer: Player | None = None
) -> ControlPointView:
    # Mirror game/server/leaflet.py: build a terrain-aware Point before converting.
    ll = DcsPoint(cp.position.x, cp.position.y, game.theater.terrain).latlng()
    sqns = sum(1 for _ in cp.squadrons)
    park = _parking(cp)
    armor = getattr(getattr(cp, "base", None), "armor", None)
    ground = {ut.display_name: n for ut, n in armor.items() if n} if armor else None
    # Only for your OWN bases: what the enemy has ORDERED is not something the
    # human can see either, and §6 is fair play.
    pending_ground = _pending_ground(cp) if cp.captured == viewer else {}
    links = [str(n.id) for n in getattr(cp, "connected_points", [])] or None
    try:
        allocations = cp.allocated_ground_units(
            game.coalition_for(cp.captured).transfers
        )
        pending_out = allocations.total_pending_transfer or None
        moving_out = allocations.total_transferring_out or None
    except Exception:
        pending_out = moving_out = None
    try:
        recruit = bool(cp.has_ground_unit_source(game)) or None
    except Exception:
        recruit = None
    operational = cp.runway_is_operational()
    try:
        repair_turns = cp.runway_status.repair_turns_remaining
    except Exception:
        repair_turns = None  # carriers/LHAs/off-map have no repairable runway
    return ControlPointView(
        motorpool=_motorpool_exposed(game, cp),
        id=str(cp.id),
        name=cp.name,
        type=cp.cptype.name,
        owner=cp.captured.value.lower(),
        pos=[_r(ll.lat), _r(ll.lng)],
        sqns=sqns or None,
        parking_free=(park[1] - park[0]) if park else None,
        parking_total=park[1] if park else None,
        can_recruit_ground=recruit,
        factories=_factories(cp),
        links=links,
        ground=ground or None,
        ground_pending_transfer=pending_out,
        ground_transferring_out=moving_out,
        pending_ground=pending_ground or None,
        air=_air_intel(cp),
        can_launch=(False if not operational else None),
        no_launch_reason=(None if operational else _no_launch_reason(cp)),
        runway_repair_turns_remaining=repair_turns,
    )


def _factories(cp: ControlPoint) -> dict[str, str] | None:
    """What each of this base's factories is doing, or nothing if it has none.

    A base recruits ground units only while a factory of its own is alive, and nothing
    else in these views says whether it has one -- a factory reads as "building" in the
    target list and does not appear at all among your own. So the state is named here,
    on both sides: your own to know which repair buys the army back, the enemy's to know
    which strike stops theirs.
    """
    factories = {}
    for tgo in cp.connected_objectives:
        if not getattr(tgo, "is_factory", False):
            continue
        if not tgo.is_dead:
            factories[tgo.name] = "alive"
        elif tgo.has_pending_repairs:
            factories[tgo.name] = "repairing"
        else:
            factories[tgo.name] = "destroyed"
    return factories or None


def _squadron_flyable(sq: Squadron, grounded: bool) -> int:
    """Aircraft this squadron can actually launch this turn: min(untasked, available pilots),
    0 if grounded (enemy-held base or cratered runway / sunk hull) or pilotless. Pilots don't
    cap it when pilot limits are off. This is what the planner can really field — untasked
    alone overstates it."""
    if grounded or sq.untasked_aircraft <= 0:
        return 0
    if not sq.pilot_limits_enabled:
        return sq.untasked_aircraft
    return min(sq.untasked_aircraft, sq.number_of_available_pilots)


def _squadron_grounded(sq: Squadron, player: Player | None) -> bool:
    """The squadron can't launch this turn: its base is enemy-held, or the runway is
    cratered / the carrier hull is sunk. The engine's mission planner excludes it either
    way, so flag it rather than advertise phantom flyable aircraft to the planner."""
    if player is not None and sq.location.captured != player:
        return True
    return not sq.location.runway_is_operational()


def _unflyable_reason(sq: Squadron, grounded: bool) -> str | None:
    """Why a squadron holding aircraft can launch none of them, or None if it can.

    Only ever set when the squadron owns aircraft: `owned: 1` with no other number beside
    it reads as "one jet ready", and the omit-when-zero rule that keeps the payload small
    hides the one field that says otherwise. Naming the reason turns a silence the planner
    fills with its own assumption into a fact it can plan around.
    """
    if not sq.owned_aircraft or _squadron_flyable(sq, grounded):
        return None
    if grounded:
        return "grounded"  # the `grounded` flag carries the detail
    if sq.untasked_aircraft <= 0:
        return f"all {sq.owned_aircraft} already tasked"
    return "no available pilots"


def idle_flyable_total(game: Game, side: str) -> int:
    """Total launchable-now aircraft still untasked across the side's air wing (the headline
    'force left on the ramp' number)."""
    player = player_for_side(side)
    return sum(
        _squadron_flyable(sq, _squadron_grounded(sq, player))
        for sq in coalition_for_side(game, side).air_wing.iter_squadrons()
    )


def build_squadron(sq: Squadron, player: Player | None = None) -> SquadronView:
    # A squadron that can't sortie (enemy-held base, or a cratered runway / sunk
    # hull) is excluded by the engine's mission planner, so flag it instead of
    # advertising phantom flyable aircraft to the planner.
    grounded = _squadron_grounded(sq, player)
    # Zero is only noise for a squadron with nothing on the ramp. Once it owns aircraft,
    # "none of them are free" is the single most decision-changing fact about it, so
    # untasked/flyable are emitted as literal zeros rather than omitted.
    owned = sq.owned_aircraft
    return SquadronView(
        id=str(sq.id),
        name=str(sq),
        aircraft=sq.aircraft.display_name,
        base=sq.location.name,
        owned=owned or None,
        untasked=sq.untasked_aircraft if owned else None,
        flyable=_squadron_flyable(sq, grounded) if owned else None,
        unflyable=_unflyable_reason(sq, grounded),
        pending=sq.pending_deliveries or None,
        pilots=sq.number_of_available_pilots,
        price=math.ceil(sq.aircraft.price),
        max_ac=(sq.max_size if sq.settings.enable_squadron_aircraft_limits else None),
        grounded=grounded or None,
    )


def _damage_word(tgo) -> str | None:
    """Short damage state for a target, or None if at full strength."""
    try:
        units = list(tgo.units)
        if not units:
            return None
        alive = sum(1 for u in units if getattr(u, "alive", True))
        total = len(units)
        if alive >= total:
            return None
        if alive == 0:
            return "destroyed"
        return "lightly damaged" if alive / total > 0.6 else "heavily damaged"
    except Exception:
        return None


def _unit_composition(tgo) -> dict[str, int] | None:
    """Alive-unit count per class for a target group. For ships: hulls per class, so the
    planner can identify Aegis escorts (Constellation/Ticonderoga). For SAM sites: alive
    launchers/radars per type, exposing PARTIAL damage (2 of 4 TELs left), not just
    alive/dead.
    """
    comp: dict[str, int] = {}
    for u in getattr(tgo, "units", []):
        if not getattr(u, "alive", True):
            continue
        name = None
        try:
            ut = u.unit_type
            name = getattr(ut, "display_name", None) if ut else None
        except Exception:
            name = None
        if not name:
            name = getattr(getattr(u, "type", None), "name", None)
        if name:
            comp[str(name)] = comp.get(str(name), 0) + 1
    return comp or None


def _build_target(game: Game, tgo, kind: str, task: str) -> TargetView:
    ll = DcsPoint(tgo.position.x, tgo.position.y, game.theater.terrain).latlng()
    threat = None
    max_range = getattr(tgo, "max_threat_range", None)
    if max_range is not None:
        try:
            rng = max_range()
            threat = int(rng.nautical_miles) if rng else None
        except Exception:
            threat = None
    detection = None
    max_detection = getattr(tgo, "max_detection_range", None)
    if max_detection is not None:
        try:
            rng = max_detection()
            detection = int(rng.nautical_miles) if rng else None
        except Exception:
            detection = None
    group_id = None
    composition = None
    if kind == "ship":
        grp = getattr(tgo, "control_point", None)
        group_id = str(grp.id) if grp is not None else None
        composition = _unit_composition(tgo)
    elif kind == "sam":
        # Alive launchers/radars per type — shows partial battle damage on a SAM site
        # (e.g. TELs killed but the radar still up), not just alive/dead.
        composition = _unit_composition(tgo)
    # Only when it is news. A planner does not need telling that every SAM on the map
    # is doing its job, and this list is long.
    status = _iads_status(game, tgo)
    notable = status is not None and status.notable
    iads_state = status.state.value if notable and status is not None else None
    iads_reason = status.reason if notable and status is not None else None
    iads_blind = True if status is not None and status.blind else None
    base = getattr(tgo, "control_point", None)
    return TargetView(
        id=str(tgo.id),
        name=tgo.name,
        kind=kind,
        suggested_task=task,
        pos=[_r(ll.lat), _r(ll.lng)],
        # Only where "building" is all the kind says. A SAM is a SAM.
        category=getattr(tgo, "category", None) if kind == "building" else None,
        base=base.name if base is not None and kind != "ship" else None,
        threat_nm=threat or None,
        detection_nm=detection or None,
        group_id=group_id,
        composition=composition,
        damage=_damage_word(tgo),
        iads_role=_iads_role(tgo),
        rebuild=_rebuild_state(tgo),
        iads_state=iads_state,
        iads_reason=iads_reason,
        iads_blind=iads_blind,
    )


def _rebuild_state(tgo: object) -> RebuildView | None:
    """What is being repaired on this site, and when it lands.

    A site rebuilt from nothing spends the delay with every unit dead but with a
    countdown on them, which reads exactly like a destroyed site: no composition, and
    for an enemy site, dropped from the target list entirely. The player sees the works
    on the map, so a planner that cannot is being asked to plan against a different
    board -- and it matters both ways round. An enemy SAM coming back in two turns is
    not a free corridor, and your own rebuilt site is not somewhere to send a repair.

    A PARTIAL repair is the same news and used to be silent: this bailed out the moment
    it found one unit standing, on the grounds that a site with something alive is
    damaged rather than under construction. True, and beside the point -- a battery that
    is firing today and gets its second launcher back next turn is a battery you are
    planning against twice. ``units_alive`` is what tells the two apart, so nothing that
    read this before has to guess.
    """
    turns = None
    repairing = 0
    alive = 0
    for unit in getattr(tgo, "units", []):
        if getattr(unit, "alive", True):
            alive += 1
            continue
        remaining = getattr(unit, "repair_turns_remaining", None)
        if remaining is not None:
            repairing += 1
            turns = remaining if turns is None else max(turns, remaining)
    if turns is None:
        return None
    name = None
    for group in getattr(tgo, "groups", []):
        name = getattr(group, "name", None)
        if name:
            break
    fallback = getattr(tgo, "name", "")
    return RebuildView(
        force_group=str(name or fallback),
        turns_remaining=int(turns),
        units_repairing=repairing,
        units_alive=alive,
    )


def _iads_status(game: Game, tgo: object) -> IadsStatus | None:
    """What the IADS will do with this site next mission, or None if it is not in one.

    Derived from the network rather than measured: DCS never reports the state back.
    The network caches the answer for the whole map, so asking per site is cheap.
    """
    try:
        return game.theater.iads_network.state_map.status_for(tgo)  # type: ignore[arg-type]
    except Exception:
        return None


def _iads_role(tgo) -> str | None:
    """This site's role in the IADS, or None if it plays no part in one.

    A ground object carries the role on its groups, so a power station reads as
    "PowerSource" instead of an anonymous code-named building. Point defenses and
    plain objects report nothing, matching what Skynet actually wires up.
    """
    from game.theater.theatergroup import IadsGroundGroup

    for group in getattr(tgo, "groups", []):
        if isinstance(group, IadsGroundGroup) and group.iads_role.participate:
            return str(group.iads_role.value)
    return None


def _build_transport_targets(game: Game, player: Player) -> list[TargetView]:
    """Enemy convoys and cargo ships, as the player's Departing Convoys tab lists them.

    They carry no id of their own (the UI has a standing TODO about that), so the
    generated name is the handle -- it is unique and stable for the turn, which is as
    long as a convoy lives.
    """
    enemy = game.coalition_for(player).opponent
    out: list[TargetView] = []
    for transports, kind, task in (
        (enemy.transfers.convoys, "convoy", "BAI"),
        (enemy.transfers.cargo_ships, "cargo_ship", "ANTISHIP"),
    ):
        for transport in transports:
            units = {
                str(unit): count for unit, count in transport.units.items() if count
            }
            if not units:
                continue  # an empty convoy is a bookkeeping husk, not a target
            pos = DcsPoint(
                transport.position.x, transport.position.y, game.theater.terrain
            ).latlng()

            def ll(point) -> list[float]:
                latlng = DcsPoint(point.x, point.y, game.theater.terrain).latlng()
                return [_r(latlng.lat), _r(latlng.lng)]

            # A Convoy exposes route_start/route_end (a road leg); a CargoShip exposes
            # `route`, the shipping lane's full point list. Report both as endpoints.
            leg = getattr(transport, "route", None)
            if leg:
                ends = [ll(leg[0]), ll(leg[-1])]
            else:
                ends = [
                    ll(transport.route_start),  # type: ignore[union-attr]
                    ll(transport.route_end),  # type: ignore[union-attr]
                ]

            out.append(
                TargetView(
                    id=transport.name,
                    name=transport.name,
                    kind=kind,
                    suggested_task=task,
                    pos=[_r(pos.lat), _r(pos.lng)],
                    origin=transport.origin.name,
                    destination=transport.destination.name,
                    route=ends,
                    composition=units,
                )
            )
    return out


def build_targets(game: Game, side: str) -> list[TargetView]:
    from game.commander.objectivefinder import ObjectiveFinder

    player = player_for_side(side)
    finder = ObjectiveFinder(game, player)
    targets: list[TargetView] = []
    for sam in finder.enemy_air_defenses():
        targets.append(_build_target(game, sam, "sam", "DEAD"))
    for ship in finder.enemy_ships():
        targets.append(_build_target(game, ship, "ship", "ANTISHIP"))
    for building in finder.strike_targets():
        targets.append(_build_target(game, building, "building", "STRIKE"))
    # Motorpools are their own finder: strike_targets() only yields buildings, so
    # without this the LLM could not see (or hit) the enemy's undeployed armor
    # reserve that the human player and the built-in AI commander both target.
    for motorpool in finder.motorpool_targets():
        targets.append(_build_target(game, motorpool, "motorpool", "BAI"))
    # Convoys and cargo ships: the human player attacks these from a base's "Departing
    # Convoys" tab, one Attack button each. They are reinforcements in transit -- killing
    # one denies the destination the units before they ever deploy, which is cheaper than
    # fighting them at the front.
    targets.extend(_build_transport_targets(game, player))
    for front in game.theater.conflicts():
        friendly_cp = front.red_cp if player.is_red else front.blue_cp
        enemy_cp = front.blue_cp if player.is_red else front.red_cp
        ll = DcsPoint(front.position.x, front.position.y, game.theater.terrain).latlng()
        targets.append(
            TargetView(
                id=str(front.id),
                name=front.name,
                kind="front",
                suggested_task="CAS",
                pos=[_r(ll.lat), _r(ll.lng)],
                friendly_cp_id=str(friendly_cp.id),
                enemy_cp_id=str(enemy_cp.id),
            )
        )
    return targets


def build_own_ground_objects(game: Game, side: str) -> list[TargetView]:
    """Your OWN ground objects, with their ids -- what ``ground/options`` needs.

    ``targets`` is the enemy's, always: it comes from ObjectiveFinder, which only ever
    yields what the other side owns. So there was no way to name one of your own sites
    to upgrade it, even though rebuilding is free on turn 0 and the player can do it
    from the map. Kept out of the per-turn payload (a dense campaign has hundreds of
    these) and served on request instead.
    """
    from game.theater.theatergroundobject import (
        IadsGroundObject,
        MissileSiteGroundObject,
        VehicleGroupGroundObject,
    )

    rebuildable = (IadsGroundObject, MissileSiteGroundObject, VehicleGroupGroundObject)
    player = player_for_side(side)
    out: list[TargetView] = []
    for cp in game.theater.controlpoints:
        if cp.captured != player:
            continue
        for go in cp.ground_objects:
            if isinstance(go, rebuildable):
                out.append(_build_target(game, go, _own_kind(go), "DEAD"))
    return out


def _own_kind(go: Any) -> str:
    from game.theater.theatergroundobject import IadsGroundObject

    return "sam" if isinstance(go, IadsGroundObject) else "ground"


def build_own_sams(game: Game, side: str) -> list[TargetView]:
    """Your own live SAM sites (friendly IADS) — for drawing your air-defense
    umbrellas alongside the enemy's. Not part of the text turn_context."""
    from game.commander.objectivefinder import ObjectiveFinder
    from game.theater.theatergroundobject import IadsGroundObject

    finder = ObjectiveFinder(game, player_for_side(side))
    out: list[TargetView] = []
    for cp in finder.friendly_control_points():
        for go in cp.ground_objects:
            if not go.is_dead and isinstance(go, IadsGroundObject):
                out.append(_build_target(game, go, "sam", "DEAD"))
    return out


def build_threats(targets: list[TargetView]) -> list[ThreatView]:
    """EVERY enemy air-defense umbrella (radar SAMs + SAM-armed ships), ranked by reach.

    Complete on purpose. This was a top-12 digest, which silently dropped 42 of 54 live
    umbrellas on a dense campaign -- and the cut landed inside a nine-way tie at 24 nm,
    so one site was listed while eight identical ones were not. The planner is told to
    route around ``threats``, so a list that quietly ends is worse than no list: it reads
    as "these are the bubbles" and the omitted ones get flown through. Ranking is the
    value here, not brevity; the payload already carries every one of these in
    ``targets`` with its full composition.
    """
    ranked = sorted(
        (t for t in targets if t.kind in ("sam", "ship") and t.threat_nm),
        key=lambda t: t.threat_nm or 0,
        reverse=True,
    )
    return [
        ThreatView(
            id=t.id,
            name=t.name,
            kind=t.kind,
            threat_nm=t.threat_nm or 0,
            pos=t.pos,
            iads_state=t.iads_state,
            iads_reason=t.iads_reason,
            iads_blind=t.iads_blind,
        )
        for t in ranked
    ]


def _naval_view(game: Game, obj, kind: str) -> NavalView:
    """A NavalView from either a ShipGroundObject (kind='ship') or a movable naval
    control point / carrier (kind='carrier') — both expose position, max_move_distance,
    and target_position the same way."""
    ll = DcsPoint(obj.position.x, obj.position.y, game.theater.terrain).latlng()
    dest = None
    tp = getattr(obj, "target_position", None)
    if tp is not None:
        dll = DcsPoint(tp.x, tp.y, game.theater.terrain).latlng()
        dest = [_r(dll.lat), _r(dll.lng)]
    threat = None
    max_range = getattr(obj, "max_threat_range", None)
    if callable(max_range):
        try:
            rng = max_range()
            threat = int(rng.nautical_miles) if rng else None
        except Exception:
            threat = None
    comp = _unit_composition(obj)
    hull_owner = obj
    if comp is None:
        # A carrier/LHA is a control point whose hulls live in its is_control_point
        # ship ground object rather than on the CP itself; dig them out so carriers
        # report composition too.
        for sub in getattr(obj, "ground_objects", []):
            if getattr(sub, "is_control_point", False):
                comp = _unit_composition(sub)
                hull_owner = sub
                break
    return NavalView(
        id=str(obj.id),
        name=obj.name,
        kind=kind,
        pos=[_r(ll.lat), _r(ll.lng)],
        move_range_nm=int(obj.max_move_distance.nautical_miles),
        destination=dest,
        threat_nm=threat or None,
        damage=_damage_word(obj),
        composition=comp,
        cruise_missiles_remaining=_cruise_missiles_remaining(game, hull_owner),
    )


def _cruise_missiles_remaining(game: Game, tgo) -> int | None:
    """The group's campaign stock of land-attack cruise missiles, or None when it has
    none — an ordinary frigate should not carry a noisy `0` through the transport. A
    naval group can hold several TheaterGroups, so sum them: the LLM tasks the group,
    not the individual hull rows."""
    from game.cruise_raids import tgo_magazines

    total = sum(remaining for _, remaining in tgo_magazines(game, tgo))
    return total or None


def _fleet_has_living_hull(cp) -> bool:
    """Whether a fleet control point still has any hull afloat. A dead FLAGSHIP only
    stops aviation (that's what ``runway_is_operational`` measures); surviving escorts
    keep sailing, and the map UI still lets the player drag such a fleet — so the AI
    must keep seeing and moving it too (else the survivors become invisible ghosts)."""
    for tgo in getattr(cp, "ground_objects", []):
        if getattr(tgo, "is_control_point", False):
            return any(u.alive for u in tgo.units)
    return False


def build_my_naval(game: Game, side: str) -> list[NavalView]:
    """The side's OWN repositionable naval groups — combatant ship groups
    (ShipGroundObject) AND carriers/LHAs (movable naval control points). These are what
    ``move_ship`` can reposition; the LLM can't see them via the enemy-only ``targets``
    list, so surface them here with their move range and any pending destination."""
    from game.theater.theatergroundobject import ShipGroundObject

    player = player_for_side(side)
    out: list[NavalView] = []
    for cp in game.theater.controlpoints:
        if cp.captured != player:
            continue
        # the carrier/LHA itself is a movable control point (a different id namespace
        # than its escort ship groups below) — skip it only when EVERY hull is sunk
        # (nothing left to move), mirroring the is_dead skip for ship groups below.
        # NOT runway_is_operational: that is the carrier-AVIATION check, and a fleet
        # that lost its flagship still sails (composition reports the survivors).
        if (
            getattr(cp, "moveable", False)
            and getattr(cp, "is_fleet", False)
            and _fleet_has_living_hull(cp)
        ):
            out.append(_naval_view(game, cp, "carrier"))
        for tgo in cp.ground_objects:
            if not isinstance(tgo, ShipGroundObject) or not tgo.moveable:
                continue
            if getattr(tgo, "is_dead", False):
                continue
            out.append(_naval_view(game, tgo, "ship"))
    return out


def _tgo_repairables(tgo) -> tuple[int, list]:
    """(total_cost, [(unit, cost), …]) for a ground object's dead, not-already-repairing
    units, mirroring the player's manual-repair UI. A BUILDING (oil/factory/ammo/…) is
    repaired as a WHOLE for one ``repair_cost()`` — its income statics have no unit_type
    (so their unit-level ``repairable`` is False), yet the building itself is repairable
    whenever it has a repair cost; this was the gap that hid oil/econ from ``repairs``.
    Other ground objects are priced per dead unit. Empty list = nothing to repair here.
    """
    from game.theater.theatergroundobject import BuildingGroundObject

    if isinstance(tgo, BuildingGroundObject):
        if not getattr(tgo, "repairable", False):
            return 0, []
        dead = [
            u
            for u in tgo.statics
            if not getattr(u, "alive", True)
            and getattr(u, "repair_turns_remaining", None) is None
        ]
        if not dead:
            return 0, []
        try:
            cost = int(tgo.repair_cost())
        except Exception:
            cost = 0
        if cost <= 0:
            return 0, []
        # Billed once for the whole building: the first dead static carries the cost,
        # the rest carry 0 so they all revive without being charged again.
        return cost, [(dead[0], cost)] + [(u, 0) for u in dead[1:]]

    out: list = []
    total = 0
    for u in tgo.units:
        if getattr(u, "alive", True) or not getattr(u, "repairable", False):
            continue
        if getattr(u, "repair_turns_remaining", None) is not None:
            continue  # already under repair
        ut = getattr(u, "unit_type", None)
        cost = int(getattr(ut, "price", 0)) if ut else 0
        if cost <= 0:
            continue
        total += cost
        out.append((u, cost))
    return total, out


def build_repairs(game: Game, side: str) -> list[RepairView]:
    """The side's OWN damaged-but-repairable assets it can pay to fix: dead SAM/EWR units,
    buildings, and cratered runways. (Repairs also happen automatically from leftover
    budget at end of turn — this list is what you can choose to fix *now*.)"""
    from game.config import RUNWAY_REPAIR_COST
    from game.theater.theatergroundobject import BuildingGroundObject

    player = player_for_side(side)
    out: list[RepairView] = []
    for cp in game.theater.controlpoints:
        if cp.captured != player:
            continue
        try:
            if getattr(cp, "runway_can_be_repaired", False):
                out.append(
                    RepairView(
                        id=str(cp.id),
                        name=cp.name,
                        kind="runway",
                        cost=int(RUNWAY_REPAIR_COST),
                    )
                )
        except Exception:
            pass
        for tgo in cp.ground_objects:
            cost, units = _tgo_repairables(tgo)
            if cost <= 0 or not units:
                continue
            # Category is the kind for everything: SAM sites -> aa/ewr, economy buildings
            # -> oil/factory/ammo (so a dead income asset is identifiable, not just "building").
            kind = str(getattr(tgo, "category", None) or "ground")
            income = None
            if isinstance(tgo, BuildingGroundObject):
                from game.config import REWARDS

                income = int(REWARDS.get(kind, 0)) or None
            out.append(
                RepairView(
                    id=str(tgo.id),
                    name=tgo.name,
                    kind=kind,
                    cost=cost,
                    dead_units=len(units),
                    income_per_turn=income,
                )
            )
    return out


def build_buyable_ground(game: Game, side: str) -> list[GroundUnitView]:
    faction = coalition_for_side(game, side).faction
    out: list[GroundUnitView] = []
    for kind, units in (
        ("front", faction.frontline_units),
        ("artillery", faction.artillery_units),
    ):
        for u in sorted(units, key=lambda x: x.display_name):
            out.append(
                GroundUnitView(
                    name=u.display_name,
                    price=math.ceil(getattr(u, "price", 0)),
                    kind=kind,
                )
            )
    return out


def build_leave_requests(game: Game, side: str) -> list[LeaveRequestView]:
    """Everyone on this side waiting to be told yes or no, worst off first.

    Empty on most turns, which is why it costs nothing to carry in the turn context.
    """
    from game.squadrons.morale import morale_state

    coalition = coalition_for_side(game, side)
    if not coalition.game.settings.live_pilots_enabled:
        return []
    requests: list[LeaveRequestView] = []
    for squadron in coalition.air_wing.iter_squadrons():
        if not squadron.morale_in_play:
            continue
        for pilot in squadron.pilots_asking_for_leave():
            rank = squadron.pilot_rank(pilot)
            requests.append(
                LeaveRequestView(
                    squadron_id=str(squadron.id),
                    squadron=str(squadron),
                    pilot_name=pilot.name,
                    rank="" if rank is None else rank.abbreviation,
                    morale=pilot.morale,
                    state=morale_state(pilot.morale, game.settings).name,
                    asked_turns=pilot.leave_turns_requested,
                    spare_pilots=squadron.spare_pilots(excluding=pilot),
                    aircraft=squadron.owned_aircraft,
                )
            )
    requests.sort(key=lambda request: request.morale)
    return requests


def build_turn_context(game: Game, side: str = "red") -> TurnContextView:
    side = side.lower()
    coalition = coalition_for_side(game, side)
    targets = build_targets(game, side)
    return TurnContextView(
        side=side,
        situation=build_situation(game),
        economy=build_economy(game, side),
        control_points=[
            build_control_point(game, cp, player_for_side(side))
            for cp in game.theater.controlpoints
        ],
        air_wing=[
            build_squadron(sq, player_for_side(side))
            for sq in coalition.air_wing.iter_squadrons()
        ],
        idle_flyable=idle_flyable_total(game, side),
        targets=targets,
        threats=build_threats(targets),
        naval=build_my_naval(game, side),
        repairs=build_repairs(game, side),
        buyable_ground=build_buyable_ground(game, side),
        leave_requests=build_leave_requests(game, side),
    )


def build_settings(game: Game) -> SettingsView:
    from game.theater.controlpoint import RUNWAY_REPAIR_TURNS

    s = game.settings
    return SettingsView(
        opfor_aggressiveness_pct=s.opfor_autoplanner_aggressiveness,
        map_coalition_visibility=getattr(
            s.map_coalition_visibility, "name", str(s.map_coalition_visibility)
        ),
        desired_player_mission_duration_min=int(
            s.desired_player_mission_duration.total_seconds() // 60
        ),
        player_income_multiplier=s.player_income_multiplier,
        enemy_income_multiplier=s.enemy_income_multiplier,
        crashes_dont_count=s.ignore_non_combat_air_losses,
        pilot_replenishment_per_squadron=(
            int(s.squadron_replenishment_rate)
            if getattr(s, "enable_squadron_pilot_limits", True)
            else None
        ),
        squadron_pilot_limit=(
            int(s.squadron_pilot_limit)
            if getattr(s, "enable_squadron_pilot_limits", True)
            else None
        ),
        runway_repair_turns=RUNWAY_REPAIR_TURNS,
        cruise_missile_strikes=bool(s.plugin_option_or("cruisemissiles", False)),
        cruise_missile_auto_raids=bool(
            s.plugin_option_or("cruisemissiles.autoRaids", False)
        ),
        all_settings=_all_settings(s),
    )


def _all_settings(s: Any) -> list[SettingView]:
    """Every setting on the pages, in the order the player reads them.

    The curated fields above cover what the planner usually needs; this is for
    everything else, and it is how a question like "how long is a mission?" gets
    answered without someone adding a field for it first.
    """
    from game.settings import Settings

    out: list[SettingView] = []
    for key, description in Settings.all_fields():
        if description.visible_when is not None and not description.visible_when(s):
            continue  # a setting the campaign is not offering right now
        out.append(
            SettingView(
                key=key,
                page=description.page,
                section=description.subsection or description.section,
                label=description.text,
                value=_setting_value(getattr(s, key, None)),
                detail=description.detail,
            )
        )
    return out


def _setting_value(value: Any) -> Any:
    """Whatever JSON can carry: minutes for a duration, the name for an enum."""
    from datetime import timedelta

    if isinstance(value, timedelta):
        return int(value.total_seconds() // 60)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return getattr(value, "name", str(value))


def _flight_loadout(flight):
    """(loadout name, {pylon: clsid}) from the flight's first member, or (None, None)."""
    try:
        member = next(iter(flight.iter_members()), None)
    except Exception:
        member = None
    loadout = getattr(member, "loadout", None)
    if loadout is None:
        return None, None
    weapons = {
        num: weapon.clsid
        for num, weapon in loadout.pylons.items()
        if weapon is not None
    }
    return loadout.name, (weapons or None)


def _startup_minutes(flight) -> int | None:
    """Minutes from mission start to this flight's engine start.

    Same clock the planner sets TOTs on, so it can be compared with tot_minutes without
    knowing the wall time. Negative means the flight cannot make its TOT.
    """
    try:
        startup = flight.flight_plan.startup_time()
        mission_start = flight.coalition.game.conditions.start_time
    except Exception:  # pragma: no cover - a flight without a plan or a live game
        return None
    if startup is None or mission_start is None:
        return None
    return round((startup - mission_start).total_seconds() / 60)


def _tot_offset_minutes(flight) -> float | None:
    """The flight's offset from the package TOT, in minutes, or None when it is zero."""
    try:
        seconds = flight.flight_plan.tot_offset.total_seconds()
    except AttributeError:  # pragma: no cover - a flight without a plan yet
        return None
    return round(seconds / 60, 1) or None


def build_flight(flight) -> FlightView:
    missing = flight.missing_pilots
    missing_count = len(missing) if hasattr(missing, "__len__") else int(missing)
    loadout_name, weapons = _flight_loadout(flight)
    return FlightView(
        id=str(flight.id),
        task=_enum_str(flight.flight_type),
        aircraft=flight.unit_type.display_name,
        count=flight.count,
        squadron=str(flight.squadron),
        start=_enum_str(flight.start_type),
        dep=getattr(flight.departure, "name", None),
        clients=flight.client_count or None,
        uncrewed=missing_count or None,
        loadout=loadout_name,
        weapons=weapons,
        startup_min=_startup_minutes(flight),
        tot_offset_min=_tot_offset_minutes(flight),
    )


def build_package(index: int, pkg) -> PackageView:
    tot = pkg.time_over_target
    desc = getattr(pkg, "custom_name", None)  # the planner stores the rationale here
    if not desc:
        desc = pkg.package_description
        if callable(desc):
            desc = desc()
    return PackageView(
        index=index,
        target=getattr(pkg.target, "name", str(pkg.target)),
        task=_enum_str(pkg.primary_task),
        tot=tot.strftime("%H:%M") if tot else None,
        desc=desc or None,
        flights=[build_flight(f) for f in pkg.flights],
    )


def build_packages(game: Game, side: str = "red") -> list[PackageView]:
    ato = coalition_for_side(game, side).ato
    return [build_package(i, p) for i, p in enumerate(ato.packages)]


def build_prev_turns(game: Game, n: int = 3) -> list[TurnForcesView]:
    """The last ``n`` turns' force totals (blue=allied, red=enemy in game_stats),
    merged with that turn's debriefed losses when available.

    Previous means previous. The turn being planned already has a stats entry --
    it gets one the moment it starts -- but it has not been flown and has no
    debrief, so including it made ``n=1`` answer with the turn you are sitting
    in, empty of losses, instead of the one you just fought.
    """
    data = game.game_stats.data_per_turn[: game.turn]
    losses_by_turn = {
        d.get("turn"): d for d in getattr(game, "debrief_history", []) or []
    }
    start = max(0, len(data) - n)
    out: list[TurnForcesView] = []
    for i in range(start, len(data)):
        td = data[i]
        loss = losses_by_turn.get(i, {})
        out.append(
            TurnForcesView(
                turn=i,
                blue_aircraft=td.allied_units.aircraft_count,
                blue_vehicles=td.allied_units.vehicles_count,
                red_aircraft=td.enemy_units.aircraft_count,
                red_vehicles=td.enemy_units.vehicles_count,
                blue_air_lost=loss.get("blue_air_lost") or None,
                red_air_lost=loss.get("red_air_lost") or None,
                blue_air_crashed=loss.get("blue_air_crashed") or None,
                red_air_crashed=loss.get("red_air_crashed") or None,
                blue_ground_lost=loss.get("blue_ground_lost") or None,
                red_ground_lost=loss.get("red_ground_lost") or None,
                red_air_lost_by_type=loss.get("red_air_lost_by_type") or None,
                blue_air_lost_by_type=loss.get("blue_air_lost_by_type") or None,
                red_air_kills_by_weapon=loss.get("red_air_kills_by_weapon") or None,
                blue_air_kills_by_weapon=loss.get("blue_air_kills_by_weapon") or None,
                red_air_kills_by_victim=loss.get("red_air_kills_by_victim") or None,
                blue_air_kills_by_victim=loss.get("blue_air_kills_by_victim") or None,
                red_air_killers=loss.get("red_air_killers") or None,
                blue_air_killers=loss.get("blue_air_killers") or None,
                blue_air_combat=(
                    (loss.get("blue_air_lost", 0) - loss.get("blue_air_crashed", 0))
                    or None
                ),
                red_air_combat=(
                    (loss.get("red_air_lost", 0) - loss.get("red_air_crashed", 0))
                    or None
                ),
                blue_sites_lost=loss.get("blue_sites_lost") or None,
                red_sites_lost=loss.get("red_sites_lost") or None,
            )
        )
    return out


# --- ground-object rebuild (parity with the player's Buy-ground-object dialog) ---


def _ground_object_role_and_tasks(tgo):
    """(GroupRole, [GroupTask]) usable to rebuild a ground object, mirroring
    QGroundObjectBuyMenu (SAM/EWR/armor/ship/missile/coastal). Raises ValueError for a
    TGO type the dialog can't rebuild (e.g. a building)."""
    from game.data.groups import GroupRole, GroupTask
    from game.theater.theatergroundobject import (
        CoastalSiteGroundObject,
        EwrGroundObject,
        MissileSiteGroundObject,
        SamGroundObject,
        ShipGroundObject,
        VehicleGroupGroundObject,
    )

    tasks: list[GroupTask] = []
    # EWR before SAM: EwrGroundObject is a subclass of IadsGroundObject like SAM, but
    # SamGroundObject is not in its MRO — order is defensive, not load-bearing.
    if isinstance(tgo, EwrGroundObject):
        role = GroupRole.AIR_DEFENSE
        tasks.append(GroupTask.EARLY_WARNING_RADAR)
    elif isinstance(tgo, SamGroundObject):
        role = GroupRole.AIR_DEFENSE
    elif isinstance(tgo, VehicleGroupGroundObject):
        role = GroupRole.GROUND_FORCE
    elif isinstance(tgo, ShipGroundObject):
        role = GroupRole.NAVAL
        tasks.append(GroupTask.NAVY)
    elif isinstance(tgo, MissileSiteGroundObject):
        role = GroupRole.DEFENSES
        tasks.append(GroupTask.MISSILE)
    elif isinstance(tgo, CoastalSiteGroundObject):
        role = GroupRole.DEFENSES
        tasks.append(GroupTask.COASTAL)
    else:
        raise ValueError(
            f"{getattr(tgo, 'name', tgo)} is a {type(tgo).__name__}, which can't be "
            f"rebuilt (only SAM/EWR/armor/ship/missile/coastal sites)"
        )
    if not tasks:
        tasks = role.tasks
    return role, tasks


def ground_object_role_tasks(tgo):
    """The GroupTasks whose ForceGroups can rebuild ``tgo`` (see the dialog mapping)."""
    return _ground_object_role_and_tasks(tgo)[1]


def _resolve_tgo(game: Game, tgo_id: str, side: str):
    """Resolve a ground-object id to a TGO you own, or raise ValueError."""
    from uuid import UUID

    try:
        tgo = game.db.tgos.get(UUID(str(tgo_id)))
    except (KeyError, ValueError, AttributeError, TypeError):
        raise ValueError(f"no ground object with id {tgo_id!r}")
    if tgo.control_point.captured != player_for_side(side):
        raise ValueError(f"{tgo.name} is not yours")
    return tgo


def _layout_option(force_group, layout) -> LayoutOption | None:
    """Build a LayoutOption for one force-group + layout, or None if it has no usable
    unit group. Mirrors the QTgoLayoutGroupRow LayoutException skip (a unit_group with no
    unit types AND no statics is dropped)."""
    slots: list[GroupSlotView] = []
    price = 0
    for tgo_group in layout.groups:
        for unit_group in tgo_group.unit_groups:
            unit_types = [
                UnitTypeOption(name=ut.display_name, price=math.ceil(ut.price))
                for ut in force_group.unit_types_for_group(unit_group)
            ]
            has_static = (
                next(force_group.statics_for_group(unit_group), None) is not None
            )
            if not unit_types and not has_static:
                continue  # unusable by this faction — skip (LayoutException parity)
            default_count = unit_group.group_size
            slots.append(
                GroupSlotView(
                    group_name=tgo_group.group_name,
                    optional=unit_group.optional,
                    default_count=default_count,
                    max_count=unit_group.max_size,
                    unit_types=unit_types,
                )
            )
            # Default price: EVERY group at the first unit type * default count, including
            # optional ones. Optional groups default to enabled -- in the player's dialog
            # (QTgoLayoutGroup.enabled = True) and in ground/rebuild alike -- so leaving
            # them out quoted a price nobody would ever be charged: 305M against a real
            # 397M on one S-300VM site. Statics-only groups price at 0 (no unit types).
            if unit_types:
                price += default_count * unit_types[0].price
    if not slots:
        return None
    return LayoutOption(
        force_group=force_group.name,
        layout=layout.name,
        price=math.ceil(price),
        groups=slots,
    )


def build_ground_object_options(
    game: Game, side: str, tgo_id: str
) -> GroundObjectOptionsView:
    """What a ground object (SAM/EWR/armor/ship/missile/coastal site) can be rebuilt into
    and at what cost — the read behind the player's Buy-ground-object dialog. Lists every
    force-group + layout available to the faction for this TGO's role, each layout's
    selectable unit types and counts, and the default net price context (the old site's
    ``value`` is refunded on rebuild)."""
    tgo = _resolve_tgo(game, tgo_id, side)
    role, tasks = _ground_object_role_and_tasks(tgo)
    coalition = coalition_for_side(game, side)
    options: list[LayoutOption] = []
    for force_group in coalition.armed_forces.groups_for_tasks(tasks):
        for layout in force_group.layouts:
            try:
                option = _layout_option(force_group, layout)
            except Exception:
                continue  # one bad layout must not sink the whole response
            if option is not None:
                options.append(option)
    return GroundObjectOptionsView(
        tgo_id=str(tgo.id),
        name=tgo.name,
        role=role.name.lower(),
        refund=int(tgo.value),
        budget=round(coalition.budget),
        options=options,
    )


def build_iads(game: Game, side: str) -> IadsView:
    """The ENEMY IADS as a graph: every participating site and what feeds it.

    The player sees these links on the campaign map, so the planner gets them too.
    Only the opponent's half is returned — this is a targeting aid, not a view of
    one's own network. Dead nodes are kept: knowing a power station is already down
    is what tells you the radars behind it are blind.

    Each node also carries what its dependencies add up to: a site whose power is gone
    reads "dark" and will not fire next mission at all, and one that has lost its comms
    or its command centre reads "autonomous" and engages only what its own radar finds.
    That is the result of the graph, so nobody has to work it out from the graph.

    And what is being done about it: ``repair_turns`` is the countdown on any work in
    progress, so a power station you flattened last turn does not read as a permanent
    hole in their network.
    """
    player = player_for_side(side)
    network = game.theater.iads_network
    nodes: list[IadsNodeView] = []
    for node in network.nodes:
        tgo = node.group.ground_object
        if tgo.is_friendly(player):
            continue  # ours, not a target
        if not node.group.iads_role.participate:
            continue
        depends = [
            str(conn.ground_object.id)
            for conn in node.connections.values()
            if conn.ground_object.id != tgo.id
        ]
        status = network.state_map.status_for(tgo)
        notable = status is not None and status.notable
        rebuild = _rebuild_state(tgo)
        nodes.append(
            IadsNodeView(
                id=str(tgo.id),
                name=tgo.name,
                role=str(node.group.iads_role.value),
                alive=node.group.alive_units > 0,
                depends_on=sorted(set(depends)) or None,
                state=status.state.value if notable and status is not None else None,
                state_reason=status.reason if notable and status is not None else None,
                blind=True if status is not None and status.blind else None,
                repair_turns=rebuild.turns_remaining if rebuild is not None else None,
            )
        )
    return IadsView(advanced=network.advanced_iads, nodes=nodes)


def _air_intel(cp) -> dict[str, dict[str, int]] | None:
    """Aircraft based here grouped by role, as the human's Intel tab shows them.

    Deliberately the same source and grouping as qt_ui's QIntelInfo — allocated
    aircraft PRESENT, keyed by the airframe's default DCS task — so the planner reads
    exactly what the player reads about a base. Without it an enemy field is just a
    number, and there is no way to tell a fighter wing worth an OCA package from a
    couple of transports that is not.
    """
    from game.theater.controlpoint import ParkingType

    try:
        allocations = cp.allocated_aircraft(
            ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
        )
    except Exception:
        return None  # off-map spawns and the like have nothing to allocate
    by_role: dict[str, dict[str, int]] = {}
    for unit_type, count in allocations.present.items():
        if not count:
            continue
        role = unit_type.dcs_unit_type.task_default.name
        by_role.setdefault(role, {})[unit_type.display_name] = count
    return by_role or None


def _no_launch_reason(cp) -> str | None:
    """Why a base cannot launch, when it cannot. Called only for those.

    The three cases need three different answers from the planner, and lumping them
    under "runway cratered" was actively misleading: a FOB with no helipads reports
    "cannot launch" forever, has no runway to crater and no repair to wait for, so
    telling the planner its runway is damaged invites a wasted OCA/Runway package.
    """
    from game.theater.controlpoint import Fob

    if isinstance(cp, Fob):
        # Fob.runway_is_operational() is really "has somewhere to launch from"
        # (helipads or ground spawns), not a runway state -- Fobs are not destroyable.
        return "no_launch_facilities"
    if not cp.runway_is_destroyable:  # a property, not a method
        return "hull_sunk"  # carrier/LHA: the ship itself is dead
    return "runway_damaged"
