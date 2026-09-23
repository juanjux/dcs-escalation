from __future__ import annotations

from dataclasses import dataclass

from dcs.weather import Wind

from game.utils import Speed, knots

#: The fastest wind DCS models. Anything above it is written into the mission and
#: ignored by the sim, so a kneeboard would brief a wind nothing was going to fly.
#: A real jet stream at FL260 beats this routinely, which is why a live observation
#: has to be held to it and not only a generated one.
MAX_WIND_SPEED: Speed = knots(97)


def capped(wind: Wind) -> Wind:
    """The same wind, never faster than the sim can fly."""
    ceiling = MAX_WIND_SPEED.meters_per_second
    if wind.speed <= ceiling:
        return wind
    return Wind(wind.direction, ceiling)


@dataclass(frozen=True)
class WindConditions:
    at_0m: Wind
    at_2000m: Wind
    at_8000m: Wind
