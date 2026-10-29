"""DCS 2.9.31 native units missing from the pinned pydcs (RetLab #1413).

Keep upstream definitions when present. These are stock DCS assets, not units
gated by a CurrentHill mod-pack setting.
"""

from typing import Any, Callable

from dcs import planes, vehicles
from dcs.countries import Iraq
from dcs.unittype import VehicleType


def _native_vehicle(category: Any) -> Callable[[type[VehicleType]], type[VehicleType]]:
    def register(fallback: type[VehicleType]) -> type[VehicleType]:
        registered = vehicles.vehicle_map.setdefault(fallback.id, fallback)
        if not hasattr(category, fallback.__name__):
            setattr(category, fallback.__name__, registered)
        return registered

    return register


@_native_vehicle(vehicles.Armor)
class CHAP_ZTQ15(VehicleType):
    id = "CHAP_ZTQ15"
    name = "LT ZTQ-15 [CH]"
    detection_range = 0
    threat_range = 4000
    air_weapon_dist = 4000
    eplrs = True


@_native_vehicle(vehicles.Armor)
class CHAP_BMD2(VehicleType):
    id = "CHAP_BMD2"
    name = "IFV BMD-2 [CH]"
    detection_range = 5000
    threat_range = 2000
    air_weapon_dist = 2000


@_native_vehicle(vehicles.Armor)
class CHAP_Atlet(VehicleType):
    id = "CHAP_Atlet"
    name = "MRAP AMN-2 Atlet [CH]"
    detection_range = 0
    threat_range = 1000
    air_weapon_dist = 1000
    eplrs = True


@_native_vehicle(vehicles.AirDefence)
class CHAP_PGZ09(VehicleType):
    id = "CHAP_PGZ09"
    name = "SPAAG PGZ-09 [CH]"
    detection_range = 20000
    threat_range = 4000
    air_weapon_dist = 4000
    eplrs = True


@_native_vehicle(vehicles.AirDefence)
class CHAP_Ural4320_ZU232(VehicleType):
    id = "CHAP_Ural4320_ZU232"
    name = "AAA ZU-23-2 on Ural 4320 [CH]"
    detection_range = 0
    threat_range = 2500
    air_weapon_dist = 2500


@_native_vehicle(vehicles.Unarmed)
class CHAP_UralTyphoon(VehicleType):
    id = "CHAP_UralTyphoon"
    name = "MRAP Ural Typhoon-U [CH]"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@_native_vehicle(vehicles.Unarmed)
class CHAP_ZIL131(VehicleType):
    id = "CHAP_ZIL131"
    name = "Truck ZIL-131 [CH]"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@_native_vehicle(vehicles.Unarmed)
class CHAP_ZIL131_Kung(VehicleType):
    id = "CHAP_ZIL131_Kung"
    name = "Truck ZIL-131 Kung C2 [CH]"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


for _aircraft in (planes.MiG_25RBT, planes.MiG_23MLD, planes.IL_76MD):
    if not hasattr(Iraq.Plane, _aircraft.__name__):
        setattr(Iraq.Plane, _aircraft.__name__, _aircraft)
    if _aircraft not in Iraq.planes:
        Iraq.planes.append(_aircraft)
