from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .optiondescription import OptionDescription, SETTING_DESCRIPTION_KEY


@dataclass(frozen=True)
class TextOption(OptionDescription):
    """A free-text setting, rendered as a single-line edit box.

    For values that cannot be offered as a list: a filesystem path, or an identifier
    (an ICAO code, say) drawn from a set too large or too external to enumerate.
    ``placeholder`` is shown greyed out while the box is empty, which is how an
    "leave blank and it will be worked out" default announces itself.
    """

    placeholder: Optional[str] = None

    #: Cap on how much can be typed. A short cap also narrows the box, because a
    #: field five characters wide should not look like one that takes a path.
    max_length: Optional[int] = None


def text_option(
    text: str,
    page: str,
    section: str,
    default: str = "",
    placeholder: Optional[str] = None,
    max_length: Optional[int] = None,
    detail: Optional[str] = None,
    tooltip: Optional[str] = None,
    causes_expensive_game_update: bool = False,
    visible_when: Optional[Callable[[Any], bool]] = None,
    subsection: Optional[str] = None,
    **kwargs: Any,
) -> str:
    return field(
        metadata={
            SETTING_DESCRIPTION_KEY: TextOption(
                page,
                section,
                text,
                detail,
                tooltip,
                causes_expensive_game_update,
                placeholder,
                max_length,
                visible_when=visible_when,
                subsection=subsection,
            )
        },
        default=default,
        **kwargs,
    )
