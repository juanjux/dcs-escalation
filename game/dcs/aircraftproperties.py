"""Campaign-date gating for era-specific aircraft *properties* (mission options).

This mirrors weapon date-gating (``game.data.weapons.Weapon.available_on``) but for
the DCS unit "properties" exposed in the payload editor — the per-airframe mission
options such as the pilot's helmet-mounted cueing system. Weapons carry an
introduction year in their data; properties do not, so each aircraft's own data file
supplies one: the ``date_gated_properties`` block in
``resources/units/aircraft/<type>.yaml`` maps a property identifier to
``{value label: introduction year}`` and loads into
``AircraftType.property_date_gate``, so lookup is a direct attribute access on the
airframe being configured — no shared table, no cross-airframe iteration.

The block is keyed by the property value *label* (e.g. ``"JHMCS"``), not the numeric
id. That is deliberate: the label pins the gate to what the option actually *is* — if
a DCS/pydcs update renumbers or renames a value, a label key degrades to "not gated"
instead of gating the wrong option (and a test pins the labels against pydcs so that
degradation is caught rather than shipped).

Only genuinely era-defining cueing systems belong in the data; the baseline options
(``Not installed``, ``Visor Only``, ``NVG``) are intentionally absent so they stay
available in every era. The whole layer is a no-op unless the campaign's
``restrict_props_by_date`` setting is on — independent of the weapons toggle so users
can enforce either or both.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterator, Mapping, Optional, Union

from dcs.unitpropertydescription import UnitPropertyDescription

#: The id type pydcs uses for ``UnitPropertyDescription.values`` keys.
PropertyValueId = Union[str, int, float, None]


@dataclass(frozen=True)
class PropertyDateGate:
    """Date gate for one airframe's era-specific property values.

    Built by :meth:`from_data` from the aircraft data file's
    ``date_gated_properties`` block. An empty gate (the default for the many
    airframes that declare no block) is falsy and gates nothing, so every method is
    safe to call unconditionally.
    """

    #: Property identifier -> value label -> real-world introduction year.
    introduction_years: Mapping[str, Mapping[str, int]] = field(default_factory=dict)

    @classmethod
    def from_data(cls, data: Optional[Mapping[str, Any]]) -> PropertyDateGate:
        """Build a gate from a yaml ``date_gated_properties`` block (or None)."""
        if not data:
            return cls()
        return cls(
            {
                str(identifier): {
                    str(label): int(year) for label, year in labels.items()
                }
                for identifier, labels in data.items()
            }
        )

    def __bool__(self) -> bool:
        return bool(self.introduction_years)

    def _introduction_year(
        self, prop: UnitPropertyDescription, value_id: PropertyValueId
    ) -> Optional[int]:
        """The introduction year for a property value, or None if not gated."""
        labels = self.introduction_years.get(prop.identifier)
        if labels is None or prop.values is None:
            return None
        label = prop.values.get(value_id)
        if label is None:
            return None
        return labels.get(label)

    def value_available_on(
        self,
        prop: UnitPropertyDescription,
        value_id: PropertyValueId,
        date: datetime.date,
    ) -> bool:
        """Whether a single property value is available at the campaign ``date``.

        Returns True for any value that is not date-gated (the common case), so
        callers can treat every non-gated property — and every era-appropriate
        gated option — as always available.
        """
        year = self._introduction_year(prop, value_id)
        if year is None:
            return True
        return date >= datetime.date(year, 1, 1)

    def available_value_ids(
        self, prop: UnitPropertyDescription, date: datetime.date
    ) -> list[PropertyValueId]:
        """The value ids of ``prop`` available at ``date``, in declared order."""
        if prop.values is None:
            return []
        return [
            value_id
            for value_id in prop.values
            if self.value_available_on(prop, value_id, date)
        ]

    def period_correct_value(
        self,
        prop: UnitPropertyDescription,
        current: PropertyValueId,
        date: datetime.date,
    ) -> PropertyValueId:
        """Clamp ``current`` to a value that is period-correct for ``prop`` at ``date``.

        Returns ``current`` unchanged when it is already available. Otherwise returns
        the first still-available value, which on every affected airframe is the
        baseline "no modern cueing" option (``Not installed`` / ``Visor Only``).
        Falls back to ``current`` if nothing is available (not expected for the
        curated data).
        """
        if self.value_available_on(prop, current, date):
            return current
        allowed = self.available_value_ids(prop, date)
        if not allowed:
            return current
        return allowed[0]

    def gated_props(
        self, properties: Mapping[str, UnitPropertyDescription]
    ) -> Iterator[UnitPropertyDescription]:
        """The subset of an airframe's ``properties`` this gate has data for.

        Iterates only the gated identifiers (not every property of the airframe), so
        a consumer clamping generated missions touches exactly the curated options.
        """
        for identifier in self.introduction_years:
            prop = properties.get(identifier)
            if prop is not None:
                yield prop


_NVG_SWITCHES = frozenset(
    {
        "MountNVG",
        "Night_Vision",  # Community A-4E-C
        "LoadNVGCase",
        "IsNvgAllowed",
        "PltNVG",
        "CpgNVG",
        "PilotNVG",
        "OperatorNVG",
    }
)
_HELMET_DEVICE_PROPERTIES = frozenset(
    {"HelmetMountedDevice", "HelmetMountedDeviceWSO", "Helmet-mounted device"}
)
_HELMET_OPT_OUT_LABELS = frozenset(
    {"Not installed", "Visor Only", "Helmet Only, No Visor"}
)


_NVG_DEVICE_LABELS = ("HMCS + NVG", "NVG")

# Verified cockpit equipment without a corresponding DCS mission property.
# See docs/game/night-vision.rst for the module and mod references.
_COCKPIT_NVG_AIRCRAFT = frozenset(
    {
        "A-10C",
        "CH-47Fbl1",
        "F-14A-95-GR",
        "F-14A-135-GR",
        "F-14A-135-GR-Early",
        "F-14B",
        "F-14BU",
        "F15EX",
        "F15EX_CFT",
        "F15IA",
        "JF-17",
        "Ka-50",
        "Mi-8MT",
        "OH-6A",
        "OH58D",
        "SA342M",
        "SA342Minigun",
        "UH-1H",
        "UH-60L",
        "UH-60L_DAP",
    }
)


class NightVision(Enum):
    MISSION_PROPERTY = auto()
    COCKPIT = auto()


def _is_nvg_property(prop: UnitPropertyDescription) -> bool:
    if prop.control == "checkbox":
        return prop.identifier in _NVG_SWITCHES
    return (
        prop.identifier in _HELMET_DEVICE_PROPERTIES
        and prop.values is not None
        and any(label in _NVG_DEVICE_LABELS for label in prop.values.values())
    )


def night_vision_support(
    aircraft_id: str, properties: Mapping[str, UnitPropertyDescription]
) -> NightVision | None:
    if any(_is_nvg_property(prop) for prop in properties.values()):
        return NightVision.MISSION_PROPERTY
    if aircraft_id in _COCKPIT_NVG_AIRCRAFT:
        return NightVision.COCKPIT
    return None


def night_vision_overrides(
    properties: Mapping[str, UnitPropertyDescription],
    overrides: Mapping[str, bool | float | int | str],
    gate: PropertyDateGate,
    date: datetime.date,
) -> Iterator[tuple[str, bool | float | int | str]]:
    """Select the available NVG configuration for each crew position."""
    for identifier, prop in properties.items():
        if not _is_nvg_property(prop):
            continue
        if prop.control == "checkbox":
            if identifier not in overrides and prop.default is not True:
                yield identifier, True
            continue
        if prop.values is None:
            continue

        current = overrides.get(identifier)
        if current is not None and (
            current not in prop.values or prop.values[current] in _HELMET_OPT_OUT_LABELS
        ):
            continue

        available = {
            prop.values[value_id]: value_id
            for value_id in gate.available_value_ids(prop, date)
            if value_id is not None
        }
        device = next(
            (available[label] for label in _NVG_DEVICE_LABELS if label in available),
            None,
        )
        if device is not None and device != overrides.get(identifier, prop.default):
            yield identifier, device
