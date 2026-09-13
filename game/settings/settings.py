from collections.abc import Iterator
from dataclasses import Field, dataclass, field, fields
from datetime import timedelta
from enum import Enum, unique
from typing import Any, ClassVar, Dict, Optional

from dcs.forcedoptions import ForcedOptions

from .booleanoption import boolean_option
from .boundedfloatoption import bounded_float_option
from .boundedintoption import bounded_int_option
from .choicesoption import choices_option
from .minutesoption import minutes_option
from .textoption import text_option
from .optiondescription import OptionDescription, SETTING_DESCRIPTION_KEY
from .skilloption import pilot_skill_option, skill_option
from .textoption import text_option
from ..ato.starttype import StartType

Views = ForcedOptions.Views


@unique
class AutoAtoBehavior(Enum):
    Disabled = "Disabled"
    Never = "Never assign player pilots"
    Default = "No preference"
    Prefer = "Prefer player pilots"


@unique
class CloudPresetPack(Enum):
    """A community cloud-preset weather mod whose presets the mission generator may
    use. Only one can be active at a time: the packs share the same preset keys
    (Preset35+) but map them to different clouds, so they must not be mixed."""

    NONE = "None (stock DCS presets)"
    BANDIT = "Bandit's Cloud Presets"
    WEATHER2 = "Weather 2.0 (Bandit)"
    ATMOSX = "ATMOS-X"


@unique
@unique
class NightMissions(Enum):
    DayAndNight = "nightmissions_nightandday"
    OnlyDay = "nightmissions_onlyday"
    OnlyNight = "nightmissions_onlynight"


@unique
class DefaultPlayerLaserCode(Enum):
    DEFAULT_1688 = "Default (1688)"
    ALLOCATE_OWN = "Allocate own (unique per flight)"


DIFFICULTY_PAGE = "Difficulty"

AI_DIFFICULTY_SECTION = "AI Difficulty"
MISSION_DIFFICULTY_SECTION = "Mission Difficulty"
MISSION_RESTRICTIONS_SECTION = "Mission Restrictions"

CAMPAIGN_MANAGEMENT_PAGE = "Campaign Management"

GENERAL_SECTION = "General"
PILOTS_AND_SQUADRONS_SECTION = "Pilots and Squadrons"
HQ_AUTOMATION_SECTION = "HQ Automation"
OPFOR_AI_SECTION = "OPFOR AI commander"
FLIGHT_PLANNER_AUTOMATION = "Flight Planner Automation"
GROUND_OBJECT_REPAIR_TUNING_SECTION = "Ground Object Repairs"
BUILDING_REPAIR_TUNING_SECTION = "Building Repairs"

CAMPAIGN_DOCTRINE_PAGE = "Campaign Doctrine"
DOCTRINE_DISTANCES_SECTION = "Doctrine distances"


MISSION_GENERATOR_PAGE = "Mission Generator"

LIVE_PILOTS_PAGE = "Live Pilots"
LIVE_PILOTS_RANKS_SECTION = "Ranks"
LIVE_PILOTS_SURVIVAL_SECTION = "Survival Chance"
LIVE_PILOTS_MORALE_SECTION = "Morale"
LIVE_PILOTS_MORALE_STATES_SECTION = "Morale States"
LIVE_PILOTS_MORALE_EVENTS_SECTION = "Morale Event Values"
LIVE_PILOTS_HARDENING_SECTION = "Hardening"
LIVE_PILOTS_FRIENDSHIP_SECTION = "Friendship"
LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION = "Friendship levels"
LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION = "Per turn random variation"
LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION = "What changes it"
LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION = "What it does"


GAMEPLAY_SECTION = "Gameplay"
MISSION_START_SECTION = "Mission Start"
AI_BEHAVIOUR_SECTION = "AI"
KNEEBOARD_SECTION = "Kneeboard"

# TODO: Make sections a type and add headers.
# This section had the header: "Disabling settings below may improve performance, but
# will impact the overall quality of the experience."
PERFORMANCE_SECTION = "Performance"


def _atmosx_pack_selected(settings: Any) -> bool:
    """The ATMOS-X live-weather options only mean anything with that pack selected."""
    return settings.cloud_preset_pack is CloudPresetPack.ATMOSX


@dataclass
class Settings:
    version: Optional[str] = None

    # Difficulty settings
    # AI Difficulty
    player_skill: str = pilot_skill_option(
        "Player coalition skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
        detail="Using Cadet is strongly recommended if you are enabling Live Pilots.",
    )
    enemy_skill: str = pilot_skill_option(
        "Enemy coalition skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
        detail="Using Cadet is strongly recommended if you are enabling Live Pilots.",
    )
    enemy_vehicle_skill: str = skill_option(
        "Enemy AA and vehicles skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
    )
    player_income_multiplier: float = bounded_float_option(
        "Player income multiplier",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.0,
    )
    enemy_income_multiplier: float = bounded_float_option(
        "Enemy income multiplier",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.0,
    )
    invulnerable_player_pilots: bool = boolean_option(
        "Player pilots cannot be killed",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        detail=(
            "Aircraft are vulnerable, but the player's pilot will be returned to the "
            "squadron at the end of the mission"
        ),
        default=True,
    )
    # Mission Difficulty
    manpads: bool = boolean_option(
        "Manpads on frontlines",
        page=DIFFICULTY_PAGE,
        section=MISSION_DIFFICULTY_SECTION,
        default=True,
    )
    night_day_missions: NightMissions = choices_option(
        "Night/day mission options",
        page=DIFFICULTY_PAGE,
        section=MISSION_DIFFICULTY_SECTION,
        choices={
            "Generate night and day missions": NightMissions.DayAndNight,
            "Only generate day missions": NightMissions.OnlyDay,
            "Only generate night missions": NightMissions.OnlyNight,
        },
        default=NightMissions.DayAndNight,
    )
    # Mission Restrictions
    labels: str = choices_option(
        "In game labels",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices=["Full", "Abbreviated", "Dot Only", "Neutral Dot", "Off"],
        default="Full",
    )
    map_coalition_visibility: Views = choices_option(
        "Map visibility options",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={
            "All": Views.All,
            "Fog of war": Views.Allies,
            "Allies only": Views.OnlyAllies,
            "Own aircraft only": Views.MyAircraft,
            "Map only": Views.OnlyMap,
        },
        default=Views.All,
    )
    opfor_ai_enabled: bool = boolean_option(
        "Allow OPFOR AI control (external LLM plays red)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=OPFOR_AI_SECTION,
        default=False,
        detail=(
            "Expose the live game over a local API so an external LLM (e.g. ChatGPT, "
            "Claude, et cetera) plans the enemy turns instead of the scripted "
            "commander. Check the toolbar OPFOR AI button for more info when enabling "
            "this."
        ),
    )
    external_views_allowed: bool = boolean_option(
        "Allow external views",
        DIFFICULTY_PAGE,
        MISSION_RESTRICTIONS_SECTION,
        default=True,
    )

    easy_communication: Optional[bool] = choices_option(
        "Easy Communication",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={"Player preference": None, "Enforced on": True, "Enforced off": False},
        default=None,
    )

    battle_damage_assessment: Optional[bool] = choices_option(
        "Battle damage assessment",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={"Player preference": None, "Enforced on": True, "Enforced off": False},
        default=None,
    )

    # CAMPAIGN DOCTRINE
    ignore_non_combat_air_losses: bool = boolean_option(
        "Non-combat (crash) aircraft losses don't count",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "The AI has too high a tendency to crash into terrain or buildings. "
            "This setting makes those losses not count as real ones: the aircraft "
            "is not removed from the squadron and its pilot survives. Only losses "
            "DCS attributes to a weapon or a SAM count as real in the campaign. "
            "Applies to both coalitions."
        ),
    )
    desired_barcap_mission_duration: timedelta = minutes_option(
        "Desired BARCAP on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
        detail="Implicitly determines the number of BARCAPs planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    desired_tarcap_mission_duration: timedelta = minutes_option(
        "Desired TARCAP on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=30),
        min=10,
        max=150,
        detail="Only applies to a TARCAP nobody asked to escort. When a flight in its"
        " package has requested an escort, the TARCAP stays for as long as the escorted"
        " mission does, whatever this says.",
    )
    desired_awacs_mission_duration: timedelta = minutes_option(
        "Desired AWACS on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=120),
        min=60,
        max=300,
        detail="Implicitly determines the number of AWACS flights planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    desired_tanker_on_station_time: timedelta = minutes_option(
        "Desired tanker on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
        detail="Implicitly determines the number of Tanker flights planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    plan_refuelling_when_needed: bool = boolean_option(
        "Plan a tanker and a refuelling waypoint when a package needs the fuel",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        invert=False,
        detail=(
            "If a tanker is available, one is planned with the package when the fuel "
            "estimate says the package needs it. The refuelling waypoint goes on the "
            "way home, in friendly airspace."
        ),
    )
    aircraft_per_recovery_tanker: int = bounded_int_option(
        "Number of aircraft per recovery tanker",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=4,
        min=2,
        max=12,
        detail=(
            "A higher number will force the autoplanner to generate less recovery tankers."
        ),
    )
    oca_target_autoplanner_min_aircraft_count: int = bounded_int_option(
        "Minimum number of aircraft (at vulnerable airfields) for auto-planner to plan OCA packages against",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "How many aircraft there has to be at an airfield for "
            "the auto-planner to plan an OCA strike against it."
        ),
    )
    ownfor_autoplanner_aggressiveness: int = bounded_int_option(
        "OWNFOR auto-planner aggressiveness (%)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "Ratio of the threat-radius that will be ignored by the OWNFOR "
            "AI-autoplanner. 0% means the entire threat-radius is considered, "
            "while 100% would have the autoplanner completely ignore OPFOR air defences."
        ),
    )
    opfor_autoplanner_aggressiveness: int = bounded_int_option(
        "OPFOR auto-planner aggressiveness (%)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "Ratio of the threat-radius that will be ignored by the OPFOR "
            "AI-autoplanner. 0% means the entire threat-radius is considered, "
            "while 100% would have the autoplanner completely ignore OWNFOR air defences."
        ),
    )
    heli_combat_alt_agl: int = bounded_int_option(
        "Helicopter combat altitude (feet AGL)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=200,
        min=1,
        max=10000,
        detail=(
            "Altitude for helicopters in feet AGL while flying between combat waypoints."
            " Combat waypoints are considered INGRESS, CAS, TGT, EGRESS & SPLIT."
            " In campaigns in more mountainous areas, you might want to increase this "
            "setting to avoid the AI flying into the terrain."
        ),
    )
    heli_cruise_alt_agl: int = bounded_int_option(
        "Helicopter cruise altitude (feet AGL)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=500,
        min=1,
        max=10000,
        detail=(
            "Altitude for helicopters in feet AGL while flying between non-combat waypoints."
            " In campaigns in more mountainous areas, you might want to increase this "
            "setting to avoid the AI flying into the terrain."
        ),
    )
    atflir_autoswap: bool = boolean_option(
        "Auto-swap ATFLIR to LITENING",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "Automatically swaps ATFLIR to LITENING pod for newly generated land-based F/A-18 flights "
            "without having to change the payload. <u>Takes effect after current turn!</u>"
        ),
    )
    ai_jettison_empty_tanks: bool = boolean_option(
        "Enable AI empty fuel tank jettison",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail="AI will jettison their fuel tanks as soon as they're empty.",
    )
    ai_vertical_takoff_landing: bool = boolean_option(
        "AI helicopters use vertical takeoff and landing",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail="AI will use vertical takeoff and landing instead of combat takeoff and landing.",
    )
    max_plane_altitude_offset: int = bounded_int_option(
        "Maximum randomized altitude offset (x1000 ft) for airplanes.",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        min=0,
        max=5,
        default=2,
        detail="Creates a randomized altitude offset for airplanes.",
    )

    player_startup_time: int = bounded_int_option(
        "Player startup time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=10,
        min=0,
        max=100,
        detail=(
            "The startup time allocated to player flights (default : 10 minutes, AI is 2 minutes). "
            "Packages have to be planned again for this to take effect. "
        ),
    )

    # Doctrine Distances Section
    airbase_threat_range: int = bounded_int_option(
        "Airbase threat range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=100,
        min=0,
        max=300,
        detail=(
            "Will impact both defensive (BARCAP) and offensive flights. Also has a performance impact, "
            "lower threat range generally means less BARCAPs are planned."
        ),
    )
    max_threat_range: int = bounded_int_option(
        "Maximum threat range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=200,
        min=60,
        max=500,
        detail=(
            "Provides an upper limit to threat-ranges to avoid partial nav-meshes, which leads to errors. "
            "Lower this setting further if the map's bounds aren't covered by the nav-mesh."
        ),
    )
    cas_engagement_range_distance: int = bounded_int_option(
        "CAS engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=10,
        min=0,
        max=100,
    )
    armed_recon_engagement_range_distance: int = bounded_int_option(
        "Armed Recon engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=5,
        min=0,
        max=25,
    )
    sead_sweep_engagement_range_distance: int = bounded_int_option(
        "SEAD Sweep engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=30,
        min=0,
        max=100,
    )
    sead_threat_buffer_min_distance: int = bounded_int_option(
        "SEAD Escort/Sweep threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=5,
        min=0,
        max=100,
        detail=(
            "How close to known threats will the SEAD Escort / SEAD Sweep engagement zone extend."
        ),
    )
    tarcap_threat_buffer_min_distance: int = bounded_int_option(
        "TARCAP threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=20,
        min=0,
        max=100,
        detail=("How close to known threats will the TARCAP racetrack extend."),
    )
    aewc_threat_buffer_min_distance: int = bounded_int_option(
        "AEW&C threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=80,
        min=0,
        max=300,
        detail=(
            "How far, at minimum, will AEW&C racetracks be planned "
            "to known threat zones."
        ),
    )
    tanker_threat_buffer_min_distance: int = bounded_int_option(
        "Theater tanker threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=70,
        min=0,
        max=300,
        detail=(
            "How far, at minimum, will theater tanker racetracks be "
            "planned to known threat zones."
        ),
    )
    max_mission_range_planes: int = bounded_int_option(
        "Auto-planner maximum mission range for airplanes (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=150,
        min=150,
        max=1000,
        detail=(
            "The maximum mission distance that's used by the auto-planner for airplanes. "
            "This setting won't take effect when a larger "
            "range is defined in the airplane's yaml specification."
        ),
    )
    max_mission_range_helicopters: int = bounded_int_option(
        "Auto-planner maximum mission range for helicopters (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=100,
        min=50,
        max=1000,
        detail=(
            "The maximum mission distance that's used by the auto-planner for helicopters. "
            "This setting won't take effect when a larger "
            "range is defined in the helicopter's yaml specification."
        ),
    )

    # Campaign management
    # General
    squadron_random_chance: int = bounded_int_option(
        "Percentage of randomly selected aircraft types (only for generated squadrons)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=50,
        min=0,
        max=100,
        detail=(
            "Aircraft type selection is governed by the campaign and the squadron definitions available to "
            "Retribution. Squadrons are generated by Retribution if the faction does not have access to the campaign "
            "designer's squadron/aircraft definitions. Use the above to increase/decrease aircraft variety by making "
            "some selections random instead of picking aircraft types from a priority list."
        ),
    )
    restrict_weapons_by_date: bool = boolean_option(
        "Restrict weapons by date (WIP)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Restricts weapon availability based on the campaign date. Data is "
            "extremely incomplete so does not affect all weapons."
        ),
    )
    restrict_props_by_date: bool = boolean_option(
        "Restrict aircraft options by date (WIP)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Restricts era-defining aircraft mission options (e.g. the JHMCS helmet "
            "cueing selection) based on the campaign date: gated options are hidden "
            "from the payload editor and clamped to a period-correct value at "
            "mission generation. Independent of the weapons restriction so either "
            "can be enforced alone. Data is curated per airframe and incomplete."
        ),
    )
    motorpool_enabled: bool = boolean_option(
        "Spawn strikeable motorpool reserves",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "Render each control point's not-yet-deployed reserve armor as a "
            "strikeable motorpool (only where the campaign authored one). "
            "Destroying reserves forces the owner to repurchase."
        ),
    )
    motorpool_spawn_cap: int = bounded_int_option(
        "Maximum motorpool vehicles per turn",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=10,
        min=0,
        max=25,
        detail=(
            "Caps how many reserve vehicles a control point renders across its "
            "motorpool(s) per turn. Lower this if motorpools hurt mission "
            "performance."
        ),
    )
    apply_target_overrides_to_loadouts: bool = boolean_option(
        "Apply target-based weapon settings to player loadouts",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "When enabled, applies target-specific weapon settings from weapon "
            "configurations to player-controlled aircraft. AI aircraft always receive "
            "target-based settings. This includes settings for degraded loadouts."
        ),
    )
    prefer_squadrons_with_matching_primary_task: bool = boolean_option(
        "Prefer squadrons with matching primary task when planning missions",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "If checked, squadrons with a primary task matching the mission will be "
            "preferred even if there is a closer squadron capable of the mission as a "
            "secondary task. Expect longer flights, but squadrons will be more often "
            "assigned to their primary task."
        ),
    )
    cloud_preset_pack: CloudPresetPack = choices_option(
        "Custom cloud preset pack",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=CloudPresetPack.NONE,
        choices={v.value: v for v in CloudPresetPack},
        detail=(
            "Make a community cloud-preset weather mod's presets available to the "
            "mission generator. Pick the pack you have installed in DCS. Only one can "
            "be active at a time, since the packs reuse the same preset keys for "
            "different clouds. 'None' uses the stock DCS presets."
        ),
    )
    atmosx_live_weather: bool = boolean_option(
        "Use ATMOS-X live weather",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Replace the generated weather with a real METAR observation, fetched by "
            "the ATMOS-X CLI for a station on this terrain. If the observation cannot "
            "be fetched -- no ATMOS-X, no network, nothing reported for that station "
            "-- the mission keeps the "
            "weather Retribution generated and says so in the log."
        ),
        visible_when=_atmosx_pack_selected,
    )
    atmosx_cli_path: str = text_option(
        "ATMOS-X CLI path",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default="",
        placeholder="Detected automatically",
        detail=(
            "Full path to atmosx-cli.exe. Leave blank to find it from the ATMOS-X "
            "installation registered with Windows; set it only if ATMOS-X was not "
            "installed by its installer or lives somewhere unusual."
        ),
        visible_when=_atmosx_pack_selected,
    )
    atmosx_metar_station: str = text_option(
        "ATMOS-X METAR station (ICAO)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default="",
        placeholder="Nearest to your base",
        detail=(
            "Which station to read the weather from, e.g. LCLK. Leave blank and the "
            "station is chosen from the airfields ATMOS-X knows on this terrain: the "
            "one you are flying from if it reports, otherwise the closest that does."
        ),
        visible_when=_atmosx_pack_selected,
    )

    # Pilots and Squadrons
    ai_pilot_levelling: bool = boolean_option(
        "Allow AI pilot leveling",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail=(
            "Set whether or not AI pilots will level up after completing 4 sorties."
            " Since pilot level affects the AI skill, you may wish to disable this,"
            " lest you face an Ace! This is disabled if Live Pilots is active, since"
            " it uses a different xp-based leveling system."
        ),
        enabled_when=lambda s: not s.live_pilots_enabled,
    )
    #: Feature flag for squadron limits.
    enable_squadron_pilot_limits: bool = boolean_option(
        "Enable per-squadron pilot limits",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail=(
            "If set, squadrons will be limited to a maximum number of pilots and dead "
            "pilots will replenish at a fixed rate, each defined with the settings "
            "below. Auto-purchase may buy aircraft for which there are no pilots"
            "available, so this feature is still a work-in-progress."
        ),
    )
    #: The maximum number of pilots a squadron can have at one time. Changing this after
    #: the campaign has started will have no immediate effect; pilots already in the
    #: squadron will not be removed if the limit is lowered and pilots will not be
    #: immediately created if the limit is raised.
    squadron_pilot_limit: int = bounded_int_option(
        "Maximum number of pilots per squadron",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=16,
        min=6,
        max=72,
        detail=(
            "Sets the maximum number of pilots a squadron may have active. "
            "Changing this value will not have an immediate effect, but will alter "
            "replenishment for future turns."
        ),
    )
    #: The number of pilots a squadron can replace per turn.
    squadron_replenishment_rate: int = bounded_int_option(
        "Squadron pilot replenishment rate",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=4,
        min=1,
        max=20,
        detail=(
            "Sets the maximum number of pilots that will be recruited to each squadron "
            "at the end of each turn. Squadrons will not recruit new pilots beyond the "
            "pilot limit, but each squadron with room for more pilots will recruit "
            "this many pilots each turn up to the limit."
        ),
    )
    ignore_parking_limits: bool = boolean_option(
        "Ignore parking space at airbases",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=False,
        detail=(
            "Airbases hold as many aircraft as you can pay for, whatever their ramp "
            "size. Carriers and FOBs are unaffected."
        ),
    )
    # Feature flag for squadron limits.
    enable_squadron_aircraft_limits: bool = boolean_option(
        "Enable per-squadron aircraft limits",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=False,
        detail=(
            "If set, squadrons will not be able to buy more aircraft than the configured maximum."
        ),
    )

    # HQ Automation
    automate_runway_repair: bool = boolean_option(
        "Automate runway repairs",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    automate_front_line_reinforcements: bool = boolean_option(
        "Automate front-line purchases",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    weighted_ground_procurement: bool = boolean_option(
        "AI buys its better ground units more often",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
        detail=(
            "The AI picks a ground unit uniformly at random from everything of the "
            "right class it can afford, so a faction fielding both a modern MBT and a "
            "gun truck buys as many of one as the other. With this enabled the roll is "
            "weighted by price, which is the only capability measure the model has. It "
            "is a weighting and not a maximum, so cheap units still appear."
        ),
    )
    automate_ground_object_repairs: bool = boolean_option(
        "Automate ground object repairs",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
        detail=(
            "If enabled, AI can spend budget to repair destroyed ground object units "
            "such as SAMs and EWRs. The gear tunes what it repairs first."
        ),
        opens_section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
    )
    ground_object_repair_turns: int = bounded_int_option(
        "Ground object repair turns",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=10,
        default=2,
        detail=(
            "Turns required for repaired ground object units to return to service. "
            "Set to 0 for instant repairs."
        ),
    )
    automate_building_repairs: bool = boolean_option(
        "Automate building repairs",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
        detail=(
            "If enabled, AI can spend budget to repair destroyed income buildings "
            "such as depots and factories. The gear tunes what it repairs first."
        ),
        opens_section=BUILDING_REPAIR_TUNING_SECTION,
    )
    building_repair_budget_percent: int = bounded_int_option(
        "Building repair budget (%)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=100,
        default=15,
        detail=(
            "Percent of the procurement budget that may be spent repairing buildings."
        ),
        enabled_when=lambda s: s.automate_building_repairs,
    )
    building_repair_turns: int = bounded_int_option(
        "Building repair turns",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=10,
        default=4,
        detail=(
            "Turns required for repaired buildings to return to service. "
            "Set to 0 for instant repairs. Applies to your own repairs as well, so it "
            "stands whether or not the AI is doing them."
        ),
    )
    automate_aircraft_reinforcements: bool = boolean_option(
        "Automate aircraft purchases",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    auto_ato_behavior: AutoAtoBehavior = choices_option(
        "Automatic package planning behavior",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=AutoAtoBehavior.Default,
        choices={v.value: v for v in AutoAtoBehavior},
        detail=(
            "Aircraft auto-purchase is directed by the auto-planner, so disabling "
            "auto-planning disables auto-purchase."
        ),
    )
    auto_ato_behavior_awacs: bool = boolean_option(
        "Automatic AWACS package planning",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    auto_ato_behavior_tankers: bool = boolean_option(
        "Automatic Theater tanker package planning",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    auto_ato_player_missions_asap: bool = boolean_option(
        "Automatically generated packages with players are scheduled ASAP",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    automate_front_line_stance: bool = boolean_option(
        "Automatically manage front line stances",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    auto_procurement_balance: int = bounded_int_option(
        "AI ground unit procurement budget ratio (%) for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=100,
        default=50,
        detail=(
            "Ratio (larger number -> more budget for ground units) "
            "that indicates how the AI procurement planner should "
            "spend its budget."
        ),
    )
    frontline_reserves_factor: int = bounded_int_option(
        "AI ground unit front-line reserves factor (%) for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=130,
        detail=(
            "Factor to be multiplied with the control point's unit count limit "
            "to calculate the procurement target for reserve troops at front-lines."
        ),
    )
    reserves_procurement_target: int = bounded_int_option(
        "AI ground unit reserves procurement target for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=10,
        detail=(
            "The number of units that will be bought as reserves for applicable control points."
        ),
    )
    auto_procurement_balance_red: int = bounded_int_option(
        "AI ground unit procurement budget ratio (%) for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=100,
        default=50,
        detail=(
            "Ratio (larger number -> more budget for ground units) "
            "that indicates how the AI procurement planner should "
            "spend its budget."
        ),
    )
    frontline_reserves_factor_red: int = bounded_int_option(
        "AI ground unit front-line reserves factor (%) for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=130,
        detail=(
            "Factor to be multiplied with the control point's unit count limit "
            "to calculate the procurement target for reserve troops at front-lines."
        ),
    )
    reserves_procurement_target_red: int = bounded_int_option(
        "AI ground unit reserves procurement target for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=10,
        detail=(
            "The number of units that will be bought as reserves for applicable control points."
        ),
    )

    building_repair_income_multiplier: float = bounded_float_option(
        "Building repair income multiplier",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=20,
        divisor=10,
        default=4.0,
        detail=("Multiplier applied to building income to compute repair cost."),
    )
    building_repair_ammo_bonus: float = bounded_float_option(
        "Building repair ammo bonus",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=50,
        divisor=5,
        default=10.0,
        detail=("Added cost for ammo depots to reflect frontline value."),
    )
    building_repair_factory_bonus: float = bounded_float_option(
        "Building repair factory bonus",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=50,
        divisor=10,
        default=12.0,
        detail=("Added cost for factories to reflect production value."),
    )
    building_repair_weight_remote: float = bounded_float_option(
        "Building repair weight: remote",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.2,
        detail=(
            "Weight for remoteness from enemy control points in repair priority. "
            + "Buildings farther from enemy control points will be prioritized for repair."
        ),
    )
    building_repair_weight_income: float = bounded_float_option(
        "Building repair weight: income",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.0,
        detail=(
            "Weight for building income in repair priority. "
            + "Buildings that generate more income will be prioritized for repair."
        ),
    )
    building_repair_weight_ammo_frontline: float = bounded_float_option(
        "Building repair weight: ammo frontline",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=BUILDING_REPAIR_TUNING_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.1,
        detail=(
            "Weight for frontline proximity when prioritizing ammo depots. "
            + "Ammo depots closer to the frontline will be prioritized for repair."
        ),
    )
    # Flight Planner Automation
    #: The weight used for 2-ships.
    fpa_2ship_weight: int = bounded_int_option(
        "2-ship weight factor (WF2)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=50,
        min=0,
        max=100,
        detail=(
            "Used as a distribution to randomize 2/3/4-ships for BARCAP, CAS, OCA & ANTI-SHIP flights. "
            "The weight W_i is calculated according to the following formula: &#10;&#13;"
            "W_i = WF_i / (WF2 + WF3 + WF4)"
        ),
    )
    #: The weight used for 3-ships.
    fpa_3ship_weight: int = bounded_int_option(
        "3-ship weight factor (WF3)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=35,
        min=0,
        max=100,
        detail="See 2-ship weight factor (WF3)",
    )
    fpa_4ship_weight: int = bounded_int_option(
        "4-ship weight factor (WF4)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=15,
        min=0,
        max=100,
        detail="See 2-ship weight factor (WF4)",
    )
    primary_task_distance_factor: int = bounded_int_option(
        "Primary task distance weight (NM)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=75,
        min=10,
        max=250,
        detail="A larger number will force the auto-planner to stick with squadrons that have a matching primary task."
        " A smaller number will ignore squadrons with a matching primary task that are too far out.",
    )

    # Repairs, formerly the "Campaign Management+" page
    sam_repair_budget_fraction: float = bounded_float_option(
        "SAM repair budget fraction",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=1.0,
        divisor=100,
        default=0.4,
        detail=("Fraction of ground unit budget reserved for SAM repairs."),
    )
    sam_repair_priority_threshold: float = bounded_float_option(
        "SAM repair priority threshold",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=1.5,
        detail=("Minimum priority score required to queue SAM repairs."),
    )
    sam_repair_weight_threat: float = bounded_float_option(
        "SAM repair weight: threat range",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=0.5,
        detail="Weight applied to SAM threat range coverage.",
    )
    sam_repair_weight_frontline: float = bounded_float_option(
        "SAM repair weight: frontline",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=1.5,
        detail="Weight applied to proximity to the front line.",
    )
    sam_repair_weight_cp_coverage: float = bounded_float_option(
        "SAM repair weight: CP coverage",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=0.6,
        detail="Weight applied to covered control points.",
    )
    sam_repair_weight_tgo_coverage: float = bounded_float_option(
        "SAM repair weight: TGO coverage",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=0.4,
        detail="Weight applied to covered ground objects.",
    )
    sam_repair_weight_tgo_income: float = bounded_float_option(
        "SAM repair weight: TGO income",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GROUND_OBJECT_REPAIR_TUNING_SECTION,
        min=0.0,
        max=5.0,
        divisor=10,
        default=0.4,
        detail="Weight applied to covered ground object income.",
    )
    # Mission Generator
    # Gameplay
    supercarrier: bool = boolean_option(
        "Use supercarrier module",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
    )
    supercarrier_deck_crew: bool = boolean_option(
        "Use supercarrier deck-crew",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    generate_portable_tacans: bool = boolean_option(
        "Place portable TACAN beacons at blue airfields",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Automatically places a portable TACAN beacon at blue-captured "
            "airfields that don't already have a built-in TACAN from the "
            "terrain data. An unused X-band channel is assigned to each."
        ),
    )
    generate_marks: bool = boolean_option(
        "Put objective markers on the map",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    eplrs_enabled: bool = boolean_option(
        "Enable EPLRS",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "The Enhanced Position Location Reporting System: DCS's datalink. Switched"
            " on, a group shares what it sees with the rest of its coalition, so an"
            " aircraft gets the datalink picture on its displays (the Hornet's SA"
            " page, the Viper's MFD, the A-10C's TAD) and ground units cue each other."
            " Switched off, every group fights on its own sensors alone."
        ),
    )
    generate_dark_kneeboard: bool = boolean_option(
        "Generate dark kneeboard",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Dark kneeboard for night missions. This will likely make the kneeboard on "
            "the pilot leg unreadable."
        ),
    )
    # Mission Start
    never_delay_player_flights: bool = boolean_option(
        "Player flights ignore TOT and spawn immediately",
        MISSION_GENERATOR_PAGE,
        MISSION_START_SECTION,
        default=True,
        detail=(
            "Does not adjust package waypoint times. Should not be used if players "
            "have runway or in-air starts."
        ),
        tooltip=(
            "Always spawns player aircraft immediately, even if their start time is "
            "more than 10 minutes after the start of the mission. <strong>This does "
            "not alter the timing of your mission. Your TOT will not change. This "
            "option only allows the player to wait on the ground.</strong>"
        ),
    )
    default_start_type: StartType = choices_option(
        "Default start type for AI aircraft",
        page=MISSION_GENERATOR_PAGE,
        section=MISSION_START_SECTION,
        choices={v.value: v for v in StartType},
        default=StartType.COLD,
        detail=(
            "Warning: Options other than Cold will significantly reduce the number of "
            "targets available for OCA/Aircraft missions, and OCA/Aircraft flights "
            "will not be included in automatically planned OCA packages."
        ),
    )
    default_start_type_client: StartType = choices_option(
        "Default start type for Player flights",
        page=MISSION_GENERATOR_PAGE,
        section=MISSION_START_SECTION,
        choices={v.value: v for v in StartType},
        default=StartType.COLD,
        detail="Default start type for flights containing Player/Client slots.",
    )
    nevatim_parking_fix: bool = boolean_option(
        "Force air-starts for aircraft at Nevatim and Ramon Airbase inoperable parking slots",
        page=MISSION_GENERATOR_PAGE,
        section=MISSION_START_SECTION,
        default=False,  # TODO: set to False or remove this when DCS is fixed
        detail=(
            "Air-starts forced for all aircraft at Nevatim and Ramon Airbase except parking slots "
            "which are known to work as of DCS World 2.9.4.53990."
        ),
    )
    player_flights_sixpack: bool = boolean_option(
        "Player flights can spawn on the sixpack",
        MISSION_GENERATOR_PAGE,
        MISSION_START_SECTION,
        default=True,
    )
    # AI
    limit_ai_radios: bool = boolean_option(
        "Limit AI radio callouts",
        page=MISSION_GENERATOR_PAGE,
        section=AI_BEHAVIOUR_SECTION,
        default=True,
        detail="Avoids the target-detection callouts over the radio by AI. (except for AWACS flights)",
    )
    silence_ai_radios: bool = boolean_option(
        "Suppress AI radio callouts",
        page=MISSION_GENERATOR_PAGE,
        section=AI_BEHAVIOUR_SECTION,
        default=False,
        detail="Keeps the AI silent at all times for flights with human pilots. (except for AWACS flights)",
    )
    use_ai_combat_landing: bool = boolean_option(
        "Use AI combat landing waypoint task",
        page=MISSION_GENERATOR_PAGE,
        section=AI_BEHAVIOUR_SECTION,
        default=False,
        detail="Turns the combat landing flag on in the landing waypoint task.",
    )
    ground_start_ai_planes: bool = boolean_option(
        "AI fixed-wing aircraft can use roadbases / bases with only ground spawns",
        MISSION_GENERATOR_PAGE,
        AI_BEHAVIOUR_SECTION,
        default=False,
        detail=(
            "If enabled, AI can use roadbases or airbases which only have ground spawns. "
            "AI will always air-start from these bases (due to DCS limitation)."
        ),
    )
    ai_unlimited_fuel: bool = boolean_option(
        "AI flights have unlimited fuel",
        MISSION_GENERATOR_PAGE,
        AI_BEHAVIOUR_SECTION,
        default=True,
        detail=(
            "AI aircraft have unlimited fuel applied at start, removed at join/racetrack start,"
            " and reapplied at split/racetrack end for applicable flights. "
        ),
    )
    # Kneeboard
    generate_target_recon_kneeboard: bool = boolean_option(
        "Generate target recon kneeboard pages",
        MISSION_GENERATOR_PAGE,
        KNEEBOARD_SECTION,
        default=True,
        detail=(
            "Generate a target reconnaissance page for player flights with air-to-ground "
            "tasks, showing aimpoints, threat rings, and target area context."
        ),
    )
    generate_all_packages_kneeboard: bool = boolean_option(
        "Generate friendly packages kneeboard page",
        MISSION_GENERATOR_PAGE,
        KNEEBOARD_SECTION,
        default=True,
        detail=(
            "Append page(s) listing every friendly package with its TOT (strike "
            "tasks) or patrol window (CAP, tanker, AWACS), for cross-package "
            "coordination."
        ),
    )
    target_recon_extra_threat_search_nmi: int = bounded_int_option(
        "Extra threat search radius (nmi)",
        MISSION_GENERATOR_PAGE,
        KNEEBOARD_SECTION,
        default=0,
        min=0,
        max=50,
        detail=(
            "Additional nautical miles beyond the default search radius to include "
            "threats on the target recon kneeboard. 0 uses the default radius only."
        ),
    )
    untasked_opfor_client_slots: bool = boolean_option(
        "Convert untasked OPFOR aircraft into client slots",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Warning: Enabling this will significantly reduce the number of "
            "targets available for OCA/Aircraft missions."
        ),
    )
    default_player_laser_code: DefaultPlayerLaserCode = choices_option(
        "Default laser code for Player flights",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        choices={v.value: v for v in DefaultPlayerLaserCode},
        default=DefaultPlayerLaserCode.ALLOCATE_OWN,
        detail=(
            "Allocate own gives every newly-created player flight a unique TGP/"
            "weapon laser code. Default (1688) leaves the code unset so bombs "
            "and the cockpit TGP fall back to 1688. Affects newly-created "
            "flights only; existing flights are unchanged."
        ),
    )
    switch_baro_fix: bool = boolean_option(
        "Switch altitude type of waypoints to AMSL above seas for helicopters",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=True,  # TODO: set to False or remove this when DCS is fixed?
        detail=(
            "AGL seems to reference the bottom of the sea which causes issues for helicopters"
            " trying to fly at altitudes lower than the sea-bottom."
        ),
    )
    # Mission specific
    desired_player_mission_duration: timedelta = minutes_option(
        "Desired mission duration",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
    )
    game_masters_count: int = bounded_int_option(
        "Number of game masters",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=1,
        min=0,
        max=10,
        detail=(
            "The number of game master slots to generate for each side. "
            "Game masters can see, control & direct all units in the mission."
        ),
    )
    tactical_commander_count: int = bounded_int_option(
        "Number of tactical commands",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=3,
        min=0,
        max=10,
        detail=(
            "The number of tactical commander slots to generate for each side. "
            "Tactical commanders can control & direct friendly units."
        ),
    )
    use_jtac: bool = boolean_option(
        "Use JTAC if the faction has one defined",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Spawns the faction's JTAC aircraft on each front line. Off, no JTAC is "
            "generated even for a faction that defines one. Separate from the number "
            "of JTAC controller slots below, which are Combined Arms seats."
        ),
    )
    jtac_count: int = bounded_int_option(
        "Number of JTAC controllers",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=3,
        min=0,
        max=10,
        detail=(
            "The number of JTAC controller slots to generate for each side. "
            "JTAC operators can only control friendly units."
        ),
    )
    observer_count: int = bounded_int_option(
        "Number of observers",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=0,
        min=0,
        max=10,
        detail=(
            "The number of observers slots to generate for each side. "
            'Use this to allow spectators when disabling "Allow external views".'
        ),
    )
    dynamic_slots: bool = boolean_option(
        "Dynamic slots",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Enables dynamic slots. Please note that losses from dynamic slots won't be registered."
        ),
    )
    dynamic_slots_hot: bool = boolean_option(
        "Allow dynamic slot hot start",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=("Enables hot start for dynamic slots."),
    )
    dynamic_cargo: bool = boolean_option(
        "Dynamic cargo",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=("Enables dynamic cargo for airfields, ships, FARPs & warehouses."),
    )
    use_auto_fog: bool = boolean_option(
        "Use DCS' automatic fog setting",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Hands the fog to DCS, which builds it from the weather it is given --"
            " temperature, dew point and pressure -- so it thickens in the cold and"
            " the damp and lifts as the day warms. Switched off, the mission carries"
            " the flat visibility and fog thickness Retribution wrote into it, which"
            " does not change while you fly."
        ),
    )
    # Performance
    perf_smoke_gen: bool = boolean_option(
        "Smoke visual effect on the front line",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_smoke_spacing: int = bounded_int_option(
        "Smoke generator spacing (higher means less smoke)",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=1600,
        min=800,
        max=24000,
    )
    perf_red_alert_state: bool = boolean_option(
        "Air defenses start in red alert mode",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
        tooltip=(
            "Applies to SAM, AAA and other air-defense sites. Turning it off makes "
            "them spawn on green alert, which costs less CPU but leaves them passive "
            "until they are shot at. Front-line ground units and EWRs are not "
            "affected: they always come up on red alert."
        ),
    )
    coastal_batteries_engage_ships: bool = boolean_option(
        "Coastal batteries engage ships",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
        detail=(
            "Let coastal anti-ship batteries fire on their own at enemy hulls that "
            "enter range, the way fleets do. Off by default: a battery from a unit "
            "mod firing anti-ship missiles has been seen to crash DCS, so try it on "
            "a throwaway mission before using it in a campaign."
        ),
    )
    perf_artillery: bool = boolean_option(
        "Artillery strikes",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    generate_fire_tasks_for_missile_sites: bool = boolean_option(
        "Generate fire tasks for missile sites",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        detail=(
            "If enabled, missile sites like V2s and Scuds will fire on random targets "
            "at the start of the mission."
        ),
        default=True,
    )
    perf_moving_units: bool = boolean_option(
        "Moving ground units",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    convoys_travel_full_distance: bool = boolean_option(
        "Convoys drive the full distance between control points",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_disable_convoys: bool = boolean_option(
        "Disable convoys",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_disable_cargo_ships: bool = boolean_option(
        "Disable shipping-convoys",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_frontline_units_prefer_roads: bool = boolean_option(
        "Front line troops prefer roads",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_frontline_units_max_supply: int = bounded_int_option(
        "Maximum ground units deployed per frontline by faction",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=60,
        min=10,
        max=300,
        causes_expensive_game_update=True,
    )
    max_frontline_width: int = bounded_int_option(
        "Maximum frontline width (km)",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=80,
        min=1,
        max=100,
    )
    perf_infantry: bool = boolean_option(
        "Generate infantry squads alongside vehicles",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_destroyed_units: bool = boolean_option(
        "Generate carcasses for units destroyed in previous turns",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_disable_untasked_blufor_aircraft: bool = boolean_option(
        "Disable untasked OWNFOR aircraft at airfields",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_disable_untasked_opfor_aircraft: bool = boolean_option(
        "Disable untasked OPFOR aircraft at airfields",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    # Performance culling
    perf_culling: bool = boolean_option(
        "Culling of distant units enabled",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_culling_distance: int = bounded_int_option(
        "Culling distance (km)",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=100,
        min=10,
        max=10000,
        causes_expensive_game_update=True,
    )
    perf_do_not_cull_threatening_iads: bool = boolean_option(
        "Do not cull threatening IADS",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_do_not_cull_carrier: bool = boolean_option(
        "Do not cull carrier's surroundings",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
        causes_expensive_game_update=True,
    )
    ground_start_scenery_remove_triggers: bool = boolean_option(
        "Generate SCENERY REMOVE OBJECTS ZONE triggers at roadbase first waypoints",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=True,
        detail=(
            "Can be used to remove lightposts and other obstacles from roadbase runways. "
            "Might not work in DCS multiplayer."
        ),
    )
    ground_start_trucks: bool = boolean_option(
        "Spawn trucks at ground spawns in airbases instead of FARP statics",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=False,
        detail=("Might have a negative performance impact."),
    )
    ground_start_trucks_roadbase: bool = boolean_option(
        "Spawn trucks at ground spawns in roadbases instead of FARP statics",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=False,
        detail=("Might have a negative performance impact."),
    )
    ground_start_ground_power_trucks: bool = boolean_option(
        "Spawn ground power trucks at ground starts in airbases",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=True,
        detail=(
            "Needed to cold-start some aircraft types. Might have a performance impact."
        ),
    )
    ground_start_ground_power_trucks_roadbase: bool = boolean_option(
        "Spawn ground power trucks at ground starts in roadbases",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=True,
        detail=(
            "Needed to cold-start some aircraft types. Might have a performance impact."
        ),
    )
    ground_start_airbase_statics_farps_remove: bool = boolean_option(
        "Remove ground spawn statics, including invisible FARPs, at airbases",
        MISSION_GENERATOR_PAGE,
        PERFORMANCE_SECTION,
        default=True,
        detail=(
            "Ammo and fuel statics and invisible FARPs should be unnecessary when creating "
            "additional spawns for players at airbases. This setting will disable them and "
            "potentially grant a marginal performance benefit."
        ),
    )
    perf_ai_despawn_airstarted: bool = boolean_option(
        "De-spawn AI in the air upon RTB",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
        detail=(
            "If enabled, AI flights will de-spawn over their base "
            "if the start-up type was manually changed to 'In-Flight'."
        ),
    )
    live_pilots_enabled: bool = boolean_option(
        "Enable Live Pilots",
        page=LIVE_PILOTS_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Pilots hold a rank, have morale, friendship and other features, and"
            " pilot names are shown in-game."
        ),
    )
    live_pilots_debrief_enemy: bool = boolean_option(
        "Report enemy aircrew in the debriefing",
        page=LIVE_PILOTS_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Show OPFOR dead, wounded, promotions and morale. Their aircraft and"
            " ground losses are always reported; this is only about their aircrew,"
            " which you would have no way of knowing about."
        ),
    )
    live_pilots_rank_names: str = choices_option(
        "Rank names",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="country",
        choices={
            "Use faction country ranks": "country",
            "Use generic ranks": "generic",
            "Use skill names": "skill",
            "Custom names (define below)": "custom",
        },
        detail=("Mapping of the internal skill level to real world like ranks."),
    )
    live_pilots_rank_cadet_short: str = text_option(
        "Cadet",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="2ndLt",
        max_length=5,
    )
    live_pilots_rank_cadet_full: str = text_option(
        "Cadet",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Second Lieutenant",
    )
    live_pilots_rank_average_short: str = text_option(
        "Average",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="1stLt",
        max_length=5,
    )
    live_pilots_rank_average_full: str = text_option(
        "Average",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="First Lieutenant",
    )
    live_pilots_rank_average_xp: int = bounded_int_option(
        "Average",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default=1000,
        min=0,
        max=1000000,
    )
    live_pilots_rank_good_short: str = text_option(
        "Good",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Capt",
        max_length=5,
    )
    live_pilots_rank_good_full: str = text_option(
        "Good",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Captain",
    )
    live_pilots_rank_good_xp: int = bounded_int_option(
        "Good",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default=2000,
        min=0,
        max=1000000,
    )
    live_pilots_rank_high_short: str = text_option(
        "High",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Maj",
        max_length=5,
    )
    live_pilots_rank_high_full: str = text_option(
        "High",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Major",
    )
    live_pilots_rank_high_xp: int = bounded_int_option(
        "High",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default=4000,
        min=0,
        max=1000000,
    )
    live_pilots_rank_excellent_short: str = text_option(
        "Excellent",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="LtCol",
        max_length=5,
    )
    live_pilots_rank_excellent_full: str = text_option(
        "Excellent",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default="Lieutenant Colonel",
    )
    live_pilots_rank_excellent_xp: int = bounded_int_option(
        "Excellent",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_RANKS_SECTION,
        default=8000,
        min=0,
        max=1000000,
    )
    live_pilots_rank_survival: bool = boolean_option(
        "Rank influences who survives a loss",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=True,
        detail=("Base chance of the pilot surviving a crash or being shot down."),
    )
    live_pilots_survival_cadet: int = bounded_int_option(
        "Cadet (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=20,
        min=0,
        max=100,
    )
    live_pilots_survival_average: int = bounded_int_option(
        "Average (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=35,
        min=0,
        max=100,
    )
    live_pilots_survival_good: int = bounded_int_option(
        "Good (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=50,
        min=0,
        max=100,
    )
    live_pilots_survival_high: int = bounded_int_option(
        "High (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=65,
        min=0,
        max=100,
    )
    live_pilots_survival_excellent: int = bounded_int_option(
        "Excellent (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=80,
        min=0,
        max=100,
    )
    morale_enabled: bool = boolean_option(
        "Enable morale",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        default=True,
        detail=(
            "Morale decides how steady the flight is under fire, how well they fly and"
            " whether a man asks for leave -- or stops turning up at all. It can also"
            " influence wound curing times."
        ),
    )
    morale_state_triumphant: int = bounded_int_option(
        "Triumphant",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_STATES_SECTION,
        default=85,
        min=0,
        max=100,
    )
    morale_state_confident: int = bounded_int_option(
        "Confident",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_STATES_SECTION,
        default=60,
        min=0,
        max=100,
    )
    morale_state_normal: int = bounded_int_option(
        "Normal",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_STATES_SECTION,
        default=40,
        min=0,
        max=100,
    )
    morale_state_shaken: int = bounded_int_option(
        "Shaken",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_STATES_SECTION,
        default=15,
        min=0,
        max=100,
    )
    morale_state_shattered: int = bounded_int_option(
        "Shattered",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_STATES_SECTION,
        default=1,
        min=0,
        max=100,
    )
    morale_drift_per_turn: int = bounded_int_option(
        "Settling back towards Normal each turn",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=5,
        min=0,
        max=25,
        detail=(
            "How far a pilot moves back towards Normal in a quiet turn, from either "
            "side and never past it. Zero makes a turn's damage permanent until "
            "something else moves him."
        ),
    )
    morale_lost_aircraft: int = bounded_int_option(
        "Lost his aircraft",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-10,
        min=-50,
        max=0,
        detail="He came home without it.",
    )
    morale_achieved_nothing: int = bounded_int_option(
        "Came home empty",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-5,
        min=-50,
        max=0,
        detail=(
            "Flew a strike, a CAS or a SEAD and destroyed nothing at all. A CAP that"
            " saw no one does not count."
        ),
    )
    morale_squadron_death: int = bounded_int_option(
        "A squadron mate killed",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-15,
        min=-50,
        max=0,
        detail=(
            "Applied to everyone else in his squadron and friends from other"
            " squadrons, once per man lost."
        ),
    )
    morale_flight_death: int = bounded_int_option(
        "Wingman killed (extra, his flight only)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-5,
        min=-50,
        max=0,
        detail=(
            "On top of the squadron's loss, for the men who were in the same flight."
        ),
    )
    morale_squadron_wound: int = bounded_int_option(
        "Squadron mate wounded (per turn out)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-2,
        min=-50,
        max=0,
        detail="Counted once per turn the medics keep him.",
    )
    morale_flight_wound: int = bounded_int_option(
        "Wingman wounded (extra, his flight only)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-1,
        min=-50,
        max=0,
        detail="As above, again, for the men who were up there with him.",
    )
    morale_squadron_recovered: int = bounded_int_option(
        "Squadron mate back from hospital",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=4,
        min=0,
        max=50,
        detail=(
            "Once, when the medics let him go. Smaller than what the wound cost them,"
            " so a man being hurt is never worth it on balance."
        ),
    )
    morale_base_lost: int = bounded_int_option(
        "Base lost",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-10,
        min=-50,
        max=0,
        detail="Any base of the coalition changing hands.",
    )
    morale_no_leave: int = bounded_int_option(
        "Each turn overdue leave",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-3,
        min=-50,
        max=0,
        detail="From the sixth turn without leave.",
    )
    morale_leave_refused: int = bounded_int_option(
        "Leave refused",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-10,
        min=-50,
        max=0,
        detail=("He asked, and was told no."),
    )
    morale_leave_cancelled: int = bounded_int_option(
        "Leave cut short",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=-4,
        min=-50,
        max=0,
        detail=(
            "What it costs a pilot to be called back before his leave is up. Worse"
            " than never being granted it: he had it in his hand."
        ),
    )
    morale_air_kill: int = bounded_int_option(
        "Shot one down",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=15,
        min=0,
        max=50,
        detail=("Per enemy aircraft."),
    )
    morale_unplanned_kill: int = bounded_int_option(
        "Target of opportunity",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=5,
        min=0,
        max=50,
        detail=("Per thing destroyed that was not what his package was sent for."),
    )
    morale_mission_complete: int = bounded_int_option(
        "Flew the mission",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=10,
        min=0,
        max=50,
        detail=("He went, and he brought the aircraft home."),
    )
    morale_promoted: int = bounded_int_option(
        "Promoted",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=25,
        min=0,
        max=50,
    )
    morale_on_leave: int = bounded_int_option(
        "Each turn of leave",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=15,
        min=0,
        max=50,
    )
    morale_leave_request_chance: int = bounded_int_option(
        "Base chance of asking for leave (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_MORALE_SECTION,
        subsection=LIVE_PILOTS_MORALE_EVENTS_SECTION,
        default=8,
        min=0,
        max=100,
        detail=(
            "Per pilot per turn at middling morale. It rises as he wears down and falls"
            " as he picks up, so a contented man asks now and then and a hollow one"
            " asks often. You answer at the end of the turn."
        ),
    )
    hardening_enabled: bool = boolean_option(
        "Enable hardening",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=True,
        detail=(
            "Requires Morale above to be enabled. Each pilot earns points for every"
            " turn he spends at Shaken morale or worse, and they never come off: morale"
            " hits land softer, he is likelier to survive losing his aircraft (or to be"
            " wounded instead of killed), and he is slower to make friends and enemies."
            " Points are not earned in hospital or on leave."
        ),
    )
    hardening_max: int = bounded_int_option(
        "Maximum value",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=40,
        min=1,
        max=50,
        detail=(
            "The most points a pilot can hold. With the default 2% reduction per point"
            " below, 50 points would take 100% off every morale hit, so it stops there."
            " Best left alone unless you change the reduction to match."
        ),
    )
    hardening_shaken: int = bounded_int_option(
        "A turn spent Shaken",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=1,
        min=0,
        max=10,
        detail="Counted on the state he started the turn in, not the one he ends it in.",
    )
    hardening_shattered: int = bounded_int_option(
        "A turn spent Shattered",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=2,
        min=0,
        max=10,
    )
    hardening_broken: int = bounded_int_option(
        "A turn spent Broken",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=3,
        min=0,
        max=10,
    )
    hardening_morale_relief_per_point: float = bounded_float_option(
        "Morale hit reduction, per point (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=2.0,
        min=0.0,
        max=5.0,
        divisor=10,
        prefix="",
        detail=(
            "A pilot with 30 points takes 30 x 2 = 60% off every morale hit: a hit of"
            " -30 becomes -12. This is on top of the reduction his rank already gives"
            " him, and a hit always costs at least 1 point."
        ),
    )
    hardening_survival_per_point: float = bounded_float_option(
        "Survival chance, per point (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=0.5,
        min=0.0,
        max=2.0,
        divisor=10,
        prefix="",
        detail=(
            "Added to both rolls made when a pilot loses his aircraft: whether he"
            " survives, and whether he is wounded instead of killed. At 0.5, a pilot"
            " with 40 points adds 20% to each."
        ),
    )
    hardening_friendship_damping_per_point: float = bounded_float_option(
        "Friendship change reduction, per point (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_HARDENING_SECTION,
        default=1.5,
        min=0.0,
        max=5.0,
        divisor=10,
        prefix="",
        detail=(
            "How much less his own opinion of other pilots moves, up and down alike."
            " At 1.5, a pilot with 40 points changes 60% slower: slower to make a"
            " friend, slower to hold a grudge. It does not change what other pilots"
            " think of him."
        ),
    )
    friendship_enabled: bool = boolean_option(
        "Enable friendship",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        default=True,
        detail=(
            "Requires Live Pilots. Each pilot holds an opinion of each other pilot,"
            " from 0 to 10, starting at 5. It is one-way: what he thinks of another"
            " pilot is not what that pilot thinks of him. It changes how much"
            " experience a mission pays him, how well his flight flies, how likely he"
            " is to be pulled out of a wreck, and how hard a death hits the men who"
            " were flying with him."
        ),
    )
    friendship_band_inseparable: float = bounded_float_option(
        "Inseparable",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=9.1,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail=(
            "The value each level starts at. A pilot's opinion of another pilot is"
            " shown as one of these words everywhere it appears. Anything below"
            " Hostile is Bad blood."
        ),
    )
    friendship_band_close: float = bounded_float_option(
        "Close",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=7.1,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_band_friendly: float = bounded_float_option(
        "Friendly",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=6.1,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_band_neutral: float = bounded_float_option(
        "Neutral",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=4.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_band_frosty: float = bounded_float_option(
        "Frosty",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=3.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_band_hostile: float = bounded_float_option(
        "Hostile",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_BANDS_SECTION,
        default=1.1,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_drift_squadron_up: int = bounded_int_option(
        "Chance of warming to a squadron mate (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=35,
        min=0,
        max=100,
        detail=(
            "Every turn, each pilot rolls once against every other pilot at his base."
            " This is the chance his opinion of a man from his own squadron goes up."
            " Whatever is left over after this and the figure below is a turn where"
            " nothing changes between them."
        ),
    )
    friendship_drift_squadron_down: int = bounded_int_option(
        "Chance of cooling towards a squadron mate (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=20,
        min=0,
        max=100,
    )
    friendship_drift_base_up: int = bounded_int_option(
        "Chance of warming to a pilot from another squadron (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=22,
        min=0,
        max=100,
        detail=(
            "Same base, different squadron: men he queues behind rather than men he"
            " flies with."
        ),
    )
    friendship_drift_base_down: int = bounded_int_option(
        "Chance of cooling towards a pilot from another squadron (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=10,
        min=0,
        max=100,
    )
    friendship_drift_step: float = bounded_float_option(
        "How much it moves when it moves",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=1.0,
        min=0.0,
        max=3.0,
        divisor=10,
        prefix="",
        detail=(
            "On the 0 to 10 scale. Only one side moves: his opinion of the other"
            " pilot, not that pilot's opinion of him, which is rolled separately."
        ),
    )
    friendship_drift_ceiling: float = bounded_float_option(
        "Highest these rolls can reach",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_DRIFT_SECTION,
        default=7.0,
        min=5.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail=(
            "Time at a base alone stops here. Anything above it has to be earned by"
            " flying together, which is what makes keeping a crew together worth"
            " something. There is no floor: these rolls alone can reach the bottom."
        ),
    )
    friendship_flew_together: float = bounded_float_option(
        "Flew in the same flight",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=2.0,
        min=0.0,
        max=5.0,
        divisor=10,
        prefix="",
        detail=(
            "Added to each pilot's opinion of every other pilot in his flight, once"
            " per mission flown."
        ),
    )
    friendship_same_package: float = bounded_float_option(
        "Flew in the same package, different flight",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=1.0,
        min=0.0,
        max=5.0,
        divisor=10,
        prefix="",
    )
    friendship_max_gain_per_turn: float = bounded_float_option(
        "Most one opinion can rise in a turn",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=4.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail="However many missions the two of them fly together that turn.",
    )
    friendship_ff_air_flight: float = bounded_float_option(
        "Shot down a friendly aircraft: taken off by his own flight",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=3.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail=(
            "Subtracted from what every other pilot in his flight thinks of him. They"
            " watched it happen."
        ),
    )
    friendship_ff_air_squadron: float = bounded_float_option(
        "Shot down a friendly aircraft: taken off by the victim's squadron",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=6.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail=(
            "Subtracted from what every pilot in the dead man's squadron thinks of"
            " him. A pilot who is in both his flight and that squadron subtracts the"
            " larger of the two figures, not both."
        ),
    )
    friendship_ff_ground: float = bounded_float_option(
        "Destroyed a friendly ground unit: taken off by his own flight",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EVENTS_SECTION,
        default=2.0,
        min=0.0,
        max=10.0,
        divisor=10,
        prefix="",
    )
    friendship_xp_per_point: float = bounded_float_option(
        "Experience multiplier addition, per point above 5",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=0.05,
        min=0.0,
        max=0.25,
        divisor=100,
        prefix="",
        decimals=2,
        detail=(
            "Average what he thinks of the other pilots in his flight, subtract 5, and"
            " multiply by this. The result is added to his experience multiplier for"
            " the mission, so a flight of men he likes pays more and a flight of men he"
            " dislikes pays less than flying alone. The multiplier never falls below 0"
            " and experience is never taken away."
        ),
    )
    friendship_survival_per_point: int = bounded_int_option(
        "Survival chance, per point above 5 (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=3,
        min=0,
        max=15,
        detail=(
            "This one reads what the other pilots in his flight think of HIM, averaged."
            " It is added to the roll for surviving the loss of his aircraft and to the"
            " roll for being wounded instead of killed. Being disliked never subtracts"
            " from either."
        ),
    )
    friendship_survival_cap: int = bounded_int_option(
        "Most those two chances can gain (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=20,
        min=0,
        max=100,
    )
    friendship_synergy_floor: float = bounded_float_option(
        "A flight flies one skill level better from",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=7.1,
        min=5.0,
        max=10.0,
        divisor=10,
        prefix="",
        detail=(
            "If the average opinion inside a flight reaches this, every pilot in it"
            " flies one DCS skill level above his rank. A whole package that reaches it"
            " does the same. Only one level either way, and it is on top of the level"
            " morale can give."
        ),
    )
    friendship_leader_spoke_weight: float = bounded_float_option(
        "The flight lead counts for",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=2.0,
        min=1.0,
        max=5.0,
        divisor=10,
        detail=(
            "When averaging what a pilot thinks of the rest of his flight, his opinion"
            " of the lead is multiplied by this. At 2, in a four-ship, the lead is half"
            " of that average. The lead himself weighs his three wingmen equally. This"
            " is why spreading veterans one to a flight beats stacking them in one."
        ),
    )
    friendship_desertion_per_point: int = bounded_int_option(
        "Desertion chance reduction, per point above 5 (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=5,
        min=0,
        max=20,
        detail=(
            "Averaged over what he thinks of his own squadron. It can only reduce the"
            " chance: a squadron he dislikes does not push him out any faster."
        ),
    )
    friendship_desertion_cap: int = bounded_int_option(
        "Most desertion can be reduced by (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=50,
        min=0,
        max=100,
    )
    friendship_leave_together_per_point: int = bounded_int_option(
        "Extra morale from leave, per point above 5 (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=8,
        min=0,
        max=25,
        detail=(
            "Averaged over the men from his own squadron who are on leave at the same"
            " time as him, and worked out again every turn: as each of them comes back,"
            " the rest lose what he was worth."
        ),
    )
    friendship_leave_together_cap: int = bounded_int_option(
        "Most leave in company can add (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=50,
        min=0,
        max=200,
    )
    friendship_drift_help_per_friend: int = bounded_int_option(
        "Morale returns to Normal faster, per friend (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=5,
        min=0,
        max=25,
        detail=(
            "A pilot below Normal recovers this much faster for each pilot in his"
            " squadron he is Close to or better. A pilot above Normal falls back this"
            " much faster for each pilot who is Hostile towards him or worse."
        ),
    )
    friendship_drift_help_cap: int = bounded_int_option(
        "Most that can change morale recovery by (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=30,
        min=0,
        max=100,
    )
    friendship_grief_per_point: float = bounded_float_option(
        "Death morale multiplier addition, per point above 5",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=0.33,
        min=0.0,
        max=1.0,
        divisor=100,
        prefix="",
        decimals=2,
        detail=(
            "A death costs morale to the pilots who were in the flight. Take what one"
            " of them thought of the dead man, subtract 5, multiply by this and add 1:"
            " that is how many times the morale hit lands on him. A pilot he disliked"
            " still counts once."
        ),
    )
    friendship_grief_cap: float = bounded_float_option(
        "Most a death can be multiplied by",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=4.0,
        min=1.0,
        max=10.0,
        divisor=10,
    )
    friendship_limit: int = bounded_int_option(
        "Opinions a pilot remembers",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_FRIENDSHIP_SECTION,
        subsection=LIVE_PILOTS_FRIENDSHIP_EFFECTS_SECTION,
        default=120,
        min=10,
        max=500,
        detail=(
            "He keeps the ones he holds most strongly and forgets the rest, so a long"
            " campaign does not end with every pilot holding an opinion of every man he"
            " ever shared a base with."
        ),
    )
    live_pilots_wounded_chance: int = bounded_int_option(
        "Wounded instead of killed (%)",
        page=LIVE_PILOTS_PAGE,
        section=LIVE_PILOTS_SURVIVAL_SECTION,
        default=35,
        min=0,
        max=100,
        detail=(
            "Base chance that a pilot who would have died is wounded instead. Wounded "
            "pilots are unavailable for 1-4 turns."
        ),
    )
    # Cheating. Not using auto settings because the same page also has buttons which do
    # not alter settings.
    enable_frontline_cheats: bool = False
    enable_base_capture_cheat: bool = False
    enable_transfer_cheat: bool = False
    enable_runway_state_cheat: bool = False
    enable_air_wing_adjustments: bool = False
    enable_enemy_buy_sell: bool = False

    # LUA Plugins system
    plugins: Dict[str, bool] = field(default_factory=dict)

    only_player_takeoff: bool = True  # Legacy parameter do not use

    @staticmethod
    def plugin_settings_key(identifier: str) -> str:
        return f"{identifier}"

    def initialize_plugin_option(self, identifier: str, default_value: Any) -> None:
        try:
            self.plugin_option(identifier)
        except KeyError:
            self.set_plugin_option(identifier, default_value)

    def plugin_option(self, identifier: str) -> Any:
        return self.plugins[self.plugin_settings_key(identifier)]

    def plugin_option_or(self, identifier: str, default: Any = None) -> Any:
        """The option's value, or ``default`` if this settings object never got it.

        Settings that used to be their own fields are read through here, so the
        defensive ``getattr(settings, name, False)`` they were written with keeps
        working for a save loaded before the plugin manager filled its defaults.
        """
        try:
            return self.plugins[self.plugin_settings_key(identifier)]
        except KeyError:
            return default

    def set_plugin_option(self, identifier: str, value: Any) -> None:
        self.plugins[self.plugin_settings_key(identifier)] = value

    def __setstate__(self, state: dict[str, Any]) -> None:
        # __setstate__ is called with the dict of the object being unpickled. We
        # can provide save compatibility for new settings options (which
        # normally would not be present in the unpickled object) by creating a
        # new settings object, updating it with the unpickled state, and
        # updating our dict with that.
        new_state = Settings().__dict__
        new_state.update(self.deserialize_state_dict(state))
        self.__dict__.update(new_state)
        from game.plugins import LuaPluginManager

        LuaPluginManager().load_settings(self)

    @staticmethod
    def deserialize_state_dict(state: dict[str, Any]) -> dict[str, Any]:
        # restore Enum & timedelta types
        s = Settings()
        Settings._migrate_legacy_bandit_clouds(state)
        Settings._migrate_settings_into_plugins(state)
        Settings._migrate_lopsided_friendship_bands(state)
        for key, value in list(state.items()):
            default = s.__dict__.get(key)
            if isinstance(default, Enum):
                # Restore the stored member, falling back to the field default
                # for any value that no longer resolves to a member of this
                # field's enum -- a stale/renamed choice, or a legacy non-enum
                # value such as None or a bool. Otherwise the bad value crashes
                # the load and later the settings UI via text_for_value.
                restored = Settings._restore_enum(value, type(default))
                state[key] = restored if restored is not None else default
            elif isinstance(default, timedelta) and isinstance(value, int):
                state[key] = timedelta(minutes=value)
            elif isinstance(value, dict):
                state[key] = s.obj_hook(value)
        return state

    @staticmethod
    def _restore_enum(value: Any, enum_cls: type[Enum]) -> Optional[Enum]:
        """Resolve a serialized value to a member of enum_cls, or None if it no
        longer maps to one (stale, renamed, or a legacy non-enum value)."""
        if isinstance(value, enum_cls):
            return value
        # Accept the JSON form {"Enum": "EnumName.MEMBER"} and the bare
        # "EnumName.MEMBER" string; ignore anything that does not eval to a
        # member of this field's enum.
        expr: Optional[str] = None
        if isinstance(value, dict):
            inner = value.get("Enum")
            if isinstance(inner, str):
                expr = inner
        elif isinstance(value, str):
            expr = value
        if expr is not None:
            try:
                restored = eval(expr)
            except Exception:
                return None
            if isinstance(restored, enum_cls):
                return restored
        return None

    #: Settings that became options of the plugin they were always about. The value
    #: is the plugin option that replaced each one; a switch whose plugin has its own
    #: switch of the same name is ANDed, because the feature used to need both.
    _MOVED_INTO_PLUGINS: ClassVar[dict[str, str]] = {
        "gps_jamming": "gpsjamming",
        "gps_jamming_default_reach_nm": "gpsjamming.defaultReachNm",
        "gps_jamming_miss_radius_m": "gpsjamming.missRadiusM",
        "naval_magazines": "navalmagazines",
        "naval_weapon_release_stagger": "navalmagazines.releaseStagger",
        "cruise_missile_strikes": "cruisemissiles",
        "cruise_missile_auto_raids": "cruisemissiles.autoRaids",
        "perf_skynet_iads_radius": "skynetiads.radiusKm",
    }

    @staticmethod
    def _migrate_settings_into_plugins(state: dict[str, Any]) -> None:
        """Carry an old save's values onto the plugin options that replaced them.

        Without this a campaign that had a feature switched OFF would load with it on,
        because every one of these plugins ships enabled and the plugin switch is now
        the only gate. The plugin manager fills defaults for options that are missing
        and leaves present ones alone, so writing here is enough.
        """
        plugins = state.setdefault("plugins", {})
        for setting, option in Settings._MOVED_INTO_PLUGINS.items():
            if setting not in state:
                continue
            value = state[setting]
            if "." not in option and isinstance(value, bool):
                # The feature ran only when the setting AND the plugin were on.
                value = value and bool(plugins.get(option, True))
            plugins[option] = value

    #: The floors the friendship bands shipped with, and what they should have been.
    #: Drift moves a pair by a whole point from a start of five, so one quiet turn
    #: leaves it on four or six -- and with Neutral starting at 4.1, four fell out of
    #: it into Frosty while six stayed in. Every pair that had drifted down once was
    #: painted as going cold and every pair that had drifted up once was painted as
    #: nothing, which read as a campaign where nobody gets on with anybody.
    LOPSIDED_FRIENDSHIP_BANDS = {
        "friendship_band_neutral": (4.1, 4.0),
        "friendship_band_frosty": (3.1, 3.0),
    }

    @staticmethod
    def _migrate_lopsided_friendship_bands(state: dict[str, Any]) -> None:
        """Straighten the bands in a campaign that never moved them itself.

        Only when the stored floor is still the one that shipped: a player who has
        set these to something of their own keeps it.
        """
        for key, (was, should_be) in Settings.LOPSIDED_FRIENDSHIP_BANDS.items():
            if state.get(key) == was:
                state[key] = should_be

    @staticmethod
    def _migrate_legacy_bandit_clouds(state: dict[str, Any]) -> None:
        """Pre-pack saves had a boolean ``use_bandit_clouds``; map it onto the new
        ``cloud_preset_pack`` choice so a user who had Bandit's clouds on keeps them."""
        legacy = state.pop("use_bandit_clouds", None)
        if legacy is not None and "cloud_preset_pack" not in state:
            state["cloud_preset_pack"] = (
                CloudPresetPack.BANDIT if legacy else CloudPresetPack.NONE
            )

    @classmethod
    def _field_description(cls, settings_field: Field[Any]) -> OptionDescription:
        return settings_field.metadata[SETTING_DESCRIPTION_KEY]

    @classmethod
    def pages(cls) -> Iterator[str]:
        seen: set[str] = set()
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if description.page not in seen:
                yield description.page
                seen.add(description.page)

    @classmethod
    def sections(cls, page: str) -> Iterator[str]:
        """The sections the page shows in its index.

        A section that some switch opens with a gear is not one of them: it is a
        detail of that switch and is reached from its row.
        """
        owned = cls.sections_opened_from_a_switch()
        seen: set[str] = set()
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if description.page != page or description.section in seen:
                continue
            seen.add(description.section)
            if description.section not in owned:
                yield description.section

    @classmethod
    def sections_opened_from_a_switch(cls) -> set[str]:
        return {
            opened
            for settings_field in cls._user_fields()
            if (opened := cls._field_description(settings_field).opens_section)
            is not None
        }

    @classmethod
    def switch_that_opens(cls, section: str) -> Optional[tuple[str, str, str]]:
        """The setting whose gear opens this section, as (name, page, its section).

        A section reached from a gear is not on any page, so anything navigating to
        one of its settings has to be sent to the switch that opens it instead.
        """
        for name, description in cls.all_fields():
            if description.opens_section == section:
                return name, description.page, description.section
        return None

    @classmethod
    def subsections(cls, page: str, section: str) -> Iterator[str]:
        """The boxes within a section, in the order their settings are declared."""
        seen: set[str] = set()
        for _, description in cls.all_fields():
            if description.page != page or description.section != section:
                continue
            name = description.subsection
            if name is not None and name not in seen:
                yield name
                seen.add(name)

    @classmethod
    def fields(
        cls, page: str, section: str, subsection: Optional[str] = None
    ) -> Iterator[tuple[str, OptionDescription]]:
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if (
                description.page == page
                and description.section == section
                and description.subsection == subsection
            ):
                yield settings_field.name, description

    @classmethod
    def all_fields(cls) -> Iterator[tuple[str, OptionDescription]]:
        """Every setting there is, whatever page, section or box it is shown in.

        The page walk above is about how the dialog is laid out; this is about what
        exists, which is what anything reading the settings wants.
        """
        for settings_field in cls._user_fields():
            yield settings_field.name, cls._field_description(settings_field)

    @classmethod
    def _user_fields(cls) -> Iterator[Field[Any]]:
        for settings_field in fields(cls):
            if SETTING_DESCRIPTION_KEY in settings_field.metadata:
                yield settings_field

    @staticmethod
    def default_json(obj: Any) -> Any:
        # Known types that don't like being serialized,
        # so we introduce our own implementation...
        if isinstance(obj, Enum):
            return {"Enum": str(obj)}
        elif isinstance(obj, timedelta):
            return {"timedelta": round(obj.seconds / 60)}
        return obj

    @staticmethod
    def obj_hook(obj: Any) -> Any:
        if (value := obj.get("Enum")) is not None:
            return eval(value)
        elif (value := obj.get("timedelta")) is not None:
            return timedelta(minutes=value)
        else:
            return obj
