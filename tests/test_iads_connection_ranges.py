"""How far comms and power reach is a setting, not a constant in the source.

Only consulted when Escalation works a network out by distance: a campaign that
wires its own IADS says what is connected to what, and no range is applied to it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.theater.iadsnetwork.iadsrole import (
    DEFAULT_COMMS_RANGE_NM,
    DEFAULT_POWER_RANGE_NM,
    IadsRole,
)
from game.utils import nautical_miles


def _settings(**options: Any) -> Any:
    return SimpleNamespace(
        plugin_option_or=lambda identifier, default=None: options.get(
            identifier, default
        )
    )


def test_the_defaults_are_the_ranges_the_fork_always_used() -> None:
    """15 and 35 nm, so a campaign in progress builds the same network it did."""
    assert DEFAULT_COMMS_RANGE_NM == 15.0
    assert DEFAULT_POWER_RANGE_NM == 35.0
    assert IadsRole.CONNECTION_NODE.connection_range() == nautical_miles(15)
    assert IadsRole.POWER_SOURCE.connection_range() == nautical_miles(35)


def test_the_options_are_read_when_they_are_set() -> None:
    settings = _settings(
        **{"skynetiads.commsRangeNm": 25, "skynetiads.powerRangeNm": 60}
    )
    assert IadsRole.CONNECTION_NODE.connection_range(settings) == nautical_miles(25)
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(60)


def test_a_save_that_never_had_the_options_gets_the_defaults() -> None:
    """plugin_option_or answers with the default for settings written before them."""
    settings = _settings()
    assert IadsRole.CONNECTION_NODE.connection_range(settings) == nautical_miles(15)
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(35)


def test_an_unreadable_value_falls_back_rather_than_raising() -> None:
    settings = _settings(**{"skynetiads.powerRangeNm": "wide"})
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(35)


def test_nothing_else_has_a_reach() -> None:
    for role in (IadsRole.SAM, IadsRole.EWR, IadsRole.COMMAND_CENTER):
        assert role.connection_range().meters == 0
