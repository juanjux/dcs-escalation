"""DCS native mission actions, not mission-sandbox Lua functions."""

from typing import Any

from dcs.action import Action


class SetUnitHealth(Action):
    """UNIT AI SET LIFE takes a mission unit ID and a percentage, not a fraction."""

    def __init__(self, unit_id: int, fraction: float) -> None:
        super().__init__("a_unit_set_life_percentage")
        if not 0 < fraction <= 1:
            raise ValueError("Health must be a positive fraction no greater than one")
        self.unit_id = unit_id
        self.percent = fraction * 100
        self.params = [unit_id, self.percent]

    def dict(self) -> dict[str, Any]:
        return super().dict() | {"unit": self.unit_id, "life_percents": self.percent}
