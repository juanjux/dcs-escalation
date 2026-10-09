"""GAU-8 ammunition indices from DCS CoreMods/aircraft/A-10/A-10A.lua.

The A-10C and A-10C II inherit this list. DCS writes its one-based index into
the unit's payload.ammo_type, not AddPropAircraft or the IFFCC settings.
"""

GAU8_AIRCRAFT = frozenset({"A-10A", "A-10C", "A-10C_2"})
GAU8_DEFAULT_AMMUNITION = 1
GAU8_AMMUNITION = {
    1: "CM Combat Mix",
    2: "HEI High Explosive Incendiary",
    3: "TP Target Practice",
}
