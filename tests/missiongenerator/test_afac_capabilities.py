"""AFAC profiles are gameplay metadata, not native AI acceptance tests."""

from dataclasses import FrozenInstanceError

import pytest

from game.dcs.afaccapabilities import (
    AFAC_AIRCRAFT,
    AFACCapabilities,
    capabilities_for,
    needs_night_warning,
    smoke_rounds,
)


@pytest.mark.parametrize(
    "aliases",
    [
        ("MQ-9", "MQ-9 Reaper"),
        ("OH-58D", "OH58D"),
        ("SA342L", "SA342M", "SA342Minigun", "SA342Mistral"),
        ("CH_Ka52", "CH_Ka52K"),
    ],
)
def test_family_variants_share_the_gameplay_maximum(aliases: tuple[str, ...]) -> None:
    profiles = [capabilities_for(name) for name in aliases]
    assert all(profile is profiles[0] for profile in profiles)


@pytest.mark.parametrize(
    "name", ["MQ-9 Reaper", "RQ-1A Predator", "WingLoong-I", "TB-2 UCAV"]
)
def test_remote_operators_and_common_designation(name: str) -> None:
    profile = capabilities_for(name)
    assert profile is not None
    assert (
        profile.remote_operator and profile.ir and profile.laser and profile.ir_pointer
    )
    assert not profile.can_embark_jtac
    with pytest.raises(ValueError, match="cannot embark"):
        capabilities_for(name, embarked_jtac=True)


@pytest.mark.parametrize("name", ["UH-1H", "Mi-8MT", "OH-6A", "UH-60A", "HKP15B"])
def test_embarked_jtac_adds_thermal_laser_and_pointer_without_mutation(
    name: str,
) -> None:
    original = capabilities_for(name)
    equipped = capabilities_for(name, embarked_jtac=True)
    assert original is not None and equipped is not None
    assert equipped.eo and equipped.ir and equipped.laser and equipped.ir_pointer
    assert equipped.embarked_jtac
    assert not original.embarked_jtac
    assert capabilities_for(name) is original
    assert not needs_night_warning(equipped, night=True)


@pytest.mark.parametrize("name", ["Yak-52", "C-101CC", "L-39ZA", "SK-60", "vwv_o-1"])
def test_fixed_wing_cannot_gain_a_passenger_designator(name: str) -> None:
    profile = capabilities_for(name)
    assert profile is not None
    assert needs_night_warning(profile, night=True)
    assert not needs_night_warning(profile, night=False)
    with pytest.raises(ValueError):
        capabilities_for(name, embarked_jtac=True)


def test_dap_is_not_treated_as_a_passenger_transport() -> None:
    with pytest.raises(ValueError):
        capabilities_for("UH-60L_DAP", embarked_jtac=True)


def test_thermal_warning_is_not_confused_with_ir_marking() -> None:
    assert needs_night_warning(
        AFACCapabilities("pointer only", ir_pointer=True), night=True
    )
    assert not needs_night_warning(
        AFACCapabilities("thermal only", ir=True), night=True
    )


def test_unknown_types_do_not_gain_capabilities_from_names() -> None:
    assert capabilities_for("MQ-9 imaginary mod") is None
    assert capabilities_for("Unknown helicopter") is None
    with pytest.raises(ValueError):
        capabilities_for("Unknown helicopter", embarked_jtac=True)


def test_profiles_are_immutable_and_equipment_exports_are_detached() -> None:
    profile = capabilities_for("OH58D")
    assert profile is not None
    equipment = profile.equipment()
    equipment["ir"] = False
    assert profile.ir
    with pytest.raises(FrozenInstanceError):
        setattr(profile, "ir", False)
    with pytest.raises(TypeError):
        AFAC_AIRCRAFT["unknown"] = profile  # type: ignore[index]


def test_smoke_counts_rounds_and_keeps_duplicate_racks() -> None:
    assert smoke_rounds(["{M260_M156}", "{M260_M156}"]) == 14
    assert smoke_rounds(["B_8V20A_CM_GN", "XM158_M156"]) == 27
    assert smoke_rounds(["OH58D_Red_Smoke_Grenade"] * 3) == 3
    assert smoke_rounds(["{OH6_SMOKE_RED}"] * 4) == 16


def test_unknown_stores_and_aerobatic_smoke_are_not_marker_ammunition() -> None:
    assert smoke_rounds(["smoke generator", "M257", "flare", "chaff", "unknown"]) == 0
    assert smoke_rounds(["{M260_A_M151_B_M156}"]) == 0
