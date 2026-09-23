"""Putting an air defence group where the player chooses."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.highcommand.placing import place
from tests.highcommand.stubs import launcher, sam


def test_the_site_is_cleared_and_every_slot_filled_facing_the_front() -> None:
    site = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40)])
    site.invalidate_threat_poly = lambda: cleared.append("ring")
    cleared: list[str] = []
    launchers = SimpleNamespace(group_size=4, max_size=6)
    tents = SimpleNamespace(group_size=3, max_size=2)
    layout = SimpleNamespace(
        groups=[SimpleNamespace(group_name="SAM", unit_groups=[launchers, tents])]
    )
    made: list[tuple[Any, ...]] = []
    group: Any = SimpleNamespace(
        layouts=[layout],
        unit_types_for_group=lambda unit_group: (
            [SimpleNamespace(dcs_unit_type="Hawk ln")]
            if unit_group is launchers
            else []
        ),
        statics_for_group=lambda unit_group: ["Tent"] if unit_group is tents else [],
        create_theater_group_for_tgo=lambda *args: made.append(args[1:]),
    )
    network: list[Any] = []
    zones: list[Any] = []
    game: Any = SimpleNamespace(
        theater=SimpleNamespace(
            heading_to_conflict_from=lambda position: "north",
            iads_network=SimpleNamespace(
                update_tgo=lambda tgo, events: network.append(tgo)
            ),
        ),
        compute_threat_zones=lambda events: zones.append(events),
    )

    events = place(game, site, group)

    assert cleared == ["ring"] and site.groups == []
    assert site.heading == "north"
    assert [(args[1], args[3], args[4]) for args in made] == [
        ("GRUMBLE (SAM)", "Hawk ln", 4),
        ("GRUMBLE (SAM)", "Tent", 2),
    ]
    assert network == [site] and zones == [events]
