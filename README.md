# DCS Retribution — juanjux fork

A personal fork of [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution)
that bundles a number of features and fixes which are not (yet) in upstream
Retribution. Some features and fixes are also adapted from the
[414Ret fork](https://github.com/bradyccox/414Ret).

## How development works here

Development happens **in this fork**. New work is opened as a
[Pull Request against this repository](https://github.com/juanjux/dcs-retribution/pulls),
targeting `master`, **not** against upstream — this keeps the upstream review
queue light and makes it easy for other forks to cherry-pick whatever they want.
Each PR describes the feature or fix it adds. Individual fixes may still be
offered upstream case by case.

## Branches

| Branch | Purpose |
| --- | --- |
| **`dev`** | A clean mirror of upstream `dcs-retribution/dev`. Pristine, untouched — the base everything is cut from. |
| **`master`** | The line you build. Every feature and fix lands here through a PR, after it has been tested. |

When upstream `dev` gets new commits they are occasionally pulled into `master`.

## Features not in upstream Retribution

Each item links to the fork PR that implements it. The authoritative, up-to-date
list is the [pull requests](https://github.com/juanjux/dcs-retribution/pulls?q=is%3Apr).

### Interface

- **The interface has been rebuilt.** Dialogs, lists and panels were redrawn to one
  visual language. Nothing about how the campaign plays changed.

  <img src="https://raw.githubusercontent.com/juanjux/dcs-retribution/juanjux/screenshots/airwing-redesign.png" width="760">

### IADS

- **Custom Skynetfork**, [juanjux/Skynet-IADS](https://github.com/juanjux/Skynet-IADS): upstream 3.3.0 with its
  HARM fixes, plus `ActMobile` and the four High Digit SAMs systems (S-400, S-300V4,
  SAMP/T, Pantsir-SM), and many, many fixes and performance improvements including (optional) culling of the network based on the
  plannet flight packages

- **Batteries with their own generator can survive a power grid cut.** A Patriot's EPP-III or a
  SAMP/T's MGE keeps the site powered when the nearest substation is bombed until the defined
   generator unit itself is destroyed.

- **IADS infrastructure can be rebuilt.**
  
- **Autonomous and dark sites are told apart from working ones.** A dark site draws no range rings
  and its health bar color and tooltip says why, network links are coloured by state.
  
- **Radar, missile battery and jamming sites are interchangeable** You can buy any of these in the place of others.
  They still have distinct icons.
  
- **Many fixed on campaigns that used IADS but had some errors in the topology or configuration.**

### Kneeboards
- **Friendly-packages list** plus a **package-targets map** page.
  ([#11](https://github.com/juanjux/dcs-retribution/pull/11))
- **DEAD/SEAD target page** — one waypoint per target with an STPT column.
  ([#18](https://github.com/juanjux/dcs-retribution/pull/18))
- **COMM2 presets** mirrored from COMM1 on twin-radio aircraft (plus an
  F/A-18-family COMM1/COMM2 fix) and clearer auto-assigned **TACAN** codes.
  ([#12](https://github.com/juanjux/dcs-retribution/pull/12),
  [#20](https://github.com/juanjux/dcs-retribution/pull/20))
- The **Support Info** page spans several pages when a package has many flights, instead
  of silently pushing the AEW&C, tanker and JTAC tables off the bottom of one.
  ([#69](https://github.com/juanjux/dcs-retribution/pull/69))



### Live Pilots
This is a completely new feature that make pilots be more than a name in a list. When enabling Live Pilots, instead of "Pilot #2", the actual name 
of the pilot and the abbreviated rank is shown in the long label in-engine.

- **Ranks and experience.** Pilots now have ranks, that map to real DCS skill levels, starting as cadets (2nd Lieutenant or whatever is the O1 equivalent in
the country selected) and earning XP by completing missions, destroying targets, and downing enemies, among other things, going up in the ladder (and in-engine skill)
as they do so.

- **Morale.** Pilots are human and thus can feel shaken or triumphant based on their own performance, their promotions, mates lost in the battle and other events (all
can be seen and their impact configured in the settings). The morale levels can make pilots act better or worse on the missions in-engine, and can improve or worsen
their surival chances on the battlefield if they are downed among other effects. Giving pilots a leave is not now useless, as it improves quickly their morale, even more
if they go together with friends. If the morale is low enough, for example when a pilot has lost several friends on a single flight, they could even refuse to fly or even desert, so try to have your pilots happy!

- **Hardening.** A pilot that has suffered some shit, lost mates and airframes, is hardened over time. Hardened pilots lost morale more slowly, have a higher
chance of surviving being downed, but also are slower to make friends or enemies.

- **Friendship.** Each pilot values each other as friends or even enemies, with different levels. Friendship have many effects and provide a positive or negative
XP multiplier for missions, modelling the synergy among the members of a flight or package and make being downed easy to survive if your friends are in the same flight (they look for you, help in the CSAR, et cetera) and make a pilot quicker to regain positive morale levels (comforting) and less prone to deserting.

- **Pilot dossier.** Double-clicking a pilot on the squadron roster opens his own dialog. It holds his rank and how much experience the next one takes, his kills grouped the way he would tell them -- air by what he shot down, ground by the sort of thing it was -- with every row opening in place to the individual kills (what, when, with what); what he has survived, and if he is gone, who got him and with what; his morale, the whole band scale, and the log of everything that has moved him; his hardening and what its three effects are worth as percentages; and his relationships in both directions -- what he thinks of each man and what that man thinks back -- friendly and unfriendly alike, washed in the same colours the rosters use. An optional cheat strip renames, promotes, heals and revives.

- **Rivals (coming soon).** Pilots can have _rivals_. Rivals are reciprocal between two pilots with an unfriendly relation and it makes them
try to best the other in XP earned when they fly in the same flight or package and thus really improves their performance in-engine. Think of Maverick and Ice! Over time,
rivals tend to be friends (but _not_ in the Tarantino interpretation of the film... or yes, that's to your imagination and preferences!).

- **Mate's Quests (coming soon).** In some turns, some mate will ask for help with some specific requirements. For example, a B52 pilot could ask you to escort him in his next mission, or a cadet could ask you, as a more experienced pilot, to fly with him on a SEAD mission with HARM missiles. These quests are optional, but if you accept and successfully fly it, both pilots will get a boost in XP and friendship.
  
- **Cantina (coming soon).** The cantina is a unified interface where you can explore all your pilots inter-relations, complete historic and stats related details of a single pilot, morale stats, leave requests and some warnings.

### Missions, AI & tasking
- **Fix escort and sead escorts not honoring the "ahead" TOT offset setting.** 
  ([#220](https://github.com/juanjux/dcs-retribution/pull/220))
  
- **Automatic refuelling waypoint and tanker added only if needed.** A package's route is costed leg by leg against and estimation of fuel usage based on the plane, speed and height
  and a flight that will not make it gets a dialog about adding a refuelling waypoint after the target and optionally a tanker in the same package.
  ([#211](https://github.com/juanjux/dcs-retribution/pull/211),
  [#213](https://github.com/juanjux/dcs-retribution/pull/213),
  [#214](https://github.com/juanjux/dcs-retribution/pull/214))
  
- **Mission Log** (plugin, off by default) — a running commentary of what happens to your
  side while you fly: who shot down whom and with what, which targets went down, who
  ejected, who crashed. 
  ([#120](https://github.com/juanjux/dcs-retribution/pull/120))

 
- **TARCAP gets its own on-station time**, that can be configured in the settings. Defaults to the 30 minutes it always was, and still gives way to
  the escorted mission.
  ([#137](https://github.com/juanjux/dcs-retribution/pull/137))
  
- **Turn times from the sun** — the four turn slots are derived from the theater's
  latitude and the campaign date rather than one fixed window per map, so a December dawn
  turn no longer starts in the pitch dark. North of the arctic circle the slots hang off
  solar noon and stay dark. A theater keeps its old table with `daytime_mode: table`.
  ([#113](https://github.com/juanjux/dcs-retribution/pull/113))
  
- **ATMOS-X live weather** — with the ATMOS-X pack selected, the turn's weather can be a
  real METAR observation fetched through the ATMOS-X CLI, for a station picked
  automatically or set by ICAO. Fetched when the turn is built, so kneeboards, the active
  runway and the carrier's course into wind all match.
  ([#101](https://github.com/juanjux/dcs-retribution/pull/101))
  
- **Custom cloud preset packs** — a campaign setting that makes a community cloud-preset
  mod's presets available to the generator: Bandit's Cloud Presets, Weather 2.0 or
  ATMOS-X, one at a time since the packs reuse the same preset keys.
  ([#53](https://github.com/juanjux/dcs-retribution/pull/53))
  
- **Smart Threat Reaction** — a plugin that keeps AI aircraft at Passive Defense and
  switches only the flight a missile is actually guiding on to Evade Fire, so one SAM
  launch no longer sends 200 planes defensive and aborting their mission, only the flight of the targeted plane does.
  ([#63](https://github.com/juanjux/dcs-retribution/pull/63))
  
- **Campaign Doctrine: "non-combat (crash) air losses don't count"** — AI crashes and
  collisions DCS credits to no weapon no longer deplete a squadron or kill the pilot.
  This makes campaigns longer and harder with more planes in the air after some turns.
  ([#1](https://github.com/juanjux/dcs-retribution/pull/1))
  
- **Realistic helicopter range** — carrier-capable transport helos (CH-53E, CH-47D/F,
  SH-60B, UH-60A/L, UH-1H) get their real combat radius instead of the 50 nm helicopter
  default.
  ([#64](https://github.com/juanjux/dcs-retribution/pull/64))
  
- **One-way air assault ("remain at destination")** — a helicopter-only option: the helos
  land at the objective and do not return, so the assault uses their full ferry range. At
  turn end the survivors redeploy there if you capture the base, otherwise they are lost.
  ([#64](https://github.com/juanjux/dcs-retribution/pull/64))
  
- **Ferry flights may return fire.** ([#99](https://github.com/juanjux/dcs-retribution/pull/99))
  
- **Automated ground-object / building repair** — the HQ repairs damaged SAM sites,
  vehicle groups and buildings each turn, with tunable budgets and priorities, and the
  turn panel reports what each side finished and what is still in progress.
  ([#29](https://github.com/juanjux/dcs-retribution/pull/29),
  [#43](https://github.com/juanjux/dcs-retribution/pull/43))
  
- **Set loadout as default** — a named payload can be made the default for an aircraft
  and mission type, so new flights start with it. 
  ([#49](https://github.com/juanjux/dcs-retribution/pull/49),
  [#51](https://github.com/juanjux/dcs-retribution/pull/51))
  
- **A fuel estimate for the plan**, beside the route total and the per-leg distances:
  taxi, the legs at their own climb/cruise/combat rates, the landing reserve and a
  margin, against what the flight carries. Only 24 aircraft have measured consumption
  figures; the rest are estimated from their capacity over a nominal range for their
  kind, leaning high.
  ([#190](https://github.com/juanjux/dcs-retribution/pull/190),
  [#189](https://github.com/juanjux/dcs-retribution/pull/189),
  [#191](https://github.com/juanjux/dcs-retribution/pull/191))
  
- **The debriefing is kept in the save**, so it can be reopened from the Misc bar after
  the session that produced it.
  
- **Money cheat for both coalitions** (OWNFOR + OPFOR).
  ([#3](https://github.com/juanjux/dcs-retribution/pull/3))
  
- **Air Wing cheat** — per-squadron aircraft count with free +/- controls.

### Campaigns
- **Battle for Area 51: both sides get a real IADS.** Red's west, central and east
  groups shared no node and drew as three networks a few miles apart; the comms are
  cross-linked into one and the three power stations feed a single grid, so the network
  survives losing a station and goes dark all at once when the last one falls. Blue had
  nothing but the bunker -- no radar, no comms, no power, so every site of its own went
  autonomous whatever happened -- and gets two early-warning radars, three relay towers
  and two power stations, so it is one working network too.
  ([#221](https://github.com/juanjux/dcs-retribution/pull/221),
  [#225](https://github.com/juanjux/dcs-retribution/pull/225))
- **Syria — Invasion of the Canary Islands 2030, new campaign**, with the **Spain 2030** and
  **Morocco 2030** factions. A rework of NoGoodNews' original: both sides fly what they
  are expected to field by 2030 (so it required the Eurofighter and F35 mods, which this fork also adds support for), and both navies are built from real hulls with pinned compositions. Air defenses are about a third lighter than the original, the IADS is fully wired, and every base on a front has a motor pool holding its undeployed armor as a bombable target and Morocco has been made stronger to better balance the campaign.
  ([#98](https://github.com/juanjux/dcs-retribution/pull/98))
  
- **GPS jamming available in every modern campaign.** 
  ([#183](https://github.com/juanjux/dcs-retribution/pull/183))

### LLM-controlled OPFOR (REST API + MCP)
- **An external LLM (Claude, ChatGPT, etc) can play the enemy commander.** A REST API and an MCP server expose a
  token-frugal turn context (forces, targets, threats, economy, naval, motorpools, runway
  states, plus an optional rendered map image) and full player parity to act on it:
  packages and flights, buying and selling, front-line stances, squadron relocation,
  fleet movement, repairs and rebuilds. The LLM gets its own briefing at `/start` and
  `/howtoplay`. Just copy the local URL from the button to Claude Coword, ChatGPT Codex, Grok build
  or any other LLM that has a local interface, and start playing with it controlling OPFOR.

### Modding & data
- **F-15EX Eagle II, F-15C EG (Golden Eagle) and Eurofighter Typhoon** mod aircraft.
  ([#31](https://github.com/juanjux/dcs-retribution/pull/31),
  [#32](https://github.com/juanjux/dcs-retribution/pull/32),
  [#33](https://github.com/juanjux/dcs-retribution/pull/33))
  
- **High Digit SAMs Ultimate Compilation, as a second selectable build.** The two builds
  cannot both be installed, so the New Game wizard offers them as mutually exclusive
  choices and a faction only sees the presets its chosen build ships. Campaign authors
  have to wire the new sites in themselves.
  (branch [`juanjux/hds_2_1_0_and_ultimate`](https://github.com/juanjux/dcs-retribution/tree/juanjux/hds_2_1_0_and_ultimate),
  upstream [#956](https://github.com/dcs-retribution/dcs-retribution/pull/956))

### Fixes

- **A package with an impossible TOT could hold for the whole mission.** The hold point
  emitted its release timer without a floor, and DCS never fires a trigger scheduled for
  a negative time. Now clamped to mission start.
  ([#100](https://github.com/juanjux/dcs-retribution/pull/100))
  
- **A CAP guarding its own base could vanish the instant the mission started.** DCS runs
  the last waypoint's tasks immediately for an air-started flight whose total route is
  short enough, and for AI that waypoint carries the despawn script. Patrol routes are
  lengthened away from the enemy until they reach 60 nm, so the threat-facing end and the
  station stay put.
  (branch [`juanjux/min-patrol-route`](https://github.com/juanjux/dcs-retribution/tree/juanjux/min-patrol-route))
  
- **Take Off died with "Duplicate convoy unit", stranding the campaign** — the name
  counter reset each turn onto a convoy still in transit.
  ([#93](https://github.com/juanjux/dcs-retribution/pull/93))
  
- **Some building objectives could never be recorded as destroyed.** An objective is
  credited by a `MapObjectIsDead` trigger over its zone, and many of those zones hold
  scenery that cannot be destroyed at all. Deaths are matched to the nearest objective by
  position within 30 m instead, and the triggers are gone.
  ([`b7cbd73`](https://github.com/juanjux/dcs-retribution/commit/b7cbd73df),
  [`afff790`](https://github.com/juanjux/dcs-retribution/commit/afff790e0))
  
- **A Strike put every iron bomb on a single aimpoint.** The dumb-bomb task aimed at the
  objective's centroid and sized its carpet from the mean distance to the targets rather
  than their spread. Heavy bombers now carpet the real extent in one pass; everything
  else re-attacks with one aimpoint per target and the load split between them.
  ([`1209839`](https://github.com/juanjux/dcs-retribution/commit/120983924))
  
- **Scud and ATACMS sites cratered empty fields.** A missile site fired at the enemy
  control point's map coordinate, displaced by up to 2500 m at random. They now aim at
  live, immobile ground objects at the target base, with range measured to the aimpoint,
  minimum ranges respected, and the top 15% of the envelope off limits.
  ([#128](https://github.com/juanjux/dcs-retribution/pull/128))
  
- **Air-assault troops stood still instead of taking the base.** CTLD walked unloaded
  troops to their waypoint and left them there, so one surviving vehicle blocked the
  capture indefinitely. Dropped troops and vehicles now advance and fight on the nearest enemy
  ground unit inside the capture radius. New CTLD plugin option, on by default.
  ([#85](https://github.com/juanjux/dcs-retribution/pull/85))
  
- **Air-assault ingress no longer zig-zags.** The join leg is anchored to the package's
  ingress point rather than the initial point.
  ([#9](https://github.com/juanjux/dcs-retribution/pull/9), upstream
  [#804](https://github.com/dcs-retribution/dcs-retribution/pull/804))
  
- **Front-line ground units never fought** — three stacked causes: defenders held position
  waiting for the enemy's first CAS package, a negative hold duration wrapped to ~24 h,
  and the FLOT took its alarm state from a mislabelled SAM toggle. Defenders engage from
  minute one; the toggle is relabelled and no longer touches the FLOT.
  ([#79](https://github.com/juanjux/dcs-retribution/pull/79))
  
- **Transferring an army mid-turn made it vanish from the ground war.** The ground war was
  planned once at the start of the turn and cached, so anything moved afterwards was
  deployed from a stale plan; and units waiting for a lift that did not exist were debited
  on order rather than on departure. Planning happens at mission generation now, and
  pending units are deployable, defending and counted until they actually leave.
  ([#133](https://github.com/juanjux/dcs-retribution/pull/133))
 
- **The Su-25 was planned to fight from a height it will not shoot from.** No aircraft in
  the fork declared a combat altitude, so both Frogfoots fell back to an estimate from
  their top speed and were tasked above the altitude the AI will attack from.
  ([#135](https://github.com/juanjux/dcs-retribution/pull/135))
  
- **The Su-25 flew DEAD carrying only weapons it cannot guide.** All six attack pylons
  were laser-guided and the plain Frogfoot has no designator, so the loadout was stripped
  and the aircraft flew unarmed. RBK-250 with PTAB-2.5M instead.
  ([#130](https://github.com/juanjux/dcs-retribution/pull/130))
  
- **Su-25s flew close air support with weapons they cannot guide.** The strip that exists
  for this checks `WeaponType.LGB`, and the whole Soviet laser family was typed
  `UNKNOWN`. S-25L, Kh-25ML, Kh-29L and the laser KABs now match; dual GPS/laser weapons
  are left alone, and the Su-25T gains its Klen-PS.
  ([#125](https://github.com/juanjux/dcs-retribution/pull/125))
  
- **The A-6E dropped iron instead of its laser-guided bombs, always.** Its TRAM turret is
  an internal designator and nothing declared it, so the planner swapped every GBU out at
  every date.
  ([`5545351`](https://github.com/juanjux/dcs-retribution/commit/55453512e))
  
- **Stores that no weapon file claimed slipped past their own introduction date.** The
  A-6E's TALD MER clsids, the AN/ALQ-167 and the Hornet's fourth AIM-7P clsid read as
  unknown stores: no weapon type for planning and no year.
  ([`309b39c`](https://github.com/juanjux/dcs-retribution/commit/309b39c24),
  [`06b7955`](https://github.com/juanjux/dcs-retribution/commit/06b7955e1))
  
- **A Patriot battery reported no threat at all.** The AN/MPQ-53 — the original Patriot
  array — was missing from `TRACK_RADARS`, and a launcher only counts when a paired
  tracker is alive.
  ([#126](https://github.com/juanjux/dcs-retribution/pull/126))
  
- **Factions with no early-warning radar fielded a SAM's acquisition radar as one.**
  Ukraine, Georgia, Morocco, France, Argentina, Peru and Iran were putting up a Patriot
  STR or a Hawk SR where a national radar belonged.
  ([#187](https://github.com/juanjux/dcs-retribution/pull/187))

- **A bombed-out motorpool showed on the map as a permanent loss.** It is only a view of
  the base's undeployed armor, so procuring ground units refills it.
  ([`81fb0d4`](https://github.com/juanjux/dcs-retribution/commit/81fb0d4d8))
  
- **Escorts of an AWACS/tanker hold on the protected flight's racetrack** instead of a
  far-away point, so they actually protect it.
  ([#42](https://github.com/juanjux/dcs-retribution/pull/42))
  
- Bumped PySide6/Qt to 6.8.3, which switches acceleration to D3D11 and fixes many OpenGL
  hangs. ([#52](https://github.com/juanjux/dcs-retribution/pull/52))

- Robust payload handling — unparseable payload files are skipped; loadouts are written
  atomically. ([#21](https://github.com/juanjux/dcs-retribution/pull/21))  
 
- Kneeboard waypoint numbering is correct for in-air-start flights.
  ([#14](https://github.com/juanjux/dcs-retribution/pull/14))

## From the 414Ret fork

These are adapted from the [**414Ret** fork](https://github.com/bradyccox/414Ret)
(414th Joint Fighter Group), with thanks to its authors — 414Ret bundles many
more features; listed here are the ones incorporated into this fork, each
crediting the original 414Ret author (the recent additions land via attributed
PRs on `juanjux-dev`, so any can be reverted cleanly). TIC vendors Grendel's
TIC script (MIT).

414Ret moves fast, so its feature list is re-reviewed periodically and only a
part of it is taken: every feature carried here is one more thing to reconcile
on each upstream sync, so the bar is "clearly worth the maintenance", not
"interesting". The last review covered the 1087 commits between 2026-06-23 and
2026-08-22. Ports are cherry-picked with the original author preserved —
`git log --author=bradyccox` is the authoritative list of what has been taken,
and it is longer than this section.

- **Troops In Contact (TIC)** — a dynamic frontline: ground forces actually fight
  along the FLOT (with ambient fire) instead of behaving as two static walls.
- **Mission Impact debrief summary** — bases captured/lost, runway damage and a
  both-sides loss overview above the casualty tables.
- **AI routes around the ground battle** — the active front line becomes a
  navmesh routing hazard, so transit flights detour around it.
- **Frontline units spread along the line** instead of stacking laterally.

- **Escorts can defend themselves before the JOIN point** — an escort was generated at an
  ROE that only permits engaging *designated* targets, and the task that designates them
  attaches at JOIN. Escorts now spawn able to return fire and escalate at JOIN.  
  
- **Coastal batteries can engage ships** — land-based anti-ship sites fire on their own at
  hulls in range, the way fleets do. Off by default (a mod battery firing anti-ship
  missiles has crashed DCS).
  
- **DEAD reachability gate** — the planner no longer marks a SAM "cleared" when the
  assigned flight cannot actually reach it.
  ([#37](https://github.com/juanjux/dcs-retribution/pull/37), porting 414Ret #83)
  
- **Weapons coverage refresh** — more modern PGMs and air-to-air missiles across
  factions, without the era date-gating (our introduction years are kept).
  ([#35](https://github.com/juanjux/dcs-retribution/pull/35), porting 414Ret #82) 
  
- **Two guidance radars per SAM site** — every layout fielded exactly one engagement
  radar, so a single anti-radiation missile was a functional site kill. The Track Radar
  slot doubles across the generic layouts, SA-2, SA-3, SA-5, S-300, HQ-22, S-350, the
  mixed SA-2/SA-3 site, the reinforced SA-6, NASAMS-3 and Sky Sabre, with the second
  position 45-121 m from the first. (porting 414Ret #582)
  
- **More SAM site layouts, tighter EWR radar pool** — dedicated battery layouts
  instead of every site reusing the same handful of shapes.
  
- **Bulk flight altitude** — "apply to all" for en-route waypoint altitude, and the
  per-waypoint arrows step 1000 ft instead of 1 ft. (porting 414Ret #805)

- **Ship groups generate as task groups** — a group was N copies of one hull, so a carrier
  screen was four identical destroyers. A slot now takes one type per position, drawn from
  the lead's own class family and capped at three types. Naval layouts only; the buy menu
  still gives exactly the hull that was picked.
  ([#104](https://github.com/juanjux/dcs-retribution/pull/104), porting 414Ret #764)
  
- **Every generated mission is archived** to
  `Missions/Retribution Archive/<campaign>_turn<NN>_<timestamp>.miz`, self-pruning, with
  the fixed output path unchanged. Each turn used to overwrite the mission just flown.
  ([#103](https://github.com/juanjux/dcs-retribution/pull/103), porting 414Ret #615)
  
- **GPS jamming** — a JDAM, JSOW, JASSM or SLAM-ER released against a target inside an
  enemy jamming bubble lands off the aimpoint, further off the deeper in. Laser, TV and
  anti-radiation weapons are unaffected, and killing the jammer restores accuracy on the
  next weapon in the same mission. The jammer is an ordinary bombable ground unit and is
  not a SEAD target. Off by default.
  ([#109](https://github.com/juanjux/dcs-retribution/pull/109), porting 414Ret #778)
  
- **Finite anti-ship magazines, and a staggered weapons release** — a warship group
  carries a campaign stock of anti-ship missiles that never rearms, and a group that runs
  dry drops to return-fire. Optionally, ships spawn on return-fire and are released to
  weapons-free one group at a time. Both off by default.
  ([#106](https://github.com/juanjux/dcs-retribution/pull/106), porting 414Ret #766)
  
- **The AI buys its better ground units more often** — the ground buy rolled uniformly
  over everything affordable of the right class. The roll is weighted by price; a
  weighting, not a maximum, so the cheap end still appears.
  ([#105](https://github.com/juanjux/dcs-retribution/pull/105), porting the
  capability-weighted half of 414Ret #68)

## Removed from upstream

- **Fast forward.** It never worked well enough to be worth the machinery. Take Off hands
  DCS the mission at the time it was planned for.  
  ([#176](https://github.com/juanjux/dcs-retribution/pull/176))
  
- **Four obsolete or duplicated plugins removed.** EWRS is the 2016 script BigEye EWR was rewritten from; Mbot's Call
  Artillery only ever answered a player flying Armed Recon, while Carsten's answers
  anyone in range; the C-130 cargo script is for a mod their authors don't support anymore; and the EW
  Jammer script cannot model jamming honestly without engine support.
  ([#175](https://github.com/juanjux/dcs-retribution/pull/175))
  
- **DCS: Pretense support.** A one-way export into a second, parallel game that never
  comes back to the Retribution campaign — ~5,400 lines of Python plus 590 KB of
  third-party Lua, carried through every upstream sync, for a project that is no longer
  maintained on either side. Gone with it: `game/pretense/`, the plugin resources, the
  toolbar actions, the settings page, `FlightType.PRETENSE_CARGO` and the four `*_full`
  campaigns tuned for it.

## Queued

Planned, not started. Enough detail here to pick each one up cold.

- **[from 414Ret] Strikes timed behind their SEAD.** Packages are scheduled independently
  today, so nothing stops a strike entering a threat ring before the SEAD servicing it.

## Halted for Now

Work that was built and soak-tested but **parked** — pulled out of `master` and
`juanjux-dev` to keep them clean, with every branch preserved here so it can be
revived later.

### Mission chronicle

An account of the mission in prose, from a button in the debriefing and as a `.md` beside
the archived `.miz`. Parked after reading one: with fixed templates it comes out
repetitive, and the Mission Log already tells you everything it does. The code has been
taken back out; the event recording it fed on still lands in `state.json`, so reviving it
means writing a better renderer against that timeline.
([#121](https://github.com/juanjux/dcs-retribution/pull/121))

### SYNTAX weapon mods (AARGM-ER, LRASM, JASSM-ER)

Optional-mod toggles in the New Game wizard that swapped a stock weapon for a
SYNTAX one: the AGM-88G AARGM-ER in place of the HARM in SEAD loadouts
([#65](https://github.com/juanjux/dcs-retribution/pull/65)), the AGM-158C LRASM
in place of the Harpoon ([#66](https://github.com/juanjux/dcs-retribution/pull/66)),
and the AGM-158B JASSM-ER in place of the JSOW-A
([#67](https://github.com/juanjux/dcs-retribution/pull/67)).
**Parked because the mods are not reliable enough** to build campaign balance on.
Removed from `master` and `juanjux-dev`; the branches are preserved.

### Electronic Warfare (EWAR "Jamming")

A dedicated **EWAR / "Jamming" flight task** for EW aircraft (EA-18G, EA-6B, Su-34, Mi-8,
plus emulated EC-130 Compass Call / Su-24MP / Tornado ECR variants), built on upstream's
`ewrj` jammer plugin: offensive radar suppression, a defensive missile-deletion bubble,
engine ECM, naval point-defense handling and a launcher-jam missile kill.

**Why halted:** a reliable EWAR is not possible without proper support from the DCS
engine. The available levers (scripted ROE, missile deletion, engine ECM) do not scale
consistently — a few jammers saturate a fleet's radar into total silence. Parked until
DCS exposes real EW hooks.
---

For installation and general usage, see the upstream
[DCS Retribution](https://github.com/dcs-retribution/dcs-retribution) documentation.
