"""Every potential land IADS consumer starts with a friendly power supply."""

from pathlib import Path

import pytest

from game.campaignloader.campaign import Campaign
from game.theater.iadsnetwork.iadsrole import IadsRole

CAMPAIGNS = sorted(Path("resources/campaigns").glob("*.yaml"))
CONSUMERS = (
    "long_range_sams",
    "medium_range_sams",
    "short_range_sams",
    "aaa",
    "ewrs",
    "iads_command_center",
    "iads_connection_node",
)


@pytest.mark.parametrize("path", CAMPAIGNS, ids=lambda path: path.stem)
def test_all_potential_iads_sites_have_initial_friendly_power(path: Path) -> None:
    campaign = Campaign.from_file(path)
    if not campaign.advanced_iads:
        return
    theater = campaign.load_theater(True)
    power = [
        (cp.starting_coalition, point)
        for cp in theater.controlpoints
        for point in cp.preset_locations.iads_power_source
    ]
    power.extend(
        (cp.starting_coalition, scenery.position)
        for cp in theater.controlpoints
        for scenery in cp.preset_locations.scenery
        if IadsRole.for_category(scenery.category) is IadsRole.POWER_SOURCE
    )
    for cp in theater.controlpoints:
        for point in cp.preset_locations.iads_power_source:
            if " IADS Power " in point.original_name:
                assert theater.is_on_land(
                    point, ignore_exclusion=True
                ), point.original_name
    missing = []
    # Ownership inversion preserves these same-side distances. Checking every
    # marker also covers random group choices, including ones without generators.
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        consumers = [
            (point.original_name, point)
            for kind in CONSUMERS
            for point in getattr(cp.preset_locations, kind)
        ]
        consumers.extend(
            (scenery.zone_def.name, scenery.position)
            for scenery in cp.preset_locations.scenery
            if IadsRole.for_category(scenery.category)
            in (IadsRole.COMMAND_CENTER, IadsRole.CONNECTION_NODE)
        )
        for name, position in consumers:
            if not any(
                side is cp.starting_coalition
                and position.distance_to_point(source)
                <= IadsRole.POWER_SOURCE.connection_range().meters
                for side, source in power
            ):
                missing.append(name)
    assert not missing, f"{path.name}: missing initial power for {missing}"
