"""What each kind of findable thing puts into the index.

Keywords are most of the work here. An objective is called MINK and holds a Patriot,
and nobody looking for the Patriot knows it is called MINK: the words that find a
thing are not always the words shown on it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.search.providers import (
    BASE,
    FLIGHT,
    OBJECTIVE,
    PILOT,
    PILOT_NOTE,
    SQUADRON,
    base_entries,
    flight_entries,
    objective_entries,
    pilot_entries,
    squadron_entries,
)


def _theater(control_points: list[Any]) -> Any:
    return SimpleNamespace(theater=SimpleNamespace(controlpoints=control_points))


def _cp(name: str, blue: bool = True, objectives: list[Any] | None = None) -> Any:
    cp = SimpleNamespace(
        name=name,
        id=f"cp-{name}",
        captured=SimpleNamespace(is_blue=blue),
        connected_objectives=objectives or [],
    )
    for objective in cp.connected_objectives:
        objective.control_point = cp
    return cp


def _tgo(name: str, category: str, units: list[str], dead: bool = False) -> Any:
    return SimpleNamespace(
        obj_name=name,
        id=f"tgo-{name}",
        category=category,
        is_dead=dead,
        units=[
            SimpleNamespace(unit_type=SimpleNamespace(display_name=unit))
            for unit in units
        ],
        __str__=lambda self: "AA Site",
    )


def test_a_base_is_found_by_its_name(qt_free: None = None) -> None:
    entries = list(base_entries(cast(Any, _theater([_cp("Creech")]))))
    assert [entry.label for entry in entries] == ["Creech"]
    assert entries[0].follow.kind == BASE


def test_a_base_carries_its_side(qt_free: None = None) -> None:
    """ "red bases" is a reasonable thing to type."""
    entries = list(base_entries(cast(Any, _theater([_cp("Groom Lake", blue=False)]))))
    assert "red" in entries[0].haystack


def test_an_objective_is_found_by_what_is_standing_in_it() -> None:
    site = _tgo("MINK", "aa", ["SAM Patriot LN", "SAM Patriot STR"])
    entries = list(
        objective_entries(cast(Any, _theater([_cp("Creech", True, [site])])))
    )

    assert [entry.label for entry in entries] == ["MINK"]
    assert "patriot" in entries[0].haystack
    assert entries[0].follow.kind == OBJECTIVE


def test_a_unit_type_is_only_listed_once_however_many_there_are() -> None:
    """Ten launchers is one thing to search for, not ten."""
    site = _tgo("MINK", "aa", ["SAM Patriot LN"] * 10)
    entry = next(iter(objective_entries(cast(Any, _theater([_cp("C", True, [site])])))))
    assert entry.folded_keywords.count("patriot") == 1


def test_an_objective_shared_by_two_bases_is_offered_once() -> None:
    """connected_objectives is per base, and one objective can be on two lists."""
    site = _tgo("MINK", "aa", [])
    first, second = _cp("Creech", True, [site]), _cp("Nellis", True, [site])
    entries = list(objective_entries(cast(Any, _theater([first, second]))))
    assert len(entries) == 1


def test_a_destroyed_objective_says_so() -> None:
    site = _tgo("MINK", "aa", [], dead=True)
    entry = next(iter(objective_entries(cast(Any, _theater([_cp("C", True, [site])])))))
    assert "destroyed" in entry.haystack


# -- the air wing -----------------------------------------------------------------


def _wing(squadrons: list[Any], player: bool = True) -> Any:
    coalition = SimpleNamespace(
        player=player,
        air_wing=SimpleNamespace(iter_squadrons=lambda: list(squadrons)),
        ato=SimpleNamespace(packages=[]),
    )
    return SimpleNamespace(coalitions=[coalition])


class _Squadron:
    """A class rather than a SimpleNamespace: the providers put a squadron into a
    label with an f-string, so it has to have a __str__ of its own."""

    def __init__(self, name: str, aircraft: str, pilots: list[Any] | None = None):
        self.name = name
        self.id = f"sq-{name}"
        self.aircraft = SimpleNamespace(display_name=aircraft)
        self.location = SimpleNamespace(name="Creech")
        self.owned_aircraft = 12
        self.primary_task = SimpleNamespace(value="CAS")
        self.nickname = "Lemmings"
        self.active_pilots = pilots or []
        self.pilot_pool: list[Any] = []
        self.dead_pilots: list[Any] = []

    def __str__(self) -> str:
        return self.name

    def pilot_rank(self, pilot: Any) -> Any:
        return SimpleNamespace(abbreviation="Capt", name="Captain")


def _squadron(name: str, aircraft: str, pilots: list[Any] | None = None) -> Any:
    return _Squadron(name, aircraft, pilots)


def test_a_squadron_is_found_by_what_it_flies() -> None:
    entries = list(squadron_entries(cast(Any, _wing([_squadron("VMA-223", "AV-8B")]))))
    assert "av-8b" in entries[0].haystack
    assert entries[0].follow.kind == SQUADRON


def test_a_pilot_carries_his_rank_and_his_squadron() -> None:
    pilot = SimpleNamespace(
        id="p1", name="Solis", status=SimpleNamespace(value="Active")
    )
    squadron = _squadron("VMA-223", "AV-8B", [pilot])
    entries = list(pilot_entries(cast(Any, _wing([squadron]))))

    assert entries[0].label == "Capt Solis"
    assert entries[0].follow.kind == PILOT
    assert "captain" in entries[0].haystack


def test_a_pilot_row_admits_it_does_not_open_a_pilot_dialog_yet() -> None:
    """There is none, and a row that silently opens something else is worse than one
    that says what it will do."""
    pilot = SimpleNamespace(
        id="p1", name="Solis", status=SimpleNamespace(value="Active")
    )
    entries = list(pilot_entries(cast(Any, _wing([_squadron("V", "AV-8B", [pilot])]))))
    assert entries[0].note == PILOT_NOTE


def test_a_pilot_on_two_lists_is_offered_once() -> None:
    pilot = SimpleNamespace(
        id="p1", name="Solis", status=SimpleNamespace(value="Active")
    )
    squadron = _squadron("V", "AV-8B", [pilot])
    squadron.pilot_pool = [pilot]
    assert len(list(pilot_entries(cast(Any, _wing([squadron]))))) == 1


def test_a_pilot_with_no_rank_is_still_found_by_his_name() -> None:
    """Live Pilots switched off means everyone is just a name."""
    pilot = SimpleNamespace(
        id="p1", name="Solis", status=SimpleNamespace(value="Active")
    )
    squadron = _squadron("V", "AV-8B", [pilot])
    squadron.pilot_rank = lambda pilot: None
    entries = list(pilot_entries(cast(Any, _wing([squadron]))))
    assert entries[0].label == "Solis"


def test_a_flight_is_found_by_its_task_its_aircraft_and_its_target() -> None:
    flight = SimpleNamespace(
        id="f1",
        custom_name=None,
        flight_type=SimpleNamespace(value="Strike"),
        count=2,
        unit_type=SimpleNamespace(display_name="AV-8B Harrier II"),
        departure=SimpleNamespace(name="Creech"),
    )
    package = SimpleNamespace(flights=[flight], target=SimpleNamespace(name="VIPER"))
    game = _wing([])
    game.coalitions[0].ato.packages = [package]

    entries = list(flight_entries(cast(Any, game)))
    assert entries[0].label == "Strike · AV-8B Harrier II"
    assert "viper" in entries[0].haystack
    assert entries[0].follow.kind == FLIGHT


def test_a_flight_with_a_name_of_its_own_uses_it() -> None:
    flight = SimpleNamespace(
        id="f1",
        custom_name="UZI",
        flight_type=SimpleNamespace(value="Strike"),
        count=2,
        unit_type=SimpleNamespace(display_name="AV-8B"),
        departure=SimpleNamespace(name="Creech"),
    )
    package = SimpleNamespace(flights=[flight], target=SimpleNamespace(name="VIPER"))
    game = _wing([])
    game.coalitions[0].ato.packages = [package]

    assert next(iter(flight_entries(cast(Any, game)))).label == "Strike · UZI"
