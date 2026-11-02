"""Conservative transit-defense profiles validated with native mission probes."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TransitDefense:
    types: frozenset[str]
    range_m: int


# Unknown and mixed batteries stay packed. Sky Sabre and S-350 did not recover
# reliably after firing; mobility alone does not qualify a site for this policy.
PROFILES = (
    TransitDefense(frozenset({"Osa 9A33 ln"}), 10000),
    TransitDefense(frozenset({"HEMTT_C-RAM_Phalanx"}), 2000),
    TransitDefense(frozenset({"CH_TorM2K"}), 12000),
    TransitDefense(
        frozenset({"CH_BukM3_9A317M", "CH_BukM3_9S18M13", "CH_BukM3_9S510M"}),
        25000,
    ),
)


def transit_defense(types: Iterable[str]) -> TransitDefense | None:
    present = frozenset(types)
    return next((profile for profile in PROFILES if present == profile.types), None)
