# AFAC implementation contract

This is the first implementation stage. `afaccapabilities.py` and `afac.lua`
provide isolated profiles and a coordination state machine. They are **not loaded
by campaign generation** and do not expose new mission types, options or faction
aircraft yet. Lua 5.1 unit tests are not DCS engine acceptance.

## Approved gameplay rules

- Mission names: **AFAC — Area** and **AFAC — Frontline**. Both require Realistic
  CAS and its future AFAC option. Aircraft availability does not require the script.
- Profiles combine equipment across variants, accepting uncertain capabilities.
  These are gameplay profiles, not claims about real aircraft equipment.
- All designators use the same configurable code, default **1688**, on both sides.
  One AFAC reserves an entire enemy group, even when marking just one member.
  Different nearby groups may still produce same-code ambiguity; exclusive group
  ownership does not claim to eliminate that limitation.
- A compatible helicopter can carry an explicit JTAC kit adding laser, IR pointer
  and thermal observation. Drones and fixed-wing aircraft cannot gain this kit.
  Do not infer passenger space from the catalogue's generic helicopter default.
- Warn about night assignments without thermal observation. An IR pointer is not
  a thermal camera. No automatic night mission ban is implied.
- Marking lasts **300 simulated seconds**, station time **3600 seconds**, and
  messages **15 seconds**, all configurable. A 20% fuel reserve overrides station
  time. Station time starts on arrival and is not renewed by leaving/re-entering.
- Smoke requires actual finite payload ammunition. No free smoke from an AFAC
  role, passenger, aerobatic emitter or countermeasure dispenser. A failed engine
  smoke attempt consumes its reserved round because the physical outcome can be
  uncertain. Mixed pods without verified marker counts remain unsupported.
- UAV operators remain normal roster members earning discovery XP, but cannot be
  killed, wounded or missing because their UAV was lost. The capability flag alone
  does **not** implement that protection; Live Pilots integration is a later stage.
- Aircraft recovery/workshops must not change pilot survival rules. Future CSAR
  mission generation remains separate.

## Coordinator boundary

Load `core.lua` then `afac.lua`, and explicitly construct `RealisticCAS.newAFAC`.
Omitted/false `enabled` is inert. Campaign `SCRIPT_ORDER` intentionally excludes it.

The mission adapter registers observers with stable IDs, coalition, capabilities
and their remaining smoke inventory. For each observer it supplies a report with
`alive`, fuel fraction, `onStation`, `night`, and a bounded contact array. Put the
currently marked unit first so a work budget cannot starve its observation.

A contact needs an ID, group, enemy coalition, finite position and explicit
`alive`, `revealed`, `observed`, `safe`, and `inZone` flags. `observed` means a fresh
sensor/LOS-approved sample, not merely an unexpired shared contact. Unknown
threats must not affect `safe`; the future threat adapter uses only known air
defences. Contacts outside the assigned area/front are never accepted.

The coordinator makes no DCS calls, reads no live targets, discovers no enemies
itself and installs no scheduler or event handler. Per-step contact work is bounded
(32 candidates by default). The existing perception scheduler will supply genuine
observations and handle search, skill, weather and LOS budgets during integration.

Required injected callbacks are `clock`, `startMark`, `updateMark`, `stopMark` and
`smoke`. Effects return exactly `true` on success. They receive detached target
snapshots. An optional `emit` callback receives the owning coalition, observer ID,
event, detail and message duration; it must not broadcast enemy information.

An adapter must clean up all resources from a partially failed `startMark` when
`stopMark` is called. Failed cleanup retains the group reservation and is retried
on subsequent steps or shutdown. `pendingState` exposes a loss/RTB request even
while cleanup is failing; route exit must not wait for successful spot deletion.
Observers with pending cleanup must remain scheduled after their source dies.

The states are `transit`, `search`, `mark`, `stopping`, `rtb`, `lost` and `stopped`.
RTB/lost/stopped cannot return to search. After a full marking period, the previous
group is skipped until another group has been marked. Without an alternative the
observer searches; it does not immediately restart five minutes on the same group.

No options are added to the live plugin UI in this stage. Native laser/IR spot
creation, realistic smoke delivery, navigation, AA/cloud avoidance, sensor and
pilot skill integration, discovery telemetry/XP and the normal mission lifecycle
still require adapters and Game Master engine probes.

## Faction allocation decisions to preserve

The reviewed roster covers 137 factions. Ancient fallback factions keep only the
Yak-52, not an anachronistic helicopter. Modern Russian, Iranian, Libyan, Syrian,
Redfor Russian, Russian PMC and insurgent rosters gain Wing Loong as a gameplay
substitute, using 2010 as the allocation cutoff. Older dated rosters do not gain it.
Israel gains Predator in 2000-era rosters and Reaper in post-2007 rosters. Morocco
2000 gains Predator; Morocco 2030 gains Predator and Reaper. USA 2020 also gains
Predator without removing its previous alternatives. US Navy 1985/2005/2009 gain
Kiowa. Turkey 2005 deliberately receives an early TB2.

Carrier support for Reaper is **not** enabled by a sensor capability profile.
The real MQ-9B STOL kit does not establish native DCS AI deck launch/recovery.
That needs a separate engine test before campaign carrier eligibility changes.

## Remaining implementation order

1. Normal squadrons, remote operator survival, faction allocations and era rules.
2. AFAC mission types/plans, assigned area/front, observations, skill and XP.
3. Native marking adapters, messages/coordinates and grouped plugin options.
4. Known-AA/cloud constraints, engine probes and campaign acceptance.

Update How to Play when the user-facing missions and settings become available;
do not document these isolated foundations as a playable feature.
