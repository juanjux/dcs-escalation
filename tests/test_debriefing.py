from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from game.debriefing import (
    AirLosses,
    BaseCaptureEvent,
    Debriefing,
    GroundLosses,
    SideLossCounts,
)
from game.theater import ControlPoint, Player


def _items(n: int) -> list[Any]:
    """n placeholder loss objects. loss_counts only needs list length."""
    return [MagicMock() for _ in range(n)]


def _airlift(cargo_size: int) -> Any:
    """An airlift loss whose .cargo has the given length."""
    return SimpleNamespace(cargo=list(range(cargo_size)))


def _capture(captured_by: Player) -> BaseCaptureEvent:
    return BaseCaptureEvent(cast(ControlPoint, MagicMock()), captured_by)


def _sample_debriefing() -> Debriefing:
    """A Debriefing with known per-side losses, built without the heavy
    __init__ (which needs a Game and UnitMap). loss_counts and the loss
    properties only read air_losses, ground_losses, and base_captures."""
    air = AirLosses(player=_items(1), enemy=_items(2))
    ground = GroundLosses(
        player_front_line=_items(3),
        enemy_front_line=_items(1),
        player_motorpool=_items(2),
        enemy_motorpool=_items(3),
        player_convoy=_items(2),
        enemy_convoy=_items(0),
        player_cargo_ships=_items(1),
        enemy_cargo_ships=_items(4),
        player_airlifts=[_airlift(2)],
        enemy_airlifts=[_airlift(1), _airlift(3)],
        player_ground_objects=_items(5),
        enemy_ground_objects=_items(2),
        player_scenery=_items(0),
        enemy_scenery=_items(1),
        player_airfields=_items(1),
        enemy_airfields=_items(2),
    )
    captures = [
        _capture(Player.BLUE),
        _capture(Player.BLUE),
        _capture(Player.RED),
    ]
    debriefing = Debriefing.__new__(Debriefing)
    debriefing.air_losses = air
    debriefing.ground_losses = ground
    debriefing.base_captures = captures
    # The aircraft headline honours the "crashes don't count" doctrine, so
    # loss_counts reads game.settings; stub it (off = count every air loss).
    debriefing.game = cast(
        Any,
        SimpleNamespace(settings=SimpleNamespace(ignore_non_combat_air_losses=False)),
    )
    return debriefing


def test_loss_counts_blue_side() -> None:
    blue = _sample_debriefing().loss_counts(Player.BLUE)
    assert blue == SideLossCounts(
        aircraft=1,
        front_line=3,
        motorpool=2,
        convoy=2,
        cargo_ships=1,
        airlift_cargo=2,
        ground_objects=5,
        scenery=0,
        bases_lost=1,  # one base captured by RED == one base Blue lost
        runways_destroyed=1,
    )


def test_loss_counts_red_side() -> None:
    red = _sample_debriefing().loss_counts(Player.RED)
    assert red == SideLossCounts(
        aircraft=2,
        front_line=1,
        motorpool=3,
        convoy=0,
        cargo_ships=4,
        airlift_cargo=4,  # 1 + 3
        ground_objects=2,
        scenery=1,
        bases_lost=2,  # two bases captured by BLUE == two bases Red lost
        runways_destroyed=2,
    )


def test_loss_counts_partition_matches_combined_totals() -> None:
    """Blue + Red for each category must equal the combined total the UI
    shows today (the existing Debriefing properties). Pins that loss_counts
    reads the same lists and never alters totals."""
    debriefing = _sample_debriefing()
    blue = debriefing.loss_counts(Player.BLUE)
    red = debriefing.loss_counts(Player.RED)

    assert blue.aircraft + red.aircraft == len(list(debriefing.air_losses.losses))
    assert blue.front_line + red.front_line == len(list(debriefing.front_line_losses))
    assert blue.motorpool + red.motorpool == len(list(debriefing.motorpool_losses))
    assert blue.convoy + red.convoy == len(list(debriefing.convoy_losses))
    assert blue.cargo_ships + red.cargo_ships == len(list(debriefing.cargo_ship_losses))
    assert blue.airlift_cargo + red.airlift_cargo == sum(
        len(loss.cargo) for loss in debriefing.airlift_losses
    )
    assert blue.ground_objects + red.ground_objects == len(
        list(debriefing.ground_object_losses)
    )
    assert blue.scenery + red.scenery == len(list(debriefing.scenery_object_losses))
    assert blue.bases_lost + red.bases_lost == len(debriefing.base_captures)
    assert blue.runways_destroyed + red.runways_destroyed == len(
        list(debriefing.damaged_runways)
    )


def test_lua_suppresses_player_despawn_loss_events() -> None:
    # A player leaving the seat (spectator / mission end) makes DCS fire a
    # crash/dead for the aircraft that must NOT count as a combat loss, while a
    # real shootdown (and any ejection) still does. The Lua needs an in-game pass,
    # but lock the guard's structure here so it can't silently regress.
    script = Path("resources/plugins/base/dcs_retribution.lua").read_text(
        encoding="utf-8"
    )
    # Tracks seat-leaves and ejections.
    assert "S_EVENT_PLAYER_LEAVE_UNIT" in script
    assert "player_left_units" in script
    assert "ejected_units" in script
    # The crash/dead/lost handlers gate on the despawn check.
    assert "is_player_despawn" in script
    despawn = script.split("local function is_player_despawn(name)", maxsplit=1)[
        1
    ].split("local function onEvent(event)", maxsplit=1)[0]
    # An ejection is a real loss -> never suppressed.
    assert "ejected_units[name]" in despawn
    # Crash recording is now guarded, not unconditional.
    assert "if not is_player_despawn(name) then" in script


def test_motorpool_losses_by_type_counts_per_side() -> None:
    """motorpool_losses_by_type buckets a side's motorpool kills by unit type,
    mirroring front_line_losses_by_type. Feeds the debrief casualty screen."""
    t90 = MagicMock(name="T-90A")
    bmp = MagicMock(name="BMP-3")
    debriefing = _sample_debriefing()
    debriefing.ground_losses = GroundLosses(
        player_motorpool=[
            MagicMock(unit_type=t90),
            MagicMock(unit_type=t90),
            MagicMock(unit_type=bmp),
        ],
        enemy_motorpool=[MagicMock(unit_type=bmp)],
    )

    assert debriefing.motorpool_losses_by_type(Player.BLUE) == {t90: 2, bmp: 1}
    assert debriefing.motorpool_losses_by_type(Player.RED) == {bmp: 1}


def test_ground_object_losses_belong_to_the_side_in_the_name() -> None:
    """The rule the LLM's debrief documents: red_sites_lost is what RED lost, not what
    red killed. The howtoplay text said the opposite of the code for both sides."""

    def _lost(type_id: str) -> Any:
        return SimpleNamespace(
            theater_unit=SimpleNamespace(type=SimpleNamespace(id=type_id))
        )

    debriefing = _sample_debriefing()
    debriefing.ground_losses = GroundLosses(
        player_ground_objects=[
            _lost("Patriot ln"),
            _lost("Patriot ln"),
            _lost("Hawk sr"),
        ],
        enemy_ground_objects=[_lost("S-300PS 5P85C ln")],
    )

    assert debriefing.ground_object_losses_by_type(Player.BLUE) == {
        "Patriot ln": 2,
        "Hawk sr": 1,
    }
    assert debriefing.ground_object_losses_by_type(Player.RED) == {
        "S-300PS 5P85C ln": 1
    }
