"""Loan status stays visible in squadron rows and detail headers."""

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.ato import FlightType
from game.highcommand.loans import Loan
from game.squadrons import Squadron
from game.theater import Player
from qt_ui.widgets.squadronloan import squadron_loan_text


@pytest.fixture(scope="module")
def app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _squadron(side: Player = Player.BLUE, on_loan: bool = True) -> Any:
    squadron = MagicMock(spec=Squadron)
    squadron.player = side
    squadron.name = "Squadron 003"
    squadron.nickname = "Loan squadron"
    squadron.aircraft = SimpleNamespace(
        display_name="AH-1W SuperCobra", dcs_id="AH-1W", variant_id="AH-1W SuperCobra"
    )
    squadron.location = SimpleNamespace(name="Carrier", is_fleet=True)
    squadron.primary_task = FlightType.CAS
    squadron.owned_aircraft = 10
    squadron.destination = None
    squadron.cohesion = None
    squadron.fit_for_duty = [None] * 16
    squadron.living_pilots = [None] * 16
    squadron.untasked_crewed_aircraft = 10
    commands = {
        Player.BLUE: SimpleNamespace(loans=[]),
        Player.RED: SimpleNamespace(loans=[]),
    }
    game = SimpleNamespace(turn=33, high_command_for=commands.__getitem__)
    squadron.coalition = SimpleNamespace(game=game)
    if on_loan:
        commands[side].loans.append(Loan(squadron, 36))
    return squadron


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_status_reads_the_owning_sides_loan(side: Player) -> None:
    squadron = _squadron(side)
    game = squadron.coalition.game
    assert squadron_loan_text(squadron) == "On loan · 3 turns remaining"
    game.turn = 35
    assert squadron_loan_text(squadron) == "On loan · 1 turn remaining"
    game.turn = 37
    assert squadron_loan_text(squadron) == "On loan · 0 turns remaining"
    game.high_command_for(side).loans.clear()
    assert squadron_loan_text(squadron) == ""


def test_permanent_squadron_with_the_same_name_has_no_badge() -> None:
    squadron = _squadron(on_loan=False)
    other = _squadron()
    squadron.coalition.game.high_command_for(Player.BLUE).loans.append(Loan(other, 36))
    assert squadron_loan_text(squadron) == ""


@pytest.mark.parametrize("grouping", [None, "base", "type"])
def test_loan_rows_get_their_own_line_in_every_grouping(
    app: Any, grouping: Any
) -> None:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage, QPainter, QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QStyleOptionViewItem
    from qt_ui.models import AirWingModel
    from qt_ui.widgets.squadrondelegate import (
        GROUPED_ROW_HEIGHT,
        GROUP_HEADER_HEIGHT,
        GroupHeaderRole,
        LOAN_LINE_HEIGHT,
        ROW_HEIGHT,
        SquadronDelegate,
    )

    model = QStandardItemModel()
    for squadron in (_squadron(), _squadron(on_loan=False)):
        item = QStandardItem()
        item.setData(squadron, AirWingModel.SquadronRole)
        model.appendRow(item)
    header = QStandardItem()
    header.setData(("Group", 2), GroupHeaderRole)
    model.appendRow(header)
    delegate = SquadronDelegate(MagicMock())
    delegate.grouping = grouping
    base_height = GROUPED_ROW_HEIGHT if grouping else ROW_HEIGHT
    assert delegate.row_height(model.index(0, 0)) == base_height + LOAN_LINE_HEIGHT
    assert delegate.row_height(model.index(1, 0)) == base_height
    assert delegate.row_height(model.index(2, 0)) == GROUP_HEADER_HEIGHT
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 1200, base_height + LOAN_LINE_HEIGHT)
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, model.index(0, 0))
    finally:
        painter.end()
    assert any(
        image.pixelColor(x, y).name() == "#e0a86b"
        for y in range(base_height, image.height() - 1)
        for x in range(120, 420)
    )


@pytest.mark.parametrize("on_loan", [False, True])
def test_detail_header_shows_the_same_status(app: Any, on_loan: bool) -> None:
    from PySide6.QtWidgets import QLabel, QWidget
    from qt_ui.windows.SquadronDialog import SquadronDialog

    squadron = _squadron(on_loan=on_loan)
    dialog: Any = SimpleNamespace(squadron=squadron)
    holder = QWidget()
    holder.setLayout(SquadronDialog._build_header(dialog))
    badge = holder.findChild(QLabel, "squadronLoanStatus")
    if on_loan:
        assert badge is not None and badge.text() == squadron_loan_text(squadron)
    else:
        assert badge is None
    holder.close()
