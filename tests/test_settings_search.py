"""What the settings search finds, and what it refuses to.

The refusing is the harder half. A forgiving matcher over two hundred long labels
matches almost everything: before the subsequence was made to stay tight, "napalm"
found "Enable per-squadron pilot limits", which is worse than finding nothing.
"""

from __future__ import annotations

from game.settings import Settings
from game.settings.search import SettingHit, fold, is_subsequence, search


def keys(query: str) -> list[str]:
    return [hit.key for hit in search(query)]


def test_a_word_from_the_label_finds_it() -> None:
    assert "use_auto_fog" in keys("fog")
    assert "perf_smoke_spacing" in keys("smoke spacing")


def test_every_word_has_to_match() -> None:
    """Words narrow the search; they do not widen it."""
    assert keys("smoke"), "the premise"
    assert not keys("smoke marzipan")


def test_a_section_is_offered_once_and_not_through_every_setting_in_it() -> None:
    """ "rank" used to answer with ten rows called Cadet, Good and High.

    They were the section's name showing through its members, twice over: through
    the page and section they sit in, and through keys like
    live_pilots_rank_good_short.
    """
    hits = search("rank")
    assert any(hit.is_section and hit.label == "Ranks" for hit in hits)
    rungs = [hit for hit in hits if hit.label in {"Cadet", "Good", "High", "Average"}]
    assert not rungs, [hit.label for hit in rungs]


def test_the_key_is_only_searched_when_a_key_is_what_was_typed() -> None:
    assert "never_delay_player_flights" in keys("never_delay")
    assert "live_pilots_rank_good_short" not in keys("rank")


def test_a_box_is_offered_as_well_as_its_section() -> None:
    labels = {hit.label for hit in search("morale") if hit.is_section}
    assert {"Morale", "Morale States", "Morale Event Values"} <= labels


def test_a_typo_still_finds_it_but_ranks_below_the_real_thing() -> None:
    assert "max_frontline_width" in keys("frntline")
    real = search("frontline")
    typo = search("frntline")
    assert real[0].score > typo[-1].score


def test_a_subsequence_scattered_over_a_long_label_is_not_a_match() -> None:
    """The bug this rule exists for: it used to answer with pilot limits."""
    assert not is_subsequence("napalm", fold("Enable per-squadron pilot limits"))
    assert is_subsequence("frntline", fold("Maximum frontline width (km)"))


def test_a_short_word_never_matches_by_subsequence() -> None:
    """Four letters land inside almost any label in the right order.

    "rank" is a tight subsequence of "recovery tanker" -- the r of recovery and the
    ank of tanker -- and it was answering with four tanker settings.
    """
    assert not is_subsequence("air", "a big irregular")
    assert not is_subsequence("rank", fold("Enable Airboss Recovery Tanker"))
    assert "rank" not in [hit.label.lower() for hit in search("rank")]
    assert not [hit for hit in search("rank") if "tanker" in hit.label.lower()]


def test_nothing_typed_finds_nothing() -> None:
    assert search("") == []
    assert search("   ") == []


def test_accents_are_ignored_both_ways() -> None:
    assert fold("Morále") == fold("morale")


def test_the_plugins_own_options_are_searchable() -> None:
    """They are the hardest to find by clicking: nothing says "napalm" until you
    have opened the right plugin's gear."""
    hits = search("napalm")
    assert hits, "Splash Damage carries seven of them"
    assert all(hit.plugin == "splashdamage3" for hit in hits)
    assert all(hit.page == "Mission Plugins" for hit in hits)


def test_a_hit_says_where_it_lives() -> None:
    (hit,) = [h for h in search("smoke spacing") if h.key == "perf_smoke_spacing"]
    assert hit.where == "Mission Generator › Performance"


def test_a_setting_in_a_box_names_the_box() -> None:
    (hit,) = [
        h for h in search("morale_state_shaken") if h.key == "morale_state_shaken"
    ]
    assert hit.where.endswith("Morale › Morale States")


def test_a_setting_the_campaign_is_not_offering_is_not_offered_here() -> None:
    """visible_when hides rows on the page; the search must not route around it."""
    hidden = [
        name
        for name, description in Settings.all_fields()
        if description.visible_when is not None
    ]
    assert hidden, "the premise: something is conditional"
    settings = Settings()
    for name in hidden:
        description = dict(Settings.all_fields())[name]
        if description.visible_when is not None and not description.visible_when(
            settings
        ):
            assert name not in [h.key for h in search(name, settings)]
            return


def test_a_shorter_label_wins_when_both_match() -> None:
    hits = search("cadet")
    assert hits[0].label == "Cadet"


def test_the_hit_is_what_the_dialog_needs_to_navigate() -> None:
    (hit,) = [h for h in search("smoke spacing") if h.key == "perf_smoke_spacing"]
    assert isinstance(hit, SettingHit)
    assert hit.page in list(Settings.pages())
    assert hit.section in list(Settings.sections(hit.page))


def test_a_setting_is_found_by_what_it_can_be_set_to() -> None:
    """Fog of war is a value of the map visibility option and appears nowhere in its
    label or its explanation, so nobody who remembered only the choice could find
    the row."""
    found = [hit.key for hit in search("fog of war")]

    assert "map_coalition_visibility" in found


def test_what_a_setting_is_called_still_beats_what_it_can_be_set_to() -> None:
    labelled, valued = "", ""
    for key, description in Settings.all_fields():
        choices = getattr(description, "choices", None)
        if not choices:
            continue
        for choice in choices:
            word = choice.split()[0].lower()
            if len(word) < 5 or word in description.text.lower():
                continue
            hits = search(word)
            if len(hits) < 2:
                continue
            labelled, valued = hits[0].label, hits[-1].label
            assert hits[0].score >= hits[-1].score
            return
    assert labelled == valued == "", "the premise: a value that is not in its label"
