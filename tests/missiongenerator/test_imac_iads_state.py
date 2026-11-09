"""The campaign's grey IADS state reaches both in-mission navigation systems."""

from types import SimpleNamespace as NS
from typing import Any

import pytest
from dcs import Point
from dcs.vehicles import AirDefence

from game.data.units import UnitClass
from game.missiongenerator import imac
from game.missiongenerator.missiondata import MissionData
from game.missiongenerator.realisticcascampaign import prepare_campaign
from game.missiongenerator.realisticcasluadata import collect_registry
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import AUTONOMOUS_STATE_DARK, IadsState
from tests.test_iads_state import _group, _map, _node, _unit
from .test_imac_generation import scenario
from .test_realisticcas_f10 import scenario as cas_scenario


def add_battery(s: Any, case: str) -> Any:
    generator = s.generator if hasattr(s, "generator") else s.g
    mission = generator.mission
    launcher, tracker = _unit(), _unit(detection=90000)
    tracker.unit_type.unit_class = UnitClass.TRACK_RADAR
    battery = _group("BATTERY", IadsRole.SAM, launcher, tracker)
    battery.ground_object.category = "aa"
    for unit in battery.units:
        unit.ground_object = battery.ground_object
    power = _group("POWER", IadsRole.POWER_SOURCE, _unit(alive=case != "no power"))
    node = _node(battery, power)
    if case == "dark autonomous":
        launcher.unit_type.skynet_properties.autonomous_behaviour = (
            AUTONOMOUS_STATE_DARK
        )
        node.add_connection_for_group(
            _group("COMMS", IadsRole.CONNECTION_NODE, _unit(alive=False))
        )
    country = mission.country("Russia")
    point = Point(20000, 0, mission.terrain)
    group = mission.vehicle_group(country, "BATTERY", AirDefence.Patriot_ln, point)
    radar = mission.vehicle("TRACKER", AirDefence.Patriot_str)
    radar.position = point
    group.add_unit(radar)
    for native, theater in zip(group.units, battery.units):
        generator.unit_map.theater_objects[native.name] = NS(
            theater_unit=theater, dcs_unit=native
        )
    pd = mission.vehicle_group(country, "PD", AirDefence.Tor_9A331, point)
    independent = _unit()
    independent.unit_type.unit_class = UnitClass.TELAR
    independent.ground_object = battery.ground_object
    generator.unit_map.theater_objects[pd.units[0].name] = NS(
        theater_unit=independent, dcs_unit=pd.units[0]
    )
    network = NS(nodes=[node], state_map=_map(node))
    if hasattr(generator.game.theater, "iads_network"):
        network.skynet_nodes = generator.game.theater.iads_network.skynet_nodes
    generator.game.theater.iads_network = network
    return NS(network=network, battery=battery, launcher=group.units[0], pd=pd.units[0])


@pytest.mark.parametrize("case", ["no power", "dark autonomous", "autonomous"])
def test_imac_and_afac_export_the_same_dark_state_without_disabling_pd(
    case: str,
) -> None:
    s = scenario()
    b = add_battery(s, case)
    status = b.network.state_map.status_for(b.battery.ground_object)
    disabled = case != "autonomous"
    assert (status.state is IadsState.DARK) is disabled
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    registry = collect_registry(
        s.mission,
        MissionData(),
        enabled=True,
        unit_map=s.unit_map,
        iads_network=b.network,
    )
    assert data is not None and registry is not None
    for threats in (data["threats"], registry["airDefenseThreats"]):
        primary = next(t for t in threats if t["name"] == b.launcher.name)
        assert primary["iadsDisabled"] is disabled
        assert primary["radars"]  # A complete tracking chain does not override DARK.
        assert (
            next(t for t in threats if t["name"] == b.pd.name)["iadsDisabled"] is False
        )


def test_campaign_preparation_passes_the_turn_state_to_afac() -> None:
    s = cas_scenario()
    b = add_battery(s, "no power")
    config = prepare_campaign(s.g, [s.plugin])
    assert config is not None
    threats = config["registry"]["airDefenseThreats"]
    assert (
        next(t for t in threats if t["name"] == b.launcher.name)["iadsDisabled"] is True
    )
    assert next(t for t in threats if t["name"] == b.pd.name)["iadsDisabled"] is False
