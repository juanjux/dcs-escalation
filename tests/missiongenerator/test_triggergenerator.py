from types import SimpleNamespace
from typing import cast

from game.missiongenerator.triggergenerator import TriggerGenerator
from game.theater import ControlPoint
from game.theater.player import Player


def _condition_names(trigger: object) -> list[str]:
    return [type(rule).__name__ for rule in trigger.rules]  # type: ignore[attr-defined]


def test_recapture_trigger_reverts_on_attacker_absence() -> None:
    """A base must revert to its owner once the attackers leave/die the zone.

    The capture trigger still needs an attacker ground unit in the zone, but the
    recapture (revert) trigger must fire on attacker absence alone -- otherwise a
    base stays captured after the intruders are wiped out from the air, because no
    friendly ground unit ever re-enters the zone (only the gun- and bomb-trucks did).
    """
    # _create_capture_trigger only builds a TriggerCondition; it touches neither
    # self.mission nor self.game, so an uninitialised instance is enough.
    gen = object.__new__(TriggerGenerator)
    cp = cast(
        ControlPoint,
        SimpleNamespace(id="cp-1", full_name="Test Base", captured=Player.BLUE),
    )

    capture = gen._create_capture_trigger(1, 600, "red", "blue", 1, cp)
    recapture = gen._create_capture_trigger(
        1,
        600,
        "blue",
        "red",
        2,
        cp,
        flag_condition_true=True,
        require_capturing_in_zone=False,
    )

    # Capture still requires the attacker to physically hold the zone.
    capture_conditions = _condition_names(capture)
    assert "AllOfCoalitionOutsideZone" in capture_conditions
    assert "PartOfCoalitionInZone" in capture_conditions

    # Recapture reverts on attacker absence, with no friendly-ground requirement.
    recapture_conditions = _condition_names(recapture)
    assert "AllOfCoalitionOutsideZone" in recapture_conditions
    assert "FlagIsTrue" in recapture_conditions
    assert "PartOfCoalitionInZone" not in recapture_conditions
