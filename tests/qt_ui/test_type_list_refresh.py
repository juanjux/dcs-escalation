"""Refreshing the type list must not be mistaken for the player picking a type.

Every type_selected rebuilds the squadrons column, and that column hides and unparents
each of its cards to rebuild it, which drops the keyboard focus. The counts in the type
list are redrawn on every press of an arrow key in a squadron's size, so a refresh that
lands back on the same type was rebuilding -- four times over -- the very card the key
was being pressed in, and the focus went with it.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


class _Aircraft:
    def __init__(self, name: str) -> None:
        self.display_name = name

    def __repr__(self) -> str:
        return self.display_name


def _squadron() -> Any:
    return SimpleNamespace(max_size=12)


def _list(wing: Any) -> Any:
    from qt_ui.windows.airwingconfig.panes import AircraftTypeList

    return AircraftTypeList(cast(Any, wing))


def test_a_refresh_that_keeps_the_type_says_nothing(qt_app: Any) -> None:
    hornet, viper = _Aircraft("F/A-18C Hornet"), _Aircraft("F-16CM Viper")
    wing = SimpleNamespace(squadrons={hornet: [_squadron()], viper: [_squadron()]})
    types = _list(wing)

    said: list[Any] = []
    types.type_selected.connect(said.append)
    before = types.selected_type()
    types.refresh()

    assert said == []
    assert types.selected_type() is before


def test_the_counts_still_come_out_right(qt_app: Any) -> None:
    """Quiet, but not idle: the row data is what the pane draws."""
    from qt_ui.windows.airwingconfig.panes import DATA_ROLE

    hornet = _Aircraft("F/A-18C Hornet")
    wing = SimpleNamespace(squadrons={hornet: [_squadron()]})
    types = _list(wing)

    wing.squadrons[hornet] = [_squadron(), _squadron()]
    types.refresh()

    data = types.item_model.item(0).data(DATA_ROLE)
    assert data["squadrons"] == 2
    assert data["aircraft_count"] == 24


def test_losing_the_selected_type_is_announced(qt_app: Any) -> None:
    hornet, viper = _Aircraft("F/A-18C Hornet"), _Aircraft("F-16CM Viper")
    wing = SimpleNamespace(squadrons={hornet: [_squadron()], viper: [_squadron()]})
    types = _list(wing)
    types.refresh(keep=hornet)

    said: list[Any] = []
    types.type_selected.connect(said.append)
    del wing.squadrons[hornet]
    types.refresh()

    assert said == [viper]
    assert types.selected_type() is viper


def test_the_player_picking_a_row_is_still_announced(qt_app: Any) -> None:
    hornet, viper = _Aircraft("F/A-18C Hornet"), _Aircraft("F-16CM Viper")
    wing = SimpleNamespace(squadrons={hornet: [_squadron()], viper: [_squadron()]})
    types = _list(wing)

    said: list[Any] = []
    types.type_selected.connect(said.append)
    # Row 0 is the Viper: "F-16" sorts before "F/A-18".
    types.setCurrentIndex(types.item_model.index(1, 0))

    assert said == [hornet]
