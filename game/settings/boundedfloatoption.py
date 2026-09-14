from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .optiondescription import OptionDescription, SETTING_DESCRIPTION_KEY


@dataclass(frozen=True)
class BoundedFloatOption(OptionDescription):
    min: float
    max: float
    divisor: int

    #: What the spinner puts in front of the number. Defaults to the multiplier these
    #: mostly are; a quantity passes an empty one.
    prefix: str = "X "

    #: How many decimals the spinner shows. One is enough for a multiplier; a setting
    #: whose real value is 0.05 needs two, or it reads as a number nobody set.
    decimals: int = 1


def bounded_float_option(
    text: str,
    page: str,
    section: str,
    default: float,
    min: float,
    max: float,
    divisor: int,
    prefix: str = "X ",
    decimals: int = 1,
    detail: Optional[str] = None,
    tooltip: Optional[str] = None,
    subsection: Optional[str] = None,
    enabled_when: Optional[Callable[[Any], bool]] = None,
    **kwargs: Any,
) -> float:
    return field(
        metadata={
            SETTING_DESCRIPTION_KEY: BoundedFloatOption(
                page,
                section,
                text,
                detail,
                tooltip,
                causes_expensive_game_update=False,
                min=min,
                max=max,
                divisor=divisor,
                prefix=prefix,
                decimals=decimals,
                subsection=subsection,
                enabled_when=enabled_when,
            )
        },
        default=default,
        **kwargs,
    )
