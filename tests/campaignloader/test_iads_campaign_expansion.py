"""Campaign-only IADS conversions preserve forces and work without authored links."""

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from dcs.lua import loads
import pytest
import yaml

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.utils import Heading
from tests.test_iads_automatic_topology import site

ROOT = Path("resources/campaigns")
MANIFEST = json.loads(Path(__file__).with_name("iads_expansion.json").read_text())
ROLES = {
    "long_range_sams": IadsRole.SAM,
    "medium_range_sams": IadsRole.SAM,
    "short_range_sams": IadsRole.SAM,
    "aaa": IadsRole.EWR,
    "ewrs": IadsRole.EWR,
    "iads_command_center": IadsRole.COMMAND_CENTER,
    "iads_connection_node": IadsRole.CONNECTION_NODE,
    "iads_power_source": IadsRole.POWER_SOURCE,
}
INFRA = {".Command Center", "Comms tower M", "GeneratorF"}


def retained_mission(mission: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Exclude infrastructure additions, not existing aircraft or defences."""
    mission = deepcopy(mission)
    for coalition in mission["coalition"].values():
        for country in coalition.get("country", {}).values():
            for category in ("static", "vehicle"):
                groups = country.get(category, {}).get("group", {})
                for key, group in list(groups.items()):
                    infrastructure = category == "static" and all(
                        unit["type"] in INFRA for unit in group["units"].values()
                    )
                    if infrastructure or group["name"] in row["new_jammers"]:
                        del groups[key]
                    elif group["name"] in row["relocated_radars"]:
                        # These two original copies of an EWR marker were at sea.
                        # Its identity, unit type and every other property remain checked.
                        for item in [
                            group,
                            *group["units"].values(),
                            *group.get("route", {}).get("points", {}).values(),
                        ]:
                            item["x"], item["y"] = 0, 0
                if category in country and not groups:
                    del country[category]
    # The resilience pass retires only these communications objectives and
    # their scenery member zones; all other trigger data remains protected.
    retired = set(row.get("retired_comms_scenery_zones", []))
    zones = mission.get("triggers", {}).get("zones", {})
    for key, zone in list(zones.items()):
        if zone["name"] in retired:
            del zones[key]
    return mission


def digest(value: Any) -> str:
    def normalized(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                f"{type(key).__name__}:{key}": normalized(value)
                for key, value in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [normalized(value) for value in item]
        return item

    return hashlib.sha256(
        json.dumps(normalized(value), sort_keys=True).encode()
    ).hexdigest()


@pytest.mark.parametrize("filename", MANIFEST)
def test_template_retains_combat_forces_and_unrelated_mission_data(
    filename: str,
) -> None:
    row = MANIFEST[filename]
    with ZipFile((ROOT / filename).with_suffix(".miz")) as archive:
        mission = loads(archive.read("mission").decode())["mission"]
        others = [
            (info.filename, hashlib.sha256(archive.read(info)).hexdigest())
            for info in archive.infolist()
            if info.filename != "mission"
        ]
    assert digest(retained_mission(mission, row)) == row["retained_mission_sha256"]
    assert digest(others) == row["other_entries_sha256"]
    for coalition in mission["coalition"].values():
        for country in coalition.get("country", {}).values():
            for group in country.get("vehicle", {}).get("group", {}).values():
                if group["name"] in row["relocated_radars"]:
                    assert [group["x"], group["y"]] == row["relocated_radars"][
                        group["name"]
                    ]


@pytest.mark.parametrize("filename", MANIFEST)
@pytest.mark.parametrize("inverted", [False, True])
def test_land_sites_have_friendly_command_paths(filename: str, inverted: bool) -> None:
    row = MANIFEST[filename]
    campaign = Campaign.from_file(ROOT / filename)
    assert campaign.advanced_iads
    assert campaign.settings["plugins"]["skynetiads"]
    assert "iads_config" not in campaign.data
    theater = campaign.load_theater(True)
    pins = campaign.data.get("ground_forces", {})
    for name in {**row["new_jammers"], **row.get("restored_jammers", {})}:
        assert pins[name].endswith(", Unescorted)")
        assert campaign.recommended_start_date is not None
        assert campaign.recommended_start_date.year >= 2000
    if campaign.recommended_start_date and campaign.recommended_start_date.year < 2000:
        assert not any("GPS Jamming" in str(value) for value in pins.values())
    objects: list[Any] = []
    selected: set[Any] = set()
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        owner = cp.starting_coalition.opponent if inverted else cp.starting_coalition
        placements = [
            (point.original_name, point, role)
            for kind, role in ROLES.items()
            for point in getattr(cp.preset_locations, kind)
        ]
        placements.extend(
            (
                scenery.zone_def.name,
                scenery.position,
                IadsRole.for_category(scenery.category),
            )
            for scenery in cp.preset_locations.scenery
            if IadsRole.for_category(scenery.category) is not IadsRole.NO_BEHAVIOR
        )
        for name, point, role in placements:
            obj = site(name, role, side=owner)
            obj.position = PointWithHeading.from_point(point, Heading.from_degrees(0))
            objects.append(obj)
            if cp.starting_coalition.name in row["sides"]:
                selected.add(obj)
            if name.startswith(
                ("Blue IADS ", "Red IADS ", "Blue GPS Jammer ", "Red GPS Jammer ")
            ):
                assert cp.starting_coalition.name in row["sides"]
                on_land = theater.is_on_land(point, ignore_exclusion=True)
                # The shipped mask omits six real northern Mariana islands.
                # Only the existing site footprints (300 m) are permitted there.
                assert on_land or any(
                    point.distance_to_point(anchor) <= 300.01
                    for anchor in [
                        PointWithHeading(x, y, Heading.from_degrees(0), theater.terrain)
                        for x, y in row["island_anchors"]
                    ]
                ), name
    names = [obj.original_name for obj in objects]
    assert max(Counter(names).values()) == 1
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    connectivity = IadsConnectivity(network)
    consumers = [
        node
        for node in network.nodes
        if node.group.ground_object in selected
        and node.group.iads_role in (IadsRole.SAM, IadsRole.EWR)
    ]
    assert consumers
    assert all(connectivity.connected(node) for node in consumers), [
        node.group.ground_object.original_name
        for node in consumers
        if not connectivity.connected(node)
    ]
    for node in consumers:
        owner = node.group.ground_object.control_point.captured
        assert all(
            root.group.ground_object.control_point.captured is owner
            for root in connectivity.centres_for(node)
        )
    commands = [
        obj for obj in objects if obj.groups[0].iads_role is IadsRole.COMMAND_CENTER
    ]
    cut = IadsConnectivity(network, commands)
    assert all(not cut.connected(node) for node in consumers)


@pytest.mark.parametrize("color", ["Blue", "Red"])
def test_unescorted_jammer_presets_cannot_fill_point_defence(color: str) -> None:
    unit = yaml.safe_load(
        Path(f"resources/units/ground_units/GPS_Spoofer_{color}.yaml").read_text()
    )
    assert unit["introduced"] == 2000
    preset = yaml.safe_load(
        Path(f"resources/groups/GPS-Jamming-Site-{color}-Unescorted.yaml").read_text()
    )
    assert preset["never_random"] is True
    assert preset["units"] == [f"GPS Jammer ({color})"]
    assert preset["layouts"] == ["GPS Jamming Site (Unescorted)"]
    layout = yaml.safe_load(
        Path("resources/layouts/anti_air/GPS_Jamming_Site_Unescorted.yaml").read_text()
    )
    assert layout["generic"] is False
    groups = [
        group
        for section in layout["groups"]
        for group_list in section.values()
        for group in group_list
    ]
    assert len(groups) == 1
    assert groups[0]["unit_count"] == [1]
    assert set(groups[0]["unit_types"]) == {"GPS_Spoofer_Blue", "GPS_Spoofer_Red"}
    assert not groups[0].get("unit_classes")
