"""Explicit ground mobility; missing data never implies self propulsion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MobilityMode(Enum):
    UNKNOWN = "unknown"
    FIXED = "fixed"
    SELF_PROPELLED = "self_propelled"
    TOWED = "towed"


@dataclass(frozen=True)
class GroundMobility:
    mode: MobilityMode = MobilityMode.UNKNOWN
    can_tow: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, MobilityMode) or type(self.can_tow) is not bool:
            raise ValueError("Invalid ground mobility data")
        if self.can_tow and self.mode is not MobilityMode.SELF_PROPELLED:
            raise ValueError("A tractor must be self propelled")

    @classmethod
    def from_data(cls, data: Any) -> GroundMobility:
        if data is None:
            return cls()
        if not isinstance(data, dict) or set(data) - {"mode", "can_tow"}:
            raise ValueError("Invalid ground mobility fields")
        return cls(
            MobilityMode(data.get("mode", "unknown")), data.get("can_tow", False)
        )
