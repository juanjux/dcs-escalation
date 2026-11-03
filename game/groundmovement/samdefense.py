"""Conservative transit-defense profiles validated with native mission probes."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TransitDefense:
    types: frozenset[str]
    range_m: int
    ceiling_m: int | None = None
    min_range_m: int = 0


# Unknown and mixed batteries stay packed. Sky Sabre, S-350 and HQ-17A did not
# recover reliably after firing. Mobility alone does not qualify a site.
PROFILES = (
    # Weapon H_max/D_min: native SA9M33 and CH 9M332/9M317M files.
    # The probe-validated outer ranges remain conservative; native AI decides
    # whether it can actually engage. C-RAM is bounded by slant range only.
    TransitDefense(frozenset({"Osa 9A33 ln"}), 10000, 5000, 1500),
    TransitDefense(frozenset({"HEMTT_C-RAM_Phalanx"}), 2000),
    TransitDefense(frozenset({"CH_TorM2K"}), 12000, 10000, 1000),
    TransitDefense(
        frozenset({"CH_BukM3_9A317M", "CH_BukM3_9S18M13", "CH_BukM3_9S510M"}),
        25000,
        35000,
        2500,
    ),
    TransitDefense(frozenset({"2S6 Tunguska"}), 8000, 3500),
    TransitDefense(frozenset({"Gepard"}), 4000),
    # Additional native probes completed detection, fire and physical recovery.
    # Ceilings use the weapon/launcher values documented in afacthreats.py.
    # Native SA9M330/SA9M338K D_min is 1500 m; Roland/Roland3 is 500 m.
    TransitDefense(frozenset({"ZSU_57_2"}), 7000, 4000),
    TransitDefense(frozenset({"ZSU-23-4 Shilka"}), 2500),
    TransitDefense(frozenset({"CHAP_PantsirS1"}), 12000, 10000),
    TransitDefense(frozenset({"CHAP_TorM2"}), 12000, 12000, 1500),
    TransitDefense(frozenset({"Tor 9A331"}), 12000, 6000, 1500),
    TransitDefense(frozenset({"Vulcan"}), 2000),
    TransitDefense(frozenset({"Roland ADS"}), 8000, 6000, 500),
    TransitDefense(frozenset({"Ural-375 ZU-23"}), 2500),
    TransitDefense(frozenset({"CH_Centurion_C_RAM"}), 2000),
    TransitDefense(frozenset({"CH_PantsirS2"}), 12000, 18000),
    # CH Starstreak D_min is 300 m; FB10A D_max is 8000 m (guns are shorter).
    TransitDefense(frozenset({"CH_StormerHVM"}), 7000, 7000, 300),
    TransitDefense(frozenset({"CH_FlaRakRad"}), 8000, 6000, 500),
    TransitDefense(frozenset({"CH_LvKv9040"}), 4000, 2500),
    TransitDefense(frozenset({"PGL_625"}), 8000, 5000),
    # Identifiable missile fire and physical recovery were also verified here.
    # Native SA9M31/SA9M333 D_min is 800 m. Mixed gun/missile systems retain
    # their close-range gun defense; native AI selects a usable weapon.
    TransitDefense(frozenset({"M1097 Avenger"}), 4500, 3500),
    TransitDefense(frozenset({"M6 Linebacker"}), 4500, 3500),
    TransitDefense(frozenset({"Strela-10M3"}), 5000, 3500, 800),
    TransitDefense(frozenset({"Strela-1 9P31"}), 4200, 3500, 800),
    TransitDefense(frozenset({"CH_LAVAD"}), 8000, 4800),
    TransitDefense(frozenset({"CH_BoxerSkyranger"}), 8000, 4800),
    TransitDefense(frozenset({"CH_Wiesel2Ozelot"}), 8000, 4800),
    # RBS-98's secondary gun recovered, but its radar-dependent missiles did not
    # fire in the independent-launcher probe. It is not a reviewed SAM profile.
)


def transit_defense(types: Iterable[str]) -> TransitDefense | None:
    present = frozenset(types)
    return next((profile for profile in PROFILES if present == profile.types), None)
