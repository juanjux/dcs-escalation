import os
from types import SimpleNamespace
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from qt_ui.widgets.combos.QSquadronLiverySelector import SquadronLiverySelector


class Livery(NamedTuple):
    id: str
    name: str
    countries: None = None


@pytest.fixture
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance()
    assert instance is None or isinstance(instance, QApplication)
    return instance or QApplication([])


def test_rebinding_livery_selector_targets_the_replacement_squadron(
    app: QApplication,
) -> None:
    aircraft = MagicMock(
        dcs_unit_type=SimpleNamespace(
            iter_liveries=lambda: [Livery("skin_a", "A"), Livery("skin_b", "B")]
        ),
        default_livery=None,
    )
    coalition = SimpleNamespace(
        faction=SimpleNamespace(
            country=SimpleNamespace(shortname="BLUE"), liveries_overrides={}
        )
    )
    original: Any = SimpleNamespace(
        aircraft=aircraft,
        coalition=coalition,
        livery="SKIN_A",
        livery_set=["skin_a", "skin_b"],
        use_livery_set=False,
    )
    replacement: Any = SimpleNamespace(
        aircraft=aircraft,
        coalition=coalition,
        livery=None,
        livery_set=["skin_a", "skin_b"],
        use_livery_set=True,
    )
    selector = SquadronLiverySelector(original)
    assert selector.currentData() == "skin_a"
    assert original.livery == "SKIN_A"

    selector.bind_squadron(replacement)
    assert selector.using_livery_set
    assert replacement.livery is None
    selector.setCurrentIndex(selector.findData("skin_b"))

    assert replacement.livery == "skin_b"
    assert not replacement.use_livery_set
    assert original.livery == "SKIN_A"
