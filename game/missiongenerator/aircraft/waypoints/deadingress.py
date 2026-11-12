import logging
import math

from dcs.point import MovingPoint
from dcs.task import AttackGroup, Bombing, Expend, OptECMUsing, WeaponType
from dcs.weapons_data import weapon_ids

from game.data.fueltanks import external_fuel
from game.data.weapons import Weapon, WeaponType as LoadoutWeaponType
from game.gpsjamming import (
    GPS_CRUISE_MISSILE_PATTERNS,
    GPS_GLIDE_WEAPON_PATTERNS,
    GPS_GUIDED_BOMB_PATTERNS,
)
from game.theater import TheaterGroundObject
from .pydcswaypointbuilder import PydcsWaypointBuilder

GPS_AIR_STORE_PATTERNS = (
    *GPS_GUIDED_BOMB_PATTERNS,
    *GPS_GLIDE_WEAPON_PATTERNS,
    *GPS_CRUISE_MISSILE_PATTERNS,
)
SUPPORT_STORE_TYPES = {
    LoadoutWeaponType.TGP,
    LoadoutWeaponType.DECOY,
    LoadoutWeaponType.JAMMER,
    LoadoutWeaponType.OFFENSIVE_JAMMER,
}


class DeadIngressBuilder(PydcsWaypointBuilder):
    def _uses_coordinate_tasks(self) -> bool:
        # Use the exported payload so this also sees date substitutions and racks.
        clsids = {
            pylon["CLSID"]
            for unit in self.group.units
            for pylon in unit.pylons.values()
        }
        has_gps_store = False
        for clsid in clsids:
            data = weapon_ids.get(clsid)
            name = str(data.get("name", "")) if isinstance(data, dict) else ""
            store = f"{clsid} {name}".upper().replace("-", "_").replace(" ", "_")
            if any(pattern in store for pattern in GPS_AIR_STORE_PATTERNS):
                has_gps_store = True
                continue
            if (
                clsid == "<CLEAN>"
                or name.upper().startswith("AIM-")
                or "AAM" in store.split("_")
                or external_fuel(clsid) is not None
            ):
                continue
            weapon = Weapon.with_clsid(clsid)
            if weapon is not None and weapon.weapon_group.type in SUPPORT_STORE_TYPES:
                continue
            # An ARM, another strike weapon, or an unknown store may need group tasking.
            return False
        return has_gps_store

    def add_tasks(self, waypoint: MovingPoint) -> None:
        self.register_special_strike_points(self.waypoint.targets)
        self.register_special_ingress_points()

        target = self.package.target
        if not isinstance(target, TheaterGroundObject):
            logging.error(
                "Unexpected target type for DEAD mission: %s",
                target.__class__.__name__,
            )
            return

        # Preemptively use ECM to better avoid getting swatted.
        ecm_option = OptECMUsing(value=OptECMUsing.Values.UseIfDetectedLockByRadar)
        waypoint.tasks.append(ecm_option)

        use_coordinates = self._uses_coordinate_tasks()
        for group in target.groups:
            miz_group = self.mission.find_group(group.group_name)
            if miz_group is None:
                logging.error(
                    "Could not find group for DEAD mission %s", group.group_name
                )
                continue

            direction = target.position.heading_between_point(waypoint.position)
            tasks = [
                AttackGroup(
                    miz_group.id,
                    weapon_type=WeaponType.ARM,
                    expend=Expend.All,
                    altitude=waypoint.alt,
                    group_attack=True,
                ),
                AttackGroup(
                    miz_group.id,
                    weapon_type=WeaponType.ASM,
                    expend=Expend.All,
                    altitude=waypoint.alt,
                    group_attack=True,
                ),
                AttackGroup(
                    miz_group.id,
                    weapon_type=WeaponType.GuidedBombs,
                    altitude=waypoint.alt,
                ),
                AttackGroup(
                    miz_group.id,
                    weapon_type=WeaponType.Unguided,
                    attack_limit=1,
                    expend=Expend.All,
                    direction=math.radians(direction),
                    altitude=waypoint.alt,
                ),
            ]
            tasks[-1].params["altitudeEnabled"] = False
            if use_coordinates and miz_group.units:
                # Keep the full task order and parameters of the point sequence
                # verified in DCS. The point comes from the exported group's lead.
                for task in tasks:
                    bombing = Bombing(miz_group.units[0].position)
                    bombing.params.update(task.params)
                    del bombing.params["groupId"]
                    waypoint.tasks.append(bombing)
            else:
                waypoint.tasks.extend(tasks)
