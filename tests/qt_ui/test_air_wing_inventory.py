from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from game.settings import Settings
from game.squadrons.pilot import Pilot
from qt_ui.windows.AirWingDialog import AirInventoryView


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


@pytest.mark.parametrize("latin_names, expected", [(False, "Иван"), (True, "Ivan")])
def test_inventory_opens_with_an_assigned_pilot(
    qt_app: QApplication, latin_names: bool, expected: str
) -> None:
    pilot = Pilot("Иван")
    flight = SimpleNamespace(
        count=2,
        flight_type=SimpleNamespace(value="BARCAP"),
        package=SimpleNamespace(target=SimpleNamespace(name="Patrol area")),
        roster=SimpleNamespace(pilot_at=[pilot, None].__getitem__),
        squadron=SimpleNamespace(
            settings=Settings(latin_pilot_names=latin_names), morale_in_play=False
        ),
        departure=SimpleNamespace(name="Test Airfield"),
        unit_type=SimpleNamespace(display_name="Test Aircraft"),
    )
    coalition = SimpleNamespace(
        ato=SimpleNamespace(packages=[SimpleNamespace(flights=[flight])]),
        air_wing=SimpleNamespace(iter_squadrons=lambda: iter(())),
    )
    game_model: Any = SimpleNamespace(
        game=SimpleNamespace(coalition_for=lambda _side: coalition)
    )

    inventory = AirInventoryView(game_model)
    try:
        assert inventory.table.rowCount() == 2
        assigned = inventory.table.item(0, 4)
        unassigned = inventory.table.item(1, 4)
        assert assigned is not None and assigned.text() == expected
        assert unassigned is not None and unassigned.text() == "Unassigned"
        assert pilot.name == "Иван"
    finally:
        inventory.close()
