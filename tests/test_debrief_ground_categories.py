"""Ground loss categories preserve counts, transport notes and saved reports."""

from dataclasses import dataclass
import os
import pickle
from typing import Any

import pytest
from dcs.ships import USS_Arleigh_Burke_IIa
from dcs.statics import groundobject_map

from game.data.units import UnitClass
from game.debriefingreport import DebriefingReport, LossCosts, ground_loss_category
from game.theater.player import Player
from tests.test_debriefing_report import _report

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@dataclass(frozen=True)
class Unit:
    name: str
    unit_class: UnitClass

    def __str__(self) -> str:
        return self.name


@pytest.mark.parametrize("player", [Player.BLUE, Player.RED])
def test_categories_keep_each_loss_once_and_preserve_transport_notes(
    player: Player,
) -> None:
    tank = Unit("Tank", UnitClass.TANK)
    manpad = Unit("MANPADS", UnitClass.MANPAD)
    missile = Unit("SSM", UnitClass.MISSILE)
    static = next(iter(groundobject_map))
    ship = USS_Arleigh_Burke_IIa.id
    report = _report(
        front_line_losses_by_type=lambda side: (
            {tank: 3, manpad: 2} if side == player else {}
        ),
        motorpool_losses_by_type=lambda side: {tank: 1} if side == player else {},
        convoy_losses_by_type=lambda side: {missile: 1} if side == player else {},
        cargo_ship_losses_by_type=lambda side: {tank: 2} if side == player else {},
        airlift_losses_by_type=lambda side: {manpad: 1} if side == player else {},
        ground_object_losses_by_type=lambda side: (
            {static: 2, ship: 1} if side == player else {}
        ),
        scenery_losses_by_type=lambda side: (
            {"Scenery factory": 4} if side == player else {}
        ),
    )
    groups = report.ground_rows_by_category(player)
    assert list(groups) == ["SAMs", "Armor", "Buildings", "Ships"]
    assert groups["SAMs"] == [("MANPADS", 2, ""), ("MANPADS from airlift", 1, "")]
    assert groups["Armor"] == [
        ("Tank", 3, ""),
        ("Tank from motorpool", 1, ""),
        ("SSM from convoy", 1, ""),
        ("Tank from cargo ship", 2, ""),
    ]
    assert groups["Buildings"] == [(static, 2, ""), ("Scenery factory", 4, "")]
    assert groups["Ships"] == [(ship, 1, "")]
    assert sorted(row for rows in groups.values() for row in rows) == sorted(
        report.ground_rows(player)
    )
    other = Player.RED if player == Player.BLUE else Player.BLUE
    assert report.ground_rows_by_category(other) == {}
    restored = pickle.loads(pickle.dumps(report))
    assert restored.ground_rows_by_category(player) == groups
    assert restored.game is None


@pytest.mark.parametrize(
    "kind",
    [
        UnitClass.AAA,
        UnitClass.EARLY_WARNING_RADAR,
        UnitClass.TELAR,
        UnitClass.MANPAD,
        UnitClass.ELECTRONIC_WARFARE,
    ],
)
def test_air_defence_types_are_not_mixed_with_armor(kind: UnitClass) -> None:
    assert ground_loss_category(Unit("Not a name heuristic", kind)) == "SAMs"


def test_old_report_classifies_exact_types_and_keeps_unknown_rows() -> None:
    report = DebriefingReport(turn=1)
    report.ground[True] = [
        ("SA-18 Igla manpad", 2, "Preserved note"),
        ("M-1 Abrams from cargo ship", 3, ""),
        (USS_Arleigh_Burke_IIa.id, 1, ""),
        ("Unregistered mod unit", 4, ""),
    ]
    del report.__dict__["ground_categories"]
    report = pickle.loads(pickle.dumps(report))
    groups = report.ground_rows_by_category(Player.BLUE)
    assert groups["SAMs"] == [("SA-18 Igla manpad", 2, "Preserved note")]
    assert groups["Armor"] == [("M-1 Abrams from cargo ship", 3, "")]
    assert groups["Ships"] == [(USS_Arleigh_Burke_IIa.id, 1, "")]
    assert groups["Other ground"] == [("Unregistered mod unit", 4, "")]


def test_ui_separates_categories_without_duplicating_totals() -> None:
    from PySide6.QtWidgets import QApplication, QLabel
    from game.debriefing import SideLossCounts
    from qt_ui.windows.QDebriefingWindow import FactionLosses

    app = QApplication.instance() or QApplication([])
    report = DebriefingReport(turn=2)
    report.losses[True] = SideLossCounts(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    report.ground_categories[True] = {
        "SAMs": [("Radar", 1, "")],
        "Armor": [("Tank", 2, "")],
        "Buildings": [("Factory", 3, "")],
        "Ships": [("Destroyer", 1, "")],
    }
    report.ground[True] = [
        row for rows in report.ground_categories[True].values() for row in rows
    ]
    report.costs[True] = LossCosts(ground=25, income=12, ships=1)
    card = FactionLosses(report, Player.BLUE)
    labels = [label.text() for label in card.findChildren(QLabel)]
    headings = [
        text
        for text in labels
        if text in ("GROUND", "SAMs", "Armor", "Buildings", "Ships")
    ]
    assert headings == ["GROUND", "SAMs", "Armor", "Buildings", "Ships"]
    assert labels.count("Cost to replace") == 1
    assert labels.count("Income lost while repairing") == 1
    assert any("cannot be replaced" in text for text in labels)
    card.close()
    app.processEvents()
