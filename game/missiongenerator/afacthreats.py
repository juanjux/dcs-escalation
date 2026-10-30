"""Ground air-defence envelopes for AFAC; unknown ceilings forbid overflight."""

from functools import cache
import math
from typing import Any

from dcs.vehicles import AirDefence, vehicle_map

from game.data.units import ANTI_AIR_UNIT_CLASSES
from game.dcs.groundunittype import GroundUnitType

# Metres above the launcher, added to its native MSL position by AFACSafety.
# Sources: installed DCS 2.9.31 TechWeaponPack and the named mod weapon files.
# Use weapon H_max, or explicit launcher max_trg_alt for guns. For mixed systems,
# use the highest weapon ceiling. Radar tracking heights are not weapon ceilings.
# Do not infer ceilings from horizontal range or copy them to unverified variants.
VERIFIED_CEILINGS = {
    # TechWeaponPack/Database/Weapons/cannon.lua; vehicles/AirDefence/ZSU_57_2.lua.
    "ZSU_57_2": 4000,
    "S-60_Type59_Artillery": 4000,
    "KS-19": 15400,
    "flak18": 10000,
    # TechWeaponPack/Database/Weapons/manpads_missiles.lua: Igla_1E, FIM_92C.
    "SA-18 Igla manpad": 3500,
    "Igla manpad INS": 3500,
    "Soldier stinger": 3500,
    "M1097 Avenger": 3500,
    "M6 Linebacker": 3500,
    # DCS MissionEditor/data/scripts/Enc/SAM/Igla-S.txt: target altitude 10-3500 m.
    "SA-18 Igla-S manpad": 3500,
    # TechWeaponPack/Database/Weapons/tunguska_family.lua: SA9M311.
    "2S6 Tunguska": 3500,
    # osa_tor_family.lua: SA9M33, SA9M330; kub_buk_family.lua: SA3M9M, SA9M38M1.
    "Osa 9A33 ln": 5000,
    "Tor 9A331": 6000,
    "Kub 2P25 ln": 8000,
    "SA-11 Buk LN 9A310M1": 22000,
    # misc_sams.lua: SA9M31, SA9M333, MIM_104, HAWK_RAKETA, ROLAND_R, SA5V28.
    "Strela-1 9P31": 3500,
    "Strela-10M3": 3500,
    "CH_9K35": 3500,  # CH Russia uses the native _9A35 launcher unchanged.
    "Patriot ln": 24240,
    "Hawk ln": 40000,
    "Roland ADS": 6000,
    "S-200_Launcher": 40000,
    # s75_s125_family.lua: SA2V755, SA5B27; s300_s400_family.lua: SA5B55.
    "S_75M_Volhov": 25000,
    "5p73 s-125 ln": 18000,
    "S-300PS 5P85C ln": 25000,
    "S-300PS 5P85D ln": 25000,
    # AircraftWeaponPack/aim9_family.lua: MIM_72G; ChinaAssetPack weapons.lua: HQ_7.
    "M48 Chaparral": 3000,
    "HQ-7_LN_P": 6000,
    "HQ-7_LN_SP": 6000,
    # misc_sams.lua: Rapier. The launcher's 8000 m station is only a tracker.
    "rapier_fsa_launcher": 3000,
    # Currenthill Assets Pack uses native SA57E6, SA9M338K and SA_IRIS_T_SL.
    # Gun CHAP_2A38M is lower than SA57E6. Tracking-only stations are excluded.
    "CHAP_PantsirS1": 10000,
    "CHAP_TorM2": 12000,
    "CHAP_IRISTSLM_LN": 20000,
    # HighDigitSAMs/Database/Weapon: 9M32, 9M32M, 9M36, 9M342 respectively.
    "SA-7 Strela-2 manpad": 2000,
    "SA-7b Strela-2M manpad": 2300,
    "SA-14 Strela-3 manpad": 3000,
    "SA-24 Igla-S manpad": 3500,
    # HighDigitSAMs: 5V27, 5V23, HQ2, 9M317, 48N6, 48N6E2.
    "5p73 V-601P ln": 18000,
    "S_75M_Volhov_V759": 30000,
    "HQ_2_Guideline_LN": 30000,
    "SA-17 Buk M1-2 LN 9A310M1-2": 50000,
    "S-300PMU1 5P85CE ln": 30000,
    "S-300PMU1 5P85DE ln": 30000,
    "S-300PMU2 5P85SE2 ln": 30000,
    # HighDigitSAMs: 9M82, 9M83, 9M82M, 9M83M; ASTER-30-1, -1NT, -2.
    "S-300V 9A82 ln": 30000,
    "S-300V 9A83 ln": 25000,
    "S-300VM 9A82ME ln": 150000,
    "S-300VM 9A83ME ln": 30000,
    "SAMPT_MLT_Blk1": 20000,
    "SAMPT_MLT_Blk1NT": 25000,
    "SAMPT_MLT_Blk2": 70000,
    # CH Military Asset Pack USA 1.5.0 / Germany 1.5.0: individual FIM92 files.
    # LAV-AD/Skyranger guns and vehicle machine guns all have lower ceilings.
    "CH_USInfantry_FIM92": 4800,
    "CH_LAVAD": 4800,
    "CH_BoxerSkyranger": 4800,
    "CH_Wiesel2Ozelot": 4800,
    # CH Russia 2.0.1: CH_9M332_missile, CH_BukM3_9M317M/MA,
    # CH_Pantsir_SPAAGM_57E6M, CH_S350_9M100/9M96D. Guns are lower.
    "CH_TorM2K": 10000,
    "CH_BukM3_9A317M": 35000,
    "CH_BukM3_9A317MA": 35000,
    "CH_PantsirS2": 18000,
    "CH_S350_50P6_9M100": 8000,
    "CH_S350_50P6_9M96D": 30000,
    # CH USA/Germany: CH_MIM104_Patriot_PAC2/PAC3, CH_MIM104_KAT1_PAC2,
    # CH_NASAMS_3_AIM9X2/AMRAAM_ER, CH_THAAD_Interceptor.
    "CH_MIM104_M903_PAC2": 24500,
    "CH_MIM104_M903_PAC2_HEMTT": 24500,
    "CH_MIM104_M901_PAC2_KAT1": 24500,
    "CH_MIM104_M903_PAC3": 50000,
    "CH_MIM104_M903_PAC3_HEMTT": 50000,
    "CH_NASAMS3_LN_AIM9X2": 18000,
    "CH_NASAMS3_LN_AMRAAM_ER": 35700,
    "CH_THAAD_M1120": 150000,
    # CH Sweden 1.5.0: CH_RBS70/90_Bolide, CH_RBS98_IRIS-T, CH_LvS103_Rb103A/B.
    "CH_RBS-70": 6000,
    "CH_RBS-90": 6000,
    "CH_RBS-98": 8000,
    "CH_LvS-103_Lavett103_Rb103A": 24500,
    "CH_LvS-103_Lavett103_HX_Rb103A": 24500,
    "CH_LvS-103_Lavett103_Rb103B": 40000,
    "CH_LvS-103_Lavett103_HX_Rb103B": 40000,
    # CH UK 1.5.0: CH_SkySabre_LandCeptor, CH_StormerHVM_Starstreak.
    "CH_SkySabre": 10000,
    "CH_StormerHVM": 7000,
    # CH China 1.1.6: HQ-17A_missile, HQ-22_missile, PGL_625_FB10A.
    "HQ17A": 10000,
    "CH_HQ22_LN": 27000,
    "PGL_625": 5000,
    # CH Germany 1.5.0: CH_FlaRakRad_Roland3 and explicit gun station ceilings.
    "CH_FlaRakRad": 6000,
    "CH_SkynexHX": 3500,
    "CH_Skyshield_Gun": 3500,
    # CH Russia 2.0.1: AC2A90 (4500 m); LG also carries CH_2S38_3UO7 (6000 m).
    "CH_2S38": 4500,
    "CH_2S38_LG": 6000,
    # CH Sweden 1.5.0: CH_LvKv9040.lua, highest actual gun station (not tracker).
    "CH_LvKv9040": 2500,
}


@cache
def envelope(type_name: str) -> dict[str, Any] | None:
    native = vehicle_map.get(type_name)
    if native is None:
        return None
    radius = getattr(native, "threat_range", 0)
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not math.isfinite(radius)
        or radius <= 0
    ):
        return None
    variants = GroundUnitType.for_dcs_type(native)
    if (
        not any(v.unit_class in ANTI_AIR_UNIT_CLASSES for v in variants)
        and native not in vars(AirDefence).values()
    ):
        return None
    return {"radius": radius, "ceiling": VERIFIED_CEILINGS.get(type_name)}
