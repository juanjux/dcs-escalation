"""Movable objectives stay readable without relocating fixed map scenery."""

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from dcs.lua import loads
from dcs import Point
import pytest

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.settings import Settings
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.utils import Heading
from tests.campaignloader.test_iads_campaign_expansion import ROLES, digest
from tests.test_iads_automatic_topology import site

ROOT = Path("resources/campaigns")
MANIFEST = json.loads(Path(__file__).with_name("objective_spacing.json").read_text())


def group_positions(group: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        group,
        *group.get("units", {}).values(),
        *group.get("route", {}).get("points", {}).values(),
    ]


def spacing_signature(mission: dict[str, Any], row: dict[str, Any]) -> str:
    mission = deepcopy(mission)
    for coalition in mission["coalition"].values():
        for country in coalition.get("country", {}).values():
            for category in ("static", "vehicle", "ship"):
                for group in country.get(category, {}).get("group", {}).values():
                    if group["name"] not in row["moved"]:
                        continue
                    move = row["moved"][group["name"]]
                    dx = move["new"][0] - move["old"][0]
                    dy = move["new"][1] - move["old"][1]
                    positions = group_positions(group)
                    assert len(positions) == len(move["positions"])
                    for position, (x, y) in zip(positions, move["positions"]):
                        assert math.isclose(
                            position["x"], x + dx, rel_tol=0, abs_tol=1e-6
                        )
                        assert math.isclose(
                            position["y"], y + dy, rel_tol=0, abs_tol=1e-6
                        )
                        position["x"], position["y"] = x, y
    return digest(mission)


def objective_points(theater: Any) -> dict[str, tuple[Any, Point, str]]:
    result = {}
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        for kind, locations in vars(cp.preset_locations).items():
            if not isinstance(locations, list):
                continue
            for location in locations:
                if kind == "scenery":
                    name, point = location.zone_def.name, location.position
                else:
                    name, point = location.original_name, location
                result[name] = cp, point, kind
    return result


@pytest.mark.parametrize("filename", MANIFEST)
def test_objective_spacing_and_preserved_ownership(filename: str) -> None:
    row = MANIFEST[filename]
    campaign = Campaign.from_file(ROOT / filename)
    theater = campaign.load_theater(campaign.advanced_iads)
    points = objective_points(theater)
    for name, move in row["moved"].items():
        cp, point, kind = points[name]
        assert kind != "scenery"
        assert kind == move["kind"]
        assert cp.name == move["base"]
        assert cp.starting_coalition.name == move["side"]
        assert [point.x, point.y] == move["new"]
        if kind in ("ships", "offshore_strike_locations"):
            assert theater.is_in_sea(point), name
        else:
            assert theater.is_on_land(point, ignore_exclusion=True) or any(
                math.hypot(point.x - x, point.y - y) <= 300.01
                for x, y in row["island_anchors"]
            ), name
    exceptions = {tuple(sorted((pair["a"], pair["b"]))) for pair in row["exceptions"]}
    actual = set()
    entries = list(points.items())
    for index, (name, (_, point, _)) in enumerate(entries):
        for other, (_, position, _) in entries[index + 1 :]:
            if point.distance_to_point(position) < 1852 - 1e-6:
                actual.add(tuple(sorted((name, other))))
    assert actual == exceptions
    assert len(actual) <= row["before_pairs"]


@pytest.mark.parametrize("filename", MANIFEST)
def test_spacing_changes_only_whole_group_coordinates(filename: str) -> None:
    row = MANIFEST[filename]
    campaign = Campaign.from_file(ROOT / filename)
    with ZipFile(campaign.path.parent / campaign.data["miz"]) as archive:
        mission = loads(archive.read("mission").decode())["mission"]
        assert spacing_signature(mission, row) == row["retained_mission_sha256"]
        assert (
            digest(
                [
                    (info.filename, hashlib.sha256(archive.read(info)).hexdigest())
                    for info in archive.infolist()
                    if info.filename != "mission"
                ]
            )
            == row["other_entries_sha256"]
        )


@pytest.mark.parametrize("filename", MANIFEST)
def test_spacing_preserves_iads_under_command_and_power_losses(filename: str) -> None:
    campaign = Campaign.from_file(ROOT / filename)
    if not campaign.advanced_iads:
        return
    row = MANIFEST[filename]
    theater = campaign.load_theater(True)
    settings = Settings()
    settings.set_plugin_option(
        "skynetiads.commsRangeNm", row["iads"].get("comms_range_nm", 15)
    )
    settings.set_plugin_option(
        "skynetiads.powerRangeNm", row["iads"].get("power_range_nm", 35)
    )
    scenery_roles = {
        scenery.zone_def.name: IadsRole.for_category(scenery.category)
        for cp in theater.controlpoints
        for scenery in cp.preset_locations.scenery
    }
    objects: dict[str, Any] = {}
    for name, (cp, point, kind) in objective_points(theater).items():
        role = scenery_roles.get(name) if kind == "scenery" else ROLES.get(kind)
        if role is None or role is IadsRole.NO_BEHAVIOR:
            continue
        obj = site(name, role, side=cp.starting_coalition, settings=settings)
        obj.position = PointWithHeading.from_point(point, Heading.from_degrees(0))
        objects[name] = obj
    network = IadsNetwork(True)
    network.initialize_network(iter(objects.values()))
    nodes = {n.group.ground_object.original_name: n for n in network.nodes}
    profile = row["iads"]
    targets = profile["targets"]
    assert set(targets) <= nodes.keys()
    for case in profile["cases"]:
        failure = case["failure"]
        loss = [] if failure is None else [objects[failure[1]]]
        connectivity = IadsConnectivity(network, loss)
        actual = sum(
            1 << index
            for index, name in enumerate(targets)
            if connectivity.connected(nodes[name])
        )
        required = int(case["connected"], 16)
        assert actual & required == required, failure
        if failure is None:
            for bits in profile["sectors"]:
                mask = int(bits, 16)
                roots = [
                    set(connectivity.roots(nodes[name]))
                    for index, name in enumerate(targets)
                    if mask & (1 << index)
                ]
                if roots:
                    assert set.intersection(*roots), bits
