"""Alerts are BLUE-only, persistent, actionable and repeat ongoing issues next turn."""

import pickle
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QToolButton, QWidget
import pytest

from game import notifications as n
from game.missiletargets import MissileTarget
from game.theater.player import Player
from game.theater.controlpoint import Fob
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    MissileSiteGroundObject,
)
from qt_ui.widgets.notifications import NotificationBell
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_missile_targets import populate


class Roster:
    def __init__(self, pilots: list[Any]) -> None:
        self.current_roster = pilots
        self.aircraft = SimpleNamespace(display_name="A-10C Thunderbolt II (Suite 7)")

    def __str__(self) -> str:
        return "Test squadron"


class Wing:
    def __init__(self, roster: Roster) -> None:
        self.roster = roster

    def iter_squadrons(self) -> list[Roster]:
        return [self.roster]


@pytest.fixture
def alerts(world: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w = world
    monkeypatch.setattr(Fob, "frontline_unit_count_limit", property(lambda cp: 20))
    w.game.settings.live_pilots_enabled = True
    w.game.settings.morale_enabled = True
    w.pilot = SimpleNamespace(id=uuid4(), name="Pilot Blue", alive=True, morale=5)
    w.roster = Roster([w.pilot])
    w.game.blue = SimpleNamespace(air_wing=Wing(w.roster))
    w.building = populate(
        w.game,
        BuildingGroundObject(
            "FACTORY", "factory", PresetLocation("FACTORY", w.a.position), w.a, None
        ),
        w.units[7].dcs_unit_type,
        500,
    )
    w.site = populate(
        w.game,
        MissileSiteGroundObject("SCUD", PresetLocation("SCUD", w.a.position), w.a),
        w.units[7].dcs_unit_type,
        501,
    )
    return w


def test_initial_load_has_conditions_but_no_historical_event_flood(alerts: Any) -> None:
    w = alerts
    notices = n.refresh(w.game)
    assert {notice.category for notice in notices} == {
        "pilot_morale",
        "weak_front",
        "missile_no_target",
    }
    assert all(notice.recurring for notice in notices)
    assert all(
        "Enemy" not in notice.title or notice.category == "weak_front"
        for notice in notices
    )
    assert n.refresh(w.game) == notices


def test_mark_read_persists_but_conditions_reappear_next_turn(alerts: Any) -> None:
    w = alerts
    notices = n.refresh(w.game)
    n.mark_read(w.game, notices)
    assert n.refresh(w.game) == []
    copied = pickle.loads(pickle.dumps(w.game))
    assert n.refresh(copied) == []
    copied.turn += 1
    again = n.refresh(copied)
    assert {notice.category for notice in again} == {
        notice.category for notice in notices
    }
    assert not ({notice.id for notice in again} & {notice.id for notice in notices})


def test_resolved_or_disabled_morale_conditions_disappear(alerts: Any) -> None:
    w = alerts
    w.pilot.morale = 50
    assert not any(item.category == "pilot_morale" for item in n.refresh(w.game))
    w.pilot.morale = -20
    w.pilot.alive = False
    assert not any(item.category == "pilot_morale" for item in n.refresh(w.game))
    w.pilot.alive = True
    w.game.settings.morale_enabled = False
    assert not any(item.category == "pilot_morale" for item in n.refresh(w.game))


def test_low_morale_uses_configured_bands(alerts: Any) -> None:
    w = alerts
    w.pilot.morale = 18
    assert not any(item.category == "pilot_morale" for item in n.refresh(w.game))
    w.game.settings.morale_state_shaken = 25
    assert any(item.category == "pilot_morale" for item in n.refresh(w.game))


@pytest.mark.parametrize(
    "aircraft", ["A-10C Thunderbolt II (Suite 7)", "F/A-18C Hornet"]
)
def test_morale_notice_includes_squadron_aircraft(alerts: Any, aircraft: str) -> None:
    w = alerts
    w.roster.aircraft.display_name = aircraft
    notice = next(item for item in n.refresh(w.game) if item.category == "pilot_morale")
    assert notice.title == f"{w.pilot.name}: very low morale"
    assert f"Test squadron · {aircraft} ·" in notice.detail
    assert "Consider rest or leave." in notice.detail
    assert notice.target_kind == "pilot" and notice.target_id == str(w.pilot.id)


def test_captures_and_losses_are_unread_events_not_recurring_conditions(
    alerts: Any,
) -> None:
    w = alerts
    n.refresh(w.game)
    w.b._coalition.player = Player.RED
    w.enemy._coalition.player = Player.BLUE
    notices = n.refresh(w.game)
    events = [
        item for item in notices if item.category in ("base_lost", "base_captured")
    ]
    assert len(events) == 2
    assert {item.target_id for item in events} == {str(w.b.id), str(w.enemy.id)}
    assert not any(item.recurring for item in events)
    n.mark_read(w.game, notices)
    assert n.refresh(w.game) == []
    w.game.turn += 1
    assert not any(item.category.startswith("base_") for item in n.refresh(w.game))


def test_building_completion_detected_once_and_ignores_enemy(alerts: Any) -> None:
    w = alerts
    unit = w.building.groups[0].units[0]
    unit.alive = False
    unit.repair_turns_remaining = 1
    n.refresh(w.game)
    unit.alive = True
    unit.repair_turns_remaining = None
    done = [item for item in n.refresh(w.game) if item.category == "building_ready"]
    assert len(done) == 1 and done[0].target_id == str(w.building.id)
    n.building_ready(w.game, w.building)
    assert (
        len([item for item in n.refresh(w.game) if item.category == "building_ready"])
        == 1
    )
    n.mark_read(w.game, done)
    n.refresh(w.game)
    n.building_ready(w.game, w.building)
    assert not any(item.category == "building_ready" for item in n.refresh(w.game))
    w.building.control_point = w.enemy
    n.building_ready(w.game, w.building)
    assert not any(item.category == "building_ready" for item in n.refresh(w.game))


def test_empty_gps_alert_repeats_every_turn_until_cleared(alerts: Any) -> None:
    w = alerts
    w.site.missile_target = MissileTarget(Player.BLUE, 10000, 20000, "GPS")
    first = [
        item for item in n.refresh(w.game) if item.category == "missile_empty_target"
    ]
    assert len(first) == 1 and first[0].target_id == str(w.site.id)
    n.mark_read(w.game, first)
    assert not any(
        item.category == "missile_empty_target" for item in n.refresh(w.game)
    )
    w.game.turn += 1
    assert any(item.category == "missile_empty_target" for item in n.refresh(w.game))
    w.site.missile_target = None
    assert not any(
        item.category == "missile_empty_target" for item in n.refresh(w.game)
    )


def test_shared_objectives_never_duplicate_or_expose_enemy_alerts(alerts: Any) -> None:
    w = alerts
    enemy = populate(
        w.game,
        MissileSiteGroundObject(
            "ENEMY SCUD", PresetLocation("ENEMY SCUD", w.enemy.position), w.enemy
        ),
        w.units[7].dcs_unit_type,
        502,
    )
    w.a.connected_objectives.append(enemy)
    w.b.connected_objectives.append(w.site)
    notices = n.refresh(w.game)
    sites = [item for item in notices if item.category == "missile_no_target"]
    assert len(sites) == 1 and sites[0].target_id == str(w.site.id)


def test_front_uses_planned_counts_when_current_and_no_enemy_stock(alerts: Any) -> None:
    w = alerts
    w.a.base.commission_units({w.units[7]: 12})
    w.game.ground_planners = {
        w.a.id: SimpleNamespace(units_per_cp={w.enemy.id: [SimpleNamespace(size=12)]})
    }
    assert not any(item.category == "weak_front" for item in n.refresh(w.game))
    w.a.base.armor.clear()
    assert any(item.category == "weak_front" for item in n.refresh(w.game))


def test_old_save_lazy_state_and_event_history_cleanup(alerts: Any) -> None:
    w = alerts
    assert not hasattr(w.game, "campaign_notifications")
    n.refresh(w.game)
    notice = n.CampaignNotice(
        "event", "future", "A future alert", "Detail", w.game.turn, "base", str(w.a.id)
    )
    n.post(w.game, notice)
    n.post(w.game, notice)
    assert n.refresh(w.game).count(notice) == 1
    n.mark_read(w.game, [notice])
    n.refresh(w.game)
    w.game.turn += 2
    n.refresh(w.game)
    assert (
        notice not in n.state(w.game).events and notice.id not in n.state(w.game).read
    )


def test_bell_counter_popup_read_navigation_and_game_switch(
    alerts: Any, controls: Any
) -> None:
    w = alerts
    shown: list[n.CampaignNotice] = []
    bell = NotificationBell(controls.model, shown.append)
    assert bell.notices and "3" in bell.accessibleName()
    bell.show_alerts()
    popup = bell.popup
    assert popup is not None and popup.findChildren(QLabel)
    item = bell.notices[0]
    popup.show_notice(item)
    assert shown == [item] and item not in bell.notices
    bell.show_alerts()
    popup = bell.popup
    assert popup is not None
    popup.dismiss(list(bell.notices))
    assert bell.notices == [] and bell.toolTip() == "0 campaign alert(s)"
    controls.model.game = None
    bell.refresh()
    assert not bell.isEnabled() and not popup.isVisible()
    popup.dismiss([item])
    bell.close()
    bell.deleteLater()


@pytest.fixture
def morale_popup(alerts: Any, controls: Any) -> Any:
    w = alerts
    w.roster.current_roster.append(
        SimpleNamespace(id=uuid4(), name="Second Pilot", alive=True, morale=0)
    )
    shown: list[n.CampaignNotice] = []
    bell = NotificationBell(controls.model, shown.append)
    bell.show_alerts()
    popup = bell.popup
    assert popup is not None
    yield SimpleNamespace(world=w, bell=bell, popup=popup, shown=shown)
    popup.close()
    bell.close()
    bell.deleteLater()


def test_morale_alerts_start_collapsed_without_hiding_other_categories(
    morale_popup: Any,
) -> None:
    p = morale_popup
    toggles = p.popup.findChildren(QToolButton, "low-morale-toggle")
    assert len(toggles) == 1
    toggle = toggles[0]
    assert toggle.text() == "Low morale (2)" and not toggle.isChecked()
    assert toggle.arrowType() == Qt.ArrowType.RightArrow
    content = p.popup.findChild(QWidget, "low-morale-notices")
    assert content.isHidden()
    assert len(content.findChildren(QPushButton)) == 4
    titles = [
        label.text() for label in p.popup.findChildren(QLabel) if label.isVisible()
    ]
    assert any("no assigned missile target" in text for text in titles)
    assert any("Few ground units" in text for text in titles)
    assert not any("very low morale" in text for text in titles)
    assert len(p.bell.notices) == 4 and "4" in p.bell.accessibleName()
    assert len(n.state(p.world.game).read) == 0


def test_morale_expansion_survives_refresh_and_individual_dismissal(
    morale_popup: Any,
) -> None:
    p = morale_popup
    p.popup.findChild(QToolButton, "low-morale-toggle").click()
    content = p.popup.findChild(QWidget, "low-morale-notices")
    assert content.isVisible()
    dismiss = next(
        b for b in content.findChildren(QPushButton) if b.text() == "Mark as read"
    )
    dismiss.click()
    toggle = p.popup.findChild(QToolButton, "low-morale-toggle")
    assert toggle.isChecked() and toggle.text() == "Low morale (1)"
    assert toggle.arrowType() == Qt.ArrowType.DownArrow
    assert p.popup.findChild(QWidget, "low-morale-notices").isVisible()
    assert len(p.bell.notices) == 3
    p.world.game.turn += 1
    p.bell.refresh()
    toggle = p.popup.findChild(QToolButton, "low-morale-toggle")
    assert toggle.isChecked() and toggle.text() == "Low morale (2)"
    toggle.click()
    p.popup.update_notices()
    assert not p.popup.findChild(QToolButton, "low-morale-toggle").isChecked()
    assert p.popup.findChild(QWidget, "low-morale-notices").isHidden()
    for pilot in p.world.roster.current_roster:
        pilot.morale = 50
    p.bell.refresh()
    assert p.popup.findChild(QToolButton, "low-morale-toggle") is None
    assert len(p.bell.notices) == 2


def test_expanded_morale_cards_show_the_aircraft(morale_popup: Any) -> None:
    p = morale_popup
    p.popup.findChild(QToolButton, "low-morale-toggle").click()
    content = p.popup.findChild(QWidget, "low-morale-notices")
    details = [
        label.text() for label in content.findChildren(QLabel) if label.isVisible()
    ]
    assert sum("A-10C Thunderbolt II (Suite 7)" in text for text in details) == 2


def test_grouped_morale_notice_still_navigates_to_its_pilot(morale_popup: Any) -> None:
    p = morale_popup
    p.popup.findChild(QToolButton, "low-morale-toggle").click()
    content = p.popup.findChild(QWidget, "low-morale-notices")
    next(b for b in content.findChildren(QPushButton) if b.text() == "Show").click()
    assert len(p.shown) == 1 and p.shown[0].category == "pilot_morale"
    assert p.shown[0] not in p.bell.notices
    assert not p.popup.isVisible()


def test_mark_all_as_read_includes_collapsed_morale_notices(morale_popup: Any) -> None:
    p = morale_popup
    next(
        b for b in p.popup.findChildren(QPushButton) if b.text() == "Mark all as read"
    ).click()
    assert p.bell.notices == []
    assert p.popup.findChild(QToolButton, "low-morale-toggle") is None
    assert any(
        label.text() == "No campaign alerts." for label in p.popup.findChildren(QLabel)
    )
