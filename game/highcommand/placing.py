"""Putting an air defence group where the player chooses, for nothing.

The same composition the buy menu starts from (qt_ui/windows/groundobject/buymodel.py):
the force group's first layout, every slot with its first unit type and as many units
as the layout asks, facing the front. Free, and ready at once rather than under a
repair delay.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from game.layout.layout import LayoutException

if TYPE_CHECKING:
    from game import Game
    from game.armedforces.forcegroup import ForceGroup
    from game.sim import GameUpdateEvents
    from game.theater.theatergroundobject import TheaterGroundObject


def place(
    game: Game, site: TheaterGroundObject, force_group: ForceGroup
) -> GameUpdateEvents:
    """Replace what stands at the site with the force group, and bring the network, the
    threat zones and the map up to date. The events for the map are returned."""
    from game.sim import GameUpdateEvents

    layout = force_group.layouts[0]
    site.heading = game.theater.heading_to_conflict_from(site.position) or site.heading
    # Clearing drops the cached threat ring along with the groups.
    site.clear()
    for group in layout.groups:
        for unit_group in group.unit_groups:
            unit_types = list(force_group.unit_types_for_group(unit_group))
            statics = list(force_group.statics_for_group(unit_group))
            if unit_types:
                dcs_type = unit_types[0].dcs_unit_type
            elif statics:
                dcs_type = statics[0]
            else:
                continue
            try:
                force_group.create_theater_group_for_tgo(
                    site,
                    unit_group,
                    f"{site.name} ({group.group_name})",
                    game,
                    dcs_type,
                    min(unit_group.group_size, unit_group.max_size),
                )
            except LayoutException:
                logging.exception(f"Could not place {dcs_type} at {site.name}")

    events = GameUpdateEvents()
    events.update_tgo(site)
    game.theater.iads_network.update_tgo(site, events)
    game.compute_threat_zones(events)
    return events
