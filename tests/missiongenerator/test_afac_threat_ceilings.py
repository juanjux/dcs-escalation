"""Coverage and optional installed-source checks for AFAC threat ceilings."""

from pathlib import Path
import re

from dcs.installation import get_dcs_install_directory, get_dcs_saved_games_directory
import pytest

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.missiongenerator.afacthreats import VERIFIED_CEILINGS, envelope
from pydcs_extensions import load_mods


@pytest.fixture(scope="module", autouse=True)
def registered_mods() -> None:
    load_mods()
    envelope.cache_clear()


@pytest.mark.parametrize("type_name,ceiling", VERIFIED_CEILINGS.items())
def test_verified_type_is_registered_and_exports_its_ceiling(
    type_name: str, ceiling: int
) -> None:
    data = envelope(type_name)
    assert data is not None, type_name
    assert data["radius"] > 0
    assert data["ceiling"] == ceiling > 0


@pytest.mark.parametrize(
    "type_name,ceiling",
    [
        ("SA-18 Igla manpad", 3500),
        ("SA-18 Igla-S manpad", 3500),
        ("Igla manpad INS", 3500),
        ("Soldier stinger", 3500),
        ("SA-7 Strela-2 manpad", 2000),
        ("SA-7b Strela-2M manpad", 2300),
        ("SA-14 Strela-3 manpad", 3000),
        ("SA-24 Igla-S manpad", 3500),
        ("CH_USInfantry_FIM92", 4800),
    ],
)
def test_all_registered_manpad_launchers_have_their_own_ceiling(
    type_name: str, ceiling: int
) -> None:
    data = envelope(type_name)
    assert data is not None and data["ceiling"] == ceiling


def test_manpad_inventory_has_no_unreviewed_armed_variant() -> None:
    # C2 soldiers have no threat radius and must not be mistaken for launchers.
    for unit_type in GroundUnitType.each_dcs_type():
        variants = GroundUnitType.for_dcs_type(unit_type)
        if any(variant.unit_class == UnitClass.MANPAD for variant in variants):
            data = envelope(unit_type.id)
            if data is not None:
                assert data["ceiling"] is not None, unit_type.id


@pytest.mark.parametrize(
    "type_name",
    ["NASAMS_LN_B", "NASAMS_LN_C", "Pantsir_SM", "S-400 51P6A ln"],
)
def test_unverified_variants_stay_conservative(type_name: str) -> None:
    data = envelope(type_name)
    assert data is not None and data["ceiling"] is None


def test_igla_s_ceiling_matches_native_encyclopedia() -> None:
    root = get_dcs_install_directory()
    if not root:
        pytest.skip("DCS is not installed")
    source_file = Path(root) / "MissionEditor/data/scripts/Enc/SAM/Igla-S.txt"
    if not source_file.is_file():
        pytest.skip("DCS encyclopedia is not available")
    source = source_file.read_text(encoding="utf-8")
    match = re.search(r"Target altitude:\s*10-(\d+)", source)
    assert match is not None
    assert VERIFIED_CEILINGS["SA-18 Igla-S manpad"] == int(match.group(1))


# Each marker selects a weapon block, not the first H_max anywhere in a family.
# These are optional checks against locally installed primary sources. CI uses
# the deterministic inventory and geometry tests above without requiring DCS.
@pytest.mark.parametrize(
    "type_name,relative_path,marker",
    [
        (
            "Soldier stinger",
            "tech/TechWeaponPack/Database/Weapons/manpads_missiles.lua",
            'name\t\t\t= "FIM_92C"',
        ),
        (
            "2S6 Tunguska",
            "tech/TechWeaponPack/Database/Weapons/tunguska_family.lua",
            'name = "SA9M311"',
        ),
        (
            "Osa 9A33 ln",
            "tech/TechWeaponPack/Database/Weapons/osa_tor_family.lua",
            'name = "SA9M33"',
        ),
        (
            "Tor 9A331",
            "tech/TechWeaponPack/Database/Weapons/osa_tor_family.lua",
            'name = "SA9M330"',
        ),
        (
            "Kub 2P25 ln",
            "tech/TechWeaponPack/Database/Weapons/kub_buk_family.lua",
            'name = "SA3M9M"',
        ),
        (
            "SA-11 Buk LN 9A310M1",
            "tech/TechWeaponPack/Database/Weapons/kub_buk_family.lua",
            'name = "SA9M38M1"',
        ),
        (
            "Strela-1 9P31",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "SA9M31"',
        ),
        (
            "Strela-10M3",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "SA9M333"',
        ),
        (
            "Patriot ln",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "MIM_104"',
        ),
        (
            "Hawk ln",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "HAWK_RAKETA"',
        ),
        (
            "Roland ADS",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "ROLAND_R"',
        ),
        (
            "S-200_Launcher",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "SA5V28"',
        ),
        (
            "rapier_fsa_launcher",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "Rapier"',
        ),
        (
            "S_75M_Volhov",
            "tech/TechWeaponPack/Database/Weapons/s75_s125_family.lua",
            'name = "SA2V755"',
        ),
        (
            "5p73 s-125 ln",
            "tech/TechWeaponPack/Database/Weapons/s75_s125_family.lua",
            'name = "SA5B27"',
        ),
        (
            "S-300PS 5P85C ln",
            "tech/TechWeaponPack/Database/Weapons/s300_s400_family.lua",
            'name = "SA5B55"',
        ),
        (
            "CHAP_PantsirS1",
            "tech/TechWeaponPack/Database/Weapons/tunguska_family.lua",
            'name = "SA57E6"',
        ),
        (
            "CHAP_TorM2",
            "tech/TechWeaponPack/Database/Weapons/osa_tor_family.lua",
            'name\t\t\t\t= "SA9M338K"',
        ),
        (
            "CHAP_IRISTSLM_LN",
            "tech/TechWeaponPack/Database/Weapons/misc_sams.lua",
            'name = "SA_IRIS_T_SL"',
        ),
        (
            "M48 Chaparral",
            "aircraft/AircraftWeaponPack/aim9_family.lua",
            'name = "MIM_72G"',
        ),
        ("HQ-7_LN_SP", "aircraft/ChinaAssetPack/Entries/Tech/weapons.lua", "HQ_7 = {"),
    ],
)
def test_native_ceiling_matches_installed_weapon(
    type_name: str, relative_path: str, marker: str
) -> None:
    root = get_dcs_install_directory()
    if not root:
        pytest.skip("DCS is not installed")
    source_file = Path(root) / "CoreMods" / relative_path
    if not source_file.is_file():
        pytest.skip("DCS weapon source is not available")
    source = source_file.read_text(encoding="utf-8")
    # Ignore formatting differences between DCS versions.
    normalized = re.sub(r"[ \t]+", "", source)
    block = normalized.split(re.sub(r"[ \t]+", "", marker), 1)[1]
    block = block.split("declare_weapon(", 1)[0]
    match = re.search(r"\bH_max=([\d.eE+-]+)", block)
    assert match is not None
    assert VERIFIED_CEILINGS[type_name] == float(match.group(1))


@pytest.fixture(scope="module")
def installed_mod_sources() -> dict[str, list[Path]]:
    root = Path(get_dcs_saved_games_directory()) / "Mods/tech"
    sources: dict[str, list[Path]] = {}
    for source in root.rglob("*.lua"):
        sources.setdefault(source.name, []).append(source)
    return sources


@pytest.mark.parametrize(
    "type_name,filename",
    [
        ("SA-7 Strela-2 manpad", "9M32.lua"),
        ("SA-7b Strela-2M manpad", "9M32M.lua"),
        ("SA-14 Strela-3 manpad", "9M36.lua"),
        ("SA-24 Igla-S manpad", "9M342.lua"),
        ("5p73 V-601P ln", "5V27.lua"),
        ("S_75M_Volhov_V759", "5V23.lua"),
        ("HQ_2_Guideline_LN", "HQ2.lua"),
        ("SA-17 Buk M1-2 LN 9A310M1-2", "9M317.lua"),
        ("S-300PMU1 5P85CE ln", "48N6.lua"),
        ("S-300PMU2 5P85SE2 ln", "48N6E2.lua"),
        ("S-300V 9A82 ln", "9M82.lua"),
        ("S-300V 9A83 ln", "9M83.lua"),
        ("S-300VM 9A82ME ln", "9M82M.lua"),
        ("S-300VM 9A83ME ln", "9M83M.lua"),
        ("SAMPT_MLT_Blk1", "ASTER-30-1.lua"),
        ("SAMPT_MLT_Blk1NT", "ASTER-30-1NT.lua"),
        ("SAMPT_MLT_Blk2", "ASTER-30-2.lua"),
        ("CH_USInfantry_FIM92", "CH_USInfantry_FIM92K.lua"),
        ("CH_LAVAD", "CH_LAV-AD_FIM92E.lua"),
        ("CH_BoxerSkyranger", "CH_BoxerSkyranger_FIM92K.lua"),
        ("CH_Wiesel2Ozelot", "CH_Wiesel2Ozelot_FIM92E.lua"),
        ("CH_TorM2K", "CH_9M332_missile.lua"),
        ("CH_BukM3_9A317M", "CH_BukM3_9M317M.lua"),
        ("CH_BukM3_9A317MA", "CH_BukM3_9M317MA.lua"),
        ("CH_PantsirS2", "CH_Pantsir_SPAAGM_57E6M.lua"),
        ("CH_S350_50P6_9M100", "CH_S350_9M100.lua"),
        ("CH_S350_50P6_9M96D", "CH_S350_9M96D.lua"),
        ("CH_MIM104_M903_PAC2", "CH_MIM104_Patriot_PAC2.lua"),
        ("CH_MIM104_M903_PAC3", "CH_MIM104_Patriot_PAC3.lua"),
        ("CH_MIM104_M901_PAC2_KAT1", "CH_MIM104_KAT1_PAC2.lua"),
        ("CH_NASAMS3_LN_AIM9X2", "CH_NASAMS_3_AIM9X2.lua"),
        ("CH_NASAMS3_LN_AMRAAM_ER", "CH_NASAMS_3_AMRAAM_ER.lua"),
        ("CH_THAAD_M1120", "CH_THAAD_Interceptor.lua"),
        ("CH_RBS-70", "CH_RBS70_Bolide.lua"),
        ("CH_RBS-90", "CH_RBS90_Bolide.lua"),
        ("CH_RBS-98", "CH_RBS98_IRIS-T.lua"),
        ("CH_LvS-103_Lavett103_Rb103A", "CH_LvS103_Rb103A.lua"),
        ("CH_LvS-103_Lavett103_Rb103B", "CH_LvS103_Rb103B.lua"),
        ("CH_SkySabre", "CH_SkySabre_LandCeptor.lua"),
        ("CH_StormerHVM", "CH_StormerHVM_Starstreak.lua"),
        ("HQ17A", "HQ-17A_missile.lua"),
        ("CH_HQ22_LN", "HQ-22_missile.lua"),
        ("PGL_625", "PGL_625_FB10A.lua"),
        ("CH_FlaRakRad", "CH_FlaRakRad_Roland3.lua"),
        ("CH_2S38_LG", "CH_2S38_3UO7.lua"),
    ],
)
def test_mod_ceiling_matches_installed_weapon(
    installed_mod_sources: dict[str, list[Path]], type_name: str, filename: str
) -> None:
    sources = installed_mod_sources.get(filename, [])
    if not sources:
        pytest.skip("Mod weapon source is not installed")
    for source_file in sources:
        source = source_file.read_text(encoding="utf-8")
        source = re.sub(r"--[^\n]*", "", source)
        block = source.split("declare_weapon(", 1)[0]
        match = re.search(r"\bH_max\s*=\s*([\d.eE+-]+)", block)
        assert match is not None, source_file
        assert VERIFIED_CEILINGS[type_name] == float(match.group(1)), source_file
