"""Publish battle reports once at the beginning of the new turn."""

import os
import pickle
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest

from game.game import Game
from game.ground_forces.combat_stance import CombatStance
from game.sim.gameupdateevents import GameUpdateEvents
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.theater.player import Player

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def campaign(monkeypatch: pytest.MonkeyPatch) -> Any:
    game: Any = Game.__new__(Game)
    game.turn = 6
    game.informations = []
    # No queue attribute: also exercises a campaign saved before it existed.
    game.theater = NS(controlpoints=[], player_points=lambda: [])
    game.blue = NS(end_turn=lambda events: game.message("Deliveries", "Done"))
    game.red = NS(end_turn=lambda events: None)
    game.high_command = game.opfor_high_command = NS(
        return_loans=lambda game: [], end_effects=lambda game: []
    )
    game.generate_conditions = lambda: None
    for target in (
        "game.groundmovement.frontline.snapshot_fronts",
        "game.groundmovement.frontline.integrate_reached_reserves",
        "game.groundmovement.dispatch.advance_armor",
        "game.persistentdamage.repair_damage",
        "game.missiletargets.remove_invalid",
        "game.theater.shipmovement.move_and_reparent_ships",
        "game.aircraftmaintenance.advance",
    ):
        monkeypatch.setattr(target, lambda *args: None)
    return game


@pytest.mark.parametrize(
    "allied,enemy,expected",
    [(5, 0, "making progress"), (0, 5, "losing ground"), (5, 5, "stalemate")],
)
def test_scoring_stays_in_old_turn_but_report_is_published_in_new_turn(
    campaign: Any, allied: int, enemy: int, expected: str
) -> None:
    game = campaign
    front = Mock()
    red = NS(
        id=uuid4(),
        name="Red Base",
        captured=Player.RED,
        base=NS(total_armor=enemy, affect_strength=Mock()),
    )
    blue = NS(
        name="Blue Base",
        connected_points=[red],
        front_line_with=lambda other: front,
        stances={red.id: CombatStance.AGGRESSIVE},
        base=NS(total_armor=allied, affect_strength=Mock()),
    )
    game.theater.player_points = lambda: [blue]
    debriefing: Any = NS(casualty_count=lambda cp: 0)
    MissionResultsProcessor(game).commit_front_line_battle_impact(
        debriefing, GameUpdateEvents()
    )
    assert game.turn == 6 and game.informations == []
    assert len(game.pending_frontline_reports) == 1
    assert expected in game.pending_frontline_reports[0]
    front.update_position.assert_called_once()
    if allied != enemy:
        blue.base.affect_strength.assert_called_once()
        red.base.affect_strength.assert_called_once()
    game.theater.player_points = lambda: []
    game.finish_turn(GameUpdateEvents())
    assert game.turn == 7
    assert [(info.title, info.turn) for info in game.informations] == [
        ("End of turn #6", 6),
        ("Frontline Report", 7),
        ("Deliveries", 7),
    ]
    assert expected in game.informations[1].text
    assert game.pending_frontline_reports == []
    game.finish_turn(GameUpdateEvents())
    assert sum(info.title == "Frontline Report" for info in game.informations) == 1


def test_pending_reports_survive_save_and_keep_front_order(campaign: Any) -> None:
    game = campaign
    game.queue_frontline_report("First front")
    game.queue_frontline_report("Second front")
    # The queue is plain text and can ride in an interrupted campaign's save.
    reports = pickle.loads(pickle.dumps(game.pending_frontline_reports))
    game.pending_frontline_reports = reports
    game.finish_turn(GameUpdateEvents(), skipped=True)
    assert [
        info.text for info in game.informations if info.title == "Frontline Report"
    ] == reports


def test_new_report_is_visible_without_show_all_turns(campaign: Any) -> None:
    from PySide6.QtWidgets import QApplication
    from qt_ui.windows.infos.eventlist import EventList

    app = QApplication.instance() or QApplication([])
    game = campaign
    game.message("Old event", "Preserved")
    game.queue_frontline_report("Battle result")
    game.finish_turn(GameUpdateEvents())
    listing = EventList(game)
    assert not listing.all_turns
    entries: list[Any] = [
        listing.entries.item(i) for i in range(listing.entries.rowCount())
    ]
    assert [item.info.title for item in entries] == ["Deliveries", "Frontline Report"]
    assert all(item.info.turn == 7 and item.is_new for item in entries)
    listing.set_all_turns(True)
    assert listing.entries.rowCount() == 4
    listing.close()
    app.processEvents()


def test_old_campaign_without_pending_reports_can_advance(campaign: Any) -> None:
    campaign.finish_turn(GameUpdateEvents(), skipped=True)
    assert campaign.turn == 7 and campaign.pending_frontline_reports == []
    assert not any(info.title == "Frontline Report" for info in campaign.informations)
