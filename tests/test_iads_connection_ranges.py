"""Configurable coverage used to rebuild IADS topology every turn."""

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


def test_both_infrastructure_ranges_default_to_35_nm() -> None:
    assert DEFAULT_COMMS_RANGE_NM == 35.0
    assert DEFAULT_POWER_RANGE_NM == 35.0
    assert IadsRole.CONNECTION_NODE.connection_range() == nautical_miles(35)
    assert IadsRole.POWER_SOURCE.connection_range() == nautical_miles(35)


def test_the_options_are_read_when_they_are_set() -> None:
    settings = _settings(
        **{"skynetiads.commsRangeNm": 25, "skynetiads.powerRangeNm": 60}
    )
    assert IadsRole.CONNECTION_NODE.connection_range(settings) == nautical_miles(25)
    assert IadsRole.COMMAND_CENTER.connection_range(settings) == nautical_miles(25)
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(60)


def test_a_save_that_never_had_the_options_gets_the_defaults() -> None:
    """plugin_option_or answers with the default for settings written before them."""
    settings = _settings()
    assert IadsRole.CONNECTION_NODE.connection_range(settings) == nautical_miles(35)
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(35)


def test_an_unreadable_value_falls_back_rather_than_raising() -> None:
    settings = _settings(**{"skynetiads.powerRangeNm": "wide"})
    assert IadsRole.POWER_SOURCE.connection_range(settings) == nautical_miles(35)


def test_nothing_else_has_a_reach() -> None:
    for role in (IadsRole.SAM, IadsRole.EWR):
        assert role.connection_range().meters == 0
