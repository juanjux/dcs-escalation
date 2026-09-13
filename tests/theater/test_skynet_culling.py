"""Unit tests for the Skynet IADS radius.

Skynet is handed every SAM site, EWR, comms tower and power station on the map, for
both coalitions, and its cost grows with what it manages. The radius hands it only what
is near the fighting.

Two things need guarding, and both are about absence meaning the wrong thing.

What is left out is *not* removed from the mission -- that is perf_culling's job, a
different setting -- so a flight that strays off the planned route still meets it. But
Escalation generates ground SAMs at alarm state green when perf_red_alert_state is off,
on the assumption that Skynet will wake them; a site nobody is going to wake has to come
up red instead, or the radius would quietly disarm the map.

And the radius must never touch the infrastructure. Skynet reads an absent dependency as
a working one: genericCheckOneObjectIsAlive starts at `#objects == 0`, and
isCommandCenterUsable returns true on an empty list. Dropping a bombed power station
would switch its SAMs back on, and dropping the last command centre would hand a
coalition its command back.
"""

from types import SimpleNamespace
from typing import Any

from dcs.task import OptAlarmState

from game.game import Game
from game.missiongenerator.tgogenerator import GroundObjectGenerator
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroundobject import (
    EwrGroundObject,
    IadsBuildingGroundObject,
    SamGroundObject,
)

ALARM_STATE_RED = 2
ALARM_STATE_GREEN = 1


class _Zone:
    """Stands in for a culling zone. skynet_culled only measures distance to one."""

    def __init__(self, distance: float) -> None:
        self.distance = distance

    def distance_to_point(self, _position: Any) -> float:
        return self.distance


def _game(radius: int, *distances: float) -> Any:
    # The radius is a skynetiads plugin option now.
    game = SimpleNamespace(
        settings=SimpleNamespace(
            plugin_option_or=lambda identifier, default=None: (
                radius if identifier == "skynetiads.radiusKm" else default
            )
        )
    )
    # Name-mangled: the attribute Game.skynet_culled reads is _Game__culling_zones.
    setattr(game, "_Game__culling_zones", [_Zone(d) for d in distances])
    return game


def _tgo(kind: type) -> Any:
    """A bare TGO of the given class.

    Built without its __init__, which needs a whole ControlPoint graph; skynet_culled
    only branches on the runtime type and reads .position.
    """
    tgo: Any = object.__new__(kind)
    tgo.position = None
    return tgo


def _culled(radius: int, *distances: float, kind: type = SamGroundObject) -> bool:
    return Game.skynet_culled(_game(radius, *distances), _tgo(kind))


def test_a_radius_of_zero_leaves_the_whole_map_in_the_network() -> None:
    """The default. Nothing changes for a campaign that never touches the setting."""
    assert not _culled(0, 5_000_000.0)


def test_with_no_conflict_located_nothing_is_culled() -> None:
    """An empty zone list would otherwise cull everything and hand Skynet nothing."""
    assert not _culled(100)


def test_a_site_inside_the_radius_stays_in_the_network() -> None:
    assert not _culled(100, 99_000.0)


def test_a_site_outside_every_zone_is_left_out() -> None:
    assert _culled(100, 150_000.0, 200_000.0)


def test_one_zone_in_reach_is_enough() -> None:
    """Near the front but far from every package target is still near the fighting."""
    assert not _culled(100, 400_000.0, 12_000.0)


def test_an_ewr_is_culled_like_a_sam() -> None:
    assert _culled(100, 500_000.0, kind=EwrGroundObject)


def test_the_infrastructure_is_never_culled_however_far() -> None:
    """Command centres, comms towers and power stations, all IadsBuildingGroundObject.

    Skynet reads their absence as "alive", so leaving one out is not a saving, it is a
    lie that switches defences back on.
    """
    assert not _culled(100, 5_000_000.0, kind=IadsBuildingGroundObject)


def _alarm_state(
    *, radius: int, distance: float, red_alert: bool, skynet: bool = True
) -> int:
    """The alarm state a ground SAM outside/inside the radius is generated at."""
    game = _game(radius, distance)
    game.settings.perf_red_alert_state = red_alert
    game.settings.plugin_option = lambda name: skynet and name == "skynetiads"
    game.skynet_culled = lambda tgo: Game.skynet_culled(game, tgo)

    generator: Any = GroundObjectGenerator.__new__(GroundObjectGenerator)
    generator.game = game
    # A SAM, not an EWR: the EWR branch would decide this for us.
    generator.ground_object = _tgo(SamGroundObject)

    group: Any = SimpleNamespace(points=[SimpleNamespace(tasks=[])])
    GroundObjectGenerator.set_alarm_state(generator, group)
    task = group.points[0].tasks[0]
    assert isinstance(task, OptAlarmState)
    return int(task.value)


def test_a_site_left_out_of_the_network_comes_up_red() -> None:
    """The whole point: nobody is coming to wake it, so it wakes itself."""
    assert (
        _alarm_state(radius=100, distance=500_000.0, red_alert=False) == ALARM_STATE_RED
    )


def test_a_site_inside_the_network_still_starts_dark() -> None:
    """Skynet is going to drive it, so the perf toggle keeps its meaning."""
    assert (
        _alarm_state(radius=100, distance=10_000.0, red_alert=False)
        == ALARM_STATE_GREEN
    )


def test_the_radius_does_not_arm_anything_when_skynet_is_off() -> None:
    """With no IADS plugin there is no network to be outside of."""
    assert (
        _alarm_state(radius=100, distance=500_000.0, red_alert=False, skynet=False)
        == ALARM_STATE_GREEN
    )


def _network(sam_distance: float, power_distance: float) -> tuple[Any, Any]:
    """A SAM inside the radius whose destroyed power station lies outside it.

    Geometrically ordinary: a power source reaches 35 nm, so a SAM 99 km from the
    action can be fed by a station 110 km from it.
    """
    power_tgo = _tgo(IadsBuildingGroundObject)
    power_tgo.is_friendly = lambda player: True
    power = SimpleNamespace(
        group_name="Power Station",
        iads_role=IadsRole.POWER_SOURCE,
        ground_object=power_tgo,
        # Bombed: nothing alive, but the static is still spawned, dead.
        units=[SimpleNamespace(alive=False, is_static=True, unit_name="Power Station")],
    )

    sam_tgo = _tgo(SamGroundObject)
    sam_tgo.is_friendly = lambda player: True
    # from_group reads the owning side through the control point.
    sam_tgo.control_point = SimpleNamespace(
        coalition=SimpleNamespace(player=SimpleNamespace(is_blue=False))
    )
    sam = SimpleNamespace(
        group_name="SA-10 Site",
        iads_role=IadsRole.SAM,
        ground_object=sam_tgo,
        units=[SimpleNamespace(alive=True, is_static=False, unit_type=None)],
    )

    class _Distances:
        """One zone that answers a different distance for each object."""

        @staticmethod
        def distance_to_point(position: Any) -> float:
            return sam_distance if position == "sam" else power_distance

    sam_tgo.position = "sam"
    power_tgo.position = "power"

    game: Any = SimpleNamespace(
        settings=SimpleNamespace(
            plugin_option_or=lambda identifier, default=None: (
                100 if identifier == "skynetiads.radiusKm" else default
            )
        ),
        iads_considerate_culling=lambda tgo: False,
    )
    setattr(game, "_Game__culling_zones", [_Distances])
    game.skynet_culled = lambda tgo: Game.skynet_culled(game, tgo)

    network: Any = IadsNetwork.__new__(IadsNetwork)
    network.nodes = [
        SimpleNamespace(group=sam, connections={"one": power}),
    ]
    return network, game


def test_a_kept_sam_keeps_a_power_source_that_falls_outside_the_radius() -> None:
    """The regression: an empty powerSources list reads as "powered".

    Dropping the bombed station would have switched this SAM back on -- the radius
    would have repaired the enemy's air defence.
    """
    network, game = _network(sam_distance=99_000.0, power_distance=110_000.0)

    nodes = IadsNetwork.skynet_nodes(network, game)

    assert len(nodes) == 1
    assert nodes[0].connections[IadsRole.POWER_SOURCE.value] == ["Power Station"]


def test_the_sam_itself_still_goes_when_it_is_the_one_out_of_range() -> None:
    """The radius still does its job; it just does not reach the infrastructure."""
    network, game = _network(sam_distance=150_000.0, power_distance=110_000.0)

    assert IadsNetwork.skynet_nodes(network, game) == []
