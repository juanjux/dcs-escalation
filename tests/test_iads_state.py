"""Reading Skynet's mind: what state each site will be in when the mission starts.

The rules are the plugin's, so the tests are written against the plugin's behaviour
rather than against the implementation: an empty dependency list means "fine", no power
beats everything else, and a SAM stays in the network only while something that can see
is feeding it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStateMap

BLUE = True


def _unit(alive: bool = True, detection: float = 0.0, power: bool = False) -> Any:
    from game.data.units import UnitClass

    return SimpleNamespace(
        alive=alive,
        detection_range=SimpleNamespace(meters=detection if alive else 0.0),
        unit_type=SimpleNamespace(
            unit_class=UnitClass.POWER if power else UnitClass.LAUNCHER,
            display_name="EPP-III" if power else "Launcher",
            skynet_properties=SimpleNamespace(autonomous_behaviour=None),
        ),
    )


class _Tgo:
    """A ground object keyed by identity, the way the real one is.

    Not a SimpleNamespace: that defines __eq__, so it cannot be a dict key, and the
    state map is keyed by ground object.
    """

    def __init__(self, name: str, at: tuple[float, float]) -> None:
        self.name = name
        self.control_point = SimpleNamespace(captured=SimpleNamespace(is_blue=BLUE))
        self.position = SimpleNamespace(
            distance_to_point=lambda other, _a=at: (
                (_a[0] - other.x) ** 2 + (_a[1] - other.y) ** 2
            )
            ** 0.5,
            x=at[0],
            y=at[1],
        )
        self.groups: list[Any] = []
        self.carries_gps_jammer = False


def _group(
    name: str, role: IadsRole, *units: Any, at: tuple[float, float] = (0.0, 0.0)
) -> Any:
    units = units or (_unit(),)
    tgo = _Tgo(name, at)
    group = SimpleNamespace(
        name=name,
        iads_role=role,
        units=list(units),
        alive_units=sum(1 for u in units if u.alive),
        ground_object=tgo,
    )
    tgo.groups = [group]
    return group


def _node(group: Any, *connections: Any) -> Any:
    return SimpleNamespace(
        group=group, connections={i: c for i, c in enumerate(connections)}
    )


def _map(*nodes: Any) -> IadsStateMap:
    return IadsStateMap(SimpleNamespace(nodes=list(nodes)))  # type: ignore[arg-type]


def _status(state_map: IadsStateMap, group: Any) -> Any:
    return state_map.status_for(group.ground_object)


def test_a_site_with_no_dependencies_is_working() -> None:
    """genericCheckOneObjectIsAlive starts at "#objects == 0": nothing to depend on
    reads as powered and connected, and an EWR has no parent to lose."""
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000))
    assert _status(_map(_node(ewr)), ewr).state is IadsState.NETWORKED


def test_losing_the_substation_puts_a_site_out_for_the_mission() -> None:
    """goLive() refuses without power, so this beats everything else the site has."""
    power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit(alive=False))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000))
    state = _status(_map(_node(sam, power), _node(power)), sam)
    assert state.state is IadsState.DARK
    assert "No power" in state.reason


def test_a_battery_with_its_own_generator_ignores_the_substation() -> None:
    dead_power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit(alive=False))
    sam = _group("PATRIOT", IadsRole.SAM, _unit(detection=90_000), _unit(power=True))
    status = _status(_map(_node(sam, dead_power)), sam)
    assert status.state is not IadsState.DARK
    # And it names the truck: the opponent's way of switching this site off is to bomb
    # that one vehicle, and guessing which is not the same as being told.
    assert "EPP-III" in status.reason


def test_a_battery_on_the_grid_says_nothing_about_generators() -> None:
    """The note is about a site running on its own power, not about owning a generator:
    with the substation standing there is nothing to say."""
    live_power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit())
    sam = _group("PATRIOT", IadsRole.SAM, _unit(detection=90_000), _unit(power=True))
    assert "EPP-III" not in _status(_map(_node(sam, live_power)), sam).reason


def test_cutting_the_comms_sets_a_sam_loose_rather_than_switching_it_off() -> None:
    """The distinction the whole feature turns on: no comms is autonomous, no power is
    dark. A site set loose still shoots at what it can see."""
    comms = _group("TOWER", IadsRole.CONNECTION_NODE, _unit(alive=False))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000))
    state = _status(_map(_node(sam, comms)), sam)
    assert state.state is IadsState.AUTONOMOUS
    assert "Comms cut" in state.reason


def test_a_sam_in_range_of_a_live_ewr_is_networked() -> None:
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(50_000.0, 0.0))
    state = _status(_map(_node(ewr), _node(sam)), sam)
    assert state.state is IadsState.NETWORKED
    assert "MOOSE" in state.reason


def test_a_sam_beyond_every_radar_is_on_its_own() -> None:
    """buildRadarCoverage makes the parent relationship by range, so a SAM outside every
    EWR's reach has no parent to keep it in the network."""
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=10_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(500_000.0, 0.0))
    assert _status(_map(_node(ewr), _node(sam)), sam).state is IadsState.AUTONOMOUS


def test_killing_the_ewrs_power_takes_the_sam_with_it() -> None:
    """The point of striking the network instead of the launchers: nothing was fired at
    the SAM at all."""
    power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit(alive=False))
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(50_000.0, 0.0))
    state_map = _map(_node(ewr, power), _node(sam), _node(power))
    assert _status(state_map, ewr).state is IadsState.DARK
    assert _status(state_map, sam).state is IadsState.AUTONOMOUS


def test_the_last_command_centre_going_down_sets_every_sam_loose() -> None:
    centre = _group("SUNBEAR", IadsRole.COMMAND_CENTER, _unit(alive=False))
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(50_000.0, 0.0))
    state = _status(_map(_node(centre), _node(ewr), _node(sam)), sam)
    assert state.state is IadsState.AUTONOMOUS
    assert "command centre" in state.reason


def test_a_command_centre_with_its_comms_cut_is_not_directing_anybody() -> None:
    """It is excluded from isCommandCenterUsable() -- that wants an active connection
    node as well as power -- so it must not report itself as running the network while
    every SAM is being told there is no command centre standing."""
    comms = _group("KEA", IadsRole.CONNECTION_NODE, _unit(alive=False))
    centre = _group("SUNBEAR", IadsRole.COMMAND_CENTER, _unit())
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(50_000.0, 0.0))
    state_map = _map(_node(centre, comms), _node(ewr), _node(sam), _node(comms))

    centre_state = _status(state_map, centre)
    assert centre_state.state is IadsState.AUTONOMOUS
    assert "directs nobody" in centre_state.reason
    # The two halves have to agree.
    assert "command centre" in _status(state_map, sam).reason


def test_a_campaign_with_no_command_centre_at_all_is_not_penalised() -> None:
    """isCommandCenterUsable() answers true to an empty table, so a campaign that wired
    none must not read as having lost one."""
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000), at=(50_000.0, 0.0))
    assert _status(_map(_node(ewr), _node(sam)), sam).state is IadsState.NETWORKED


def test_a_gps_jammer_cut_off_from_the_network_is_not_reported_as_autonomous() -> None:
    """It sits in an early-warning slot but is not a radar: nobody cues it, it reports
    to nobody, and the bubble it denies depends only on its trucks being alive. The
    violet bar would be a colour on the map for a state that means nothing here."""
    comms = _group("KEA", IadsRole.CONNECTION_NODE, _unit(alive=False))
    jammer = _group("MINK", IadsRole.EWR, _unit())
    jammer.ground_object.carries_gps_jammer = True
    state = _status(_map(_node(jammer, comms), _node(comms)), jammer)
    assert state.state is IadsState.NETWORKED
    assert state.blind is False
    assert state.notable is False


def test_a_gps_jammer_with_no_power_is_still_dark() -> None:
    """Power is the one thing it wants."""
    power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit(alive=False))
    jammer = _group("MINK", IadsRole.EWR, _unit())
    jammer.ground_object.carries_gps_jammer = True
    state = _status(_map(_node(jammer, power), _node(power)), jammer)
    assert state.state is IadsState.DARK
    # "dark, and blind" reads as a radar that lost its dish; this one never had one.
    assert state.blind is False


def test_an_ordinary_ewr_with_its_comms_cut_is_still_autonomous() -> None:
    """The jammer rule must not let every early-warning radar off."""
    comms = _group("KEA", IadsRole.CONNECTION_NODE, _unit(alive=False))
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000))
    assert (
        _status(_map(_node(ewr, comms), _node(comms)), ewr).state
        is IadsState.AUTONOMOUS
    )


def test_a_site_that_has_lost_its_search_radar_is_blind() -> None:
    """Asked of the reach rather than of a list of radar classes: what matters is
    whether anything left can find a target."""
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=0.0), _unit(detection=0.0))
    assert _status(_map(_node(sam)), sam).blind is True


def test_a_site_that_still_has_a_tracker_is_not_blind() -> None:
    """A HAWK whose search radar is rubble still has an MPQ-46 with 90 km on it."""
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=90_000), _unit())
    assert _status(_map(_node(sam)), sam).blind is False


def test_a_destroyed_site_says_so_rather_than_dark() -> None:
    """Kept apart from dark on purpose: a site with no power needs its threat ring
    taken away, and a flattened one needs whatever survives around it left alone."""
    sam = _group("BADGER", IadsRole.SAM, _unit(alive=False))
    status = _status(_map(_node(sam)), sam)
    assert status.state is IadsState.DESTROYED
    assert not status.notable  # the map and the API already say it is gone


def test_infrastructure_has_no_state_of_its_own() -> None:
    """A power station has no radar to switch on or off; what matters about it is what
    it feeds."""
    power = _group("SUBSTATION", IadsRole.POWER_SOURCE, _unit())
    assert _status(_map(_node(power)), power) is None


def test_a_site_working_normally_is_not_notable() -> None:
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000))
    assert not _status(_map(_node(ewr)), ewr).notable


def test_a_blind_but_networked_site_is_notable() -> None:
    """It can be handed targets, but it is worth knowing before spending a package."""
    ewr = _group("MOOSE", IadsRole.EWR, _unit(detection=100_000), at=(0.0, 0.0))
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=0.0), at=(1_000.0, 0.0))
    status = _status(_map(_node(ewr), _node(sam)), sam)
    assert status.state is IadsState.NETWORKED
    assert status.notable


def test_the_map_is_told_about_the_sites_that_changed_without_being_touched() -> None:
    """The trap this feature sets for itself.

    Bombing a substation changes what its SAMs will do, but nothing touches those SAM
    objects, so without this the map keeps drawing their confident threat rings until
    the campaign is reloaded.
    """
    from game.theater.iadsnetwork.iadsnetwork import IadsNetwork

    power_unit = _unit(alive=True)
    power = _group("SUBSTATION", IadsRole.POWER_SOURCE, power_unit)
    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000))

    network = IadsNetwork(True, [])
    network.nodes = [_node(sam, power), _node(power)]
    assert _status(network.state_map, sam).state is not IadsState.DARK

    before = {obj: status for obj, status in network.state_map}
    power_unit.alive = False
    power.alive_units = 0
    network.invalidate_state_map()

    pushed: list[Any] = []
    network._push_state_changes(
        before, SimpleNamespace(update_tgo=pushed.append)  # type: ignore[arg-type]
    )

    assert sam.ground_object in pushed
    assert _status(network.state_map, sam).state is IadsState.DARK


def test_nothing_is_pushed_when_nothing_changed() -> None:
    """It runs on every death in the mission results, so it must be quiet."""
    from game.theater.iadsnetwork.iadsnetwork import IadsNetwork

    sam = _group("BADGER", IadsRole.SAM, _unit(detection=50_000))
    network = IadsNetwork(True, [])
    network.nodes = [_node(sam)]

    before = {obj: status for obj, status in network.state_map}
    network.invalidate_state_map()

    pushed: list[Any] = []
    network._push_state_changes(
        before, SimpleNamespace(update_tgo=pushed.append)  # type: ignore[arg-type]
    )

    assert pushed == []
