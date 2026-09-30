"""The two fuel displays use the same rows and refresh their units and segments."""

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from game.ato.fuelestimate import FuelEstimate
from game.utils import pounds
from qt_ui.windows.mission.flight.fuelsummary import FuelBar, FuelSummary, segment_label


@pytest.fixture(scope="module")
def qt_app() -> Any:
    return QApplication.instance() or QApplication([])


def label_texts(widget: FuelSummary) -> list[str]:
    result = []
    for i in range(widget.rows.count()):
        item = widget.rows.itemAt(i)
        assert item is not None
        label = item.widget()
        if isinstance(label, QLabel):
            result.append(label.text())
    return result


@pytest.mark.parametrize("bars", [False, True])
def test_segments_units_and_refresh(qt_app: Any, bars: bool) -> None:
    widget = FuelSummary(show_bars=bars)
    estimates = [
        FuelEstimate(pounds(1500), pounds(1000)),
        FuelEstimate(pounds(500), pounds(2000)),
    ]
    widget.show_estimates(estimates)
    texts = label_texts(widget)
    assert "Before refuel" in texts and "After refuel" in texts
    assert "short 500 lb" in texts and "+1,500 lb" in texts
    assert len(widget.findChildren(FuelBar)) == (2 if bars else 0)
    widget.show_estimates(estimates[:1], kg=True)
    texts = label_texts(widget)
    assert "Fuel" in texts
    assert "Before refuel" not in texts
    assert any("kg" in text for text in texts)
    assert not any("lb" in text for text in texts)
    widget.close()


def test_multiple_refuel_labels() -> None:
    assert [segment_label(i, 3) for i in range(3)] == [
        "To refuel 1",
        "Refuel 1 → 2",
        "After refuel 2",
    ]


def test_payload_updates_units_fuel_and_edited_route(qt_app: Any) -> None:
    from game.ato.flightwaypointtype import FlightWaypointType as W
    from qt_ui.windows.mission.flight.payload.QFlightPayloadTab import DcsFuelSelector
    from qt_ui.windows.mission.flight.QFlightPlanner import QFlightPlanner
    from tests.test_refuel_fuel_estimate import flight_for

    flight = flight_for([(W.TAKEOFF, 0), (W.REFUEL, 100), (W.LANDING_POINT, 200)])
    selector = DcsFuelSelector(flight)
    assert "Before refuel" in label_texts(selector.fuel_summary)
    selector.unit.setCurrentIndex(0)
    assert any("kg" in text for text in label_texts(selector.fuel_summary))
    selector.fuel.setValue(1500)
    texts = label_texts(selector.fuel_summary)
    assert any("1,500 kg" in text for text in texts)
    assert any("2,000 kg" in text for text in texts)
    selector.unit.setCurrentIndex(1)
    assert not any("kg" in text for text in label_texts(selector.fuel_summary))

    flight.flight_plan.waypoints.pop(1)
    payload = SimpleNamespace(fuel_selector=selector)
    planner: Any = SimpleNamespace(
        widget=lambda _: payload, payload_tab=payload, waypoint_tab=object()
    )
    QFlightPlanner.on_tab_changed(planner, 1)
    assert "Before refuel" not in label_texts(selector.fuel_summary)
    assert "Fuel" in label_texts(selector.fuel_summary)
    selector.close()


@pytest.mark.parametrize("short_segment", [None, 0, 1])
def test_header_checks_each_segment(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch, short_segment: int | None
) -> None:
    from game.ato.starttype import StartType
    from qt_ui.windows.mission.flight.header import FlightHeader

    estimates = [FuelEstimate(pounds(500), pounds(1000)) for _ in range(2)]
    if short_segment is not None:
        estimates[short_segment] = FuelEstimate(pounds(1500), pounds(1000))
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.header.estimate_fuel_segments",
        lambda _: estimates,
    )
    header: Any = SimpleNamespace(
        flight=SimpleNamespace(missing_pilots=0, start_type=StartType.COLD)
    )
    attention = FlightHeader._attention(header)
    if short_segment is None:
        assert attention == []
    else:
        assert len(attention) == 1
        assert attention[0][0] == "short 500 lb of fuel"
