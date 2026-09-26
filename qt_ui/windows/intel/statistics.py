"""Selectable campaign history charts, with independent units for each metric."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.game import Game
from game.theater import Player
from qt_ui.widgets.cards import CARD_BG

METRICS = (
    ("aircraft_count", "Aircraft", "Aircraft"),
    ("vehicles_count", "Ground vehicles", "Vehicles"),
    ("money", "Money", "$M"),
    ("income", "Income", "$M / turn"),
    ("pilots", "Living pilots", "Pilots"),
    ("bases", "Bases", "Bases"),
)


def history(
    game: Game, player: Player, metric: str
) -> list[tuple[int, Optional[float]]]:
    """Missing fields in old saves remain gaps, never invented zeroes."""
    return [
        (
            turn,
            getattr(
                record.allied_units if player.is_blue else record.enemy_units,
                metric,
                None,
            ),
        )
        for turn, record in enumerate(game.game_stats.data_per_turn)
    ]


class StatisticsPane(QWidget):
    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.player = Player.BLUE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(QLabel("Turn history · choose the figures to display"))
        controls = QGridLayout()
        self.checks: dict[str, QCheckBox] = {}
        saved = getattr(
            game,
            "intel_statistics_metrics",
            ["aircraft_count", "vehicles_count", "money", "income"],
        )
        for index, (key, title, _) in enumerate(METRICS):
            check = QCheckBox(title)
            check.setChecked(key in saved)
            check.toggled.connect(self._selection_changed)
            controls.addWidget(check, index // 3, index % 3)
            self.checks[key] = check
        layout.addLayout(controls)
        self.compare = QCheckBox("Compare with the other faction")
        self.compare.setChecked(True)
        self.compare.toggled.connect(self.redraw)
        layout.addWidget(self.compare)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        self.charts = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        note = QLabel(
            "Money, income, pilots and bases are recorded from the next turn update. Older saves may have gaps."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #B7C6D2; font-size: 11px;")
        layout.addWidget(note)
        self.redraw()

    def _selection_changed(self) -> None:
        self.game.intel_statistics_metrics = [
            key for key, check in self.checks.items() if check.isChecked()
        ]
        self.redraw()

    def show_side(self, player: Player) -> None:
        if self.player != player:
            self.player = player
            self.redraw()

    def redraw(self) -> None:
        while self.charts.count():
            item = self.charts.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()
        chosen = [metric for metric in METRICS if self.checks[metric[0]].isChecked()]
        if not chosen:
            self.charts.addWidget(QLabel("Select a metric above to show its history."))
        for metric, title, units in chosen:
            chart = QChart()
            chart.setBackgroundBrush(QColor(CARD_BG))
            chart.setTitle(title)
            chart.setTitleBrush(QColor("#F2F7FA"))
            chart.legend().setLabelColor(QColor("#B7C6D2"))
            sides = [self.player]
            if self.compare.isChecked():
                sides.append(Player.RED if self.player.is_blue else Player.BLUE)
            values: list[float] = []
            last_turn = 0
            for side in sides:
                series: Optional[QLineSeries] = None
                labelled = False
                for turn, value in history(self.game, side, metric):
                    last_turn = max(last_turn, turn)
                    if value is None:
                        series = None
                        continue
                    if series is None:
                        series = QLineSeries()
                        series.setName("BLUFOR" if side.is_blue else "OPFOR")
                        series.setPen(
                            QPen(QColor("#8FC3F0" if side.is_blue else "#E8B79E"), 2)
                        )
                        series.setPointsVisible(True)
                        chart.addSeries(series)
                        if labelled:
                            for marker in chart.legend().markers(series):
                                marker.setVisible(False)
                        labelled = True
                    series.append(turn, value)
                    values.append(value)
            if not values:
                chart.setTitle(f"{title} · no recorded data yet")
            x = QValueAxis()
            x.setTitleText("Turn")
            x.setLabelFormat("%.0f")
            step = max(1, math.ceil(last_turn / 5))
            end = max(step, math.ceil(last_turn / step) * step)
            x.setRange(0, end)
            x.setTickCount(end // step + 1)
            y = QValueAxis()
            y.setTitleText(units)
            low, high = min([0.0] + values), max([1.0] + values)
            y.setRange(low * 1.1, high * 1.1)
            y.setLabelFormat("%.0f")
            for axis, alignment in (
                (x, Qt.AlignmentFlag.AlignBottom),
                (y, Qt.AlignmentFlag.AlignLeft),
            ):
                axis.setLabelsColor(QColor("#B7C6D2"))
                axis.setTitleBrush(QColor("#B7C6D2"))
                axis.setGridLineColor(QColor("#33414F"))
                chart.addAxis(axis, alignment)
                for line in chart.series():
                    line.attachAxis(axis)
            view = QChartView(chart)
            view.setRenderHint(QPainter.RenderHint.Antialiasing)
            view.setMinimumHeight(290)
            self.charts.addWidget(view)
        self.charts.addStretch()
