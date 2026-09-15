"""Final-mission weather/time -> cheap Realistic CAS perception inputs.

Read-only, no plugin activation. Cloud presets expose no numeric layer geometry:
their authored description selects an APPROXIMATE slab, never their reused name.
All approximations travel with the export as warnings for logging/review.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

COVERS = frozenset({"desert", "grassland", "tundra", "forest", "city"})
SunTimes = Callable[[float, float, timezone, date], tuple[datetime, datetime] | None]


def _number(value: Any, label: str, low: float, high: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Realistic CAS: invalid {label}: {value!r}")
    return float(value)


def _seconds(value: datetime) -> float:
    return (
        value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6
    )


def export_environment(
    mission: Any,
    theater: Any,
    *,
    default_cover: str,
    sun_times: SunTimes | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Use the FINAL pydcs mission (including live-weather overrides).

    The caller must select an explicit approximate biome. This does not infer
    cities/forests from land/water, objective names or airbase locations. Three
    local calendar days cover a mission crossing midnight; Lua repeats the last
    daily schedule beyond that documented horizon. Polar days use constant light.
    """
    if default_cover not in COVERS:
        raise ValueError("Realistic CAS requires an explicit terrain-cover profile")
    if sun_times is None:
        from game.theater.daytimecalculator import _sun_times

        sun_times = _sun_times
    start = mission.start_time
    if not isinstance(start, datetime):
        raise ValueError("Realistic CAS requires the generated mission's datetime")
    tz = theater.timezone
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    else:
        start = start.astimezone(tz)
    position = theater.reference_position
    lat = _number(position.lat, "latitude", -90, 90)
    lon = _number(position.lng, "longitude", -180, 180)
    warnings = [
        f"Approximate homogeneous terrain cover: {default_cover}; no city/forest map exported",
        "Solar schedule uses the campaign reference position, not a per-unit ephemeris; horizon 3 local days",
    ]
    days: list[dict[str, float]] = []
    for index in range(3):
        date = start.date() + timedelta(days=index)
        times = sun_times(lat, lon, tz, date)
        if times is None:
            # Only used AFTER the existing solar calculator establishes no
            # horizon crossing. Seasonal declination sign distinguishes polar
            # summer from winter; not a model of polar twilight brightness.
            declination = -23.44 * math.cos(
                2 * math.pi * (date.timetuple().tm_yday + 10) / 365.2425
            )
            light = 1 if lat * declination > 0 else 0
            days.append({"constantLight": light})
            warnings.append(
                f"{date}: polar illumination approximated as constant {light}"
            )
        else:
            rise, setting = (t.astimezone(tz) for t in times)
            sunrise, sunset = _seconds(rise), _seconds(setting)
            if sunrise == sunset:
                raise ValueError(
                    "Realistic CAS received an ambiguous zero-length solar day"
                )
            days.append({"sunrise": sunrise, "sunset": sunset})

    weather = mission.weather
    visibility = _number(weather.visibility_distance, "visibility", 0, 1_000_000)
    if weather.auto_fog:
        # Native automatic fog has no exported temporal density here. In
        # particular, the default fog_visibility=25 must NOT become 25m weather.
        warnings.append(
            "Native automatic fog density is unavailable; using exported general visibility"
        )
    elif weather.enable_fog and weather.fog_thickness > 0:
        visibility = min(
            visibility, _number(weather.fog_visibility, "fog visibility", 0, 1_000_000)
        )
        warnings.append(
            "Manual fog approximated as a uniform visibility limit for ground observation"
        )
    if weather.enable_dust:
        visibility = min(
            visibility, _number(weather.dust_density, "dust visibility", 0, 1_000_000)
        )
        warnings.append("Dust approximated as a uniform visibility limit")
    rain = getattr(weather.clouds_iprecptns, "value", weather.clouds_iprecptns) != 0
    config: dict[str, Any] = {
        "defaultCover": default_cover,
        "startTime": _seconds(start),
        "solarDays": days,
        "weather": 0.7 if rain else 1,
        "visibility": visibility,
        "zones": [],
    }
    preset = weather.clouds_preset
    thickness: float
    if preset is not None:
        # Names such as Preset1 are reused by different cloud packs. Classify
        # descriptive text instead; unsupported custom text has a logged fallback.
        text = f"{preset.ui_name} {preset.description}".lower()
        if re.search(r"\b(rain|storm|precipitation)\b", text):
            config["weather"] = 0.7
        if re.search(r"\b(overcast|ovc)\b", text):
            label, thickness, visual, ir = "overcast", 3000, 0.05, 0.35
        elif re.search(r"\b(broken|bkn)\b", text):
            label, thickness, visual, ir = "broken", 2000, 0.25, 0.55
        elif re.search(r"\b(scattered|sct)\b", text):
            label, thickness, visual, ir = "scattered", 1250, 0.6, 0.8
        elif re.search(r"\b(few)\b", text):
            label, thickness, visual, ir = "few", 750, 0.8, 0.9
        elif re.search(r"\b(clear|clr|cavok)\b", text):
            label, thickness, visual, ir = "clear", 0, 1, 1
        else:
            label, thickness, visual, ir = "unclassified fallback", 2000, 0.3, 0.6
        warnings.append(
            f"Cloud preset {preset.name!r}: {label} approximate slab; not native layer geometry"
        )
    else:
        density = _number(weather.clouds_density, "cloud density", 0, 10)
        thickness = _number(weather.clouds_thickness, "cloud thickness", 0, 50000)
        visual, ir = max(0.05, 1 - density / 10), max(0.35, 1 - density * 0.065)
        if density == 0:
            thickness = 0
        elif thickness == 0:
            thickness = 1000
            warnings.append(
                "Nonzero cloud density without thickness: approximate 1000m slab"
            )
    if thickness:
        base = _number(weather.clouds_base, "cloud base", 0, 50000)
        config["clouds"] = {
            "base": base,
            "top": base + thickness,
            "visualTransmission": visual,
            "irTransmission": ir,
        }
    return config, warnings
