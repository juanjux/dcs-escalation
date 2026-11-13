"""GPS jamming -> Lua config bridge (``dcsRetribution.gpsJamming``).

Python resolves jamming sites and their coverage. The Lua script receives:

* ``sites`` -- one record per live jammer: the owning coalition, the campaign
  position, the denial reach, the miss it scores at full strength, and the
  generated DCS group names so the runtime can re-check liveness (kill the
  jammer mid-mission and accuracy returns on the next weapon).
* ``weaponPatterns`` -- the curated satellite-guided weapon fragments. Emitted
  rather than hardcoded in the Lua so the pattern list has exactly one home
  (Python) and a campaign can never drift from it.

Emits nothing unless the setting is on and a live jammer exists, so a normal
mission has no GPS jamming configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from game.data.units import UnitClass
from game.settings.settings import GPS_JAMMING_OPTIONS
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroup import SceneryUnit

if TYPE_CHECKING:
    from game import Game
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterUnit

    from .luagenerator import LuaData, LuaItem
    from .missiondata import MissionData


def populate_gps_jamming_lua(
    root: "LuaData", game: "Game", mission_data: "MissionData"
) -> None:
    """Build the ``dcsRetribution.gpsJamming`` subtree."""
    from game.gpsjamming import (
        GPS_GUIDED_WEAPON_PATTERNS,
        gps_jammer_sites,
        gps_jamming_enabled,
    )

    sites = gps_jammer_sites(game, include_unpowered=True)
    if not sites:
        # Say so at generation time, while it can still be fixed. "The setting is
        # on but nothing jams" is otherwise indistinguishable from "the feature is
        # broken" -- and the likeliest cause is a campaign whose factions field no
        # unit carrying a `gps_jamming` block (or one whose jammers are all dead).
        if gps_jamming_enabled(game):
            logging.info(
                "GPS jamming is enabled but no live jamming site exists in this "
                "theater -- no unit in play declares a `gps_jamming` block in its "
                "definition (resources/units/ground_units/<unit>.yaml), or every "
                "jammer is destroyed. Nothing will be jammed this mission."
            )
        return

    node = root.add_item("gpsJamming")
    options = node.add_item("options")
    for key, field in GPS_JAMMING_OPTIONS.items():
        options.add_key_value(key, getattr(game.settings, field))
    # As its OWN child item, never add_data_array on the node: LuaData.serialize
    # drops an object's scalar key-values once it also has nested items, so the
    # pattern list would silently vanish alongside `sites` (the same trap the
    # IADS `engine` marker hit).
    node.add_item("weaponPatterns").set_data_array(list(GPS_GUIDED_WEAPON_PATTERNS))
    site_list = node.add_item("sites")
    objectives = {
        unit.unit_name: tgo
        for cp in game.theater.controlpoints
        for tgo in cp.ground_objects
        for unit in tgo.units
    }
    for site in sites:
        rec = site_list.add_item()
        rec.add_key_value("name", site.name)
        rec.add_key_value("coalition", site.coalition)
        # pydcs Point: x = north, y = east (the emitter frame every 414th mover
        # plugin shares; the Lua converts to the DCS x/z world frame).
        rec.add_key_value("x", str(site.x))
        rec.add_key_value("y", str(site.y))
        rec.add_key_value("reachM", str(site.reach.meters))
        rec.add_key_value("missRadiusM", str(site.miss_radius.meters))
        # The exact names Unit.getByName needs (TheaterUnit.unit_name, what the
        # generator stamps onto the .miz vehicle). UNITS, not groups: a jammer
        # shares its group with the rest of the site, so a group-level liveness
        # check would keep jamming after the jammer truck itself was killed.
        rec.add_data_array("units", list(site.unit_names))
        _add_power(rec, game, objectives[site.unit_names[0]])


def _add_power(rec: LuaItem, game: Game, tgo: TheaterGroundObject) -> None:
    """Export fixed physical supplies independently of Skynet's runtime state."""
    network = getattr(game.theater, "iads_network", None)
    if network is None or not getattr(network, "advanced_iads", False):
        return
    node = next(
        (node for node in network.nodes if node.group.ground_object is tgo), None
    )
    units = [
        unit
        for group in tgo.groups
        for unit in group.units
        if unit.unit_type is not None and unit.unit_type.unit_class is UnitClass.POWER
    ]
    if node is not None:
        units.extend(
            unit
            for group in node.connections.values()
            if group.iads_role is IadsRole.POWER_SOURCE
            and group.ground_object.control_point.captured == tgo.control_point.captured
            for unit in group.units
        )
    power = rec.add_item("power")
    power.add_key_value("required", True)
    sources = power.add_item("sources")
    seen = set()
    for unit in units:
        key = unit.unit_name
        if key in seen:
            continue
        seen.add(key)
        _add_source(sources.add_item(), unit)


def _add_source(rec: LuaItem, unit: TheaterUnit) -> None:
    if isinstance(unit, SceneryUnit):
        # The base script tracks physical scenery even with Skynet disabled.
        rec.add_key_value("kind", "scenery")
        rec.add_key_value("name", unit.name)
        rec.add_key_value("alive", unit.alive)
    else:
        rec.add_key_value("kind", "static" if unit.is_static else "unit")
        rec.add_key_value(
            "name", unit.unit_name + " object" if unit.is_static else unit.unit_name
        )
