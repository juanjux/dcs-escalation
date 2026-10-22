"""Gameplay capability profiles for the forthcoming Realistic CAS AFAC missions.

Profiles deliberately combine equipment across variants. They are not aircraft
specifications. This module does not enable missions or change existing sensors.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType


@dataclass(frozen=True)
class AFACCapabilities:
    family: str
    eo: bool = False
    ir: bool = False
    laser: bool = False
    ir_pointer: bool = False
    remote_operator: bool = False
    can_embark_jtac: bool = False
    embarked_jtac: bool = False

    @property
    def visual_only(self) -> bool:
        return not self.eo and not self.ir

    def equipment(self) -> dict[str, bool]:
        """Explicit metadata for the sensor and marking adapters, not DCS tasks."""
        return {
            "eo": self.eo,
            "ir": self.ir,
            "laser": self.laser,
            "irPointer": self.ir_pointer,
            "remoteOperator": self.remote_operator,
            "embarkedJTAC": self.embarked_jtac,
        }


def _catalogue() -> Mapping[str, AFACCapabilities]:
    result: dict[str, AFACCapabilities] = {}

    def add(profile: AFACCapabilities, *types: str) -> None:
        for type_name in types:
            if type_name in result:
                raise ValueError(f"Duplicate AFAC type: {type_name}")
            result[type_name] = profile

    for family, aliases in (
        ("Reaper", ("MQ-9 Reaper", "MQ-9")),
        ("Predator", ("RQ-1A Predator",)),
        ("Wing Loong", ("WingLoong-I",)),
        ("Bayraktar", ("TB-2 UCAV",)),
    ):
        add(
            AFACCapabilities(
                family,
                eo=True,
                ir=True,
                laser=True,
                ir_pointer=True,
                remote_operator=True,
            ),
            *aliases,
        )
    for family, aliases in (
        ("Kiowa", ("OH-58D", "OH58D")),
        ("Ka-52", ("CH_Ka52", "CH_Ka52K")),
        ("Black Hawk DAP", ("UH-60L_DAP",)),
        # The family maximum includes the Bronco's observation/designator variants.
        ("Bronco", ("Bronco-OV-10A",)),
    ):
        add(
            AFACCapabilities(family, eo=True, ir=True, laser=True, ir_pointer=True),
            *aliases,
        )
    add(
        AFACCapabilities(
            "Gazelle", eo=True, ir=True, ir_pointer=True, can_embark_jtac=True
        ),
        "SA342M",
        "SA342L",
        "SA342Minigun",
        "SA342Mistral",
    )
    add(
        AFACCapabilities("HKP15", eo=True, ir=True, can_embark_jtac=True),
        "HKP15B",
    )
    # The C-101 family's optional designator is a gameplay allowance. It does not
    # imply a thermal camera, and the generated mission still needs an adapter.
    add(AFACCapabilities("Aviojet", laser=True), "C-101CC", "C-101EB")
    for family, types in (
        ("Huey", ("UH-1H",)),
        ("Hip", ("Mi-8MT",)),
        ("Cayuse", ("OH-6A",)),
        ("Black Hawk", ("UH-60A", "UH-60L")),
        ("Hind", ("Mi-24P", "Mi-24V")),
        ("Chinook", ("CH-47D", "CH-47Fbl1")),
        ("Sea Stallion", ("CH-53E",)),
        ("Halo", ("Mi-26",)),
        ("Seahawk", ("SH-60B",)),
        ("Seasprite", ("uh2a", "uh2b", "uh2c", "sh2f")),
        ("Sea Knight", ("vwv_ch46d", "vwv_ch46d_late")),
        ("Osprey", ("V22_Osprey",)),
    ):
        add(AFACCapabilities(family, can_embark_jtac=True), *types)
    for family, types in (
        ("Albatros", ("L-39ZA", "L-39C")),
        ("Yak", ("Yak-52",)),
        ("MB-339", ("MB-339A",)),
        ("Bird Dog", ("vwv_o-1",)),
        ("Saab 105", ("SK-60",)),
    ):
        add(AFACCapabilities(family), *types)
    return MappingProxyType(result)


AFAC_AIRCRAFT = _catalogue()


def capabilities_for(
    type_name: str, *, embarked_jtac: bool = False
) -> AFACCapabilities | None:
    """Resolve an exact DCS ID; no name heuristics or generic helicopter defaults."""
    profile = AFAC_AIRCRAFT.get(type_name)
    if not embarked_jtac:
        return profile
    if profile is None or not profile.can_embark_jtac or profile.remote_operator:
        raise ValueError(f"Aircraft cannot embark an AFAC JTAC: {type_name}")
    return replace(
        profile, eo=True, ir=True, laser=True, ir_pointer=True, embarked_jtac=True
    )


def needs_night_warning(profile: AFACCapabilities, *, night: bool) -> bool:
    """Warn about missing thermal observation, not merely a missing IR pointer."""
    return night and not profile.ir


# Only exact, known loadouts contribute ammunition. Values count rounds, not
# racks. Duplicate racks must remain duplicated in the final pydcs payload.
# Illumination, countermeasures, aerobatic smoke and unknown mixed pods do not
# become an unlimited ground-marker supply.
_SMOKE: dict[str, int] = {
    "{M260_M156}": 7,
    "{M260_M259}": 7,
    "{M260_M274}": 7,
    "XM158_M156": 7,
    "XM158_M274": 7,
    "M261_MK156": 19,
    "{4F977A2A-CD25-44df-90EF-164BFA2AE72F}": 7,
    "{0877B74B-5A00-4e61-BA8A-A56450BA9E27}": 7,
    "UH60_LWL12_M156": 12,
    "UH60_LWL12_M259": 12,
    "UH60_LWL12_M274": 12,
}
for _color in ("Red", "Blue", "Green", "Yellow", "Violet", "White"):
    _SMOKE[f"OH58D_{_color}_Smoke_Grenade"] = 1
for _color in ("BLUE", "GREEN", "RED", "YELLOW"):
    _SMOKE[f"{{OH6_SMOKE_{_color}}}"] = 4
for _suffix in ("", "_GN", "_RD", "_WH", "_BU", "_YE", "_VT"):
    _SMOKE[f"B_8V20A_CM{_suffix}"] = 20
SMOKE_LOADOUTS: Mapping[str, int] = MappingProxyType(_SMOKE)


def smoke_rounds(payload_clsids: Iterable[str]) -> int:
    """Count a payload snapshot; the runtime must also account for spent stores."""
    return sum(SMOKE_LOADOUTS.get(clsid, 0) for clsid in payload_clsids)
