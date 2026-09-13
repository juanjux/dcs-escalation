from __future__ import annotations

import copy
import datetime
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Iterator, Optional, TYPE_CHECKING, Type, Dict, Any

from dcs.unittype import FlyingType

from game.ato.flighttype import FlightType
from game.data.weapons import Pylon, Weapon, WeaponType
from game.dcs.aircrafttype import AircraftType
from game.factions.faction import Faction
from game.persistency import payloads_dir, prefer_liberation_payloads
from game.utils import Distance, max_optional_distance

if TYPE_CHECKING:
    from .flight import Flight
    from game.theater import MissionTarget


# Default-loadout overrides: the payload editor's "Set as default" button lets a
# user mark a specific named payload as the default for an aircraft + flight type.
# Stored globally (all campaigns) next to the DCS payload files, keyed by aircraft
# id then FlightType name. default_for_task_and_aircraft consults these before the
# "Escalation <task>" name conventions. This only changes WHICH named payload is
# picked as default; it never renames or overwrites a payload.
_DEFAULT_LOADOUT_OVERRIDES_FILE = "retribution_default_loadouts.json"


def _default_loadout_overrides_path() -> Path:
    return payloads_dir() / _DEFAULT_LOADOUT_OVERRIDES_FILE


def load_default_loadout_overrides() -> Dict[str, Dict[str, str]]:
    try:
        with _default_loadout_overrides_path().open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get_default_loadout_override(aircraft_id: str, task: FlightType) -> Optional[str]:
    return load_default_loadout_overrides().get(aircraft_id, {}).get(task.name)


def _write_default_loadout_overrides(data: Dict[str, Dict[str, str]]) -> None:
    # Written via a temporary file and replaced in one step: a half-written JSON here
    # would silently drop every default the user has set.
    path = _default_loadout_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def set_default_loadout_override(
    aircraft_id: str, task: FlightType, payload_name: str
) -> None:
    data = load_default_loadout_overrides()
    data.setdefault(aircraft_id, {})[task.name] = payload_name
    _write_default_loadout_overrides(data)


def clear_default_loadout_override(aircraft_id: str, task: FlightType) -> bool:
    """Drop the default for this aircraft + task. True if there was one to drop."""
    data = load_default_loadout_overrides()
    per_aircraft = data.get(aircraft_id)
    if not per_aircraft or task.name not in per_aircraft:
        return False
    del per_aircraft[task.name]
    if not per_aircraft:
        del data[aircraft_id]
    _write_default_loadout_overrides(data)
    return True


class Loadout:
    def __init__(
        self,
        name: str,
        pylons: Dict[int, Optional[Weapon]],
        date: Optional[datetime.date],
        is_custom: bool = False,
        pylon_settings: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        self.name = name
        # We clear unused pylon entries on initialization, but UI actions can still
        # cause a pylon to be emptied, so make the optional type explicit.
        self.pylons: Dict[int, Optional[Weapon]] = {
            k: v for k, v in pylons.items() if v is not None
        }
        self.date = date
        self.is_custom = is_custom
        # Store weapon settings per pylon (pylon_number -> settings_dict)
        self.pylon_settings: Dict[int, Dict[str, Any]] = pylon_settings or {}

    def __setstate__(self, state: Dict[str, Any]) -> None:
        """Handle loading from old save files that don't have pylon_settings."""
        # Ensure pylon_settings exists for backwards compatibility
        if "pylon_settings" not in state:
            state["pylon_settings"] = {}
        self.__dict__.update(state)

    def derive_custom(self, name: str) -> Loadout:
        return Loadout(
            name,
            self.pylons,
            self.date,
            is_custom=True,
            pylon_settings=self.pylon_settings.copy(),
        )

    def clone(self) -> Loadout:
        return Loadout(
            self.name,
            dict(self.pylons),
            copy.deepcopy(self.date),
            self.is_custom,
            copy.deepcopy(self.pylon_settings),
        )

    def has_weapon_of_type(self, weapon_type: WeaponType) -> bool:
        for weapon in self.pylons.values():
            if weapon is not None and weapon.weapon_group.type is weapon_type:
                return True
        return False

    def max_standoff_range(self) -> Optional[Distance]:
        """The longest stand-off launch range among the equipped weapons, if any."""
        return max_optional_distance(
            weapon.launch_range for weapon in self.pylons.values() if weapon
        )

    @staticmethod
    def _fallback_for(
        weapon: Weapon,
        pylon: Pylon,
        date: datetime.date,
        faction: Faction,
        skip_types: Optional[Iterable[WeaponType]] = None,
    ) -> Optional[Weapon]:
        if skip_types is None:
            skip_types = set()
        for fallback in weapon.fallbacks:
            if not pylon.can_equip(fallback):
                continue
            if not fallback.available_on(date, faction):
                continue
            if fallback.weapon_group.type in skip_types:
                continue
            return fallback
        return None

    def degrade_for_date(
        self,
        unit_type: AircraftType,
        date: datetime.date,
        faction: Faction,
        target: Optional["MissionTarget"] = None,
    ) -> Loadout:
        if self.date is not None and self.date <= date:
            return Loadout(
                self.name,
                self.pylons,
                self.date,
                self.is_custom,
                pylon_settings=self.pylon_settings.copy(),
            )

        new_pylons = dict(self.pylons)
        new_settings = self.pylon_settings.copy()
        for pylon_number, weapon in self.pylons.items():
            if weapon is None:
                del new_pylons[pylon_number]
                new_settings.pop(pylon_number, None)
                continue
            if not weapon.available_on(date, faction):
                pylon = Pylon.for_aircraft(unit_type, pylon_number)
                fallback = self._fallback_for(weapon, pylon, date, faction)
                if fallback is None:
                    del new_pylons[pylon_number]
                    new_settings.pop(pylon_number, None)
                else:
                    new_pylons[pylon_number] = fallback
                    new_settings.pop(pylon_number, None)
        loadout = Loadout(
            self.name,
            new_pylons,
            date,
            self.is_custom,
            pylon_settings=new_settings,
        )
        # If this is not a custom loadout, we should replace any LGBs with iron bombs if
        # the loadout lost its TGP.
        #
        # If the loadout was chosen explicitly by the user, assume they know what
        # they're doing. They may be coordinating buddy-lase.
        if not loadout.is_custom:
            loadout.replace_lgbs_if_no_tgp(unit_type, date, faction)

        # Apply target-based weapon settings to the degraded loadout if a target is provided
        if target is not None:
            loadout.apply_target_overrides(target)

        return loadout

    def replace_lgbs_if_no_tgp(
        self, unit_type: AircraftType, date: datetime.date, faction: Faction
    ) -> None:
        if self.has_weapon_of_type(WeaponType.TGP):
            return

        if unit_type.has_built_in_target_pod:
            return

        new_pylons = dict(self.pylons)
        for pylon_number, weapon in self.pylons.items():
            if weapon is not None and weapon.weapon_group.type is WeaponType.LGB:
                pylon = Pylon.for_aircraft(unit_type, pylon_number)
                fallback = self._fallback_for(
                    weapon, pylon, date, faction, skip_types={WeaponType.LGB}
                )
                if fallback is None:
                    del new_pylons[pylon_number]
                    self.pylon_settings.pop(pylon_number, None)
                else:
                    new_pylons[pylon_number] = fallback
                    self.pylon_settings.pop(pylon_number, None)
        self.pylons = new_pylons

    def apply_target_overrides(self, target: "MissionTarget") -> None:
        """Apply target-based weapon setting overrides to this loadout.

        This applies weapon-specific settings defined in the weapon YAML files
        for the given target type to all weapons in this loadout.
        """
        # Convert loadout to pydcs payload format for reuse of adjust_payload_for_target
        payload = [
            (pylon_num, {"clsid": weapon.clsid, "settings": {}})
            for pylon_num, weapon in self.pylons.items()
            if weapon is not None
        ]

        # Use the existing method to apply target-based settings
        adjusted_payload = self.adjust_payload_for_target(payload, target)

        # Extract the updated settings and apply them to our loadout
        for pylon_number, pylon_data in adjusted_payload:
            if "settings" in pylon_data and pylon_data["settings"]:
                self.pylon_settings[pylon_number] = pylon_data["settings"]

    @classmethod
    def iter_for(cls, flight: Flight) -> Iterator[Loadout]:
        return cls.iter_for_aircraft(flight.unit_type)

    @classmethod
    def iter_for_aircraft(cls, aircraft: AircraftType) -> Iterator[Loadout]:
        # Dict of payload ID (numeric) to:
        #
        # {
        #   "name": The name the user set in the ME
        #   "pylons": List (as a dict) of dicts of:
        #       {"CLSID": class ID, "num": pylon number}
        #   "tasks": List (as a dict) of task IDs the payload is used by.
        # }
        payloads = aircraft.dcs_unit_type.load_payloads()
        for payload in payloads.values():
            if not cls.valid_payload(payload["pylons"]):
                msg = f'Incompatible loadout for {aircraft} skipped: {payload["name"]}'
                logging.warning(msg)
                continue
            name = payload["name"]
            pylons = payload["pylons"]
            try:
                yield Loadout(
                    name,
                    {p["num"]: Weapon.with_clsid(p["CLSID"]) for p in pylons.values()},
                    date=None,
                    pylon_settings={
                        p["num"]: p.get("settings", {}) for p in pylons.values()
                    },
                )
            except KeyError:
                # invalid loadout
                continue

    @staticmethod
    def valid_payload(pylons: Dict[int, Dict[str, str]]) -> bool:
        for p in pylons.values():
            # An empty pylon is a pylon carrying nothing, not an unknown store.
            # Treating it as invalid threw away whole payloads: the Tornado IDS
            # "STRIKE" fit leaves stations 5-8 free, so the aircraft was planned
            # with no loadout at all rather than with its GBU-16s.
            if not p["CLSID"]:
                continue
            if Weapon.with_clsid(p["CLSID"]) is None:
                return False
        return True

    @classmethod
    def default_loadout_names_for(cls, task: FlightType) -> Iterator[str]:
        # This is a list of mappings from the FlightType of a Flight to the type of
        # payload defined in the resources/payloads/UNIT_TYPE.lua file. A Flight has no
        # concept of a PyDCS task, so COMMON_OVERRIDE cannot be used here. This is used
        # in the payload editor, for setting the default loadout of an object. The left
        # element is the FlightType name, and the right element is a tuple containing
        # what is used in the lua file. Some aircraft differ from the standard loadout
        # names, so those have been included here too. The priority goes from first to
        # last - the first element in the tuple will be tried first, then the second,
        # etc.
        # The payload names keep the old spelling: they are strings inside the
        # player's own MissionEditor/UnitPayloads, put there by every version of this
        # program and by Liberation before it. A renamed application still has to find
        # the loadouts already on his disk.
        loadout_names = {
            t: (
                [f"Liberation {t.value}", f"Retribution {t.value}"]
                if prefer_liberation_payloads()
                else [f"Retribution {t.value}", f"Liberation {t.value}"]
            )
            for t in FlightType
        }
        legacy_names = {
            FlightType.TARCAP: (
                "CAP HEAVY",
                "CAP",
                "Retribution BARCAP",
                "Liberation BARCAP",
            ),
            FlightType.BARCAP: (
                "CAP HEAVY",
                "CAP",
                "Retribution TARCAP",
                "Liberation TARCAP",
            ),
            FlightType.CAS: ("CAS MAVERICK F", "CAS"),
            FlightType.STRIKE: ("STRIKE",),
            FlightType.ANTISHIP: ("ANTISHIP",),
            FlightType.DEAD: ("DEAD",),
            FlightType.SEAD: ("SEAD",),
            FlightType.BAI: ("BAI",),
            FlightType.OCA_RUNWAY: ("RUNWAY_ATTACK", "RUNWAY_STRIKE"),
            FlightType.OCA_AIRCRAFT: ("OCA",),
        }
        for flight_type, names in legacy_names.items():
            loadout_names[flight_type].extend(names)
        # A SEAD escort typically does not need a different loadout than a regular
        # SEAD flight, so fall back to SEAD if needed.
        loadout_names[FlightType.SEAD_ESCORT].extend(loadout_names[FlightType.SEAD])
        loadout_names[FlightType.SEAD_SWEEP].extend(
            loadout_names[FlightType.SEAD_ESCORT]
        )
        # Sweep and escort can fall back to TARCAP.
        loadout_names[FlightType.ESCORT].extend(loadout_names[FlightType.TARCAP])
        loadout_names[FlightType.SWEEP].extend(loadout_names[FlightType.TARCAP])
        # Intercept can fall back to BARCAP.
        loadout_names[FlightType.INTERCEPTION].extend(loadout_names[FlightType.BARCAP])
        # OCA/Aircraft falls back to BAI, which falls back to CAS.
        loadout_names[FlightType.BAI].extend(loadout_names[FlightType.CAS])
        loadout_names[FlightType.ARMED_RECON].extend(loadout_names[FlightType.CAS])
        loadout_names[FlightType.OCA_AIRCRAFT].extend(loadout_names[FlightType.BAI])
        # DEAD also falls back to BAI.
        loadout_names[FlightType.DEAD].extend(loadout_names[FlightType.BAI])
        # OCA/Runway falls back to Strike
        loadout_names[FlightType.OCA_RUNWAY].extend(loadout_names[FlightType.STRIKE])
        yield from loadout_names[task]

    @classmethod
    def default_for(cls, flight: Flight) -> Loadout:
        return cls.default_for_task_and_aircraft(
            flight.flight_type, flight.unit_type.dcs_unit_type, flight.package.target
        )

    @classmethod
    def default_for_task_and_aircraft(
        cls,
        task: FlightType,
        dcs_unit_type: Type[FlyingType],
        target: Optional[MissionTarget] = None,
    ) -> Loadout:
        # This is cached, but must be called before loadout_by_name will work. A
        # malformed or unsupported payload .lua (e.g. from a third-party mod)
        # makes pydcs raise while parsing it; fall back to an empty loadout
        # instead of aborting mission planning for the whole turn.
        try:
            dcs_unit_type.load_payloads()
        except Exception:
            logging.exception(
                "Could not load payloads for %s; using an empty loadout. This is "
                "usually a malformed or unsupported payload file, often from a "
                "third-party mod.",
                dcs_unit_type.id,
            )
            return cls.empty_loadout()

        # A user-chosen default (set via the payload editor's "Set as default"
        # button) takes priority over the "Escalation <task>" name conventions.
        # If its payload is missing or invalid we fall through to the conventions.
        names = list(cls.default_loadout_names_for(task))
        override = get_default_loadout_override(dcs_unit_type.id, task)
        if override:
            names = [override] + [n for n in names if n != override]

        # Iterate through each possible payload type for a given aircraft.
        # Some aircraft have custom loadouts that aren't in the standard set.
        for name in names:
            payload = dcs_unit_type.loadout_by_name(name)
            if payload is not None:
                if target:
                    payload = cls.adjust_payload_for_target(payload, target)
                pylons = {i: {"CLSID": d["clsid"]} for i, d in payload}
                if not cls.valid_payload(pylons):
                    aircraft = dcs_unit_type.id
                    msg = f"Incompatible loadout for {aircraft} skipped: {name}"
                    logging.warning(msg)
                    continue
                return Loadout(
                    name,
                    {i: Weapon.with_clsid(d["clsid"]) for i, d in payload},
                    date=None,
                    pylon_settings={i: d.get("settings", {}) for i, d in payload},
                )

        # TODO: Try group.load_task_default_loadout(loadout_for_task)
        return cls.empty_loadout()

    @classmethod
    def empty_loadout(cls) -> Loadout:
        return Loadout("Empty", {}, date=None)

    @classmethod
    def adjust_payload_for_target(cls, payload: Any, target: MissionTarget) -> Any:
        """
        Apply target-based weapon settings overrides to a raw pydcs payload.

        This checks each weapon in the payload for target-specific settings overrides
        defined in the weapon YAML files and applies them.

        Args:
            payload: Raw pydcs payload (dict-like with pylon data containing clsid and settings)
            target: The mission target containing type information

        Returns:
            The payload with adjusted weapon settings, or the original if no adjustments apply
        """
        if not target:
            return payload

        from game.theater import TheaterGroundObject
        from game.transfers import Convoy

        targets: tuple[Any, ...] = ()
        unit: Any
        if isinstance(target, Convoy):
            for unit in target.units:
                if unit.dcs_unit_type and unit.dcs_unit_type.id:
                    targets += (unit.dcs_unit_type.id,)
        elif isinstance(target, TheaterGroundObject):
            for unit in target.units:
                if unit.type and unit.type.id:
                    targets += (unit.type.id,)

        if not targets:
            return payload

        adjusted_payload = copy.deepcopy(payload)

        # payload is a list of (pylon_number, pylon_data) tuples
        for pylon_number, pylon_data in adjusted_payload:
            clsid = pylon_data.get("clsid")
            if not clsid:
                continue

            weapon = Weapon.with_clsid(clsid)
            if weapon is None:
                continue

            # Get target-based overrides from the weapon definition
            target_overrides = weapon.get_target_overrides(targets)
            if target_overrides:
                pylon_data["settings"] = target_overrides

        return adjusted_payload
