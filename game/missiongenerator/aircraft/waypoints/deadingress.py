import logging
import math

from dcs.point import MovingPoint
from dcs.task import AttackGroup, Bombing, OptECMUsing, WeaponType, Expend
from dcs.weapons_data import weapon_ids

from game.gpsjamming import (
    GPS_CRUISE_MISSILE_PATTERNS,
    GPS_GLIDE_WEAPON_PATTERNS,
    GPS_GUIDED_BOMB_PATTERNS,
)
from game.theater import TheaterGroundObject
from .pydcswaypointbuilder import PydcsWaypointBuilder

# DCS Weapon.flag values not named in pydcs's WeaponType enum.
SATELLITE_GUIDED_BOMB = 1 << 3  # SNSGB
FIRE_AND_FORGET_ASM = 1 << 18  # FireAndForgetASM


class DeadIngressBuilder(PydcsWaypointBuilder):
    def _coordinate_attack_mask(self) -> int:
        # Use the exported payload so this also sees date substitutions and racks.
        clsids = {
            pylon["CLSID"]
            for unit in self.group.units
            for pylon in unit.pylons.values()
        }
        names = []
        for clsid in clsids:
            data = weapon_ids.get(clsid)
            name = data.get("name", "") if isinstance(data, dict) else ""
            names.append(f"{clsid} {name}".upper().replace("-", "_").replace(" ", "_"))
        mask = 0
        for patterns, flags in (
            (GPS_GUIDED_BOMB_PATTERNS, SATELLITE_GUIDED_BOMB),
            (GPS_GLIDE_WEAPON_PATTERNS, FIRE_AND_FORGET_ASM | SATELLITE_GUIDED_BOMB),
            (GPS_CRUISE_MISSILE_PATTERNS, WeaponType.CruiseMissile.value),
        ):
            if any(pattern in name for pattern in patterns for name in names):
                mask |= flags
        return mask

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

        coordinate_mask = self._coordinate_attack_mask()
        for group in target.groups:
            miz_group = self.mission.find_group(group.group_name)
            if miz_group is None:
                logging.error(
                    f"Could not find group for DEAD mission {group.group_name}"
                )
                continue

            task = AttackGroup(
                miz_group.id,
                weapon_type=WeaponType.ARM,
                expend=Expend.All,
                altitude=waypoint.alt,
                group_attack=True,
            )
            waypoint.tasks.append(task)

            for weapon_type, expend, group_attack in (
                (WeaponType.ASM, Expend.All, True),
                (WeaponType.GuidedBombs, Expend.Auto, False),
            ):
                point_mask = (
                    weapon_type.value & coordinate_mask if miz_group.units else 0
                )
                if point_mask:
                    # DCS can skip group tasks with coordinate-guided stores.
                    # The point is fixed at the group's position in the exported mission.
                    bombing = Bombing(
                        miz_group.units[0].position,
                        weapon_type=weapon_type,
                        expend=expend,
                        altitude=waypoint.alt,
                        group_attack=group_attack,
                    )
                    bombing.params["weaponType"] = point_mask
                    waypoint.tasks.append(bombing)

                task = AttackGroup(
                    miz_group.id,
                    weapon_type=weapon_type,
                    expend=expend,
                    altitude=waypoint.alt,
                    group_attack=group_attack,
                )
                task.params["weaponType"] &= ~point_mask
                waypoint.tasks.append(task)

            dir = target.position.heading_between_point(waypoint.position)

            task = AttackGroup(
                miz_group.id,
                weapon_type=WeaponType.Unguided,
                attack_limit=1,
                expend=Expend.All,
                direction=math.radians(dir),
                altitude=waypoint.alt,
            )
            task.params["altitudeEnabled"] = False
            waypoint.tasks.append(task)
