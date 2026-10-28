"""Location-button hovering is transient and does not navigate the map."""

import gc
import os
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dcs.mapping import LatLng
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton
import pytest
import shiboken6

from game.server import EventStream
from game.server.eventstream.models import GameUpdateEventsJs
from game.sim.gameupdateevents import GameUpdateEvents
from qt_ui.widgets.maphover import bind_map_hover


@pytest.fixture
def hover(monkeypatch: pytest.MonkeyPatch) -> Any:
    app = QApplication.instance() or QApplication([])
    sent: list[GameUpdateEvents] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    button = QPushButton("Show on map")
    target = SimpleNamespace(
        id=uuid4(), position=SimpleNamespace(latlng=lambda: LatLng(33, 69))
    )
    bind_map_hover(button, lambda: target)
    gc.collect()
    yield SimpleNamespace(app=app, button=button, target=target, sent=sent)
    if shiboken6.isValid(button):
        button.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize(
    "clear", [QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.EnabledChange]
)
def test_enter_and_leave_share_an_owner_without_navigation(
    hover: Any, clear: QEvent.Type
) -> None:
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    entered = hover.sent[-1]
    assert entered.map_hover is not None
    owner, target, position = entered.map_hover
    assert target == hover.target.id and position == LatLng(33, 69)
    assert entered.fly_to is None and entered.fly_to_zoom is None
    QCoreApplication.sendEvent(hover.button, QEvent(clear))
    assert hover.sent[-1].map_hover == (owner, None, None)
    count = len(hover.sent)
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Leave))
    assert len(hover.sent) == count


def test_destroyed_button_clears_an_active_hover(hover: Any) -> None:
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    owner = hover.sent[-1].map_hover[0]
    hover.button.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert hover.sent[-1].map_hover == (owner, None, None)


def test_disabled_buttons_do_not_start_a_hover(hover: Any) -> None:
    hover.button.setEnabled(False)
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    assert not hover.sent


def test_repeated_enter_is_deduplicated_and_updated_targets_are_resolved(
    hover: Any,
) -> None:
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    assert len(hover.sent) == 1
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    assert len(hover.sent) == 1
    hover.target.position = SimpleNamespace(latlng=lambda: LatLng(34, 70))
    QCoreApplication.sendEvent(hover.button, QEvent(QEvent.Type.Enter))
    assert len(hover.sent) == 2
    assert hover.sent[-1].map_hover[2] == LatLng(34, 70)


def test_target_is_resolved_at_hover_time_and_none_is_ignored(hover: Any) -> None:
    current: list[Any] = [None]
    other = QPushButton()
    bind_map_hover(other, lambda: current[0])
    QCoreApplication.sendEvent(other, QEvent(QEvent.Type.Enter))
    assert not hover.sent
    current[0] = SimpleNamespace(latlng=lambda: LatLng(34, 70))
    QCoreApplication.sendEvent(other, QEvent(QEvent.Type.Enter))
    assert hover.sent[-1].map_hover[1:] == (None, LatLng(34, 70))
    other.deleteLater()


def test_hover_events_serialize_set_and_clear_without_requiring_a_campaign() -> None:
    owner, target = uuid4(), uuid4()
    for position in (LatLng(33, 69), None):
        event = GameUpdateEvents(
            map_hover=(owner, target if position else None, position)
        )
        assert not event.empty
        payload = GameUpdateEventsJs.from_events(event, None).model_dump(mode="json")
        assert payload["map_hover"] == {
            "owner": str(owner),
            "target_id": str(target) if position else None,
            "position": {"lat": 33, "lng": 69} if position else None,
        }
        assert payload["fly_to"] is None
