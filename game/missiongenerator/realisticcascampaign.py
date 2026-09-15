"""Opt-in campaign wiring; no settings mutation or default activation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .realisticcasenvironment import SunTimes, export_environment
from .realisticcasluadata import SCRIPT_ORDER, collect_registry, render_startup


def enabled(plugins: Any) -> bool:
    return any(p.identifier == "realisticcas" and p.enabled for p in plugins)


def suppress_legacy_jtac(plugins: Any) -> bool:
    """Temporary scope explicitly accepted by the user: no legacy generated JTAC."""
    return enabled(plugins)


class RealisticCASConfigurationError(ValueError):
    """Actionable plugin conflict, not an unexpected generation failure."""


def validate_compatibility(plugins: Any) -> None:
    """Shared preflight for Take Off and non-UI mission generation."""
    plugins = list(plugins)
    if not enabled(plugins):
        return
    incompatible = sorted(
        p.identifier
        for p in plugins
        if p.enabled and p.identifier in {"tic", "ctld", "MooseAutolase"}
    )
    if incompatible:
        raise RealisticCASConfigurationError(
            "Realistic CAS experimental: disable these plugins before generating: "
            + ", ".join(incompatible)
            + ". Their JTAC/dynamic-unit visibility adapters are not implemented yet."
        )


def prepare_campaign(
    generator: Any, plugins: Any, *, sun_times: SunTimes | None = None
) -> dict[str, Any] | None:
    plugins = list(plugins)
    plugin = next(
        (p for p in plugins if p.identifier == "realisticcas" and p.enabled), None
    )
    if plugin is None:
        return None  # Do not even inspect the mission when disabled.
    validate_compatibility(plugins)
    if generator.mission_data.jtacs:
        raise ValueError(
            "Realistic CAS experimental requires no legacy JTACs in the generated mission"
        )
    options = {
        o.identifier.removeprefix("realisticcas."): o.get_value for o in plugin.options
    }
    profile = options.get("terrainProfile", 0)
    covers = {1: "desert", 2: "grassland", 3: "tundra", 4: "forest", 5: "city"}
    if type(profile) is not int or not 0 <= profile <= 5:
        raise ValueError("Realistic CAS: terrain profile must be 0..5")
    if profile == 0:
        name = generator.mission.terrain.name.lower().replace(" ", "")
        cover = {
            "iraq": "desert",
            "syria": "desert",
            "persiangulf": "desert",
            "nevada": "desert",
            "sinaimap": "desert",
            "afghanistan": "desert",
            "caucasus": "grassland",
            "normandy": "grassland",
            "thechannel": "grassland",
            "germanycw": "grassland",
            "kola": "tundra",
            "falklands": "grassland",
            "marianaislands": "forest",
        }.get(name)
        if cover is None:
            raise ValueError(
                "Realistic CAS: unknown theater biome; select terrain profile 1..5"
            )
    else:
        cover = covers[profile]
    environment, warnings = export_environment(
        generator.mission,
        generator.game.theater,
        default_cover=cover,
        sun_times=sun_times,
    )
    registry = collect_registry(
        generator.mission,
        generator.mission_data,
        enabled=True,
        unit_map=generator.unit_map,
    )
    assert registry is not None
    registry["warnings"].extend(warnings)
    registry["warnings"].append(
        "Experimental: legacy JTAC generation suppressed; runtime-created units need adapters"
    )
    acquisition = options.get("acquisitionSeconds", 20)
    ttl = options.get("contactSeconds", 600)
    if type(ttl) is not int or not 30 <= ttl <= 3600:
        raise ValueError("Realistic CAS: contact duration must be 30..3600 seconds")
    debug = options.get("debug", False)
    if type(debug) is not bool:
        raise ValueError("Realistic CAS: debug must be boolean")
    config = {
        "enabled": True,
        "registry": registry,
        "environment": environment,
        "acquisitionSeconds": acquisition,
        "ttl": ttl,
        "debug": debug,
        "interval": 0.25,
        "revisit": 5,
        "targetBudget": 64,
        "workBudget": 1024,
        "observerBudget": 64,
        "observerQuantum": 128,
        "losBudget": 64,
    }
    render_startup(config)  # Validate typed metadata/options before adding triggers.
    return config


def inject_campaign(generator: Any, config: dict[str, Any] | None) -> None:
    if config is None:
        return
    startup = render_startup(config)
    if startup is None:
        return
    # The ordinary injector only logs missing files. Preflight ALL dependencies
    # here so a damaged installation cannot ship a half-loaded fog plugin.
    root = Path("resources/plugins/realisticcas")
    for name in SCRIPT_ORDER:
        if not (root / name).is_file():
            raise FileNotFoundError(root / name)
    for name in SCRIPT_ORDER:
        generator.inject_plugin_script("realisticcas", name, f"realisticcas-{name}")
    generator.inject_lua_trigger(startup, "Realistic CAS: campaign registry and start")
    registry = config["registry"]
    logging.info(
        "Realistic CAS: %d groups, %d targets, %d observers; %d fixed SAM groups exempt",
        len(registry["groups"]),
        len(registry["targets"]),
        len(registry["observers"]),
        len(registry["knownAirDefenseGroups"]),
    )
    for warning in registry["warnings"]:
        logging.warning("Realistic CAS: %s", warning)
