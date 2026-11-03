"""Conservative transit-defense profiles validated with native mission probes."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TransitDefense:
    types: frozenset[str]
    range_m: int
    ceiling_m: int | None = None
    min_range_m: int = 0


# Unknown and mixed batteries stay packed. Sky Sabre and S-350 did not recover
# reliably after firing; mobility alone does not qualify a site for this policy.
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
)


def transit_defense(types: Iterable[str]) -> TransitDefense | None:
    present = frozenset(types)
    return next((profile for profile in PROFILES if present == profile.types), None)
