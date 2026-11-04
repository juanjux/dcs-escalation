# Campaign IADS expansion

This batch enables automatic IADS in 43 previously basic campaigns. The templates
add command centres, radio repeaters and power supplies, not SAM/AAA batteries,
combat aircraft, ships or armor depots. All existing combat markers are retained.
The sole position correction is the same offshore EWR marker (`Ground-34`) in
Battle of Abu Dhabi and PG Wargames, moved to nearby friendly land.

Mainland radio backbones use the default 15 NM communication range. Separate
islands and territorial enclaves receive local command sectors instead of relay
chains across open water. Power supplies near new command sites are paired where
there were not already two nearby sources. This provides destructible objectives;
it does not make the entire network immune to losing a command centre or relay.

## Campaign identity and scope

- Northern Guardian and The Valley of Rotary gain infrastructure only on BLUE.
  Their RED irregular forces are not given a national command network.
- Aleppo Insurgency uses small local RED command sectors around existing bases,
  rather than a new country-wide insurgent backbone.
- Helicopter campaigns retain their original SAM/AAA placements. Newly added
  jammers use emitter-only presets, so optional point-defence filling cannot add
  an extra Tunguska, Avenger or other escort battery.
- Ships remain independent of the land command network.
- Battle for No Man's Land, Caen to Evreux, Operation Dynamo, Final Countdown 2
  and Operation Shattered Dagger are unchanged. The previously converted advanced
  IADS campaigns are also unchanged.
- Existing saves are not rewritten; these are starting-template changes.

## GPS chronology

The modeled generic GPS jammer is introduced in **2010** in both unit definitions.
New jammers require a dated campaign at or after that year and a recommended
faction that already has access to the corresponding emitter. Undated scenarios
and improvised insurgent sectors receive no new jammer. This is a conservative
model-availability rule, not a claim that GPS jamming was invented in 2010 or that
every fictional faction fielded an identical truck in that year.

GPS jamming was already operationally documented in Iraq in 2003: the
[US Air Force report of 25 March 2003](https://www.af.mil/News/Article-Display/Article/139712/coalition-pilots-strike-satellite-guidance-jammers/)
describes six jammers attacked on 22 and 24 March. That does not establish
availability in 1988, or justify backdating the specific modeled 2010 equipment.
The 13 pre-2010 jammer overrides in this batch are therefore removed: those
existing EWR markers generate their normal period-appropriate radar again.
Modern jammer overrides already present in the campaigns are retained.

## Placement exceptions

The shipped Marianas planning mask omits Pagan, Agrihan, Anatahan, Uracas,
Asuncion and Guguan. In Pacific Repartee and Marianas 2027, added infrastructure
there is limited to within 300 m of the existing authored FOB/defence positions.
Each island has its own command sector. These are real islands, not permission to
place relays at sea; see the [USGS northern Mariana island survey](https://pubs.usgs.gov/of/1993/0541/report.pdf).

Mozdok to Maykop already had one AAA placeholder (`Ground-36`) which its
recommended faction does not generate. It is retained unchanged; this batch
does not add AAA to fill it.

## Added infrastructure by campaign

Counts below are additions, not final network totals. Existing nodes and modern
jammer overrides are not included. Actual topology is rebuilt from current
positions and ownership each turn; this table is not a topology definition.

| Campaign | Scope | Command | Relay | Power | GPS |
| --- | --- | ---: | ---: | ---: | ---: |
| Persian Gulf - Battle of Abu Dhabi | campaign | 4 | 59 | 8 | 0 |
| Caucasus - Black Sea | campaign | 2 | 68 | 4 | 0 |
| Caucasus - Full | campaign | 2 | 69 | 4 | 0 |
| Caucasus - Muti-Part Georgia | campaign | 2 | 26 | 4 | 0 |
| Caucasus - Multi-Part Russia | campaign | 2 | 69 | 4 | 0 |
| Germany - Crossing the Rubicon | campaign | 2 | 68 | 4 | 0 |
| Kola Peninsula - Able Archer 83 | campaign | 3 | 97 | 6 | 0 |
| Sinai - Exercise Bright Star | campaign | 2 | 46 | 3 | 1 |
| Sinai - Exercise Quasar (v1) | campaign | 2 | 48 | 2 | 1 |
| Nevada - Exercise Vegas Nerve | campaign | 2 | 43 | 2 | 1 |
| South Atlantic - Grabthar's Hammer | regional | 4 | 44 | 6 | 0 |
| Afghanistan - Graveyard of Empires | campaign | 2 | 49 | 4 | 0 |
| Marianas - Second Island Chain (2027) | regional | 10 | 0 | 18 | 1 |
| Marianas - Guam - Mount Barrigada | regional | 2 | 0 | 4 | 0 |
| Marianas - Guam - Landing at Agat | regional | 2 | 0 | 4 | 0 |
| Caucasus - Mozdok to Maykop | campaign | 2 | 25 | 2 | 0 |
| Germany - Northern Guardian | selective | 3 | 6 | 6 | 1 |
| Caucasus - Northern Russia | campaign | 2 | 38 | 4 | 0 |
| Sinai - Operation Desert Sabre (v1) | campaign | 2 | 42 | 1 | 1 |
| Syria - Aegean Aegis | regional | 1 | 10 | 2 | 0 |
| Syria - Operation Allied Sword | campaign | 1 | 69 | 2 | 0 |
| Syria - Operation Blackball | regional | 1 | 19 | 2 | 0 |
| Iraq - Operation Desert Aladeen | campaign | 2 | 26 | 4 | 2 |
| Syria - Desert Trident | campaign | 3 | 50 | 6 | 0 |
| Kola Peninsula - Operation Frostbite (Test Build) | campaign | 3 | 52 | 6 | 2 |
| Sinai - Operation Gazelle (Yom Kippur War) | campaign | 2 | 60 | 4 | 0 |
| Persian Gulf - Noisy Cricket | regional | 7 | 62 | 14 | 1 |
| Syria - Operation Peace Spring | campaign | 3 | 70 | 6 | 2 |
| Caucasus - Vectron's Claw | campaign | 3 | 46 | 6 | 0 |
| Marianas - Operation Velvet Thunder | regional | 5 | 2 | 8 | 0 |
| Marianas - Pacific Repartee | regional | 9 | 0 | 16 | 0 |
| Sinai - Red Sea Rising | campaign | 3 | 74 | 6 | 0 |
| South Atlantic - Retake the Falklands | regional | 3 | 50 | 6 | 0 |
| Caucasus - Slava Ukraini | campaign | 2 | 39 | 4 | 1 |
| Syria - Full Map | campaign | 3 | 63 | 5 | 1 |
| Syria - Task Force Thunder | campaign | 2 | 72 | 4 | 0 |
| Caucasus - The Tblisi Gap | campaign | 2 | 16 | 4 | 0 |
| Kola Peninsula - The Anvil of War | campaign | 3 | 102 | 6 | 0 |
| Persian Gulf - Valley of Rotary | selective | 1 | 0 | 2 | 1 |
| Syria - Tripoint Hostility | campaign | 2 | 36 | 4 | 0 |
| Syria - WRL - Aleppo Insurgency (v1.1) | selective | 12 | 22 | 6 | 1 |
| Caucasus - WRL - Battle for Georgia (v1.2) | campaign | 2 | 24 | 4 | 1 |
| Persian Gulf - WRL - Wargames (v1.1) | regional | 5 | 41 | 10 | 1 |

## Verification

The regression suite checks every converted template with normal and inverted
ownership, friendly command paths, loss of all command centres, land placement,
unique objective identities and emitter-only jammer presets. Baseline hashes
protect the original combat groups, routes, control points and all non-mission
ZIP entries (including duplicate filenames). The two documented EWR relocations
are checked separately; their unit types and other properties remain protected.

Full generation with each campaign's recommended factions, mods and air wing is
also checked at seeds 17 and 29, including generated ground-node command paths
and parity with the production Lua mission-export connectivity graph. Each seed
has 2,113 of 2,113 selected land nodes connected; all 2,557 compared Lua elements
agree with the campaign graph. The deliberately excluded RED irregular sides
are not included in the 2,113 total. This is generation/runtime-graph verification,
not a claim of manual DCS playtesting.
