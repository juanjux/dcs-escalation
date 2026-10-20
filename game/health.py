"""Health and automatic recovery reported by the map and planner APIs."""

from pydantic import BaseModel


class UnitHealthStatus(BaseModel):
    """Repair amounts are percentage points of original maximum health."""

    id: int
    name: str
    health_percent: float
    persistent: bool
    damage_repaired_per_turn_percent: int
    repair_next_turn_percent: float
    health_next_turn_percent: float


class HealthStatus(BaseModel):
    """Group health averages include destroyed units at zero health."""

    health_percent: float
    damage_repaired_per_turn_percent: int
    repair_next_turn_percent: float
    health_next_turn_percent: float
    units: list[UnitHealthStatus]
