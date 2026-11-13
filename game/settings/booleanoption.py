from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .optiondescription import OptionDescription, SETTING_DESCRIPTION_KEY


@dataclass(frozen=True)
class BooleanOption(OptionDescription):
    invert: bool
    forced_true_when_off: Optional[str] = None


def boolean_option(
    text: str,
    page: str,
    section: str,
    default: bool,
    invert: bool = False,
    detail: Optional[str] = None,
    tooltip: Optional[str] = None,
    causes_expensive_game_update: bool = False,
    visible_when: Optional[Callable[[Any], bool]] = None,
    subsection: Optional[str] = None,
    opens_section: Optional[str] = None,
    enabled_when: Optional[Callable[[Any], bool]] = None,
    forced_true_when_off: Optional[str] = None,
    **kwargs: Any,
) -> bool:
    return field(
        metadata={
            SETTING_DESCRIPTION_KEY: BooleanOption(
                page,
                section,
                text,
                detail,
                tooltip,
                causes_expensive_game_update,
                invert,
                visible_when=visible_when,
                subsection=subsection,
                enabled_when=enabled_when,
                opens_section=opens_section,
                forced_true_when_off=forced_true_when_off,
            )
        },
        default=default,
        **kwargs,
    )
