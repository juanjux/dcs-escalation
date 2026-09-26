"""Selectable campaign history charts, with independent units for each metric."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.game import Game
from game.theater import Player
from qt_ui.widgets.cards import CARD_BG, card
from qt_ui.widgets.controls import (
    BORDER,
    CONTROL_HEIGHT,
    IDLE_BG,
    IDLE_TEXT,
    SELECTED_TEXT,
)

METRICS = (
    ("aircraft_count", "Aircraft", "Aircraft"),
    ("vehicles_count", "Ground vehicles", "Vehicles"),
    ("money", "Money", "$M"),
    ("income", "Income", "$M / turn"),
    ("pilots", "Living pilots", "Pilots"),
    ("bases", "Bases", "Bases"),
)


def _toggle(title: str, checked: bool, accent: str = "#8FC3F0") -> QPushButton:
    button = QPushButton(title)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(CONTROL_HEIGHT)
    button.setStyleSheet(
        f"QPushButton {{ background: {IDLE_BG}; color: {IDLE_TEXT};"
        f" border: 1px solid {BORDER}; border-radius: 3px;"
        " padding: 4px 12px; font-size: 12px; }"
        f"QPushButton:checked {{ background: {accent}; color: {SELECTED_TEXT};"
        " font-weight: 600; }"
        f"QPushButton:hover {{ border-color: {accent}; }}"
    )
    return button


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
        controls_card = card()
        control_layout = QVBoxLayout(controls_card)
        control_layout.setContentsMargins(14, 12, 14, 12)
        control_layout.setSpacing(10)
        heading = QLabel("TURN HISTORY · METRICS")
        heading.setStyleSheet("color: #B7C6D2; font-size: 11px; font-weight: 600;")
        control_layout.addWidget(heading)
        controls = QGridLayout()
        controls.setSpacing(6)
        self.checks: dict[str, QPushButton] = {}
        saved = getattr(
            game,
            "intel_statistics_metrics",
            ["aircraft_count", "vehicles_count", "money", "income"],
        )
        for index, (key, title, _) in enumerate(METRICS):
            check = _toggle(title, key in saved)
            check.setAccessibleName(f"Show {title.lower()} history")
            check.toggled.connect(self._selection_changed)
            controls.addWidget(check, index // 3, index % 3)
            self.checks[key] = check
        control_layout.addLayout(controls)
        factions = QHBoxLayout()
        factions.addWidget(QLabel("Compare factions"))
        self.sides: dict[Player, QPushButton] = {}
        for side, title, accent in (
            (Player.BLUE, "BLUFOR", "#8FC3F0"),
            (Player.RED, "OPFOR", "#E8B79E"),
        ):
            toggle = _toggle(title, True, accent)
            toggle.setAccessibleName(f"Show {title} in all charts")
            toggle.toggled.connect(self.redraw)
            self.sides[side] = toggle
            factions.addWidget(toggle)
        factions.addStretch()
        control_layout.addLayout(factions)
        layout.addWidget(controls_card)
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
        # Comparison controls are independent of the other Intel tabs' selected side.
        self.player = player

    def redraw(self) -> None:
        while self.charts.count():
            item = self.charts.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.hide()
                widget.deleteLater()
        chosen = [metric for metric in METRICS if self.checks[metric[0]].isChecked()]
        sides = [side for side, toggle in self.sides.items() if toggle.isChecked()]
        if not chosen:
            self.charts.addWidget(QLabel("Select a metric above to show its history."))
        elif not sides:
            self.charts.addWidget(
                QLabel("Select BLUFOR or OPFOR above to show its history.")
            )
            chosen = []
        for metric, title, units in chosen:
            chart = QChart()
            chart.setBackgroundBrush(QColor(CARD_BG))
            chart.setTitle(title)
            chart.setTitleBrush(QColor("#F2F7FA"))
            chart.legend().setLabelColor(QColor("#B7C6D2"))
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
