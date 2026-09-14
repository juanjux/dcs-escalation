"""Finding anything in a campaign by typing part of what it is called.

The settings dialog had a search and the map had another; everything else had none.
This is the one index behind all of it, and the rules it has to keep are about
ranking: a thousand entries where four hundred are pilots will bury everything else
unless the scoring says which answer is the better one.
"""

from __future__ import annotations

import pytest

from game.search.index import (
    ENOUGH_WITHOUT_THE_NET,
    Entry,
    Follow,
    GameIndex,
    Index,
)


def _entry(
    label: str,
    detail: str = "",
    keywords: str = "",
    kind: str = "setting",
    key: str = "",
) -> Entry:
    return Entry(
        label=label,
        detail=detail,
        follow=Follow(kind, label),
        keywords=keywords,
        key=key,
    )


def _labels(index: Index, query: str, limit: int = 40) -> list[str]:
    return [hit.entry.label for hit in index.search(query, limit)]


def test_a_word_from_the_label_finds_it() -> None:
    index = Index([_entry("Napalm damages units"), _entry("Maximum frontline width")])
    assert _labels(index, "napalm") == ["Napalm damages units"]


def test_every_word_has_to_match() -> None:
    """The words are an AND: "frontline width" is one thing, not two searches."""
    index = Index([_entry("Maximum frontline width"), _entry("Frontline manpads")])
    assert _labels(index, "frontline width") == ["Maximum frontline width"]


def test_nothing_typed_finds_nothing() -> None:
    index = Index([_entry("Napalm damages units")])
    assert index.search("") == []
    assert index.search("   ") == []


def test_the_text_is_folded_once_when_the_entry_is_made() -> None:
    """Which is the whole reason this exists: folding every label on every keystroke
    is what made the settings search cost four milliseconds at two hundred items."""
    entry = _entry("Máximum Frontline", detail="Bandolier", keywords="Ñu")
    assert entry.folded_label == "maximum frontline"
    assert entry.folded_detail == "bandolier"
    assert entry.folded_keywords == "nu"
    assert "maximum frontline" in entry.haystack
    assert "bandolier" in entry.haystack


def test_accents_are_ignored_both_ways() -> None:
    index = Index([_entry("Morale")])
    assert _labels(index, "móral") == ["Morale"]


def test_a_keyword_finds_it_without_being_shown() -> None:
    """A site is called MINK and holds a Patriot. Nobody looking for the Patriot
    knows it is called MINK."""
    index = Index([_entry("MINK", detail="AA Site", keywords="patriot launcher")])
    assert _labels(index, "patriot") == ["MINK"]


def test_a_word_is_worth_the_best_place_it_appears_not_the_first() -> None:
    """The bug this replaced: an aircraft name sits in a squadron's detail line and
    in the keywords of every pilot in it, so taking the first match made the
    squadron worth twenty and each of its pilots worth forty. The squadron came
    last, behind fifteen of its own men."""
    squadron = _entry(
        "VMA-223",
        detail="AV-8B Harrier II · Creech",
        keywords="squadron AV-8B Harrier II",
        kind="squadron",
    )
    pilot = _entry(
        "Capt Solis", detail="VMA-223", keywords="pilot AV-8B Harrier II", kind="pilot"
    )
    assert _labels(Index([pilot, squadron]), "harrier")[0] == "VMA-223"


def test_a_squadron_outranks_a_pilot_when_both_are_worth_the_same() -> None:
    """Four hundred pilots will bury everything else on any word they share."""
    index = Index(
        [
            _entry("Alpha", keywords="hornet", kind="pilot"),
            _entry("Bravo", keywords="hornet", kind="squadron"),
        ]
    )
    assert _labels(index, "hornet") == ["Bravo", "Alpha"]


def test_a_shorter_label_wins_when_both_match_the_same_way() -> None:
    index = Index([_entry("Napalm effects for the M-2000C"), _entry("Napalm")])
    assert _labels(index, "napalm")[0] == "Napalm"


def test_a_label_beats_a_detail() -> None:
    index = Index(
        [_entry("Ammo depots", kind="base"), _entry("Repairs", detail="ammo")]
    )
    assert _labels(index, "ammo")[0] == "Ammo depots"


def test_a_typo_still_finds_it_but_only_when_little_else_did() -> None:
    """The net is for a query that did not answer. One that did does not need it."""
    index = Index([_entry("Maximum frontline width")])
    assert _labels(index, "frntline") == ["Maximum frontline width"]


def test_the_typo_net_is_not_run_when_the_query_answered() -> None:
    plenty = [_entry(f"Frontline setting {n}") for n in range(ENOUGH_WITHOUT_THE_NET)]
    near_miss = _entry("Frontline width")
    index = Index(plenty + [near_miss])

    # "frontline" is a real hit on all of them, so nothing needs the net; the point
    # is that a query that answered does not also drag in near misses.
    hits = index.search("frontline")
    assert len(hits) == len(plenty) + 1


def test_a_short_word_never_matches_by_typo() -> None:
    """ "rank" is a tight subsequence of "recovery tanker", which is a coincidence."""
    index = Index([_entry("Recovery tanker")])
    assert _labels(index, "rank") == []


def test_the_limit_cuts_the_list() -> None:
    index = Index([_entry(f"Napalm {n}") for n in range(50)])
    assert len(index.search("napalm", limit=5)) == 5


def test_a_key_is_only_searched_when_a_key_is_what_was_typed() -> None:
    index = Index([_entry("Enable Live Pilots", key="live_pilots_enabled")])
    assert _labels(index, "live_pilots_enabled") == ["Enable Live Pilots"]
    assert _labels(index, "enabled") == []


# -- the index for one campaign ---------------------------------------------------


class _Game:
    def __init__(self, turn: int) -> None:
        self.turn = turn


def test_the_index_is_built_once_for_a_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuilding it on every keystroke would cost seventy milliseconds a letter."""
    built = 0

    def count(game: object) -> list[Entry]:
        nonlocal built
        built += 1
        return [_entry("Napalm")]

    monkeypatch.setattr("game.search.providers.entries_for", count)
    holder = GameIndex()
    game = _Game(turn=3)

    for _ in range(10):
        holder.of(game)
    assert built == 1


def test_a_new_turn_builds_it_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn changes the flights, the pilots and half the objectives at once."""
    built = 0

    def count(game: object) -> list[Entry]:
        nonlocal built
        built += 1
        return []

    monkeypatch.setattr("game.search.providers.entries_for", count)
    holder = GameIndex()
    game = _Game(turn=3)

    holder.of(game)
    game.turn = 4
    holder.of(game)
    assert built == 2


def test_a_different_campaign_builds_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both campaigns here are short-lived, and the second lands on the address the
    first has just given up -- which is why the index is keyed on the object and not
    on its id. Keyed on the id, this answered about the campaign that was closed.
    """
    built = 0

    def count(game: object) -> list[Entry]:
        nonlocal built
        built += 1
        return []

    monkeypatch.setattr("game.search.providers.entries_for", count)
    holder = GameIndex()

    holder.of(_Game(turn=1))
    holder.of(_Game(turn=1))
    assert built == 2


def test_a_campaign_sized_index_answers_inside_the_budget() -> None:
    """A large theatre has a few thousand findable things, and the box is searched
    on a pause in typing: anything approaching a tenth of a second would be felt.

    A generous ceiling, because this runs on whatever machine CI gives it. The
    measurement that matters is on a real campaign, where a thousand entries answer
    in about one millisecond.
    """
    import time

    index = Index(
        _entry(
            f"Objective {n} SA-{n % 20} site",
            detail=f"AA Site · Base {n % 40} · red",
            keywords="aa red SA-11 Buk TEL launcher radar",
            kind="objective",
        )
        for n in range(5000)
    )

    start = time.perf_counter()
    for _ in range(5):
        index.search("buk radar", limit=40)
    each = (time.perf_counter() - start) / 5

    assert each < 0.15, f"{each * 1000:.0f} ms per search over 5000 entries"
