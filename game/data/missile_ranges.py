"""Minimum engagement ranges for the launchers that arm missile sites.

pydcs exposes ``threat_range`` but not the minimum, and several of these launchers have
one that nothing in Escalation has ever respected: a DF-21D battery cannot engage
anything inside 300 km, an ATACMS or Iskander battery nothing inside 75. Tasked at a
closer target they fire anyway and the rounds go nowhere.

Values are the ``ThreatRangeMin`` each unit declares in its own mod files. A launcher
with no entry has no minimum -- the Scud is the common case, and the reason a Scud site
lands its rounds somewhere near the target while an ATACMS site does not.
"""

MISSILE_SITE_MIN_RANGE_M: dict[str, int] = {
    "CH_M270A1_ATACMS": 75000,
    "CHAP_9K720_HE": 75000,
    "CHAP_9K720_Cluster": 75000,
    "CH_DF21D": 300000,
    "CH_CJ10": 20000,
    "CH_IskanderK": 20000,
    "CH_YJ12B": 10000,
    # ED shipped Currenthill's assets with the game as the CHAP pack, and those
    # declare their own minimums in CoreMods/tech/Currenthill Assets Pack.
    "CHAP_M142_ATACMS_M48": 50000,
    "CHAP_M142_ATACMS_M39A1": 50000,
    "CHAP_M142_GMLRS_M30": 15000,
    "CHAP_M142_GMLRS_M31": 15000,
}
