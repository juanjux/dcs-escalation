"""The pilot dialog: what it says about a man, and what it refuses to say.

Everything here is the arithmetic the dialog does before it draws anything -- which
fate chip he gets, how his kills are grouped, which friendships are worth a row -- plus
the one piece of behaviour worth a widget: only one kill row is open at a time.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest

from dcs.unit import Skill

from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.squadrons import friendship
from game.squadrons.pilot import Pilot, PilotRecord, PilotStatus, KilledBy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def _squadron(
    settings: Optional[Settings] = None, skill: Skill = Skill.Good, **extra: Any
) -> Any:
    """A squadron double: the dialog asks it for the rules and for the man's rung."""
    if settings is None:
        settings = Settings()
        # Rank, morale and friendship are all Live Pilots; without it there is no
        # dialog worth testing.
        settings.live_pilots_enabled = True
    return SimpleNamespace(
        settings=settings,
        country=None,
        pilot_skill=lambda _pilot: skill,
        pilot_rank=lambda _pilot: SimpleNamespace(name="Captain", abbreviation="Capt"),
        location=SimpleNamespace(name="Nellis"),
        morale_in_play=True,
        friendship_in_play=True,
        **extra,
    )


def _pilot(name: str = "Abascal", **fields: Any) -> Pilot:
    pilot = Pilot(name)
    for key, value in fields.items():
        setattr(pilot, key, value)
    return pilot


# --- the chip that says where he stands -------------------------------------


def test_an_active_pilot_reads_as_active() -> None:
    from qt_ui.windows.pilot.header import fate_of

    words, _ink, _fill = fate_of(_pilot())
    assert words == "ACTIVE"


def test_a_wound_says_how_long_it_has_left() -> None:
    from qt_ui.windows.pilot.header import fate_of

    pilot = _pilot(status=PilotStatus.Wounded, wounded_turns=2)
    words, _ink, _fill = fate_of(pilot)
    assert words == "WOUNDED · 2 TURNS"


def test_open_ended_leave_says_only_that_he_is_away() -> None:
    """Leave granted with no length runs until the player fetches him, so there is no
    number to put on the chip."""
    from qt_ui.windows.pilot.header import fate_of

    pilot = _pilot(status=PilotStatus.OnLeave, leave_turns=0)
    words, _ink, _fill = fate_of(pilot)
    assert words == "ON LEAVE"


def test_the_dead_are_dated() -> None:
    from qt_ui.windows.pilot.header import fate_of

    pilot = _pilot(status=PilotStatus.Dead)
    pilot.record.killed_by = KilledBy(pilot_name="Ali Hassan", turn=11)
    words, ink, _fill = fate_of(pilot)
    assert words == "KIA · TURN 11"
    assert ink == "#D9645E"


def test_a_death_with_nobody_credited_is_still_a_death() -> None:
    from qt_ui.windows.pilot.header import fate_of

    words, _ink, _fill = fate_of(_pilot(status=PilotStatus.Dead))
    assert words == "KIA"


# --- the ladder -------------------------------------------------------------


def test_the_next_rank_is_named_with_what_it_costs() -> None:
    from qt_ui.windows.pilot.header import next_rung

    squadron = _squadron(skill=Skill.Good)
    pilot = _pilot()
    pilot.record.xp = 2400
    name, price, held = next_rung(squadron, pilot)
    # Good is the third rung, so the one above it is High -- Major in the generic
    # ladder -- at 4,000, and the one he holds cost 2,000.
    assert name == "Maj"
    assert (price, held) == (4000, 2000)


def test_the_top_of_the_ladder_has_nothing_above_it() -> None:
    from qt_ui.windows.pilot.header import next_rung

    name, price, held = next_rung(_squadron(skill=Skill.Excellent), _pilot())
    assert name is None
    assert (price, held) == (0, 0)


def test_without_levelling_there_is_no_promotion_to_point_at() -> None:
    """Rank is the coalition's setting then, and a bar towards a promotion that cannot
    happen is worse than no bar."""
    from qt_ui.windows.pilot.header import next_rung

    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = False
    name, _price, _held = next_rung(_squadron(settings), _pilot())
    assert name is None


def test_the_bottom_rung_counts_from_nothing() -> None:
    from qt_ui.windows.pilot.header import next_rung

    name, price, held = next_rung(_squadron(skill=CADET_SKILL), _pilot())
    assert name is not None
    assert (price, held) == (1000, 0)


# --- the kills --------------------------------------------------------------


def _with_kills() -> Pilot:
    pilot = _pilot()
    for what, weapon, turn in (
        ("JF-17 Thunder", "AIM-120C", 11),
        ("JF-17 Thunder", "AIM-120C", 11),
        ("Ka-50", "AIM-9X", 10),
    ):
        pilot.record.note_kill(True, what, "", turn, weapon)
    for what, kind, weapon, turn in (
        ("SA-15 Tor", "Air defence", "AGM-88C", 11),
        ("SA-15 Tor", "Air defence", "AGM-88C", 11),
        ("ZU-23", "Air defence", "Mk-82", 8),
        ("T-72B", "Armour", "GBU-12", 7),
    ):
        pilot.record.note_kill(False, what, kind, turn, weapon)
    return pilot


def test_air_kills_are_grouped_by_what_he_shot_down() -> None:
    from qt_ui.windows.pilot.record import air_groups

    groups = air_groups(_with_kills().record)
    assert [(group.name, group.count) for group in groups] == [
        ("JF-17 Thunder", 2),
        ("Ka-50", 1),
    ]


def test_an_air_row_opens_into_the_weapons_he_used() -> None:
    """The row is already the aircraft type, so naming it again inside would be the
    same fact twice: what is left to say is the weapon and the turn."""
    from qt_ui.windows.pilot.record import air_groups

    groups = air_groups(_with_kills().record)
    children = groups[0].children
    assert [(child.name, child.count, child.detail) for child in children] == [
        ("AIM-120C", 2, "T11")
    ]


def test_ground_kills_are_grouped_by_the_sort_of_thing_it_was() -> None:
    from qt_ui.windows.pilot.record import ground_groups

    groups = ground_groups(_with_kills().record)
    assert [(group.name, group.count) for group in groups] == [
        ("Air defence", 3),
        ("Armour", 1),
    ]


def test_a_closed_ground_row_names_what_is_inside_it() -> None:
    from qt_ui.windows.pilot.record import ground_groups

    groups = ground_groups(_with_kills().record)
    assert groups[0].summary == "SA-15 Tor x2 · ZU-23"


def test_a_ground_row_opens_into_the_types_with_turn_and_weapon() -> None:
    from qt_ui.windows.pilot.record import ground_groups

    children = ground_groups(_with_kills().record)[0].children
    assert [(child.name, child.count, child.detail) for child in children] == [
        ("SA-15 Tor", 2, "T11 · AGM-88C x2"),
        ("ZU-23", 1, "T8 · Mk-82"),
    ]


def test_kills_the_log_no_longer_holds_are_still_counted() -> None:
    """The tallies are never trimmed and the log is, so a long campaign says "and n
    earlier" rather than quietly showing fewer kills than the header does."""
    from qt_ui.windows.pilot.record import EARLIER, air_groups, ground_groups

    record = PilotRecord()
    record.air_kills = {"MiG-29": 4}
    record.ground_kills = {"T-72B": 6}
    record.kills = []

    air = air_groups(record)
    assert [(child.name, child.count) for child in air[0].children] == [(EARLIER, 4)]

    ground = ground_groups(record)
    assert [(group.name, group.count) for group in ground] == [(EARLIER, 6)]


def test_a_span_of_turns_reads_as_a_span() -> None:
    from game.squadrons.pilot import Kill
    from qt_ui.windows.pilot.record import turns_phrase

    assert turns_phrase([Kill("T-72B", turn=4)]) == "T4"
    assert turns_phrase([Kill("T-72B", turn=4), Kill("T-72B", turn=9)]) == "T4-T9"
    assert turns_phrase([Kill("T-72B")]) == ""


# --- friendships ------------------------------------------------------------


def _friend(his: float, theirs: float) -> Any:
    from qt_ui.windows.pilot.state import Friend

    pilot, other = _pilot("He"), _pilot("Other")
    if his != friendship.FRIENDSHIP_START:
        pilot.friendships[other.id] = his
    if theirs != friendship.FRIENDSHIP_START:
        other.friendships[pilot.id] = theirs
    return Friend(pilot, other, True, Settings())


def test_a_pair_is_ranked_by_how_far_it_is_from_where_it_started() -> None:
    """Warm and cold both count, and either direction: a man he cannot stand costs
    the flight what a friend earns it."""
    assert _friend(5.0, 5.0).strength == 0
    assert _friend(1.5, 5.0).strength == 3.5
    assert _friend(5.0, 1.5).strength == 3.5
    assert _friend(9.0, 5.0).strength == 4.0


def test_the_row_carries_the_wash_the_roster_uses() -> None:
    """The same colour in both places, so it is learnt once."""
    assert _friend(9.0, 9.0).tint.startswith("rgba(")
    assert _friend(5.0, 5.0).tint == ""


def test_the_card_is_never_empty_for_a_man_who_knows_people() -> None:
    """Filtering by band left the player's own pilot -- a whole squadron of Neutral,
    which is most of a first campaign -- with nothing on the card at all."""
    from qt_ui.windows.pilot.state import friends_of

    squadron = _squadron()
    pilot = _pilot("He")
    others = [_pilot(f"Other {index}") for index in range(3)]
    for index, other in enumerate(others):
        pilot.friendships[other.id] = 5.2 + index * 0.1

    wing = {man.id: (squadron, man) for man in [pilot, *others]}
    friends = friends_of(pilot, wing, squadron)
    assert [friend.other.name for friend in friends] == [
        "Other 2",
        "Other 1",
        "Other 0",
    ]


def test_two_men_who_agree_read_as_mutual() -> None:
    line = _friend(8.0, 8.0).line
    assert "mutual" in line
    assert "and back" not in line


def test_a_gap_of_two_bands_is_called_out() -> None:
    friend = _friend(6.5, 9.5)
    assert "not returned" in friend.line


def test_one_band_apart_is_just_said_plainly() -> None:
    friend = _friend(9.5, 8.0)
    assert "and back" in friend.line
    assert "not returned" not in friend.line


def test_friends_are_found_in_both_directions_and_ranked() -> None:
    from qt_ui.windows.pilot.state import friends_of

    squadron = _squadron()
    pilot = _pilot("He")
    warm = _pilot("Warm")
    admirer = _pilot("Admirer")
    stranger = _pilot("Stranger")

    pilot.friendships[warm.id] = 8.0
    admirer.friendships[pilot.id] = 9.0

    wing = {man.id: (squadron, man) for man in (pilot, warm, admirer, stranger)}
    friends = friends_of(pilot, wing, squadron)
    assert [friend.other.name for friend in friends] == ["Warm", "Admirer"]


def test_a_friend_who_has_left_the_wing_is_not_a_row() -> None:
    """The dead are pruned from everyone's friendships, but a save mid-migration can
    still carry an id nobody answers to."""
    from qt_ui.windows.pilot.state import friends_of

    squadron = _squadron()
    pilot = _pilot("He")
    gone = _pilot("Gone")
    pilot.friendships[gone.id] = 9.0
    assert friends_of(pilot, {pilot.id: (squadron, pilot)}, squadron) == []


# --- morale -----------------------------------------------------------------


def test_the_band_above_him_is_the_one_to_aim_at() -> None:
    from qt_ui.windows.pilot.state import _next_band

    above = _next_band(72, Settings())
    assert above is not None
    assert (above.name, above.floor) == ("Triumphant", 85)


def test_the_top_band_has_nothing_above_it() -> None:
    from qt_ui.windows.pilot.state import _next_band

    assert _next_band(100, Settings()) is None


# --- the widgets ------------------------------------------------------------


def test_only_one_kill_row_is_open_at_a_time(qt_app: Any) -> None:
    """Two open rows turn the card into a list of everything, which is the thing the
    grouping was for."""
    from qt_ui.windows.pilot.record import GroupRow, KillRows

    rows = KillRows(_with_kills())
    openable = [
        row
        for row in rows.stack.rows
        if isinstance(row, GroupRow) and row.group.children
    ]
    assert len(openable) >= 2

    openable[0].clicked.emit()
    assert rows.open_row is openable[0]
    openable[1].clicked.emit()
    assert rows.open_row is openable[1]

    # And clicking the open one again shuts it.
    openable[1].clicked.emit()
    assert rows.open_row is None


def test_survival_says_what_it_knows_and_no_more(qt_app: Any) -> None:
    from qt_ui.windows.pilot.record import survival_rows

    pilot = _pilot()
    pilot.record.aircraft_lost = 2
    pilot.record.survived_losses = 2
    pilot.record.wounds = 1
    pilot.record.last_wound_turn = 9
    pilot.record.last_wound_turns = 2
    stack = survival_rows(pilot)
    assert len(stack.rows) == 3


def test_a_dead_man_gets_the_card_that_says_how(qt_app: Any) -> None:
    from qt_ui.windows.pilot.record import killed_in_action

    assert killed_in_action(_pilot()) is None

    pilot = _pilot(status=PilotStatus.Dead)
    pilot.record.killed_by = KilledBy(
        pilot_name="SA-11 Buk", squadron="site at Al Kut", weapon="9M38M1", turn=11
    )
    stack = killed_in_action(pilot)
    assert stack is not None
    assert len(stack.rows) == 2


def test_a_man_lost_with_nobody_credited_says_so(qt_app: Any) -> None:
    from qt_ui.windows.pilot.record import killed_in_action

    stack = killed_in_action(_pilot(status=PilotStatus.Dead))
    assert stack is not None
    assert len(stack.rows) == 1


def test_show_all_opens_the_rest_of_the_log(qt_app: Any) -> None:
    """It sat on a row that toggles the card, so the press that asked for every event
    shut the card instead."""
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

    from game.squadrons.morale import MoraleLogEntry
    from qt_ui.windows.pilot.state import LOG_PREVIEW, MoraleLog

    pilot = _pilot()
    pilot.morale_log = [
        MoraleLogEntry(turn, 3, "flew the mission", 50) for turn in range(25)
    ]
    log = MoraleLog(pilot)
    log.open = True
    log._apply()

    holder = QWidget()
    column = QVBoxLayout()
    column.addWidget(log)
    column.addStretch()
    holder.setLayout(column)
    holder.resize(400, 900)
    holder.show()
    QApplication.processEvents()

    def shown() -> int:
        return sum(1 for row in log.rows if not row.isHidden())

    assert shown() == LOG_PREVIEW
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPoint(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(log.more, press)
    QApplication.processEvents()
    assert shown() == 25
    assert log.open

    # And there is a way back to the recent ones.
    assert "last" in log.more.text()
    QApplication.sendEvent(log.more, press)
    QApplication.processEvents()
    assert shown() == LOG_PREVIEW

    # The row itself still shuts the card.
    QApplication.sendEvent(log.head, press)
    QApplication.processEvents()
    assert shown() == 0
    holder.close()


def test_the_air_wing_is_opened_by_the_window_that_owns_it(qt_app: Any) -> None:
    """One Air Wing window, whoever asks for it: the top panel keeps it that way."""
    from PySide6.QtWidgets import QWidget

    from qt_ui.windows.pilot.header import open_air_wing

    asked: list[bool] = []
    parent = cast(Any, QWidget())
    parent.top_panel = SimpleNamespace(open_air_wing=lambda: asked.append(True))
    child = QWidget(parent)

    open_air_wing(child)
    assert asked == [True]

    # Nothing above it that knows about air wings: no exception.
    open_air_wing(QWidget())
