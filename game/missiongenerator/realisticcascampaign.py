"""Opt-in campaign wiring; no settings mutation or default activation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .realisticcasenvironment import SunTimes, export_environment
from .realisticcasf10 import collect_frontline_map_groups, apply_frontline_map_groups
from .realisticcasluadata import (
    SCRIPT_ORDER,
    afac_marking_config,
    collect_registry,
    probability_config,
    render_startup,
)


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
    incompatible = []
    for plugin in plugins:
        if not plugin.enabled:
            continue
        if plugin.identifier == "ctld":
            autolase = next(
                (
                    option.get_value
                    for option in getattr(plugin, "options", [])
                    if option.identifier == "ctld.autolase"
                ),
                True,  # Matches the manifest default for older definitions.
            )
            if autolase is not False:
                incompatible.append("ctld: turn off 'JTAC autolase targets'")
        elif plugin.identifier == "tic":
            incompatible.append("tic: disable the plugin (visibility/clone conflict)")
        elif plugin.identifier == "MooseAutolase":
            incompatible.append("MooseAutolase: disable the autolase plugin")
    if incompatible:
        raise RealisticCASConfigurationError(
            "Realistic CAS experimental: "
            + "; ".join(sorted(incompatible))
            + ". CTLD logistics may remain enabled with autolase off. "
            "Combined Arms JTAC controller slots do not enable AI autolase."
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
    include_armor = options.get("includeArmorGroups", False)
    if type(include_armor) is not bool:
        raise ValueError("Realistic CAS: armor group discovery must be boolean")
    f10_frontline = options.get("f10FrontlineContacts", False)
    if type(f10_frontline) is not bool:
        raise ValueError("Realistic CAS: F10 frontline contacts must be boolean")
    afac_enabled = options.get("afacEnabled", False)
    if type(afac_enabled) is not bool:
        raise ValueError("Realistic CAS: AFAC enabled must be boolean")
    if not afac_enabled and any(
        f.flight_type.is_afac
        for f in generator.mission_data.flights
        if hasattr(f.flight_type, "is_afac")
    ):
        raise ValueError("Enable AFAC search missions or remove AFAC flights")
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
        include_armor_groups=include_armor,
    )
    assert registry is not None
    registry["warnings"].extend(warnings)
    if afac_enabled:
        for observer in registry["observers"]:
            if observer.get("afac") and "navigation" not in observer["afac"]:
                raise ValueError(
                    "Realistic CAS: AFAC native patrol and exit metadata missing"
                )
        generator.unit_map.afac_targets = {
            t["name"]: (t["groupName"], t["coalition"])
            for t in registry["targets"] + registry["afacKnownTargets"]
        }
    registry["warnings"].append(
        "Experimental: legacy JTAC generation suppressed; runtime-created units need adapters"
    )
    # Ignore the retired option in older saves; no continuous-observation delay.
    acquisition = 0
    probabilistic = options.get("probabilisticDetection", True)
    if type(probabilistic) is not bool:
        raise ValueError("Realistic CAS: probabilistic detection must be boolean")
    ttl = options.get("contactSeconds", 600)
    if type(ttl) is not int or not 30 <= ttl <= 3600:
        raise ValueError("Realistic CAS: contact duration must be 30..3600 seconds")
    debug = options.get("debug", False)
    if type(debug) is not bool:
        raise ValueError("Realistic CAS: debug must be boolean")
    contact_reports = options.get("contactReports", True)
    contact_report_seconds = options.get("contactReportSeconds", 15)
    config: dict[str, Any] = {
        "enabled": True,
        "contactReports": contact_reports,
        "contactReportSeconds": contact_report_seconds,
        "f10FrontlineContacts": f10_frontline,
        "frontlineMapGroups": (
            collect_frontline_map_groups(
                generator.mission, generator.mission_data, registry
            )
            if f10_frontline
            else []
        ),
        "afacEnabled": afac_enabled,
        "afacMarking": afac_marking_config(options) if afac_enabled else None,
        "afacAvoidance": (
            {"clouds": environment.get("clouds")} if afac_enabled else None
        ),
        "registry": registry,
        "environment": environment,
        "acquisitionSeconds": acquisition,
        "probabilisticDetection": probabilistic,
        "probability": probability_config(options),
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
    if f10_frontline:
        apply_frontline_map_groups(generator.mission, config["frontlineMapGroups"])
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
