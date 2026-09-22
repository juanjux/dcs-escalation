# Requires Turkish Military Assets for DCS by Currenthill:
# https://www.currenthill.com/turkey
#

from typing import Set

from dcs import task
from dcs.planes import PlaneType

from game.modsupport import planemod
from pydcs_extensions.weapon_injector import inject_weapons


class WeaponsTR:
    MAM_C = {"clsid": "{MAMC}", "name": "MAM-C", "weight": 6.5}
    MAM_L = {"clsid": "{MAML}", "name": "MAM-L", "weight": 22}


inject_weapons(WeaponsTR)


@planemod
class TB_2_UCAV(PlaneType):
    id = "TB-2 UCAV"
    height = 4.2
    width = 12
    length = 6.5
    fuel_max = 200
    max_speed = 220
    category = "UAV"
    # No cockpit: the mod is AI only, and the airframe carries no radio of its own.
    radio_frequency = 251

    livery_name = "TB-2 UCAV"  # from type

    class Pylon1:
        MAM_C = (1, WeaponsTR.MAM_C)

    class Pylon2:
        MAM_C = (2, WeaponsTR.MAM_C)
        MAM_L = (2, WeaponsTR.MAM_L)

    class Pylon3:
        MAM_C = (3, WeaponsTR.MAM_C)
        MAM_L = (3, WeaponsTR.MAM_L)

    class Pylon4:
        MAM_C = (4, WeaponsTR.MAM_C)

    pylons: Set[int] = {1, 2, 3, 4}

    tasks = [
        task.CAS,
        task.GroundAttack,
        task.AFAC,
        task.Reconnaissance,
    ]
    task_default = task.Reconnaissance
