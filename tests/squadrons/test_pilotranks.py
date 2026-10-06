"""Rank ladders, the naming choices, and the Cadet rung pydcs was missing."""

from typing import List

import pytest
from dcs.countries import country_dict
from dcs.country import Country
from dcs.unit import Skill

from game.dcs.skills import CADET_SKILL, SKILL_LADDER, ground_skill
from game.settings import ChoicesOption, Settings, TextOption
from game.settings.skilloption import GROUND_SKILL_CHOICES, PILOT_SKILL_CHOICES
from game.squadrons.pilotranks import (
    COUNTRY_RANKS,
    GENERIC_RANKS,
    RANK_NAMES_COUNTRY,
    RANK_NAMES_CUSTOM,
    RANK_NAMES_GENERIC,
    RANK_NAMES_SKILL,
    RankLadder,
    rank_for_skill,
    ranks_for,
)


def _country(name: str) -> Country:
    for factory in country_dict.values():
        country = factory()
        if country.name == name:
            return country
    raise AssertionError(f"no such DCS country: {name}")


def _abbreviations(ladder: RankLadder) -> List[str]:
    return [rank.abbreviation for rank in ladder]


# --- the engine ------------------------------------------------------------


def test_cadet_reaches_the_mission_file() -> None:
    """DCS has five air skills; pydcs shipped four."""
    assert Skill("Cadet") is CADET_SKILL
    assert CADET_SKILL.value == "Cadet"


def test_the_ladder_runs_from_cadet_to_ace() -> None:
    assert [skill.value for skill in SKILL_LADDER] == [
        "Cadet",
        "Average",
        "Good",
        "High",
        "Excellent",
    ]


def test_ground_units_never_see_cadet() -> None:
    """Blue shares one setting between its pilots and its tanks."""
    assert ground_skill(CADET_SKILL) is Skill.Average
    for skill in SKILL_LADDER[1:]:
        assert ground_skill(skill) is skill


def test_only_pilots_are_offered_cadet() -> None:
    assert PILOT_SKILL_CHOICES == ["Cadet", *GROUND_SKILL_CHOICES]
    assert "Cadet" not in GROUND_SKILL_CHOICES


# --- the ladders -----------------------------------------------------------


@pytest.mark.parametrize("ladder", [GENERIC_RANKS, *COUNTRY_RANKS.values()])
def test_every_ladder_has_one_rung_per_skill(ladder: RankLadder) -> None:
    assert len(ladder) == len(SKILL_LADDER)
    assert all(rank.abbreviation and rank.name for rank in ladder)


@pytest.mark.parametrize(
    "country_name,expected",
    [
        ("USA", ["2ndLt", "1stLt", "Capt", "Maj", "LtCol"]),
        ("UK", ["PltOff", "FgOff", "FltLt", "SqnLdr", "WgCdr"]),
        ("Russia", ["MlLt", "Lt", "StLt", "Kpt", "Mjr"]),
        ("Spain", ["Alf", "Tte", "Cap", "Cte", "Tcol"]),
    ],
)
def test_a_squadron_promotes_through_its_own_service(
    country_name: str, expected: List[str]
) -> None:
    ladder = ranks_for(RANK_NAMES_COUNTRY, _country(country_name))
    assert _abbreviations(ladder) == expected


@pytest.mark.parametrize(
    "country_name", ["Combined Joint Task Forces Blue", "Insurgents"]
)
def test_countries_with_no_ladder_of_their_own_fall_back(country_name: str) -> None:
    assert ranks_for(RANK_NAMES_COUNTRY, _country(country_name)) == GENERIC_RANKS


def test_no_country_falls_back() -> None:
    assert ranks_for(RANK_NAMES_COUNTRY, None) == GENERIC_RANKS


def test_generic_ranks_can_be_asked_for_explicitly() -> None:
    """A player who does not want Hauptmanns gets the plain ladder."""
    germany = _country("Germany")
    assert ranks_for(RANK_NAMES_COUNTRY, germany) != GENERIC_RANKS
    assert ranks_for(RANK_NAMES_GENERIC, germany) == GENERIC_RANKS


def test_skill_names_are_the_dcs_levels() -> None:
    ladder = ranks_for(RANK_NAMES_SKILL, _country("Germany"))
    assert _abbreviations(ladder) == ["Cdt", "Avg", "Gdd", "Hig", "Exc"]
    assert [rank.name for rank in ladder] == [skill.value for skill in SKILL_LADDER]


def test_custom_names_are_used_as_typed() -> None:
    ladder = ranks_for(
        RANK_NAMES_CUSTOM,
        None,
        [
            ("Nov", "Novato"),
            ("Pil", "Piloto"),
            ("Vet", "Veterano"),
            ("Jef", "Jefe"),
            ("As", "As de ases"),
        ],
    )
    assert _abbreviations(ladder) == ["Nov", "Pil", "Vet", "Jef", "As"]
    assert [rank.name for rank in ladder] == [
        "Novato",
        "Piloto",
        "Veterano",
        "Jefe",
        "As de ases",
    ]


def test_each_half_of_a_custom_rung_falls_back_on_its_own() -> None:
    """Filling in the full names should not require inventing abbreviations too."""
    ladder = ranks_for(
        RANK_NAMES_CUSTOM,
        None,
        [("Nov", "Novato"), ("", "Piloto"), ("Vet", "  "), ("", ""), ("As", "As")],
    )
    assert _abbreviations(ladder) == ["Nov", "1stLt", "Vet", "Maj", "As"]
    assert [rank.name for rank in ladder] == [
        "Novato",
        "Piloto",
        "Captain",
        "Major",
        "As",
    ]


def test_an_unknown_naming_falls_back_rather_than_raising() -> None:
    assert ranks_for("something a future version wrote", None) == GENERIC_RANKS


@pytest.mark.parametrize("skill", [Skill.Random, Skill.Player, Skill.Client])
def test_a_skill_that_is_not_a_rung_reads_as_the_bottom(skill: Skill) -> None:
    """Random, Player and Client are skills to DCS but not steps of a career."""
    assert rank_for_skill(skill, GENERIC_RANKS) == GENERIC_RANKS[0]


# --- the settings ----------------------------------------------------------


def test_the_setting_offers_exactly_the_namings_that_exist() -> None:
    """settings.py cannot import the constants without a cycle, so pin them here."""
    (description,) = [
        d
        for n, d in Settings.fields("Live Pilots", "Ranks")
        if n == "live_pilots_rank_names"
    ]
    assert isinstance(description, ChoicesOption)
    assert list(description.choices.values()) == [
        RANK_NAMES_COUNTRY,
        RANK_NAMES_GENERIC,
        RANK_NAMES_SKILL,
        RANK_NAMES_CUSTOM,
    ]


def test_the_rank_boxes_are_always_shown() -> None:
    """They preview whichever naming is chosen, greyed out unless it is the custom one."""
    fields = list(Settings.fields("Live Pilots", "Ranks"))
    # The naming choice heads the ladder, then a short and a full name per rung, and
    # a price for every rung but the one everybody starts on.
    assert len(fields) == 1 + 2 * len(SKILL_LADDER) + (len(SKILL_LADDER) - 1)
    assert all(description.visible_when is None for _, description in fields)


def test_every_rung_but_the_first_has_a_price_that_can_be_set() -> None:
    """Cadet is where everyone starts, so it costs nothing by definition."""
    from game.dcs.skills import SKILL_XP_SETTINGS, xp_thresholds

    assert SKILL_XP_SETTINGS[0] is None
    names = {n for n, _ in Settings.fields("Live Pilots", "Ranks")}
    assert all(key in names for key in SKILL_XP_SETTINGS[1:])

    settings = Settings()
    assert xp_thresholds(settings) == xp_thresholds()
    settings.live_pilots_rank_good_xp = 2500
    assert xp_thresholds(settings) == (0, 1500, 2500, 8000, 16000)


@pytest.mark.parametrize(
    "saved_prices", [(0, 1000, 2000, 4000, 8000), (0, 2000, 5000, 10000, 20000)]
)
def test_loading_saved_rank_prices_preserves_them(
    saved_prices: tuple[int, ...],
) -> None:
    from game.dcs.skills import SKILL_XP_SETTINGS, xp_thresholds

    state = {
        key: value
        for key, value in zip(SKILL_XP_SETTINGS, saved_prices)
        if key is not None
    }
    settings = Settings()
    settings.__setstate__(state)
    assert xp_thresholds(settings) == saved_prices


def test_loading_settings_without_rank_prices_uses_defaults() -> None:
    from game.dcs.skills import xp_thresholds

    settings = Settings()
    settings.__setstate__({})
    assert xp_thresholds(settings) == (0, 1500, 4000, 8000, 16000)


def test_only_the_abbreviation_boxes_are_capped() -> None:
    for name, description in Settings.fields("Live Pilots", "Ranks"):
        if not isinstance(description, TextOption):
            continue
        assert description.max_length == (5 if name.endswith("_short") else None)


def test_the_custom_boxes_start_filled_with_the_generic_ladder() -> None:
    settings = Settings()
    assert [
        settings.live_pilots_rank_cadet_short,
        settings.live_pilots_rank_average_short,
        settings.live_pilots_rank_good_short,
        settings.live_pilots_rank_high_short,
        settings.live_pilots_rank_excellent_short,
    ] == _abbreviations(GENERIC_RANKS)
    assert [
        settings.live_pilots_rank_cadet_full,
        settings.live_pilots_rank_average_full,
        settings.live_pilots_rank_good_full,
        settings.live_pilots_rank_high_full,
        settings.live_pilots_rank_excellent_full,
    ] == [rank.name for rank in GENERIC_RANKS]
