"""Spino F-15EX v3.0 air-to-air aircraft and station-specific stores."""

from dcs import task
from dcs.planes import PlaneType
from dcs.weapons_data import weapon_ids

from game.modsupport import planemod
from pydcs_extensions.weapon_injector import inject_weapons


class WeaponsF15EX:
    F15EX_V3_AIM200_4XRACK = {
        "clsid": "{AIM200-4XRACK}",
        "name": "BRU-61C - 4 x AIM-200A - Active Radar AAM",
        "weight": 681.4,
    }
    F15EX_V3_AMBER_2xAIM120C5 = {
        "clsid": "{AMBER_2xAIM120C5}",
        "name": "AMBER 2x AIM-120C AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_AMBER_2xAIM120C7 = {
        "clsid": "{AMBER_2xAIM120C7}",
        "name": "AMBER 2x AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_AMBER_2xAIM120C8 = {
        "clsid": "{AMBER_2xAIM120C8}",
        "name": "AMBER 2x AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_AMBER_2xAIM120D_P3I = {
        "clsid": "{AMBER_2xAIM120D_P3I}",
        "name": "AMBER 2x AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_AMBER_2xAIM120D = {
        "clsid": "{AMBER_2xAIM120D}",
        "name": "AMBER 2x AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_AMBER_2xAIM260A = {
        "clsid": "{AMBER_2xAIM260A}",
        "name": "AMBER 2x AIM-260A - Active Radar AAM",
        "weight": 405.6,
    }
    F15EX_V3_ASG_34_LegionPod = {
        "clsid": "{ASG-34_LegionPod}",
        "name": "AN/ASG-34 Legion IRST Pod (Cosmetic)",
        "weight": 208,
    }
    F15EX_V3_F_15EX_AIM_9X_O = {
        "clsid": "{F-15EX_AIM-9X_O}",
        "name": "2x AIM-9X Sidewinder IR AAM",
        "weight": 321,
    }
    F15EX_V3_F15EX_2xAIM_120C_5 = {
        "clsid": "{F15EX_2xAIM-120C-5}",
        "name": "2x AIM-120C AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_F15EX_2xAIM_120C_7 = {
        "clsid": "{F15EX_2xAIM-120C-7}",
        "name": "2x AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_F15EX_2xAIM_120C_8 = {
        "clsid": "{F15EX_2xAIM-120C-8}",
        "name": "2x AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_F15EX_2xAIM_120D_3 = {
        "clsid": "{F15EX_2xAIM-120D-3}",
        "name": "2x AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_F15EX_2xAIM_120D = {
        "clsid": "{F15EX_2xAIM-120D}",
        "name": "2x AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_F15EX_2xAIM_260A = {
        "clsid": "{F15EX_2xAIM-260A}",
        "name": "2x AIM-260A - Active Radar AAM",
        "weight": 405.6,
    }
    F15EX_V3_F15EX_AIM_120C_5_CFT_A = {
        "clsid": "{F15EX_AIM-120C-5_CFT_A}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_CFT_F = {
        "clsid": "{F15EX_AIM-120C-5_CFT_F}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_CFT_RA = {
        "clsid": "{F15EX_AIM-120C-5_CFT_RA}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_FUS_LA = {
        "clsid": "{F15EX_AIM-120C-5_FUS_LA}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_FUS_LF = {
        "clsid": "{F15EX_AIM-120C-5_FUS_LF}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_FUS_RA = {
        "clsid": "{F15EX_AIM-120C-5_FUS_RA}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_FUS_RF = {
        "clsid": "{F15EX_AIM-120C-5_FUS_RF}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_STA11A = {
        "clsid": "{F15EX_AIM-120C-5_STA11A}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_STA11B = {
        "clsid": "{F15EX_AIM-120C-5_STA11B}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_STA2A = {
        "clsid": "{F15EX_AIM-120C-5_STA2A}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_5_STA2B = {
        "clsid": "{F15EX_AIM-120C-5_STA2B}",
        "name": "AIM-120C AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_CFT_A = {
        "clsid": "{F15EX_AIM-120C-7_CFT_A}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_CFT_F = {
        "clsid": "{F15EX_AIM-120C-7_CFT_F}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_CFT_RA = {
        "clsid": "{F15EX_AIM-120C-7_CFT_RA}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_FUS_LA = {
        "clsid": "{F15EX_AIM-120C-7_FUS_LA}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_FUS_LF = {
        "clsid": "{F15EX_AIM-120C-7_FUS_LF}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_FUS_RA = {
        "clsid": "{F15EX_AIM-120C-7_FUS_RA}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_FUS_RF = {
        "clsid": "{F15EX_AIM-120C-7_FUS_RF}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_STA11A = {
        "clsid": "{F15EX_AIM-120C-7_STA11A}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_STA11B = {
        "clsid": "{F15EX_AIM-120C-7_STA11B}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_STA2A = {
        "clsid": "{F15EX_AIM-120C-7_STA2A}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_7_STA2B = {
        "clsid": "{F15EX_AIM-120C-7_STA2B}",
        "name": "AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120C_8_CFT_A = {
        "clsid": "{F15EX_AIM-120C-8_CFT_A}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_CFT_F = {
        "clsid": "{F15EX_AIM-120C-8_CFT_F}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_CFT_RA = {
        "clsid": "{F15EX_AIM-120C-8_CFT_RA}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_FUS_LA = {
        "clsid": "{F15EX_AIM-120C-8_FUS_LA}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_FUS_LF = {
        "clsid": "{F15EX_AIM-120C-8_FUS_LF}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_FUS_RA = {
        "clsid": "{F15EX_AIM-120C-8_FUS_RA}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_FUS_RF = {
        "clsid": "{F15EX_AIM-120C-8_FUS_RF}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_STA11A = {
        "clsid": "{F15EX_AIM-120C-8_STA11A}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_STA11B = {
        "clsid": "{F15EX_AIM-120C-8_STA11B}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_STA2A = {
        "clsid": "{F15EX_AIM-120C-8_STA2A}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120C_8_STA2B = {
        "clsid": "{F15EX_AIM-120C-8_STA2B}",
        "name": "AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_CFT_A = {
        "clsid": "{F15EX_AIM-120D-3_CFT_A}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_CFT_F = {
        "clsid": "{F15EX_AIM-120D-3_CFT_F}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_CFT_RA = {
        "clsid": "{F15EX_AIM-120D-3_CFT_RA}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_FUS_LA = {
        "clsid": "{F15EX_AIM-120D-3_FUS_LA}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_FUS_LF = {
        "clsid": "{F15EX_AIM-120D-3_FUS_LF}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_FUS_RA = {
        "clsid": "{F15EX_AIM-120D-3_FUS_RA}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_FUS_RF = {
        "clsid": "{F15EX_AIM-120D-3_FUS_RF}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_STA11A = {
        "clsid": "{F15EX_AIM-120D-3_STA11A}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_STA11B = {
        "clsid": "{F15EX_AIM-120D-3_STA11B}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_STA2A = {
        "clsid": "{F15EX_AIM-120D-3_STA2A}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_3_STA2B = {
        "clsid": "{F15EX_AIM-120D-3_STA2B}",
        "name": "AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 166.7241,
    }
    F15EX_V3_F15EX_AIM_120D_CFT_A = {
        "clsid": "{F15EX_AIM-120D_CFT_A}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_CFT_F = {
        "clsid": "{F15EX_AIM-120D_CFT_F}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_CFT_RA = {
        "clsid": "{F15EX_AIM-120D_CFT_RA}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_FUS_LA = {
        "clsid": "{F15EX_AIM-120D_FUS_LA}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_FUS_LF = {
        "clsid": "{F15EX_AIM-120D_FUS_LF}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_FUS_RA = {
        "clsid": "{F15EX_AIM-120D_FUS_RA}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_FUS_RF = {
        "clsid": "{F15EX_AIM-120D_FUS_RF}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_STA11A = {
        "clsid": "{F15EX_AIM-120D_STA11A}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_STA11B = {
        "clsid": "{F15EX_AIM-120D_STA11B}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_STA2A = {
        "clsid": "{F15EX_AIM-120D_STA2A}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_120D_STA2B = {
        "clsid": "{F15EX_AIM-120D_STA2B}",
        "name": "AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 161.48,
    }
    F15EX_V3_F15EX_AIM_174B_CFT = {
        "clsid": "{F15EX_AIM-174B_CFT}",
        "name": "AIM-174B Gunslinger - Active Radar ULRAAM (CFT)",
        "weight": 860,
    }
    F15EX_V3_F15EX_AIM_174B = {
        "clsid": "{F15EX_AIM-174B}",
        "name": "AIM-174B Gunslinger - Active Radar ULRAAM",
        "weight": 910,
    }
    F15EX_V3_F15EX_AIM_200A_CFT_A = {
        "clsid": "{F15EX_AIM-200A_CFT_A}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_CFT_F = {
        "clsid": "{F15EX_AIM-200A_CFT_F}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_CFT_RA = {
        "clsid": "{F15EX_AIM-200A_CFT_RA}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_FUS_LA = {
        "clsid": "{F15EX_AIM-200A_FUS_LA}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_FUS_LF = {
        "clsid": "{F15EX_AIM-200A_FUS_LF}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_FUS_RA = {
        "clsid": "{F15EX_AIM-200A_FUS_RA}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_200A_FUS_RF = {
        "clsid": "{F15EX_AIM-200A_FUS_RF}",
        "name": "AIM-200A - Active Radar AAM",
        "weight": 157.85,
    }
    F15EX_V3_F15EX_AIM_260A_CFT_A = {
        "clsid": "{F15EX_AIM-260A_CFT_A}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_CFT_F = {
        "clsid": "{F15EX_AIM-260A_CFT_F}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_CFT_RA = {
        "clsid": "{F15EX_AIM-260A_CFT_RA}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_FUS_LA = {
        "clsid": "{F15EX_AIM-260A_FUS_LA}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_FUS_LF = {
        "clsid": "{F15EX_AIM-260A_FUS_LF}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_FUS_RA = {
        "clsid": "{F15EX_AIM-260A_FUS_RA}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_FUS_RF = {
        "clsid": "{F15EX_AIM-260A_FUS_RF}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_STA11A = {
        "clsid": "{F15EX_AIM-260A_STA11A}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_STA11B = {
        "clsid": "{F15EX_AIM-260A_STA11B}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_STA2A = {
        "clsid": "{F15EX_AIM-260A_STA2A}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_260A_STA2B = {
        "clsid": "{F15EX_AIM-260A_STA2B}",
        "name": "AIM-260A - Active Radar AAM",
        "weight": 177.8,
    }
    F15EX_V3_F15EX_AIM_9X_ED_STA11A = {
        "clsid": "{F15EX_AIM-9X-ED_STA11A}",
        "name": "AIM-9X Sidewinder IR AAM (ED)",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_ED_STA11B = {
        "clsid": "{F15EX_AIM-9X-ED_STA11B}",
        "name": "AIM-9X Sidewinder IR AAM (ED)",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_ED_STA2A = {
        "clsid": "{F15EX_AIM-9X-ED_STA2A}",
        "name": "AIM-9X Sidewinder IR AAM (ED)",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_ED_STA2B = {
        "clsid": "{F15EX_AIM-9X-ED_STA2B}",
        "name": "AIM-9X Sidewinder IR AAM (ED)",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_STA11A = {
        "clsid": "{F15EX_AIM-9X_STA11A}",
        "name": "AIM-9X Sidewinder IR AAM",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_STA11B = {
        "clsid": "{F15EX_AIM-9X_STA11B}",
        "name": "AIM-9X Sidewinder IR AAM",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_STA2A = {
        "clsid": "{F15EX_AIM-9X_STA2A}",
        "name": "AIM-9X Sidewinder IR AAM",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_AIM_9X_STA2B = {
        "clsid": "{F15EX_AIM-9X_STA2B}",
        "name": "AIM-9X Sidewinder IR AAM",
        "weight": 85.5,
    }
    F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = {
        "clsid": "{F15EX_LAU_115_2xAIM-120C-5}",
        "name": "LAU-115 with 2 x LAU-127 AIM-120C AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = {
        "clsid": "{F15EX_LAU_115_2xAIM-120C-8}",
        "name": "LAU-115 with 2 x LAU-127 AIM-120C-8 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_F15EX_LAU_115_2xAIM_120D = {
        "clsid": "{F15EX_LAU_115_2xAIM-120D}",
        "name": "LAU-115 with 2 x LAU-127 AIM-120D P3I AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_F15EX_PYTHON_5_STA11A = {
        "clsid": "{F15EX_PYTHON-5_STA11A}",
        "name": "Python-5 IR AAM",
        "weight": 105,
    }
    F15EX_V3_F15EX_PYTHON_5_STA11B = {
        "clsid": "{F15EX_PYTHON-5_STA11B}",
        "name": "Python-5 IR AAM",
        "weight": 105,
    }
    F15EX_V3_F15EX_PYTHON_5_STA2A = {
        "clsid": "{F15EX_PYTHON-5_STA2A}",
        "name": "Python-5 IR AAM",
        "weight": 105,
    }
    F15EX_V3_F15EX_PYTHON_5_STA2B = {
        "clsid": "{F15EX_PYTHON-5_STA2B}",
        "name": "Python-5 IR AAM",
        "weight": 105,
    }
    F15EX_V3_F15IA_PYTHON_5 = {
        "clsid": "{F15IA_PYTHON-5}",
        "name": "2 x Python-5 IR AAM",
        "weight": 315,
    }
    F15EX_V3_LAU_115_2xAIM_120C_7 = {
        "clsid": "{LAU_115_2xAIM-120C-7}",
        "name": "LAU-115 with 2 x LAU-127 AIM-120C-7 AMRAAM - Active Radar AAM",
        "weight": 372.96,
    }
    F15EX_V3_LAU_115_2xAIM_120D_3 = {
        "clsid": "{LAU_115_2xAIM-120D-3}",
        "name": "LAU-115 with 2 x LAU-127 AIM-120D-3 AMRAAM - Active Radar AAM",
        "weight": 383.4482,
    }
    F15EX_V3_LAU_115_2xAIM_260A = {
        "clsid": "{LAU_115_2xAIM-260A}",
        "name": "2x AIM-260A - Active Radar AAM",
        "weight": 405.6,
    }


inject_weapons(WeaponsF15EX)


@planemod
class F_15EX(PlaneType):
    id = "F15EX"
    flyable = True
    height = 5.6
    width = 13.05
    length = 19.43
    fuel_max = 6146
    max_speed = 2655
    chaff = 120
    flare = 120
    charge_total = 240
    chaff_charge_size = 1
    flare_charge_size = 1
    eplrs = True
    category = "Interceptor"
    radio_frequency = 251
    livery_name = "F-15EX"
    panel_radio = {
        1: {"channels": {n: 251.0 for n in range(1, 21)}},
        2: {"channels": {n: 124.0 for n in range(1, 21)}},
    }
    pylons = set(range(1, 16))
    tasks = [task.CAP, task.Escort, task.FighterSweep, task.Intercept]
    task_default = task.CAP

    class Pylon1:
        F15EX_V3_F15EX_2xAIM_260A = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_260A)
        F15EX_V3_F15EX_2xAIM_120D_3 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D_3)
        F15EX_V3_F15EX_2xAIM_120D = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D)
        F15EX_V3_F15EX_2xAIM_120C_8 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_8)
        F15EX_V3_F15EX_2xAIM_120C_7 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_7)
        F15EX_V3_F15EX_2xAIM_120C_5 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_5)
        F15EX_V3_F_15EX_AIM_9X_O = (1, WeaponsF15EX.F15EX_V3_F_15EX_AIM_9X_O)

    class Pylon2:
        F15EX_V3_F15E_EXTTANK = (2, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (2, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_260A = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_260A)
        F15EX_V3_LAU_115_2xAIM_120C_7 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_F15EX_AIM_174B = (2, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    class Pylon3:
        F15EX_V3_F15EX_AIM_120C_8_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA2A,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA2A,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA2A,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA2A,
        )
        F15EX_V3_F15EX_AIM_120D_STA2A = (3, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA2A)
        F15EX_V3_F15EX_AIM_260A_STA2A = (3, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_STA2A)
        F15EX_V3_F15EX_AIM_9X_STA2A = (3, WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_STA2A)
        F15EX_V3_F15EX_AIM_9X_ED_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA2A,
        )

    class Pylon4:
        F15EX_V3_F15EX_AIM_120C_8_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA2B,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA2B,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA2B,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA2B,
        )
        F15EX_V3_F15EX_AIM_120D_STA2B = (4, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA2B)
        F15EX_V3_F15EX_AIM_260A_STA2B = (4, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_STA2B)
        F15EX_V3_F15EX_AIM_9X_STA2B = (4, WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_STA2B)
        F15EX_V3_F15EX_AIM_9X_ED_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA2B,
        )

    class Pylon5:
        F15EX_V3_F15EX_AIM_120C_8_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_120C_7_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_120C_5_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_120D_3_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_120D_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_260A_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_FUS_LF,
        )
        F15EX_V3_F15EX_AIM_200A_FUS_LF = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_FUS_LF,
        )

    class Pylon6:
        F15EX_V3_F15EX_AIM_120C_8_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_120C_7_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_120C_5_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_120D_3_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_120D_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_260A_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_FUS_LA,
        )
        F15EX_V3_F15EX_AIM_200A_FUS_LA = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_FUS_LA,
        )

    class Pylon7:
        F15EX_V3_A111396E_D3E8_4b9c_8AC9_2432489304D5 = (
            7,
            weapon_ids["{A111396E-D3E8-4b9c-8AC9-2432489304D5}"],
        )
        F15EX_V3_AN_AAQ_33 = (7, weapon_ids["{AN_AAQ_33}"])
        F15EX_V3_F_15E_AAQ_14_LANTIRN = (7, weapon_ids["{F-15E_AAQ-14_LANTIRN}"])

    class Pylon8:
        F15EX_V3_F15E_EXTTANK = (8, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (8, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_ASG_34_LegionPod = (8, WeaponsF15EX.F15EX_V3_ASG_34_LegionPod)
        F15EX_V3_AN_AAQ_33 = (8, weapon_ids["{AN_AAQ_33}"])

    class Pylon9:
        F15EX_V3_F_15E_AAQ_13_LANTIRN = (9, weapon_ids["{F-15E_AAQ-13_LANTIRN}"])

    class Pylon10:
        F15EX_V3_F15EX_AIM_120C_8_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_120C_7_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_120C_5_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_120D_3_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_120D_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_260A_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_FUS_RA,
        )
        F15EX_V3_F15EX_AIM_200A_FUS_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_FUS_RA,
        )

    class Pylon11:
        F15EX_V3_F15EX_AIM_120C_8_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_120C_7_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_120C_5_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_120D_3_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_120D_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_260A_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_FUS_RF,
        )
        F15EX_V3_F15EX_AIM_200A_FUS_RF = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_FUS_RF,
        )

    class Pylon12:
        F15EX_V3_F15EX_AIM_120C_8_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA11B,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA11B,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA11B,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA11B,
        )
        F15EX_V3_F15EX_AIM_120D_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA11B,
        )
        F15EX_V3_F15EX_AIM_260A_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_STA11B,
        )
        F15EX_V3_F15EX_AIM_9X_STA11B = (12, WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_STA11B)
        F15EX_V3_F15EX_AIM_9X_ED_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA11B,
        )

    class Pylon13:
        F15EX_V3_F15EX_AIM_120C_8_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA11A,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA11A,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA11A,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA11A,
        )
        F15EX_V3_F15EX_AIM_120D_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA11A,
        )
        F15EX_V3_F15EX_AIM_260A_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_STA11A,
        )
        F15EX_V3_F15EX_AIM_9X_STA11A = (13, WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_STA11A)
        F15EX_V3_F15EX_AIM_9X_ED_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA11A,
        )

    class Pylon14:
        F15EX_V3_F15E_EXTTANK = (14, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (14, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_260A = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_260A)
        F15EX_V3_LAU_115_2xAIM_120C_7 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_F15EX_AIM_174B = (14, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    class Pylon15:
        F15EX_V3_F_15EX_AIM_9X_O = (15, WeaponsF15EX.F15EX_V3_F_15EX_AIM_9X_O)
        F15EX_V3_F15EX_2xAIM_260A = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_260A)
        F15EX_V3_F15EX_2xAIM_120D_3 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D_3)
        F15EX_V3_F15EX_2xAIM_120D = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D)
        F15EX_V3_F15EX_2xAIM_120C_8 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_8)
        F15EX_V3_F15EX_2xAIM_120C_7 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_7)
        F15EX_V3_F15EX_2xAIM_120C_5 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_5)


@planemod
class F_15EX_CFT(F_15EX):
    id = "F15EX_CFT"
    payloads = None
    fuel_max = 10571
    livery_name = "F-15EX_CFT"

    Pylon1 = F_15EX.Pylon1

    class Pylon2:
        F15EX_V3_F15E_EXTTANK = (2, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (2, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_260A = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_260A)
        F15EX_V3_LAU_115_2xAIM_120C_7 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_AIM200_4XRACK = (2, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B = (2, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    Pylon3 = F_15EX.Pylon3

    Pylon4 = F_15EX.Pylon4

    class Pylon5:
        F15EX_V3_AMBER_2xAIM120C8 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AMBER_2xAIM260A = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM260A)
        F15EX_V3_F15EX_AIM_120C_8_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_F = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_F)
        F15EX_V3_F15EX_AIM_260A_CFT_F = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_CFT_F)
        F15EX_V3_F15EX_AIM_200A_CFT_F = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_F)
        F15EX_V3_AIM200_4XRACK = (5, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B_CFT = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B_CFT)

    class Pylon6:
        F15EX_V3_AMBER_2xAIM120C8 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AMBER_2xAIM260A = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM260A)
        F15EX_V3_AIM200_4XRACK = (6, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_120C_8_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_A = (6, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_A)
        F15EX_V3_F15EX_AIM_260A_CFT_A = (6, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_CFT_A)
        F15EX_V3_F15EX_AIM_200A_CFT_A = (6, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_A)

    Pylon7 = F_15EX.Pylon7

    class Pylon8:
        F15EX_V3_AMBER_2xAIM120C8 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AMBER_2xAIM260A = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM260A)
        F15EX_V3_AIM200_4XRACK = (8, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15E_EXTTANK = (8, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (8, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_ASG_34_LegionPod = (8, WeaponsF15EX.F15EX_V3_ASG_34_LegionPod)

    Pylon9 = F_15EX.Pylon9

    class Pylon10:
        F15EX_V3_AMBER_2xAIM120C8 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AMBER_2xAIM260A = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM260A)
        F15EX_V3_AIM200_4XRACK = (10, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_120C_8_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_260A_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_200A_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_8_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_A = (10, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_A)
        F15EX_V3_F15EX_AIM_260A_CFT_A = (10, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_CFT_A)
        F15EX_V3_F15EX_AIM_200A_CFT_A = (10, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_A)

    class Pylon11:
        F15EX_V3_AMBER_2xAIM120C8 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AMBER_2xAIM260A = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM260A)
        F15EX_V3_F15EX_AIM_120C_8_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_F = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_F)
        F15EX_V3_F15EX_AIM_260A_CFT_F = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_260A_CFT_F)
        F15EX_V3_F15EX_AIM_200A_CFT_F = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_F)
        F15EX_V3_AIM200_4XRACK = (11, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B_CFT = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B_CFT)

    Pylon12 = F_15EX.Pylon12

    Pylon13 = F_15EX.Pylon13

    class Pylon14:
        F15EX_V3_F15E_EXTTANK = (14, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (14, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_260A = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_260A)
        F15EX_V3_LAU_115_2xAIM_120C_7 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_AIM200_4XRACK = (14, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B = (14, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    Pylon15 = F_15EX.Pylon15


@planemod
class F_15IA(F_15EX):
    id = "F15IA"
    payloads = None
    fuel_max = 10571
    livery_name = "F-15IA"

    class Pylon1:
        F15EX_V3_F15EX_2xAIM_120D_3 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D_3)
        F15EX_V3_F15EX_2xAIM_120D = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D)
        F15EX_V3_F15EX_2xAIM_120C_8 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_8)
        F15EX_V3_F15EX_2xAIM_120C_7 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_7)
        F15EX_V3_F15EX_2xAIM_120C_5 = (1, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_5)
        F15EX_V3_F15IA_PYTHON_5 = (1, WeaponsF15EX.F15EX_V3_F15IA_PYTHON_5)

    class Pylon2:
        F15EX_V3_F15E_EXTTANK = (2, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (2, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_120C_7 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (2, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            2,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_AIM200_4XRACK = (2, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B = (2, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    class Pylon3:
        F15EX_V3_F15EX_AIM_120C_8_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA2A,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA2A,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA2A,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA2A,
        )
        F15EX_V3_F15EX_AIM_120D_STA2A = (3, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA2A)
        F15EX_V3_F15EX_PYTHON_5_STA2A = (3, WeaponsF15EX.F15EX_V3_F15EX_PYTHON_5_STA2A)
        F15EX_V3_F15EX_AIM_9X_ED_STA2A = (
            3,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA2A,
        )

    class Pylon4:
        F15EX_V3_F15EX_AIM_120C_8_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA2B,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA2B,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA2B,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA2B,
        )
        F15EX_V3_F15EX_AIM_120D_STA2B = (4, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA2B)
        F15EX_V3_F15EX_PYTHON_5_STA2B = (4, WeaponsF15EX.F15EX_V3_F15EX_PYTHON_5_STA2B)
        F15EX_V3_F15EX_AIM_9X_ED_STA2B = (
            4,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA2B,
        )

    class Pylon5:
        F15EX_V3_AMBER_2xAIM120C8 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (5, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_F15EX_AIM_120C_8_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_F = (
            5,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_F = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_F)
        F15EX_V3_F15EX_AIM_200A_CFT_F = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_F)
        F15EX_V3_AIM200_4XRACK = (5, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B_CFT = (5, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B_CFT)

    class Pylon6:
        F15EX_V3_AMBER_2xAIM120C8 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (6, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AIM200_4XRACK = (6, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_120C_8_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_A = (
            6,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_A = (6, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_A)
        F15EX_V3_F15EX_AIM_200A_CFT_A = (6, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_A)

    class Pylon7:
        F15EX_V3_A111396E_D3E8_4b9c_8AC9_2432489304D5 = (
            7,
            weapon_ids["{A111396E-D3E8-4b9c-8AC9-2432489304D5}"],
        )
        F15EX_V3_F_15E_AAQ_14_LANTIRN = (7, weapon_ids["{F-15E_AAQ-14_LANTIRN}"])

    class Pylon8:
        F15EX_V3_AMBER_2xAIM120C8 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (8, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AIM200_4XRACK = (8, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15E_EXTTANK = (8, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (8, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_ASG_34_LegionPod = (8, WeaponsF15EX.F15EX_V3_ASG_34_LegionPod)

    Pylon9 = F_15EX.Pylon9

    class Pylon10:
        F15EX_V3_AMBER_2xAIM120C8 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (10, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_AIM200_4XRACK = (10, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_120C_8_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_200A_CFT_RA = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_RA,
        )
        F15EX_V3_F15EX_AIM_120C_8_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_A = (
            10,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_A,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_A = (10, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_A)
        F15EX_V3_F15EX_AIM_200A_CFT_A = (10, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_A)

    class Pylon11:
        F15EX_V3_AMBER_2xAIM120C8 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C8)
        F15EX_V3_AMBER_2xAIM120C7 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C7)
        F15EX_V3_AMBER_2xAIM120C5 = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120C5)
        F15EX_V3_AMBER_2xAIM120D = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D)
        F15EX_V3_AMBER_2xAIM120D_P3I = (11, WeaponsF15EX.F15EX_V3_AMBER_2xAIM120D_P3I)
        F15EX_V3_F15EX_AIM_120C_8_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_7_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120C_5_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_3_CFT_F = (
            11,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_CFT_F,
        )
        F15EX_V3_F15EX_AIM_120D_CFT_F = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_CFT_F)
        F15EX_V3_F15EX_AIM_200A_CFT_F = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_200A_CFT_F)
        F15EX_V3_AIM200_4XRACK = (11, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B_CFT = (11, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B_CFT)

    class Pylon12:
        F15EX_V3_F15EX_AIM_120C_8_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA11B,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA11B,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA11B,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA11B,
        )
        F15EX_V3_F15EX_AIM_120D_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA11B,
        )
        F15EX_V3_F15EX_PYTHON_5_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_PYTHON_5_STA11B,
        )
        F15EX_V3_F15EX_AIM_9X_ED_STA11B = (
            12,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA11B,
        )

    class Pylon13:
        F15EX_V3_F15EX_AIM_120C_8_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_8_STA11A,
        )
        F15EX_V3_F15EX_AIM_120C_7_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_7_STA11A,
        )
        F15EX_V3_F15EX_AIM_120C_5_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120C_5_STA11A,
        )
        F15EX_V3_F15EX_AIM_120D_3_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_3_STA11A,
        )
        F15EX_V3_F15EX_AIM_120D_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_120D_STA11A,
        )
        F15EX_V3_F15EX_PYTHON_5_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_PYTHON_5_STA11A,
        )
        F15EX_V3_F15EX_AIM_9X_ED_STA11A = (
            13,
            WeaponsF15EX.F15EX_V3_F15EX_AIM_9X_ED_STA11A,
        )

    class Pylon14:
        F15EX_V3_F15E_EXTTANK = (14, weapon_ids["{F15E_EXTTANK}"])
        F15EX_V3_F15E_EXTTANK_EMPTY = (14, weapon_ids["{F15E_EXTTANK_EMPTY}"])
        F15EX_V3_LAU_115_2xAIM_120C_7 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120C_7)
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_8 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_8,
        )
        F15EX_V3_LAU_115_2xAIM_120D_3 = (14, WeaponsF15EX.F15EX_V3_LAU_115_2xAIM_120D_3)
        F15EX_V3_F15EX_LAU_115_2xAIM_120D = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120D,
        )
        F15EX_V3_F15EX_LAU_115_2xAIM_120C_5 = (
            14,
            WeaponsF15EX.F15EX_V3_F15EX_LAU_115_2xAIM_120C_5,
        )
        F15EX_V3_AIM200_4XRACK = (14, WeaponsF15EX.F15EX_V3_AIM200_4XRACK)
        F15EX_V3_F15EX_AIM_174B = (14, WeaponsF15EX.F15EX_V3_F15EX_AIM_174B)

    class Pylon15:
        F15EX_V3_F15IA_PYTHON_5 = (15, WeaponsF15EX.F15EX_V3_F15IA_PYTHON_5)
        F15EX_V3_F15EX_2xAIM_120D_3 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D_3)
        F15EX_V3_F15EX_2xAIM_120D = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120D)
        F15EX_V3_F15EX_2xAIM_120C_8 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_8)
        F15EX_V3_F15EX_2xAIM_120C_7 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_7)
        F15EX_V3_F15EX_2xAIM_120C_5 = (15, WeaponsF15EX.F15EX_V3_F15EX_2xAIM_120C_5)
