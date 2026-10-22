"""Ground air-defence envelopes for AFAC; unknown ceilings forbid overflight."""

from functools import cache
import math
from typing import Any

from dcs.vehicles import AirDefence, vehicle_map

from game.data.units import ANTI_AIR_UNIT_CLASSES
from game.dcs.groundunittype import GroundUnitType

# DCS TechWeaponPack: ZSU_57_2.lua and LN_t.S_60_gun in weapons/cannon.lua
# both define max_trg_alt = 4000 m. Do not infer ceilings from horizontal range.
VERIFIED_CEILINGS = {"ZSU_57_2": 4000, "S-60_Type59_Artillery": 4000}


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
