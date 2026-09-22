"""A route whose two ends are the same base is not a route.

Each end is matched to the nearest control point on its own, so a single-waypoint
marker -- or a road drawn back onto its own field -- binds a base to itself. The base
then lists itself among its neighbours, and routing a base to itself returns an empty
path that the transport planner indexes unguarded.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _init_persistency(tmp_path_factory: pytest.TempPathFactory) -> None:
    from game import persistency

    persistency.setup(str(tmp_path_factory.mktemp("saved_games")), False, 16897)


def _loader() -> Any:
    from game.campaignloader.mizcampaignloader import MizCampaignLoader

    return MizCampaignLoader


def _cp(name: str) -> Any:
    return SimpleNamespace(name=name)


def test_two_different_bases_are_a_route() -> None:
    palmyra, tiyas = _cp("Palmyra"), _cp("Tiyas")
    assert not _loader()._binds_one_control_point("supply route", "r", palmyra, tiyas)


def test_one_base_at_both_ends_is_not() -> None:
    palmyra = _cp("Palmyra")
    assert _loader()._binds_one_control_point("supply route", "r", palmyra, palmyra)


def test_the_skipped_route_is_named(caplog: pytest.LogCaptureFixture) -> None:
    """Silently dropping an authored route would look like the campaign lost a road."""
    havadarya = _cp("Havadarya")
    with caplog.at_level(logging.WARNING):
        _loader()._binds_one_control_point(
            "shipping lane", "lane 3", havadarya, havadarya
        )
    assert "lane 3" in caplog.text
    assert "Havadarya" in caplog.text
    assert "shipping lane" in caplog.text
