# Escalation v1.6.3 (414th)

## Features/Improvements
* **[FIX]** The rename asked for the first-start configuration again: the file holding your DCS paths, theme and server port was renamed with everything else.
* **[Escalation]** The fork is called **DCS Escalation** now. Your campaigns, factions, layouts and payloads are untouched: they stay in `Saved Games\DCS\Retribution` and saves keep the `.retribution` extension, so nothing has to be moved.
* **[FIX]** Opening a package from the ATO list raised "'Package' object has no attribute 'id'".
* **[FIX]** Choosing a pilot in the command palette did nothing for anyone who was wounded, on leave or gone.
* **[FIX]** Choosing a plugin option in the command palette opened the settings window on its first page for many of them, Skynet's among them.
* **[UI]** The command palette zooms the map in on what was chosen rather than only centring on it.
* **[FIX]** Opening the same package, flight, squadron, pilot or the Air Wing twice opened a second window of it instead of raising the one already up.
* **[OPFOR-AI]** The external planner can read a pilot's whole record: `GET /squadrons/{id}/pilots/{name}/record` (MCP `pilot_record`), and the roster carries his kills and what he has survived as counts.
* **[FIX]** A black console window flashed over the game whenever the live weather was fetched.
* **[FIX]** The command palette found no pilot who was not fit to fly this minute: the wounded, the men on leave and the deserters were not indexed at all.
* **[FIX]** Choosing a setting in the command palette opened the settings window on its first page instead of the setting's own.
* **[UI]** Choosing a base or an objective in the command palette puts the map on it.
* **[Live Pilots]** Double-clicking a pilot on a squadron's roster opens his own dialog: his combat record, what he has survived, how he died, his morale and hardening with the log behind them, and his relationships -- warm and cold -- in both directions.
* **[FIX]** Opening the command palette took the menu row -- the menus and the toolbar icons -- off the main window for good, and Ctrl+P with it.
* **[UI]** The command palette opens a pilot's own dialog instead of his squadron's.
* **[Live Pilots]** Optional pilot cheats (Settings, Cheats page): rename, set rank, heal and revive.
* **[Live Pilots]** A pilot's kills are kept individually as well as counted -- what, when and with what -- and his ground kills are grouped by class.
* **[UI]** Command palette: Ctrl+P finds settings, bases, objectives, squadrons, pilots, flights and every command in the menus, and opens what is chosen.
* **[FIX]** A pilot who had drifted one step away from a squadron mate was shown as going cold, while one who had drifted a step closer was shown as nothing: the Neutral band was not centred on the value every pair starts at.
* **[Live Pilots]** A pilot's record now keeps what he has shot down and destroyed by type, the missions he came home from, the aircraft he has lost and walked away from, his wounds, and who finally got him.
* **[FIX]** Inserting a waypoint where the flight plan had no room for one drew a detour back the way the flight came instead of saying so.
* **[FIX]** Base menu: ordering a ground unit took seconds and the window resized itself on opening.
* **[UI]** A flight plan is no longer drawn through its target: the target waypoints are marked in red, a dashed red run joins the ingress to each of them, the route carries on to the next navigation point, and every leg is labelled with its length in nautical miles. Double-clicking a target opens the objective.
* **[UI]** Base menu: the buy lists sort by any column and their headings line up with the figures, a squadron opens from anywhere on its row, a base states what it has no ammunition or factory rather than going quiet, a FARP counts its helipads instead of claiming a runway, and the ammunition and factory pills explain what they do.
* **[UI]** A flight plan is no longer drawn through its target: the target waypoints are marked in red and the route runs from the ingress to the next navigation point.
* **[UI]** An enemy base reports its air defences -- how many sites and of what kind -- alongside its aircraft and ground units, its known units are grouped by class, and a convoy leaving this turn is shown on the intel tab as well as its own.
* **[UI]** Buying ground units: the catalogue is grouped by class with a filter row and an "Owned" view, the front-line stance names the enemy it is about and shows the unit balance, and a card lists what is deployed at the base.
* **[UI]** Buying aircraft: each squadron's row carries its silhouette, task and name, with what is present, its cap, what is on order and what is idle as figures, and a row pinned above the list says what the order leaves you with.
* **[UI]** Delete removes the selected waypoints in the flight's waypoint tab.
* **[UI]** The base menu states what the base is, who holds it and whether its runway, depots and factory work, turns the aircraft, ground units and budget into figures, names its tabs with their counts, gives the flights planned from the base a tab of its own, and can be resized.
* **[UI]** Waypoints can be edited from the map: double-click opens one, right-click offers rename, delete and insert, Delete removes the selected one, and alt-clicking a leg draws a nav point into it.
* **[FIX]** Closing the flight editor stopped asking whether the ingress point should move after a payload change, or whether to send a tanker.
* **[UI]** The flight plan you have selected is drawn whether or not its side's flight plans are switched on in Map Layers.
* **[FIX]** One of a strike's several target points could never be deleted: the rule meant to allow it asked the wrong object and never fired.
* **[Plugins]** How far a comms tower and a power station reach are Skynet options now (15 and 35 nm, as before) instead of constants in the source.
* **[UI]** A repair message names what was repaired -- "PYTHON (Factory)" -- instead of the code name alone.
* **[FIX]** An objective added to a campaign already under way -- a migrated motorpool, for one -- could not be opened from the map.
* **[FIX]** A player shot down with "invulnerable player pilots" on was paid the mission-complete experience as though he had landed.
* **[FIX]** Closing a package dialog left every flight editor in the session unopenable, with "Internal C++ object (QEditFlightDialog) already deleted".
* **[FIX]** The loadout lists opened without their search field below twelve presets, and the searchable popup dropped the pylon tooltip.
* **[UI]** Filling a flight gives the lead seat to the squadron's senior available pilot, and the seats after it to whoever that crew gets on with best.
* **[FIX]** A GPS jamming site cut off from the IADS was painted and reported as autonomous, which means nothing for a jammer: it is cued by nobody and jams for as long as its trucks are alive.
* **[FIX]** A command centre whose comms were cut reported itself as directing the network, while every SAM under it reported having no command centre.
* **[Campaigns]** Battle for Area 51: red's IADS is one network instead of three with its three power stations feeding a single grid, and blue gets the radars, comms towers and power stations it never had.
* **[Mission Generator]** An Escort or SEAD Escort with an "ahead" TOT offset now reaches the target ahead of its package.
* **[FIX]** A patrol in a package (TARCAP, BARCAP, tanker) could be given a takeoff before the mission started, because its station time comes from the package's escort window rather than from the package TOT. The earliest package TOT is now measured against every flight's own takeoff, not just estimated.
* **[UI]** Every flight in a package shows its own timeline -- departure, the waypoint where it starts working (ingress, sweep start or orbit start), and landing -- so TOT offsets can be lined up without opening each flight.
* **[FIX]** The OPFOR API hid partial repairs: a site's repair countdown stopped being reported the moment one of its units was standing, so a battery that was firing today and getting three launchers back next turn looked like a battery at full strength. It reports the countdown either way now, with the live and repairing unit counts, and `/iads` carries the same countdown per node.
* **[FIX]** Planning an escort into a package that holds nothing but escorts crashed instead of creating the flight: the escort was its own package's primary flight, so it escorted itself. It now flies the package's ordinary geometry, and a flight plan that asks for itself raises a planning error naming both flights rather than overflowing the stack.
* **[UI]** Air Wing Configuration papercuts: one squadron card stays open per aircraft type rather than per dialog, the disclosure arrow is big enough to see and turns blue when open, labels no longer paint their own background over the cheat header, and closing the window asks whether to keep the changes instead of whether to discard them.
* **[UI]** The Air Wing Configuration dialog was redrawn: three panes (types, squadrons, bases) instead of a form, so parking is on screen instead of hidden at the bottom of a group box; squadrons are collapsible cards; the twenty-row task grid is chips grouped by family, showing only what the aircraft can fly; and the header says whether you are composing a new air wing or cheating into a running campaign.
* **[Mission Generator]** A battery that deploys with its own generator (Patriot EPP, SAMP/T MGE) no longer goes dark when the nearest substation is bombed; killing the generator itself puts it back on the grid.
* **[UI]** A SAM cut off from its network paints its health bar violet, and one with no power paints it grey and draws no range rings at all, with the reason in the tooltip. A battery running on its own generator says so and names the vehicle.
* **[UI]** A waypoint you can give up — one you added, a refuelling stop, the join of a flight that is the whole package — can be deleted on an AI flight again; only *adding* is still reserved for all-player flights.
* **[UI]** Pilots can be selected several at a time, for Discharge and for Send on leave.
* **[UI]** The map has a search box: find a place by its code name, by what is parked there ("Patriot", "Linebacker") or by what kind of thing it is, with filters by side and by kind.
* **[UI]** Delete cancels the selected flight inside a package, the same key that already cancels a package.
* **[UI]** The loadout list in the flight creator can be searched, like the one on the payload tab.
* **[Campaign AI]** The OPFOR API reports which sites are autonomous or dark and why, on targets, threats and /iads.
* **[FIX]** A destroyed site was dropped from the IADS network, so its links vanished from the map instead of drawing broken -- and losing your last command centre handed command back.
* **[UI]** The only flight in a package has NAV where a formation would have JOIN and SPLIT; a second flight in the package brings them back.
* **[FIX]** A destroyed site left the IADS network in saves written before this, taking its links off the map for good; the network is rebuilt once on load to put them back.
* **[UI]** The squadron dialog reads the roster as figures — max, current, on leave, wounded, broken, available — in the same shape as the aircraft inventory, and the Pilots header says how full the squadron is.
* **[UI]** A squadron can carry its own *Max pilots*, beside *Max size*, instead of every squadron following the campaign-wide limit; it follows the setting until you move it.
* **[FIX]** A plugin option that takes a word drew its label and no control at all, so the Mission Log's good- and bad-news words could be read and not changed.
* **[FIX]** Skynet switched an element's radar back on the moment it lost its comms node, power station or no power station: going autonomous means it lost its network, not that it grew a generator. Bombing the comms of an unpowered site was worse than bombing nothing.
* **[FIX]** The squadron dialog and the Air Wing row counted pilots who refuse to fly as available, so a squadron with nobody to send read as fully manned.
* **[Plugins]** Mission Log: a kill and a loss of ours get a word in front — YEAH! and OH NO! by default, both settings, empty for none.
* **[Plugins]** Mission Log: *monitoring* is off by default, a ground kill carries the same "enemy" prefix an aircraft already had, and SHOT DOWN / CRASHED / EJECTED / DESTROYED are shouted so a kill does not read like a takeoff.
* **[UI]** The Edit Flight dialog was redrawn: a header naming the aircraft, squadron, package and target with an attention stack for an empty seat or a fuel shortfall, cards instead of stacked group boxes, a button per seat labelled with the pilot's name, a pilot selector painted like the Air Wing roster, consecutive target waypoints folded into one row that opens on a click, a colour dot per waypoint type, a fuel bar against what the aircraft carries, and a footer with Done and *Go to package*.
* **[UI]** The flight editor is no longer modal and follows the flight you pick: a selector in its header lists the package's other flights, and clicking one in the main window's Flights list switches the open editor to it.
* **[UI]** Long combo lists — payload presets, liveries, predefined waypoints and every pylon's own store list, which runs to seventy-five stores on a Hornet — open with a search field; below a dozen items they keep the ordinary popup.
* **[UI]** Adding waypoints by hand is greyed out for a flight with an AI seat in it and says how many; JTAC laser codes are only offered when the campaign is generating JTACs.
* **[Campaign AI]** The flight editor asks again on the way out when an edit has left the flight short of fuel, or given it fuel to spare, offering *Add waypoint and tanker* or *Add waypoint only* — with the first greyed out and the reason on screen when there is nothing to send. Saying yes does not rebuild the plan.
* **[FIX]** A tanker planned for a package held for five minutes plus four a head and reached station ninety seconds before an arrival time that is itself an estimate. It now holds for the campaign's tanker on-station time and is there ten minutes early.
* **[FIX]** Planning a tanker into a defensive package asserted: it has no split point to lay the track along or to time the receiver from.
* **[FIX]** A flight given a TOT offset **ahead** of its package arrived *behind* it instead. The package now leaves room for the flights that have to arrive first.
* **[FIX]** The tanker the auto-planner proposed for Strike, OCA and DEAD packages was pruned every time, so the three settings that asked for it did nothing.
* **[Campaign AI]** One *Plan a tanker and a refuelling waypoint when a package needs the fuel* option replaces the three per-task ones, and the refuelling waypoint is only added to a flight the fuel estimate says cannot make the plan.
* **[FIX]** The METAR refresh button drew a text glyph that fell back to the wrong font; it uses the reload icon now, on a slightly larger button.
* **[UI]** The Repository, Issues and Releases links and the About box point at this fork; the manual and forum thread still point upstream, where that documentation actually is.
* **[Plugins]** Mission Log: fighters watching a contact without committing have their own switch, apart from those moving to intercept.
* **[Plugins]** Mission Log: enemy pilots, aircraft, flights and missiles are named as enemy, so a campaign where both sides fly the same airframes still says who shot whom.
* **[FIX]** The fuel figure did not move when a drop tank was added or removed.
* **[FIX]** The fuel estimate ignored the altitude flown, and charged the join and split legs at the combat rate.
* **[FIX]** Take Off crashed on any flight with a racetrack, reading an option of the removed EW jamming plugin.
* **[Campaign AI]** Morale can go below zero, down to -30, so being *Broken* lasts more than the one turn a quiet turn's drift used to undo.
* **[Settings]** How far morale settles back towards Normal each turn is a Morale Event Value now, and several event sizes were re-weighed.
* **[FIX]** *Apply to all* moved nothing on a helicopter's flight plan and little on a low-level one.
* **[UI]** A pilot's morale shows as a face after his name where the word does not fit, above all in the pilot selector for a flight.
* **[FIX]** The pilot selector elided the rank and the name, in the box and in the list, and widening the dialog did not help.
* **[UI]** *Internal Fuel Quantity* is *Fuel Quantity*, and says what the external tanks add.
* **[FIX]** Mission Log read every missile in the air as a helicopter: a Patriot firing at an AGM-84 came out as the AGM-84 defending itself, and downing one counted as an air-to-air kill.
* **[UI]** The waypoints tab estimates the fuel the plan needs, against what the flight is carrying.
* **[FIX]** The fuel estimate charged a large aircraft a fighter's rate per mile, so a B-1B's 195,000 lb came out at 433 lb a mile and a 306 nm route asked for more fuel than the aircraft holds. The warning also says how short it is rather than always reading *tight*.
* **[UI]** The waypoint table shows each leg's distance and the route total.
* **[Mission Generator]** New *Use JTAC if the faction has one defined* option under Gameplay, beside *Number of JTAC controllers*, so the JTAC aircraft can be switched off mid-campaign instead of only in the new-game wizard.
* **[UI]** Qt updated to 6.11.2.
* **[UI]** Every task has its own chip colour in the package and Air Wing lists; CAS, Strike, DEAD and Armed Recon all painted the same brown.
* **[UI]** Back to the native Windows file, colour and font dialogs.
* **[Plugins]** GeneraLLM can rest a pilot who never asked for leave, or call one back early, the way the Air Wing button does; the leave endpoints are listed in `capabilities` now.
* **[FIX]** Nine factions had no early-warning radar, so their EWR markers fielded a SAM's acquisition radar instead.
* **[FIX]** GeneraLLM: a package spec the API rejected stayed in the ATO with its crews tasked, so retrying it answered *already tasked*. A TOT before the mission starts also read as inside the mission window.
* **[Settings]** GPS jamming, cruise missile strikes and naval magazines are switched on by their plugin alone, and their options live with it.
* **[Settings]** The Skynet IADS radius moved to the Skynet plugin's options.
* **[FIX]** GeneraLLM: the debrief docs had `*_sites_lost` inverted, saying a side's entry was what it killed rather than what it lost.
* **[FIX]** A GPS jamming site drew its point defence on the map, a couple of miles, instead of its jamming bubble.
* **[FIX]** GPS jamming is switched on by its plugin alone; the duplicate setting in Mission Generator is gone.
* **[UI]** The jammer is called *GPS Jammer* and its map icon reads GPS.
* **[Campaign]** New *Ignore parking space at airbases* option.
* **[UI]** Radar sites, missile batteries and jamming sites are interchangeable: buy any of the three where one stands, and the icon follows what is parked there.
* **[Map]** A site that only watches draws its detection range dashed, in its faction's colour.
* **[FIX]** A site pinned by a campaign generated without its point defence.
* **[Factions]** WRL Task Force Blue gets an AN/FPS-117, so its EWR markers stop fielding Patriot search radars.
* **[FIX]** A campaign's `ground_forces` pin was ignored on EWR markers, so GPS jamming sites never generated.
* **[Campaigns]** Every modern campaign gets a GPS jamming site on its enemy's EWR belt.
* **[FIX]** IADS configs named 39 buildings their missions never had, and hung command centres off sites, which does nothing.
* **[UI]** Added a search box to the settings dialog. It covers the plugins' options too.
* **[FIX]** Boxes inside a settings section had no frame, and short sections showed a scrollbar they did not need.
* **[UI]** New *Mission Start* and *AI* sections in Mission Generator, split out of *Gameplay*.
* **[FIX]** Settings pages opened at the previous page's scroll position, and a setting could not grey out one on another page.
* **[Plugins]** Moose's MarkerOps follows the other Moose plugins instead of having a switch of its own.
* **[FIX]** Escalation would not start after the fast-forward removal.
* **[Plugins]** Splash Damage updated to 3.4.7, which fixes the Walleye crash, and 65 of its options are offered instead of 33.
* **[FIX]** Three Splash Damage options had never done anything: the parked-aircraft boost, the ship-radar kill and the cluster bomblet reduction.
* **[Sim]** Removed fast forward and its two settings. Take Off hands DCS the mission at the time it was planned for.
* **[Plugins]** Dropped EWRS, Mbot's Call Artillery, the C-130 cargo script and the EW Jammer script.
* **[Plugins]** Skynet is listed as *Skynet IADS (juanjux's fork)*, and Splash Damage, MarkerOps and Troops In Contact have descriptions.
* **[UI]** The settings window opens wide enough that no page needs a horizontal scrollbar, and its section index no longer scrolls away with the settings.
* **[FIX]** Turning Live Pilots off and back on left several of its settings greyed out for good.
* **[Live Pilots]** *Rank Names* is now *Ranks*, and each rung's price in XP is set there beside its name.
* **[UI]** *Automate building repairs* carries its tuning behind a gear and owns the repair budget.
* **[FIX]** Player pilots no longer play the morale game.
* **[UI]** Settings pages no longer spread their rows over the height of the window.
* **[UI]** *Automate ground object repairs* carries its tuning behind a gear; the *Ground Object Repairs* page is gone and *Building Repairs* moved under *HQ Automation*.
* **[Live Pilots]** The morale bands are settings now, and a pilot's rank shift follows them instead of two numbers of its own.
* **[UI]** The Air Wing squadron list was redesigned: the aircraft type is now the one large, bold thing on a fixed rail so you can scan for an airframe, the primary task shows as a colour-coded chip, and the list gained a live filter, a sort order, grouping by aircraft type or base, and a running count.
* **[UI]** The unit transfer dialog gets "All >>" and "None <<" buttons, so a whole garrison no longer has to be queued one unit type at a time.
* **[FIX]** A CAP guarding its own base could be given a patrol route so short that DCS deleted the flight the moment it spawned, without it flying a metre. Patrol routes are now lengthened away from the enemy until they are long enough to be flown.
* **[FIX]** Every orbit in a package ended at the same time, whichever flight's time was generated first, so an AWACS or a tanker packaged with a shorter-lived BARCAP left station early — up to two hours in one case.
* **[FIX]** A payload with an empty pylon was thrown away whole and the aircraft was planned carrying nothing at all: the Tornado IDS strike fit leaves four stations free, so a Tornado sent on a strike flew with no bombs.
* **[Mission Generation]** Turn times now come from the theater's latitude and the campaign date instead of one fixed window per map.
* **[FIX]** Some building objectives would never be recorded as destroyed. An objective was only credited once every map object inside its trigger zone was dead, and many of those zones hold scenery that cannot be destroyed at all, so those objectives read as intact however often you flattened them, while others scored normally. Objectives standing on scenery with no damage model, such as the moored submarines on Kola, are now credited on a direct hit.
* **[OPFOR AI]** A ground object being rebuilt now reports `rebuild: {force_group, turns_remaining}` instead of reading as destroyed, so an external planner sees the works on the map the same way the player does.
* **[FIX]** Faction edits from the Air Wing dialog now take effect in the running campaign.
* **[FIX]** The faction editor's tick boxes never removed anything; entries have a remove button now, which refuses a unit the campaign still has deployed, and its lists are sorted by the name you read.
* **[Mission Generation]** New option "GPS jamming" (off by default): a JDAM, JSOW, JASSM or SLAM-ER released against a target inside an enemy jamming bubble flies its normal profile and lands off the aimpoint, further off the deeper in. Laser, TV and anti-radiation weapons are unaffected, and killing the jammer restores accuracy on the next weapon in the same mission. A jammer is an ordinary bombable ground unit -- any type whose data file carries a `gps_jamming` block, shipped on DCS's own GPS spoofer vehicles (adapted from the 414Ret fork).
* **[OPFOR AI]**  now breaks air losses down by type: what died by airframe, what did the killing by weapon alone, and which airframe killed which. All aggregates keyed by type, so they cost the same few hundred tokens whatever happened in the mission.
* **[Campaign]** New campaign "Marianas - Second Island Chain (2027)": a Taiwan crisis gone kinetic, with Guam cratered and Rota, Tinian and Saipan taken. A modern PLA air-defence belt, three PLAN carrier groups, and no ground front -- the islands are not connected, so they change hands by air assault and paradrop. Brings the China 2027 faction with it (adapted from the 414Ret fork).
* **[Mission Generation]** Ship groups generate as mixed task groups instead of N copies of one hull: a carrier screen fields destroyers, frigates and a cruiser where the faction has them, capped at three types, and a patrol boat never turns up in a cruiser slot. Naval layouts only; the buy menu still gives exactly the hull you picked, and a navy with one hull of the class is unchanged (adapted from the 414Ret fork).
* **[Mission Generation]** **Ship groups are task groups now, not four copies of one hull.** Every naval objective generated as N identical ships — four Arleigh Burkes ringing the carrier, two identical corvettes as a "naval group" — no matter how many classes the navy actually fielded, because a group picked **one** ship type and stamped it into every position. A group now gets a **type per position**: a US carrier screen comes out as Burkes with a Perry and a Ticonderoga, a PLAN group mixes Type 052B/052C/054A. The mix stays sensible rather than random — extra hulls are only drawn from the lead ship's own family (frigates, destroyers and cruisers screen together; **a patrol boat never joins a cruiser's screen, submarines pair with submarines, and a carrier is never doubled up**), and no group fields more than three classes, so you get a task group and not one of everything. A navy that genuinely only fields one hull of a class still generates the same coherent group it always did. The **carrier and LHA screens** were also opened up to every surface combatant (they were declared destroyers-only, which both forced the uniform look and locked the layout out of frigate-only navies), with the "frigate escort" variants kept as a deliberate lighter screen. Buying a group from a base's menu is unchanged — you still get exactly the hull you picked — and SAM sites, EWRs and armor groups are untouched. NEW game required (composition is decided when the campaign is generated).
* **[Mission Generation]** **The CJS Super Hornets get a data cartridge too.** Every player **F/A-18E, F/A-18F and EA-18G** now spawns with the mission already in the jet — comm presets named to match your kneeboard, the route with push times and ETAs, and the boat's TACAN/ICLS/ACLS pre-tuned — the same auto-loading cartridge the stock Hornet and Viper have had, because the mod ships its own cartridge support. One deliberate difference: these jets get **no SA picture** — no FLOT, no friendly CAP/tanker racetracks and no enemy threat rings — because the mod's cartridge format has nowhere to put one, so those sections are skipped rather than written somewhere the jet can't read them (the DTC tab's three SA switches simply do nothing on these airframes, and a flight with *only* those ticked gets no cartridge instead of an empty one). The Super Hornet tanker variants get none — the mod ships no cartridge support for them.
* **[Plugins]** **Fixed the BigEye EWR sensor toggles doing nothing.** The BigEye EWR plugin's *BLUE/RED has datalink / RWR / IRST* options were wired to the config but never reached the radar-picture engine — the picture was always built from visual + radar only, so ticking "BLUE has datalink" (or RWR, or IRST) changed nothing for either coalition. The plugin now applies those sensor choices when the mission loads, so a datalink-equipped coalition gets the fuller, networked picture the option promises. Only affects the (default-off) BigEye EWR plugin.
* **[Mission Generation]** **Your front-line JTAC is back.** Escalation's standard JTAC — a FAC orbiting the front line, lasing for your CAS runs — had been replaced fork-wide by a drone that flies inside your air-to-ground packages. That drone was built for the COIN campaigns, where it genuinely is the better model (Enduring Resolve has no front line at all, and Inherent Resolve's war is fought at the strongholds and in Mosul rather than along its one Highway-1 front, so a FAC orbiting the FLOT would circle empty ground for the entire campaign) — but it shipped everywhere, so every ordinary campaign lost the JTAC it should have had. The front-line JTAC is now restored and is **the default again for every campaign**, and the packaged drone is opt-in per campaign via the new `COIN packaged drone JTAC` setting (**Campaign Management → Insurgency**, default **off**, needs COIN replenishment on). The two are mutually exclusive by design — running both would double-laze the same targets and list two JTACs on your kneeboard. The two COIN campaigns turn it on for you; nothing else does. Related: the drone squadron that used to be **auto-added to every modern campaign's air wing** (`Auto-field a JTAC drone squadron`, which has moved to the same Insurgency section) now only appears on campaigns actually flying the COIN drone JTAC, so a campaign you didn't expect to have a Reaper no longer quietly gains one. NEW game required.
* **[UI]** **Fixed SAM sites that drew a threat ring with nothing at the centre.** If you ever unticked **Air defences** in the map layers panel, every air-defense site lost its map icon — *and* so did its "suspected activity" circle — while **Enemy SAM threat range** kept drawing the rings, because those are separate layers. The result looked like broken fog of war: a ring around empty ground that you could only identify by hovering it (on one save, 54 sites and 25 suspected-activity circles were invisible this way). Reveal fog of war itself was working correctly the whole time. The **LORAD / MERAD / SHORAD / AAA** rows are now **filters of the "Air defences" master** rather than four more layers: switch the master off and the four rows **grey out** so it's clear where the icons went; switch it on with none ticked and you get every class; tick some and you get only those. This also fixes air-defense sites drawing **two stacked icons** (and two tooltips) when the master and a class row were both ticked. If the panel was your problem, tick **Air defences** once — the choice is remembered in the campaign save.
* **[Campaigns]** **Three authored factories that never existed are back.** The campaign loader read factory markers from only one authoring block (and SAM/ship/missile markers from only the other — the same class of bug fixed for markers earlier this cycle), so a factory placed in the "wrong" block silently never generated: **The Tblisi Gap**, **Retake the Falklands**, and **Operation Allied Sword** each shipped one such factory, now restored as a real strike target at the enemy base it was authored beside. The rule is now total — every object class loads from **either** authoring block, so campaign authors no longer have to memorize which block each marker type demands. NEW game required to see the restored factories.
* **[UI]** **Set a loadout once and every future flight of that aircraft and task gets it.** Build the fit you want in *Edit flight → Payload* and hit the new **Set as default for &lt;task&gt;** — from then on every F-4E planned as CAS (or whatever airframe and task you're looking at) is generated carrying it, and **Clear default** hands the slot back to Escalation's built-in fit. This was always technically possible — a payload saved under the exact name the planner looks up would override the shipped one — but nothing told you that, and the Save Payload box pre-fills a name (`Custom CAS`) that the planner *never* reads, so the obvious action produced a preset that did nothing. The scope is spelled out before you commit, because it is wide: it applies to **both sides**, in **every campaign**, until you clear it, and only to **newly planned** flights. Your own hand-made Mission Editor payloads in the same file are never touched, and the file is backed up before the first change. The same panel already remembered your fuel and cockpit settings per airframe.
* **[UI]** The **Payload tab** got a cleanup pass. The laser-code rows now **disappear when the loadout has no use for a code** — a Phantom carrying Snakeyes and Rockeyes is no longer shown an "Assigned TGP laser code" row, while the stock Pave Spike + GBU-12 fit still gets one. With *Use custom loadout* ticked, the Loadout box now says **(customised)** instead of silently reading like the stock preset is loaded. The **fuel figure in the spinner and the fuel-plan line below it finally agree** (they could differ by a pound or two). Long store names that get cut off show the full name **on hover**. Saving over an existing payload name **replaces** it in the dropdown instead of adding a duplicate. Stepping through flight members can no longer overwrite a member's custom loadout. And the Edit Flight window **names the flight in its title bar**, so a stack of them is navigable. Also fixed: the weapon laser-code dropdown was meant to be disabled for AI but never actually was, and wrongly claimed "AI does not use laser codes" — AI *does* need a weapon code to drop LGBs on a JTAC's designation, so the dropdown stays available and the false label is gone.
* **[Campaigns]** **The S-3 Viking stops flying the A-6's missions.** The Viking's mission weights out-ranked the A-6E Intruder on *every* land-attack task (BAI 690 vs 675, Strike 480 vs 440, OCA 510 vs 480), so any carrier air wing that fielded both sent the **anti-submarine aircraft** on the **bomber's** strike missions while the Intruder sat on deck. The S-3B is now **sea control only** — it flies **Anti-ship** and nothing else, and it now out-ranks every carrier fast jet for that role, so a Harpoon shot draws the dedicated platform instead of a Hornet. Strike work went back to the **A-6E Intruder**, and carrier tanking to the **A-6E buddy tanker** (the KA-6D store), across 23 factions and 39 campaigns; carrier decks keep a small 4-6 aircraft Viking anti-ship detachment. Also fixes two silent bugs this turned up: Grabthar's Hammer had **16 Vikings assigned to DEAD**, a mission the airframe cannot fly (a squadron whose aircraft can't do its job never flies at all), and five modern factions' only carrier tanker was the **mod-gated** Super Hornet tanker — with the mod off they had no carrier gas whatsoever. NEW game required.
* **[Kneeboards]** **Recon kneeboard pages are ~6x smaller — and so is every mission.** The target-recon pages draw satellite imagery, but were being saved as PNG — a lossless format meant for text and line art — at ~1.2 MB per page. With recon pages switched on they were **~90% of the entire mission file**: 16.5 MB of a fully-crewed 22 MB event mission, re-downloaded by every pilot and re-loaded by the server every single turn. They are now saved as JPEG, the same format DCS's own campaigns use for their imagery pages (a scan of 2,945 shipped missions found 7,971 JPEG kneeboard pages to 2,542 PNG). A fully-crewed mission drops from **22.4 MB to 9.0 MB — 60% smaller, with nothing removed** and no visible difference on the page. Text pages are untouched (PNG is the right format there). Only affects campaigns running "Generate target recon kneeboard pages".
* **[Mission Generation]** **Every generated mission is now archived**, so the one you flew is still there next week. Escalation still writes each turn to `retribution_nextturn.miz` and you load it exactly as you always have — but a named, dated copy now *also* lands in `Missions/Retribution Archive/` (e.g. `germany_1980_red_tide_turn03_20260716-193205.miz`). DCS's own mission browser lists that folder, so a past turn re-opens straight from the game when you want to see what actually spawned, and hosts no longer have to hand-copy the miz to a named file before every event. Re-planning and generating a turn again keeps **both** copies instead of overwriting the one that was flown. The newest 20 are kept; anything you put in that folder yourself is never touched.
* **[Plugins]** Cruise missile auto raids now launch **staggered inside a random window** (default 240–900 s after mission start, both ends tunable in the plugin options) instead of one mass volley at exactly 240 s — the same stagger the SCUD fire tasks use, so campaigns with several launching naval groups (or groups on both sides) don't stack every salvo's missile count against the framerate, and the defender's LAUNCH WARNINGs arrive per raid. The old single-delay option is still honored as the window's opening edge.
* **[Mission Generation]** **Warships fire real cruise missile raids.** A Burke's Tomahawks (or the enemy's Kalibr ships, with the CurrentHill packs) finally do their job: put an F10 map marker on a shore target and call **F10 → Cruise Missile Strike** to ripple a salvo from the nearest capable ship (type just a number in the marker's text — `6` or `#6` — to fire exactly that many) — or turn on auto raids and each side commits one salvo a turn at its best reachable target (command bunkers and comms first, then war industry), announced to the defender only as a bare **LAUNCH WARNING**. The missiles are real weapons from real, sinkable ships: kills count at debrief, point-defense SAMs (Tor, Pantsir, your Patriots) get to intercept them, and every ship carries a **finite campaign magazine with no rearm** ("Magazine status" on the same F10 menu shows what's left) — a salvo spent on a truck park is a salvo you won't have for the command bunker. New settings `Ship-launched cruise missile strikes` + `Auto-plan cruise missile raids` (**Mission Generation → Naval strike**, both default **off**; keep the new `Cruise missile strikes` plugin enabled).
* **[Settings]** Era-gated **cockpit options** now have their **own toggle** — `Restrict aircraft options by campaign date` (Difficulty & Realism, next to the weapons restriction) — so you can enforce weapons, cockpit options, or both. Previously the helmet gate rode the weapons toggle; if your save relied on that, flip the new setting once. The gate also grew per-airframe data: alongside JHMCS (F/A-18C, F-16C · 2003) it now covers the A-10C II's **Scorpion HMCS** (2012) and the MiG-29's **HMS** helmet sight (1983) — hidden from the payload dropdown and clamped to the period-correct visor in the generated mission.
* **[Campaigns]** **The enemy's supply roads got the same treatment.** Nine campaigns had no road between two enemy bases, so the enemy side of the ambient convoys — the columns you hunt with Armed Recon/BAI — silently never existed there. A red corridor pass traced their real highways too: the Aleppo belt (Aleppo Insurgency, Battle for Syria North — which also gets its Turkish FOB supply line), the Iranian Bandar Abbas–Kerman/Shiraz–Bushehr mainland highways (both Noisy Crickets), Cyprus's motorways (Aegean Aegis), the Calais coastal roads (Operation Dynamo), the full Enduring-Resolve ratline for Operation Shattered Dagger, Saipan's Middle Road and Tinian's Broadway (Velvet Thunder — enemy convoys now run per island), and Guam's Marine Corps Drive for Pacific Repartee. Every campaign now runs at least one side's convoys unless its map genuinely has no two same-side land bases. NEW game required.
* **[Campaigns]** **21 more campaigns got their supply roads.** The ambient-convoy/ambush layer needs a road between two friendly bases, and most campaigns never authored one — so a corridor-authoring pass traced the **real highways** (by real-world lat/lon, following the driveable-corridor standard) and gave a blue rear corridor to: TblisiGap and Vectron's Claw (the Kakheti Highway), Battle4Georgia and Kutaisi2Vaziani (west Georgia's E60/S2), Slava Ukraini (Anapa–Novorossiysk), The Long Road to H3 / Syria Full Map / Aleppo Insurgency / Battle4SyriaNorth (the Turkish O-52 and E91), Task Force Thunder (the H4–H3 pipeline highway), Battle4Area51 (US-95), Noisy Cricket ×2 and Scenic Merge (the UAE E11), Operation Gazelle (Israel's route 40), Red Sea Rising (route 40 + the Egyptian Delta), Desert Aladeen (the Baghdad ring), Shattered Dagger (Highway 1, Kandahar–Bastion), Velvet Thunder (Guam's Marine Corps Drive), Final Countdown 2 (the New Forest A-roads), and The Anvil of War (the Swedish/Norwegian E10/E45/E6 chain). **48 of the 67 campaigns** now run convoys; the rest are island/sea-split maps with no road to author. NEW game required to see the roads.
* **[Mission Generation]** **The roads have traffic now.** Every turn, each side's supply-convoy flow is topped up to a small **randomized** number of real columns on its own road network — some sharing a road, some spread out, never a forced count — so every mission on a road-bearing map has convoys to see, hunt, and protect on both sides. Enemy columns are ordinary Armed Recon/BAI targets; every column is a real, tracked transfer whose losses count at debrief. New setting `Ambient supply convoys` (**Mission Generation**, default **on**; a map with no roads between friendly bases simply gets none).
* **[Mission Generation]** Your own supply convoys **might get ambushed** — and nothing warns you beforehand. Sometimes (a chance roll, never a certainty) hidden enemy ambush teams dig in along a friendly convoy's route: one contact, or a gauntlet of five or six down the same road. The convoy looks like any other friendly convoy, **no objective or escort package shows anywhere in the UI**, and the first sign of trouble is the **TROOPS IN CONTACT** call (plus an F10 mark at the fight) when an ambush springs mid-mission — fly to the column's aid and clear the ambushers, or let it fight through alone; your call. Both sides are real, tracked units: a ground-down column is reinforcements that never arrive, and dead ambushers are a real enemy ground loss at debrief. New setting `Friendly convoy ambushes` (**Mission Generation**, default **on** — keep the `Convoy ambush` plugin enabled; the COIN campaigns, 1968 Yankee Station, and Red Tide force it on over saved defaults).
* **[Campaign]** The campaign now runs on **one continuous clock**. Instead of every turn jumping to a random hour of the day and re-rolling the weather from scratch, the mission clock **marches forward a few hours per turn** from the campaign's start date, the date **rolls over at midnight** (not once every four turns), and the **weather evolves from the turn before** — fronts roll in and clear over several turns instead of a thunderstorm one sortie and clear skies the next. Time of day and weather now read as one believable timeline that moves in step with the campaign phases. New setting `Continuous time & weather` (**Campaign Management**, default **on**; requires day-and-night missions — the day-only / night-only mission-time settings keep the old per-turn behaviour). Turn it off for the stock per-turn clock and random weather.
* **[Campaign Layer]** 1968 Yankee Station's political-will economy now has a **real clock**. The Vietnam defaults left both meters passively *rising*, so the narrated race — "break Hanoi before Washington's patience runs out" — had no time pressure: a careful player was never on a timer and effectively couldn't lose by will, and the will-coupled ROE escalation almost never fired. Washington's patience now **erodes with the war's duration** (war weariness, offset by winning the air battle and compounded by losses), and Hanoi's resolve is no longer near-unbreakable, so **sustained trail interdiction genuinely strangles the regime** and the bombing halt's "just wait it out" finally costs you leverage. The result is a genuine three-way race: strangle the trail fast and Hanoi folds early; fly it clean and you ride the full Rolling Thunder → Linebacker II arc to a negotiated win; flounder and Washington orders the withdrawal. And **Hanoi's counter-moves are now legible** — when the enemy answers the arc (surging the Ho Chi Minh Trail during the halt, opening a Tet/Easter ground offensive under Linebacker), you get a "Hanoi's response" briefing instead of only feeling the levers. Per-campaign tuning; Velvet Thunder and Red Flag 81-2 are unchanged.
* **[Campaigns]** The three Caucasus Vietnam campaigns are **consolidated into one** — **1968 Yankee Station** now carries the whole in-country air war in its scenario, and the standalone **Khe Sanh: Operation Niagara** and **Steel Tiger: Trail Interdiction** are dropped. Nothing is lost: the **Steel Tiger** trail war folds in as an armed-recon/BAI order-of-battle tilt (Navy Intruders, Skyraiders and Broncos hunting the Ho Chi Minh Trail), and the **Niagara** siege folds in as the DMZ front — a depleted Da Nang starts the line pressed in near the wire, the forward strips draw rocket/mortar harassment, and the encircled FOB Khe Sanh lives on the Super Gaggle resupply. The order of battle was also **rebalanced** to a leaner ~3:1 (BLUE ~116 / RED ~40 airframes) so it plays as a tense will-economy fight instead of a turkey shoot: blue's income trimmed and the enemy given a real trail war chest, every base sized to fit its parking (so "squadrons start full" fields the whole wing), and the off-map Guam B-52 base folded into U-Tapao (Maykop). NEW game required.
* **[Aircraft]** Fixed two squadron liveries that pointed at personal **Saved-Games-only** skins (they rendered as a default/wrong skin for anyone without the custom pack, e.g. on a server): the UH-1H and the C-130J-30 now use real in-game liveries (**US ARMY 1972** and **USAF Air Mobility Command**). The C-130J one was the *only* C-130J-30 squadron definition, so this corrects the transport's livery across every campaign.
* **[Campaigns]** COIN now has **dispersed cells**: the insurgency operates out in the countryside between the strongholds, not just in them. Small recon-fogged cells appear in the open field — **patrol for them** (TARPS + CAS), don't just hit known positions. A cell you leave alone matures and slips into its home stronghold, bringing a **destroyed ammo cache back into operation** — re-opening the regeneration you worked to shut off (or reinforcing the garrison if no cache is down). Hunting the field cells is how you *keep* a stronghold starved. New setting `COIN dispersed cells` (default off, preseeded on in Operation Enduring Resolve; requires COIN replenishment on).
* **[Campaigns]** COIN now has a **high-value-target hunt**: a named insurgent leader periodically surfaces near a stronghold for a **limited strike window** — a real recon-fogged target. Kill him inside the window and you deal the insurgency's momentum a real blow — but he often shelters among his people (a stronghold on a population-center ring), so the strike carries the **collateral-damage dilemma the rings price**: take the shot dirty (a momentum blow *and* a mandate-draining ROE violation), wait for a clean one, or let the window close. New setting `COIN high-value targets` (default off, preseeded on in Operation Enduring Resolve; requires COIN replenishment on) with a campaign-priced `red_hvt_killed` will weight.
* **[Campaigns]** COIN now has **roadside IEDs**: the insurgent supply roads (the ratline) are mined. Hidden IED emplacements appear on the trail — ordinary recon-fogged targets you must **find (TARPS/ISR) and strike (CAS/Armed Recon)** within a few turns. An IED you clear costs the insurgency nothing but the device; one you leave un-swept **detonates on the coalition and drains your mandate**. Sweeping the trail is a real job now — the political price of an un-secured road. New setting `COIN roadside IEDs` (default off, preseeded on in Operation Enduring Resolve; requires COIN replenishment on) with a campaign-priced `blue_ied_detonation` will weight.
* **[Campaigns]** COIN now has **re-infiltration**: the insurgency can **retake ground you cleared but did not hold**. An under-garrisoned base near a healthy stronghold draws a staged, announced pipeline over ~4 turns — first an infiltration cell appears, then a supply cache, then the base changes hands — each stage a real unit on the map you can strike to stop it. Garrison the base, kill the cell or cache, or strangle the source stronghold's caches to break the attempt. Total insurgent bases never exceed the campaign start (relocate, never grow), and a completed flip drains your **mandate** like any lost base. Clearing a stronghold is no longer enough — you have to *hold* it. New setting `COIN re-infiltration` (default off, preseeded on in Operation Enduring Resolve; requires COIN replenishment on).
* **[Kneeboard]** Fixed kneeboard content **clipping off the right edge**. Wide tables (the Comms & Coordination support ladders when a package is on three radio channels) now **wrap the over-wide column to fit the page** instead of running the FREQ / Departure / TOT columns off the edge, the package FREQ/TOT header line splits when it would overrun, and the enemy-AD threat **bullseye cue lists truncate to the page width** (with a "…" or "+N") instead of being cut mid-number. Narrow tables that already fit are untouched.
* **[Kneeboard]** The compact deck's **Threats & Targets** page no longer leaves its lower half blank when the enemy air defenses are still unidentified. When the target-recon photo takes the flex page (which drops the Fuel Ladder from the deck), the **Fuel Ladder now backfills that blank space** below the threat cards — so on a fogged-threat turn you get the ladder instead of empty page, and a page full of identified threats simply omits it.
* **[Planner]** New **long-range carrier ops** (`long_range_carrier_ops`, default off): when the carrier stands off far beyond the auto-planner's reach (Enduring Resolve parks it ~800 km out in the Gulf of Oman, the real OEF cycle), the stock range gate left the whole air wing on the deck. The campaign now raises the airplane range gate so the carrier Hornets join the wider war, and frags one deterministic **carrier strike package each turn** from the boat's own squadrons — a Hornet strike section, an A-6 tanker, and an E-2 on AEW&C — built through the engine's own package planner. The boat's **other** carrier flights (the SEAD Sweep/Escort Hornets the commander frags in their own packages) now **tank from that same A-6**: a post-planning pass pins their refuel point onto the A-6's held orbit — which sits right on their launch/recovery route — instead of the dry far-end refuel point the stock planner gave them. Preseeded on in Operation Enduring Resolve; other campaigns are untouched.
* **[Campaigns]** Enduring Resolve's supply lines now **follow the roads you'd actually drive** — Highway 1 (the Ring Road) out to Farah, Route 611 up the Helmand River valley (Gereshk → Sangin → Kajaki), and the Uruzgan mountain road (Kandahar → Tarin Kowt) — instead of straight lines across the ridgelines. Traced from the real Afghan road network (the DCS Afghanistan map is real-world-coordinate) via a new authoring helper, `tools/supply_route_geo.py`. This is now the **414th standard for every supply-line drawing**: trace the corridor you'd travel between the two points; the route still binds to the same bases (only its endpoints matter), the shape in between just follows the real road.
* **[Campaigns]** The corridor standard now reaches the built campaigns. **Red Flag 81-2's** supply routes are re-traced onto the **real NTTR road network** — US-95 out of Las Vegas (Nellis → Indian Springs → Camp Mercury), US-6 east out of Tonopah, and the Gold Flat / Kawich valley down to Pahute Mesa. The one line that genuinely cut country — the "US-95 west corridor" from the Tonopah Test Range to Beatty, which used to run straight down the Kawich Range — now doglegs the real way: **west to Goldfield, then south through Scotty's Junction**. **Yankee Station / Steel Tiger** (the shared Vietnam-on-Caucasus trail) get their worst offenders cleaned up too: the Senaki → Thanh Hoa line is no longer a bare straight shot across the Kolkheti plain, and the Ban Laboy trail legs no longer detour ~25 km east into the lowland and back. Every endpoint is untouched, so all routes still bind the same bases (engine-verified). `tools/supply_route_geo.py` is now multi-campaign (`coin`, `red_flag_81_2`, the Caucasus trail fixes). Red Tide (Germany) was already traced on the autobahns and is left as-is.
* **[Campaigns]** Enduring Resolve gets the **2006 OEF air war**: a new multi-national **OEF Coalition 2006** faction — **Dutch F-16s (322 Squadron) and RAF Harriers (IV (AC) Squadron) on the Kandahar ramp** beside the A-10s, Marine Harriers at Bastion, **carrier Hornets (VFA-113) and an E-2 flying from a REAL carrier in the Gulf of Oman** (the map has water — a user-proven placement; ~780 km cycles up the drawn safe corridor), and the **CENTAF heavies — Strike Eagles (391st FS), B-1s, and KC-135s — home-based at Kandahar** (the coalition airhead's long runway; no floating off-map spawn base), each squadron under its own nation's flag and voice. A new **COIN doctrine** (faction key `coin`) lets the coalition strike through gun/IR threat — against an enemy with no radar SAMs the stock suppress-first rule deadlocked every strike (0 legal targets in the probe), and there is nothing to SEAD. The insurgents answer with **ZU-23 sites at every stronghold, SHORAD at seven, and a light radar-SAM crust at the anchors** — an SA-6 battery over Farah, an SA-3 site at Tarinkot, a Kub at the Kandahar gate, SA-8/13/15 in the short-range mix (none inside the town rings, so SEAD/DEAD stays AI-playable) — enough to make SEAD a real job again, never enough to stop the war. The Navy tanks itself: **VA-165 A-6E buddy tankers** embark alongside the Hornets and the Hawkeye. NEW game required.
* **[Campaigns]** Enduring Resolve draws **the horror of COIN onto the map** as four big **positive-control valleys** — no-strike areas over the real populated river valleys of the 2006 campaign, drawn as two corridor lanes (the **Helmand green zone** Kajaki → Sangin → Gereshk → Lashkar Gah → Marjah; the **Musa Qala** Route-611 feeder Now Zad → Musa Qala → Kajaki) and two boxes (the **Tarin Kowt** bowl and the **Delaram** junction). The strongholds and much of the insurgency's cells and caches sit inside them, so every fixed strike near the people is **priced per kill** (the ROE violation weight drops 6.0 → 1.0: CDE pressure, not taboo — a careful town fight is survivable once, a carpet habit bleeds the mandate out). The open desert and the northern gate stay free; trail convoys and troops in contact are never gated and air assaults (captures) are never blocked, so you still retake your objectives — you just pay for the collateral when you fight where the insurgency hides. (This **replaces** the earlier 9-town-ring + invisible whole-map free-fire model with explicit, visible box/corridor no-strike zones.) NEW game required.
* **[UI]** ROE zones now **read as shaded areas, not thin lines** on the campaign map — the restricted/free-fire fill was bumped from a barely-there 6% to a legible 14%, so a large box or corridor shows its whole footprint over the satellite imagery instead of just a lone dashed edge. Enduring Resolve's four positive-control valleys were also **enlarged** (the Helmand and Musa Qala corridors widened, the Tarin Kowt and Delaram boxes grown ~3×) so they properly blanket the populated belt.
* **[Campaigns]** Enduring Resolve's **population-center ring now has teeth** (it was an empty circle — nothing inside to tempt you). **FOB Geronimo's ammo caches now hide inside Lashkar Gah** and the new Geronimo supply leg runs **through the town**: starve that stronghold or interdict its column in-town and the strike prices into the Coalition's mandate; the clean options (air-assault the FOB, catch the convoy in the open desert) cost more effort instead. The empty **Herat ring is cut** — a ROE ring must guard something. NEW game required.
* **[Campaigns]** Operation Enduring Resolve's **ratline is now real** (it was promised by the arc copy but nothing could run: the laydown had no supply routes, the trail picker required front lines, and the insurgent strongholds held no transferable stock). The campaign now authors **8 red-to-red supply corridors** (Farah and Tarinkot rear chains feeding the Helmand ring and the Kandahar gate — visible on the map), the §35 trail machinery orients toward the opposing bases when a campaign has no front lines, and on COIN campaigns the rear source is seeded with irregular kit (external support over the border) so a real, interdictable convoy is always flowing. Killing it is a real loss and a momentum drain.
* **[Factions]** **Toyota Al Gaib 2001** (the COIN insurgent faction) was missing most of the insurgent kit its sibling factions carry: it gains the four **DIM' Toyota technicals** (incl. the kamikaze truck), the **§41 HDS ERO ZU-23 family** (Toyota/armored technicals + open/closed emplacements + the ERO preset group — resolve only with the HDS mod, drop silently without it), and the **SA-9**. Deliberately still no armor — the 2006 insurgency stays light, and the COIN regen pool grows from 6 to 9 unit types. Operation Enduring Resolve now preseeds `high_digit_sams` so the ERO technicals actually appear.
* **[Campaigns]** New **Afghanistan - Operation Enduring Resolve (COIN)** — the first **living counterinsurgency campaign** (a fork of Starfire's Operation Shattered Dagger). The insurgency's 13 strongholds **regenerate**: cleared cells quietly come back toward their original strength each turn (and your last recon picture stands until you re-fly it — "we cleared that position last week; it's shooting again"), throttled by **hidden ammo caches** you can recon and strike; kill a stronghold's caches and its regeneration collapses to a trickle. The war is decided by the will meters — **the Coalition's mandate** (bleeds from airframes, lost bases, strikes near the Lashkar Gah/Herat population-center rings, and plain time) versus **the insurgency's momentum** (bleeds from caches, trail convoys, and strongholds — almost never from dead fighters). Three authored phases (Disrupt the Network → Clear and Hold → Break the Momentum), FOB standoff fire, and the supply-trail ratline round out the loop. The insurgent replenishment engine (`coin_insurgency`) is generic and default-off — any future COIN campaign can preseed it.
* **[Campaign Layer]** The **political-will economy is now campaign-generic**: the Washington-vs-Hanoi framing and every feed weight are just the *defaults* of a per-campaign **will profile**. A campaign YAML's `will:` block re-labels both meters and their exhaustion headlines (a Falklands can read "London recalls the task force") and re-weights every feed — plus a new **warship-loss feed** (`blue_ship_lost` / `red_ship_lost`), so naval wars bleed will from sunk ships the way Vietnam bleeds it from downed B-52s. The four Vietnam campaigns carry no block and play exactly as before; the authored labels follow through the per-turn will message, the map ribbon meters, the intel box, and the Stats chart.
* **[Campaigns]** The Vietnam-era campaigns (1968 Yankee Station, Velvet Thunder, Red Flag 81-2) now ship **`high_digit_sams: true`** and their laydowns carry **red EWR sites**, so the period **P-37 "Bar Lock"** the HDS faction pass added actually spawns — closing the "period red IADS has no early-warning net" gap in practice, not just in the faction files. New EWR markers: Hanoi + Vinh on the Yankee Station board, Saipan for Velvet Thunder (Red Flag 81-2 already had its two). **HDS Ultimate Compilation is now on the campaign Required-Mods lists.**
* **[Campaigns]** New **Nevada - Red Flag 81-2** campaign — the 1981 Red Flag exercise played as the war it rehearses (after the Reflected Simulations F-4E campaign the squadron flies). An F-4E wing detachment at Nellis fights the historically-real Red Force: 64th/65th **Aggressor F-5Es** on MiG-21 GCI hit-and-run doctrine, the **4477th "Red Eagles" Constant Peg MiGs out of Tonopah Test Range**, an **SA-2/SA-3 emulator array around Tolicha Peak**, AAA belts on the ingress corridors, and a simulated enemy army on a FEBA north of Camp Mercury. Ships with two new era factions (**USA Red Flag 1981** / **Red Force 1981 (Nellis Aggressors)**, wired to the Vietnam doctrines) and the full **Vietnam mechanics stack preseeded**: political will as the TAC exercise assessment, the static exercise FEBA, the Vietnam Ops battlefield suite (no naval gunfire — no sea), and a three-phase authored escalation arc (**Week One → Force on Force → Surge Week**) whose **Groom Lake box never releases** — enter it and the assessment bleeds, exactly like the real range.
* **[Mods]** High Digit SAMs support retargeted from the abandoned original mod (v1.4.0) to the actively-maintained **[Ultimate Compilation](https://github.com/dcs-sams/HighDigitSAMs-Ultimate-Compilation)** (v1.4.3+), behind the same New Game toggle. Absorbs the compilation's breaking changes (renamed S-300PS radars re-pointed everywhere; the dropped HDS KS-19/SON-9/SA-24 replaced by their vanilla equivalents) and registers its new content: **S-400/SA-21** and **S-300V4** batteries (new presets on the extended S-300 site), the **S-300PT** launcher, **Pantsir-SM** SHORAD, the **SAMP/T** Aster battery (new Patriot-geometry layout, wired to France), **SA-7/SA-7b manpads** for 70s–80s red factions, four new **EWRs** — including the **P-37 Bar Lock**, which closes the "period red faction has zero EWR units" IADS blind-net gap across 16 factions — and the ERO **ZU-23 Toyota technicals** for insurgents. Also fixes a silent gating bug where the mod-off strip matched display names instead of DCS type ids, so HDS manpads/C2 units were never actually removed when the mod was disabled.
* **[Campaigns]** Audited every bundled campaign and swapped aircraft from **cut mods** for in-game (or kept-mod) equivalents, so the stock campaigns generate cleanly on the 414th's trimmed mod set. Replacements honour each campaign's faction and era: e.g. CurrentHill **[CH] B-21 → B-1B Lancer**, Swedish **[CH] JAS-39C → F-16CM**, Ukrainian **[CH] MiG-29MU2 / Su-24MU / Su-27P1M → MiG-29S / Su-24M / Su-27**, **KC-130J → KC-135**, **UH-60L → UH-60A**, **F-111C → F-15E**, and the Vietnam-era *1968 Yankee Station* carrier wing rebuilt on period **F-8E Crusader / A-6E Intruder / A-1H Skyraider**. Kept mods (F-22A, EA-18G/Super Hornet, the CurrentHill Russian pack, Vietnam War Vessels) are untouched; the **[CH] B-21 is removed** from the blue factions per squadron preference, and the period **A-6E Intruder / F-100D Super Sabre** are added to the Vietnam faction so the carrier/strike slots resolve. Each campaign's mod toggles are set to match, and a handful of genuinely-broken aircraft references (e.g. `IL-78MD`, `Mi-8`, `E-3`) are fixed along the way.
* **[Factions]** Extended the cut-mod cleanup to the **faction definitions** (#267 had only swapped the campaigns): the same trimmed-mod-set swaps now apply across all faction JSONs — **UH-60L → UH-60A**, **KC-130J → KC-135**, the Ukrainian **[CH] MiG-29MU2 / Su-24MU / Su-27P1M → MiG-29S / Su-24M / Su-27**, and **F-111C → F-15E** (removed outright in the Vietnam-era USA faction). It's dedup-aware (the cut entry is dropped where the modern equivalent was already in the roster, rather than duplicated), the matching `liveries_overrides` keys move with the aircraft, and the Swedish **JAS-39 (+ AJS37 Viggen fallback)** is intentionally kept. A new test (`tests/test_faction_modernization.py`) fails CI if any cut-mod aircraft is re-introduced into a faction or campaign — the faction loader otherwise drops it silently, so the regression would be invisible.
* **[Mods]** Updated the bundled **Community A-4E-C** mod definition to **v2.3.0** (upstream PR #840) — refreshed weapon set plus the Shrike payload-rail CLSID fix (`AGM-45B → LAU-34_AGM-45B`) in the SEAD/anti-ship presets.
* **[SCAR]** Strike Coordination and Reconnaissance reworked to a **loiter-and-task** model: the flight holds over a **static kill box** and services a **real, static enemy armor target** (still hidden among look-alike decoys + clutter — the discrimination puzzle survives). Because the target is a real campaign unit, destroying it attrits the enemy through the normal loss/debrief path — no bespoke SCAR scoring. The commander-capture path is preserved and **inverted**: a purchased SOF team (C-130 airdrop) assaults the **held** command vehicle and takes the commander alive if you leave him intact (revealing enemy command posts next turn), with a stranded-SOF CSAR recovery loop and enemy command-post intel fog. The old moving/fleeing-target chase is retired. Default ON for new campaigns. *(The C-130 "King" on-scene-commander designation/talk-on is a follow-on phase.)*
* **[Combat SAR]** A new bespoke pilot-rescue flight type: a CH-47 orbits near the front as the rescuer while a C-130 flies the overhead HC-130 "King" on-scene-command orbit (lighting an air-tracking TACAN every rescue helo can home on, plus an F10 LARS survivor-locator). When a human pilot ejects, the MOOSE CSAR engine spawns them with a beacon and the helo recovers them — and delivering a downed pilot to a friendly field now **spares that aviator** in the campaign (you still lose the jet, but the experienced pilot returns to the squadron instead of being killed). The same Combat SAR helo can also **extract a stranded SCAR SOF team** in-mission (a botched commander-capture leaves a team behind): fly out, pick it up, deliver it home, and the team is recovered + refunded — an alternative to the dedicated CSAR air-assault sortie. The rescue helo is the player-flyable CH-47F with its door M60D gunners for self-protection (AI CH-47D stays as a fallback), and the King is the player-flyable C-130J-30. Player-flown, with an optional AI standing alert (`auto_combat_sar`, default OFF).
* **[Aircraft]** Consolidated the C-130 transport fleet onto the player-flyable C-130J-30 (Airplane Simulation Company module, which the DCS AI can also fly): the stock AI-only C-130 "ugly model" is retired and every faction now fields the C-130J-30 for transport / SOF airdrop / the Combat SAR King. The KC-130 / KC-130J aerial tankers are unchanged. In-progress campaigns with an old C-130 squadron migrate to the C-130J-30 automatically on load. (The dead Anubis Hercules mod is fully out of Escalation.)
* **[Mission Generation]** DEAD and SEAD flights against a ground target now get one waypoint per individual target (with coordinates, matching the kneeboard), and the SEAD/DEAD kneeboard target list gains an "STPT" column. AI plain-SEAD reworked to loiter at a standoff orbit and engage reactively, and AI DEAD flights receive the best available standoff/PGM loadout.
* **[Kneeboard]** New recon kneeboard pages — target reconnaissance, a friendly-packages coordination list, and a package-targets theater map. Basemap tiles are fetched once at mission generation and cached under Saved Games; on offline or locked-down networks the pages fall back automatically to an offline coastline basemap (the cache is safe to delete). Ships the per-terrain airport-imagery dataset (satellite-mosaic alignment, runway thresholds, DCS-accurate field elevations) so airfield diagrams line up and the ATIS block shows a temperature-corrected altimeter setting (QNH) with QFE reduced to the field — matching the in-sim ATIS.
* **[Plugins]** ATIS for player flights via a MOOSE voice-ATIS plugin (per-airfield frequencies and spoken reports). Self-documenting Lua plugin options with a label/doc pass across plugins.
* **[Map]** Carrier/LHA ship groups and blue non-carrier ships appear on the campaign map with their air-defense rings; hovering a SAM/detection ring highlights its emitter (and vice versa); enemy IADS links are coloured by kind and state.
* **[UX]** Bulk-set altitude across a flight's en-route waypoints and step the per-waypoint altitude editor by 1000 ft; configurable altitude scatter band and patrol floor. Improved fast-forward with combat-skip and a "Player at IP" stop condition.
* **[Planner]** Opt-in, per-side auto-planner target unpredictability — weighted-random reordering of opportunistic offensive targets so the enemy stops hitting the same things every turn (reactive threat response stays deterministic).
* **[Target Intel]** The Approximate target-location cue offset is tightened to 1-3 NM, so players still have to visually acquire but aren't sent hunting across the map.
* **[Plugins]** CTLD updated to ciribob 1.6.1.
* **[Cleanup]** Removed **DCS: Pretense** support entirely — the one-way campaign exporter (`game/pretense/`, ~5,400 lines), its 590 KB of unmaintainable third-party Lua, the toolbar actions, the settings page, the `Cargo Transport` flight type and the four Pretense-tuned `*_full` campaigns. Nothing generated in Pretense ever came back to the campaign, and both Pretense and the upstream integration are abandoned. Old saves that had generated a Pretense mission still load: their cargo flights read back as ordinary transports.
* **[Cleanup]** Retired the `dismounts` plugin (a MIST-only, performance-heavy infantry-dismount script with no MOOSE successor, not registered in the active plugin list). First step of the MIST → MOOSE framework consolidation; old saves drop any orphaned `dismounts` plugin keys on load.
* **[Cleanup]** Retired the `ewrs` plugin (legacy MIST-based EWR threat-callout script), superseded by the MOOSE `Ops.INTEL`-based `bigeye` EWR. Part of the MIST → MOOSE consolidation; old saves drop any orphaned `ewrs` plugin keys on load.
* **[Cleanup]** Removed the unused `arty` (CG ArtySpotter) and `artymbot` (Mbot Call-Artillery) player fire-support scripts. Both had been silently dropped from the active plugin list during the QRA-reserve integration and never re-enabled; their directories are now deleted and old saves drop any orphaned `arty`/`artymbot` plugin keys on load.
* **[Cleanup]** Deleted dead resource files that still shipped in the build: six orphaned Pretense mission files (`*_full.miz` / `normandy_small.miz`, left behind when the Pretense generator and its campaign descriptors were removed) and two legacy root landmap pickles (`channellandmap.p`, `cau_groundobjects.p`, superseded by the per-theater `theaters/<name>/landmap.p`).
* **[Plugins]** New experimental MANTIS IADS engine (MOOSE-based, alternative to Skynet). Inert by default — only active when a campaign's IADS engine is set to MANTIS; core SAM/EWR networking + emissions control (pending in-game validation).

* **[UI]** **Cruise missile strikes are visible outside the F10 menu now.** The mission briefing gets a CRUISE MISSILES section — your side's tasked auto raid (count, shooter, target) and each launcher's remaining magazine, plus the marker call-for-fire how-to; the naval group's info dialog shows its remaining missiles (friendly ships only); and the debriefing window reports what was expended per ship group with the post-mission remainder. Enemy residual stock is never shown anywhere — the other side's LAUNCH WARNING stays their only cue.

## Fixes
* **[FIX]** **Naval stagger and magazines were off even with both settings ticked.** A node's own key/value pairs were dropped whenever it also had children -- the Lua serializer emitted the children alone -- so `navalMagazines` reached the mission with its `magazines` list but no `stagger` or `metered` flag, the plugin read nil for both and armed itself with everything disabled. Only that node mixed pairs and children, so nothing else was affected, but for this feature it was total.
* **[FIX]** **The naval magazines plugin never loaded.** Plugin options were written into the mission with a blanket `str(value).lower()` and no quoting, which is fine for `true`/`false` and numbers but not for a string: the anti-ship weapon patterns contain `3M24`, and an unquoted `3M24` is a malformed Lua number, so DCS threw a syntax error over the whole configuration block and the plugin sat inert -- no staggered weapons release, no cross-turn magazine, every mission. The lowercasing was the second half of the bug: those patterns are matched against DCS's upper-case weapon type names, so they would have missed everything even once quoted. Option values are now rendered by type.
* **[FIX]** The AH-1W carries TOW again in Blufor Late Cold War (80s). DCS models only the BGM-71D, dated 1985, so a 1983 campaign left the Cobra with rocket pods against armour -- the AH-1 has carried TOW since 1973. The faction now overrides the weapon's year to 1970, which the weapon file itself suggests as the stand-in for the variants DCS does not model.
* **[FIX]** The AIM-7P is date-gated on the Hornet's LAU-115 rails. Only three of its four clsids were declared, so picking the Sparrow P from those stations gave an unrecognised store with no introduction year -- a 1987 missile that flew in any campaign, however early. The F, M and MH rail clsids were already listed.
* **[FIX]** The A-6E's TALDs and its AN/ALQ-167 pod are recognised weapons now. The Intruder's four MER-mounted TALD stores were in no weapon file, so they read as unknown: they never counted as decoys for SEAD planning, and they dodged the TALD's 1987 date, arming pre-1987 campaigns with an anachronism. The ALQ-167 was missing outright and so never counted as a jammer.
* **[FIX]** **The A-6E drops laser-guided bombs again.** Its TRAM turret is an internal laser designator, but nothing declared it, so the planner saw a loadout with no targeting pod and swapped every GBU for iron -- in every campaign, at every date: `Strike` flew Mk 83 instead of GBU-16, `OCA/Runway` Mk 84 instead of GBU-10, `OCA/Aircraft` Mk 82 instead of GBU-12. The A-6A has no TRAM and is unchanged.
* **[Build]** **Fixed the release crashing on launch** with `mgrs.core.MGRSError: Unable to load libmgrs.cp311-win_amd64.pyd`. The recon-kneeboard map feature added the `mgrs` package as a dependency, and `mgrs` loads its compiled library via ctypes from *one level above* its own package folder — so PyInstaller's import analysis never saw the native `.pyd` and never bundled it, and the frozen app died on the first import at startup. The library is now bundled at the dist root, where both `mgrs`'s own lookup and the default DLL search next to the exe find it. This is the bug that made **v1.6.2-414th crash immediately on a clean machine** (v1.6.1 predates the `mgrs` dependency, which is why it was unaffected); v1.6.3 supersedes it.
* **[Mission Generation]** Scenery objectives keep their kill-tracking trigger zones (and IADS command stand-ins) even when performance culling skips the rest of the objective. The map buildings backing a scenery objective exist whether or not the campaign spawns anything, so bombing one in a culled region used to visibly destroy a target whose death was never recorded at debrief.
* **[Mission Generation]** Cruise missile raid targets are no longer **performance-culled out of existence**. The auto raid usually strikes a rear-area objective no flight package is fragged against, so with performance culling on the target's buildings were never spawned into the mission — the missiles then visibly demolished the *map's* scenery at those coordinates while the campaign recorded no damage at all (flown and confirmed against a culled refinery: perfect impacts, zero effect). Planned raid targets and every launching ship group now get culling exclusion zones, so the campaign objects are really there when the salvo arrives. Marker call-for-fire into deep culled regions can still only hurt map scenery — aim marker strikes at campaign objects near the action, or widen the culling distance.
* **[Mission Generation]** Cruise missile strikes now see **carrier escorts**. The launching-ship scan only looked at standalone ship objects, but the vanilla Burke's usual home is a carrier task force — a different object category — so a CVBG's Tomahawk escorts got no magazine, no F10 "Cruise Missile Strike" menu, and no raids, silently (the feature looked enabled but nothing ever fired). Carrier and LHA task-force groups now count as launchers (the CVN itself carries no missiles — only its LACM escorts add to the group magazine), while enemy carrier groups remain un-raidable (moving naval targets stay the carrier-strike/ANTISHIP job).
* **[Mission Generation]** Fixed an unloadable-mission corner in the neutral-country pick: when every preferred neutral nation (UN Peacekeepers, Switzerland, USAF Aggressors) was already claimed by a belligerent — e.g. an Aggressors enemy faction against a coalition fielding UN and Swiss squadrons — the generator handed a claimed country to the neutral coalition anyway, putting one nation on two coalitions (DCS rejects the `.miz`). It now picks any genuinely unclaimed nation.
* **[Plugins]** Restored the **BigEye EWR** plugin to the active plugin list. It was the documented successor to the retired `ewrs` script, but had itself been silently dropped during the QRA-reserve integration — so the *BigEye EWR* option was missing from the Plugin Options page and players had no early-warning picture/threat-report calls despite the docs claiming the capability had moved to BigEye. (Off by default, like before.)
* **[Plugins]** Restored the **LotATC export** plugin to the active plugin list (it was silently dropped during the QRA-reserve integration, so the *LotATC Export* option had disappeared from the Plugin Options page even though its scripts still shipped). Also fixed a cross-wired option in its config: the "Export anti-air symbols" toggle was being read into the "Export BLUE anti-air" flag, so symbols couldn't be turned off and the blue-AA export was driven by the wrong checkbox. (Threat-circle export works on MANTIS; the optional NATO-name label on each ring relied on Skynet globals and stays blank now that Skynet is removed.)
* **[Air Defense]** Generic AAA sites are no longer auto-issued a search radar, so they generate as optically-guided guns instead of radar-directed flak. The shared `AAA Site` / `Cold War Flak Site` layouts kept a fill-by-default radar slot that pulled in *any* of the faction's search radars (sometimes even a SAM site's big search radar); the slot is now `fill: false`, so only groups that explicitly bring a radar (e.g. the KS-19's SON-9 Fire Can) are radar-directed.
* **[Air Defense]** Reworked the Cold War Flak Site, which previously fielded WWII German 8.8 cm Flak 18 guns for every faction that used it (US, Vietnam, Korea, Sweden, GDR, Israel, …). The hardcoded German gun preset is gone; the flak site is now a generic layout that each faction fills from its own era/nation-appropriate AAA pool.
* **[Air Defense]** In-progress campaigns self-heal on load: any stray search radar that an older build attached to an AAA site (e.g. a ZU-23 site wearing an SA-11 Buk search radar) is stripped, so the guns revert to optical and the site stops acting as a long-range radar/EWR node. The KS-19's SON-9 Fire Can is preserved.
* **[Mission]** Fixed a `woCharacterHuman` sim crash caused by orphaned civilian-helo spawns (civilian traffic is now airfields-only with deferred orphan despawn, and kept clear of the active battle).
* **[Debrief]** Player despawns are no longer counted as combat losses, and untracked ground-unit deaths are summarised in one log line.
* **[New Game]** Fixed a crash creating a new game from a malformed settings JSON member, and stopped seeded plugin-option defaults being dropped when merging campaign settings.
* **[Mission Generation]** Fixed crashes planning a strike against a fully-destroyed objective (divide-by-zero), the "Fix TOTs automatically" action, and player ground-start flights spawning in the air.
* **[Performance]** `is_on_land`/`is_in_sea` now test a prepared MultiPolygon, cutting ground generation from ~7 minutes to seconds.
* **[UI]** Player cold-start CAP is no longer flagged in the past-start-times warning.
* **[Server]** Bounded uvicorn's graceful shutdown so the app can no longer hang on exit.

# Escalation v1.6.0

## Features/Improvements
* **[FIX]** Su-57 payloads no longer lose stations. Its presets asked internal weapons bays for stores they cannot take (an R-73 on station 10 in all seven, rocket pods, a BetAB-500) and asked every anti-ship station for a Kh-59MK2, which this mod declares but offers on no pylon at all — so the anti-ship preset flew with 8 of 12 stations empty. DCS drops such a station silently. Added `tools/audit_mod_pylons.py`, which checks every payload the fork ships against each installed mod's own pylon table.
* **[FIX]** The F-117A and both Tu-160s no longer offer DEAD. Their DCS types only know Pinpoint Strike, and a DEAD ingress tasks the group with AttackGroup, which only SEAD/CAS/AFAC/Antiship aircraft can execute — so planning one raised at Take Off, after the whole turn was planned. Use Strike against SAM sites with these aircraft.
* **[Balance]** Ground objects (SAM/EWR/armor/ship/coastal sites) now cost money on turn 0 like on any other turn. They were free before while the buy dialog still quoted a price, so a campaign could open with a belt of S-300s bought for nothing — by either side, or by the OPFOR AI.
* **[Campaign]** New option "AI buys its better ground units more often" (on by default): the AI picked a ground unit uniformly at random from everything of the right class it could afford, so a faction fielding both a modern MBT and a gun truck bought as many of one as the other. The roll is now weighted by price, the only capability measure the model has -- a weighting, not a maximum, so cheap units still appear (adapted from the 414Ret fork).
* **[Mission Generation]** Two new naval options (both off by default): warships can be released to weapons-free one group at a time across a window instead of every hull opening up at once, and each warship group can carry a finite campaign stock of anti-ship missiles that never rearms — a group that runs dry drops back to return-fire rather than being disarmed. Land-attack cruise missiles keep their own separate magazine, so no shot is charged twice (adapted from the 414Ret fork).
* **[UX]** Every generated mission is also archived to `Missions/Retribution Archive/<campaign>_turn<NN>_<timestamp>.miz`, so `retribution_nextturn.miz` no longer silently overwrites the mission you just flew. Self-pruning, and the fixed output path is unchanged (adapted from the 414Ret fork).
* **[Modding]** Update High Digit SAMs support to 2.1.0: adds the SAMP/T battery (Aster 30, Block 1/1NT/2 launchers up to 200 km, ARABEL and Ground Fire 300 radars) and the SA-7/SA-7b Strela-2 MANPADS, and retires the units the mod dropped.
* **[Mission Generation]** Ship-launched cruise missile strikes: warships carrying land-attack cruise missiles (Burke/Ticonderoga, CurrentHill Kalibr hulls) can hit shore targets, with an F10 "Cruise Missile Strike" call-for-fire onto your last map marker and an optional one-raid-per-side-per-turn auto planner. Each ship group carries a finite campaign magazine that never rearms, tracked across turns and shown in the briefing, the ground object dialog and the debrief. Both settings are off by default (adapted from the 414Ret fork).
* **[Performance]** Faster mission generation: the land/sea point tests behind front-line and ground-unit placement now use shapely's `contains_xy` (no per-check `Point` allocation or predicate-wrapper overhead), ~5x faster on the check that dominated a Take-Off profile.
* **[Mod]** Add support for the F-15EX Eagle II mod (by Spino).
* **[Mod]** Add support for the F-15C EG Golden Eagle mod (by Spino).
* **[Mod]** Add support for the Eurofighter Typhoon mod (by Lechuzas Negras).
* **[Map]** A ground object that is fully destroyed but being repaired now shows an orange health bar instead of yellow, so it reads distinctly from a partially-damaged group (some units dead, some alive) which stays yellow.
* **[Map]** Combatant (non-carrier) ship groups can be repositioned on the campaign map: drag the group to a destination (up to 80 nm/turn, open water only), it sails there in-mission and snaps to the destination at end of turn, re-parenting to the nearest friendly base. Player-driven for now. (Adopts upstream geofffranks' implementation, dcs-retribution#802.)
* **[Weather]** "Use ATMOS-X live weather": with the ATMOS-X cloud preset pack selected, the generated weather is replaced by a real METAR observation fetched through the ATMOS-X CLI. The station is picked automatically — the airfield you fly from if it reports, otherwise the closest one on the map that does — or set by ICAO. The mission always keeps its own date and time and takes only the weather, so a campaign set in another era can fly today's real sky. If ATMOS-X is missing or the observation cannot be fetched, the mission keeps the weather Escalation generated.
* **[Options]** "Custom cloud preset pack" setting (replaces "Use Bandit's clouds") makes a community cloud-preset weather mod's presets available to the mission generator — choose Bandit's Cloud Presets, Weather 2.0, or ATMOS-X to match the pack you have installed.
* **[Map]** Unified, dark, grouped/collapsible map-layers panel with presets, replacing the scattered layer toggles (adapted from the 414Ret fork; the fog-of-war row is omitted and the emitter-highlight and destroyed-object toggles keep their existing behaviour).
* **[AI]** AI AWACS and tanker support orbits are anchored on the front line and held deep behind the FLOT instead of drifting forward (adapted from the 414Ret fork).
* **[AI]** Optimistic DEAD "site cleared" assumptions are now gated on whether the flight can actually reach the target, so the planner stops clearing SAMs it can't prosecute (adapted from the 414Ret fork).
* **[Loadouts]** Weapons coverage refresh: many modern PGMs and air-to-air missiles are now available across factions, without the era date-gating (coverage adapted from the 414Ret fork; our existing introduction years are kept).
* **[Mission Generation]** Player despawns (leaving an aircraft) no longer count as combat losses in the debriefing (adapted from the 414Ret fork).
* **[Mission Generation]** More variety in generated air defenses: new SAM site layout variants (SA-2 four/six-launcher rings, an SA-2/SA-3 mixed site, SA-3, legacy SA-5 and reinforced SA-6 sites) wired into the period factions' preset pools, and generated EWR sites now draw true early-warning radars only instead of falling back to any search radar. (#892)
* **[Mission Generation]** SAM sites field two engagement radars (the shared site templates gain a second, dispersed radar position), so a single anti-radiation missile no longer functionally kills the whole site. Buy-menu counts and site prices follow. A deliberate survivability/balance call — rationale and trade-offs in the PR body. (#893)
* **[Mission Generator]** Stand-off/cruise-missile-armed flights now ingress from a realistic launch distance. Weapons can declare a `range` (nautical miles) in their `resources/weapons` YAML, and when a package carries such a weapon whose range exceeds the doctrine ingress distance, the ingress point is pushed out to that range (e.g. Tu-16s with Kh-22s begin their run ~160nm from the target instead of being dragged in to the doctrine ingress point). Weapons without a `range` are unaffected. Initial ranges are provided for the major stand-off, cruise, and anti-ship missiles and can be extended per-weapon. If a flight's payload is changed in the Edit Flight dialog such that the package's stand-off range changes, closing the dialog offers to regenerate the package's flight plans so the ingress point follows the new loadout.
* **[UX]** Escalation snapshots your DCS custom-payload library on startup, keeping the last 10 copies under `Retribution/PayloadBackups`. Deleting `Saved Games/DCS/MissionEditor` is common troubleshooting advice and takes every custom loadout with it; nothing else holds a copy.
* **[Mission Generator]** Motorpool target missions now match their mission-type counterparts: STRIKE keeps one player target waypoint per parked vehicle with one AI bombing task per vehicle at ingress; BAI gets a single player target-area waypoint with one AI engage task per unit-type group at ingress; armed recon gets a single player target waypoint with a garage-centered engagement zone sized to a full 5x5 parked grid plus 20 m, independent of the configured engagement range.
* **[Modding]** Added support for the CurrentHill Iran Military Assets pack: the Shahed-136 launcher, two IRGCN fast-attack craft, and a new `[CH] Iran 2020` faction, behind a New Game mods checkbox. (#886)
* **[Kneeboard]** Use a light-grey daytime kneeboard background instead of near-white, to avoid glare under HDR / Auto-HDR while staying readable in daylight.
* **[UX]** Hovering a friendly flight's route line on the map highlights it in yellow, and clicking it selects that flight's package (and the flight) in the ATO sidebar.
* **[UX]** Press Delete with a package selected in the Packages list to cancel it, making it quick to clear several packages in a row.
* **[UX]** Avoid having escorts from wondering off too far while chasing a target.
* **[UX]** Improved fast-forward settings with the ability to skip combat.
* **[UX]** Show an "End of Mission Detected, processing Mission Data" busy dialog while turn results are processed, so the wait is not mistaken for a missed detection
* **[UX]** The info panel now reports finished repairs for runways and all repairable ground objects/buildings (both coalitions), plus per-base "in progress, N turns remaining" lines for your own repairs each turn.
* **[UI]** Reworked the Finances dialog to show gross income, the HQ's automated per-category spending and the resulting net per turn, with a collapsible income breakdown and in-dialog automation toggles.
* **[Map]** Hovering a SAM threat or detection ring highlights its emitter — and hovering an emitter highlights its ring — making it easy to tell which site a ring belongs to. Can be disabled from the map's layer control.
* **[Map]** New "Red/Blue: destroyed (non-repairable)" layer toggles (below the ruler) to hide fully destroyed, non-rebuildable ground objects (buildings, ships, ...) per coalition. Repairable objects (air defenses, vehicle groups) are never hidden. Both shown by default.
* **[Mission Generation]** Target recon kneeboard pages for each player flight: overview map of the package corridor with nearby threats and threat rings, detail map of the target with numbered aimpoints (MGRS), recommended attack-axis arrow, and an aimpoint table. OCA missions get an airfield-layout variant. Ground-start flights also get an airfield-departure page with spawn-slot markers, runway-in-use highlight, wind arrow, and an ATIS-like weather block (winds aloft, QNH, temp, clouds, sunrise/sunset). Toggleable via new "Generate target recon kneeboard pages" setting (default on); threats can be widened beyond the corridor with a new search-radius slider. Requires the new `mgrs` dependency.
* **[Mission Generation]** DEAD and SEAD flights against a ground target now get one waypoint per individual target — the same targets (with coordinates) already listed on the SEAD/DEAD kneeboard page — so they can be designated quickly with TOO, just like Strike flights. The waypoints are player-only (AI tasking is unchanged), and targets the kneeboard does not list with coordinates (e.g. SEAD against a naval group) are unaffected. The SEAD/DEAD kneeboard target list also gains an "STPT" column showing each target's assigned waypoint number, matching the strike task page.
* **[Loadouts]** Aircraft where DEAD isn't a natural role (A-10, F-35, Su-57, Su-35S, strategic bombers, etc.) can now fly DEAD when assigned manually, with a proper standoff loadout, without DEAD being auto-assigned to them by default. Aircraft yamls gain an optional `secondary_tasks` list for this.
* **[Loadouts]** AI DEAD flights use the best standoff/PGM each airframe can carry instead of short-range or missing loadouts.
* **[Comms]** Preset radio channels (ATC, AWACS, tanker, package, JTAC) are also mirrored onto COMM2 on aircraft with a second radio (e.g. F/A-18C, F-16), so you can monitor two nets at once; the kneeboard shows both channels.
* **[IADS]** IADS infrastructure can be rebuilt: comms towers, power stations and command centres produce no income, so they had no repair price and stayed rubble for the rest of the campaign once bombed -- neither side ever restored its own network. They now cost a flat 15M (power station), 10M (command centre) or 5M (comms tower) to rebuild, and still generate no income, so striking the network becomes an attrition loop instead of a one-off: the SAMs behind a destroyed power station go dark and the owner has to pay to bring them back.
* **[IADS]** A destroyed IADS building now reads as destroyed rather than absent: skynet_nodes dropped any node or connection whose units were all dead, and Skynet treats a missing dependency as satisfied, so bombing a power station switched its SAMs back on the next mission and destroying a coalition's last command centre handed it perfect command back. Buildings keep reaching Skynet destroyed (a static spawned dead answers getByName=ok, isExist=false, life=0, which is what Skynet tests); vehicle-backed roles still drop out.
* **[Options]** New option to spawn TACAN beacons at captured airfields
* **[Options]** New Campaign Doctrine option so AI non-combat (crash) air losses don't count: only losses DCS attributes to a weapon or SAM deplete a squadron, and the debriefing shows how many were not counted. Applies to both coalitions.
* **[Cheat]** The money cheat can give or take money to both OWNFOR and OPFOR (previously OWNFOR only).
* **[Mission Status]** Mission result window splits every loss category into OwnFor (your faction) and OpFor (enemy) columns instead of a single combined total.
* **[AirWing]** Track per-squadron campaign aircraft stats (initial/destroyed/purchased, save-compatible) and expose pilot experience level and living/dead pilot views for the UI
* **[AirWing]** Squadron list shows living-pilot, aircraft and unassigned counts; squadron dialog shows each pilot's experience level, lists killed-in-action pilots separately and hides the redundant "Active" status
* **[AirWing]** Squadron dialog shows the aircraft type, an aircraft inventory (initial/current/destroyed/purchased), and buy/sell aircraft controls with price, on-order count and available parking slots
* **[AirWing]** Insufficient-parking warnings are consolidated into a single non-modal dialog that names the missing parking type and links each squadron to its dialog
* **[AirWing]** Air Wing list shows a "transfer ordered to X" indicator, and Airfield Command lists the units transferring into the base next turn
* **[AirWing]** Airfield Command shows idle aircraft per squadron (e.g. "20 (10 idle)") with a "transfer ordered to X" indicator, lets you open a squadron's dialog by clicking its name, and lays the count below the name so long text no longer adds a horizontal scrollbar
* **[BaseMenu]** Base intel summary shows aircraft occupied/transferring/free and a per-parking-type breakdown (shared / fixed-wing-exclusive / rotary-wing-exclusive / ground spawns), fixing the misleading "0 fixed-wing only parking" at bases whose slots are all shared
* **[Plugins]** Update EW Script to version 2.1
* **[Modding]** Add CurrentHill UK Assets Pack support (v1.1.2)
* **[Modding]** Add support for Su-35S mod (v2.0.27b)
* **[Modding]** Add support for the F-15EX Eagle II mod (by Spino).
* **[Modding]** Add support for the F-15C EG Golden Eagle mod (by Spino).
* **[Modding]** Add support for the Eurofighter Typhoon mod (by Lechuzas Negras).
* **[Data]** Add Refueling/Recovery tasks to A-6E Intruder mod
* **[Layouts]** Add signature to layouts' binary file for automatic reloading of updated layouts.
* **[Mission Generator]** New campaign setting "Default laser code for Player flights" controls whether newly-created player flights are assigned a unique allocated TGP/weapon laser code (the new default, matching existing behavior) or stay on 1688. When a code is allocated it is applied to both the TGP/kneeboard code and the weapon code by default, so LGBs home on the player's own code without extra clicks; both remain independently overridable in the payload tab.
* **[Engine]** Support for DCS 2.9.28.26283 including F-100D, F-14A (Export), and F-14BU.
* **[Options]** Add new option to fast forward until player is at the IP.
* **[Modding]** Update to CJS Super Hornet Mod to v2.4.5.260501.RC1
* **[Modding]** Update Community A4EC Mod to 2.3.0 (May 2025)
* **[Mission Generator]** Squadrons now spawn using the proper country instead of CTJF, enabling various DCS AI voiceovers
* **[Options]** New option to restrict helmet devices by date
* **[Flight Plans]** Renaming a waypoint in the flight-plan list now propagates to the aircraft CDU/HUD and the kneeboard, not just the list — one name in all three places (#695).
* **[Campaigns]** Ability to define motor pool objects which spawn reserve armor
* **[UX]** Show motorpool reserve, in-transit, and expected inventory in Qt and React views with live updates
* **[Mission Planning]** Autoplanner targets eligible motorpool reserve armor with prioritized armed-recon flights
* **[Campaigns]** Motorpool placement is Garage_A-anchored and empty reserve pools are excluded from attack planning; updated placement measurements are documented.
* **[UX]** Add the ability to filter campaigns by version, map, and performance
* **[Engine]** Bump campaign version to 10.9 for motorpool support
* **[Modding]** Update UH-60L mod to v2.1.5 including MH-60L DAP

## Fixes
* **[UX]** Editing a faction from the Air Wing dialog now takes effect in the running campaign; only preset-group changes did before.
* **[UX]** The faction editor's tick boxes did nothing outside the New Game wizard; entries have a remove button there instead, which refuses a unit the campaign still has deployed.
* **[UX]** The faction editor sorts its lists by the name shown rather than the internal DCS id.
* **[Mission Generation]** Fix mission generation dying on "Duplicate convoy unit": convoy and cargo-ship names no longer reset each turn onto a convoy still in transit.
* **[Mission Generator]** Dynamically allocated TACAN channels no longer collide with map beacons: DME/VOR-DME beacons (which share TACAN's channelization) are now blacklisted alongside TACAN/VORTAC, and beacons whose DCS data omits a channel (e.g. Syria's KALDE "KAD" VOR-DME) have their channel/band derived from the beacon's VHF frequency per the ICAO VOR/TACAN channelling plan instead of being silently skipped. The "Assign TACAN" dialog now warns in real time when the selected channel/band is already in use by a map beacon or another carrier/airfield/flight. (#36)
* **[Map]** Right-clicking a front line under a blue flight-plan route now opens the new-package dialog instead of the browser context menu (the route's invisible hover overlay swallowed the click).
* **[Mod Support]** Fix SA-10B/S-300PS sites never spawning at all: High Digit SAMs 2.1.0 dropped the whole S-300PS family, DCS silently discards a unit type it cannot resolve, and Escalation went on believing the site was alive. Now uses the stock S-300PS.

## Fixes
* **[Mission Generation]** Fix mission generation dying on "Duplicate convoy unit": convoy and cargo-ship names no longer reset each turn onto a convoy still in transit.
* **[Mod Support]** Fix SA-10B/S-300PS sites never spawning at all: High Digit SAMs 2.1.0 dropped the whole S-300PS family, DCS silently discards a unit type it cannot resolve, and Escalation went on believing the site was alive. Now uses the stock S-300PS.
* **[Data]** Fix the modern Spain faction's air defence: the WWII 2 cm Flak 38 needs the WWII Assets Pack, so without it DCS discarded every gun and the sites came up empty while Escalation counted them as defended. Spain operates neither the Soviet ZU-23 nor the US Avenger either, so its point defence is now the Stinger alone.
* **[Data]** The F-14A-135-GR Early's payload file declared the wrong unitType, so the Early Tomcat flew every tasking unarmed; its loadouts now resolve (with a guard test pinning the payload to the airframe). (#889)
* **[Mission Generator]** EWR sites now get the DCS "EWR" enroute task and come up on RED alarm, so their radars actually scan and report contacts (previously they could sit inert, especially with the "red alert state" performance option off). Works with or without the Skynet IADS plugin.
* **[Plugins]** Fix the escort leash never running (DCS has no `Group.getByID`; look the group up by name via mist), so escorts are actually held to their engagement range.
* **[Mission Planning]** Carrier/LHA targets now offer SEAD in the flight-task list and no longer list SEAD Escort twice (their escorts are SAM platforms, so they can be suppressed directly like any other naval group).
* **[App]** Escalation no longer stays alive in the background after its window is closed: the API server's graceful shutdown is now bounded (uvicorn otherwise waited forever on the long-lived event-stream websocket and the join hung).
* **[App]** Relaunching the executable while it is already running no longer spawns orphaned, windowless duplicate processes; a second instance detects the first via an OS file lock and exits immediately.
* **[App]** Upgrade PySide6/Qt to 6.8.3. On 6.4.x QtWebEngine composited the embedded map through the native desktop-OpenGL driver, whose context cleanup could deadlock (e.g. nvoglv64.dll DrvValidateVersion / WaitForSingleObject during window destroy) when a fullscreen GPU application — most notably DCS itself — took over the GPU, freezing Escalation. Qt 6.8 composites the web view via Direct3D 11 instead, so no native-GL context is created and the deadlock is gone (still hardware-accelerated). This also resolves the intermittent "Not Responding" freeze when a dialog/panel is shown over the map, which had the same root cause.
* **[Mission]** Reliably auto-detect end of mission, even when DCS wrote the final state.json before the wait dialog started watching
* **[Mission]** End-of-mission detection now finds DCS' state.json wherever the export hook actually wrote it (install dir, ESCALATION_EXPORT_DIR, TEMP, or the DCS Saved Games Missions folder) instead of only the working directory, polls more responsively, and logs the watched paths — fixing missions frequently not being detected as finished
* **[Mission]** Fix a crash when choosing "Fix TOTs automatically" in the past-start-times dialog at Take Off: the automatic fix called `TotEstimator.earliest_tot()` without the required current-time argument and raised a `TypeError`.
* **[AirWing]** Selling aircraft no longer lets the same units be re-sold (and re-flown) after a turn re-initialisation, which refunded their price repeatedly and could drive a squadron's aircraft count negative and then balloon it to ~airfield capacity on reload.
* **[AirWing]** Squadron transfer-destination parking now accounts for already-ordered incoming transfers, matching the Airfield Command hangar count
* **[UI]** Use Qt's non-native file dialogs (`AA_DontUseNativeDialogs`) so opening a file picker no longer freezes the whole app. The native Windows dialog deadlocks on a synchronous Win32 message when the embedded web map (QtWebEngine) is alive — e.g. clicking "Manually submit" on the modal "waiting for mission result" window hung Escalation ("Not Responding").
* **[UI]** Avoid a crash dialog ("'QWidgetItem' object has no attribute 'width'") when a list using the two-column row delegate relayouts with a malformed style option under PySide6 6.4.x.
* **[Kneeboard]** A dropped connection while fetching recon-kneeboard basemap tiles (e.g. `RemoteDisconnected`, which urllib does not wrap in `URLError`) no longer aborts mission generation at Take Off; the tile fetch now degrades to the offline basemap on any transient network error, with a last-resort backstop so a tile failure can never crash turn generation.
* **[Kneeboard]** Flight-plan kneeboard now matches the in-game waypoint numbering for flights that start in the air: previously it always listed the full plan from takeoff, so for an in-air start the kneeboard waypoints were offset from the cockpit's (e.g. kneeboard "1: Hold" while DCS showed "1: Escort Hold"). The kneeboard now starts at the spawn waypoint, like the generated mission.
* **[Kneeboard]** Stop the Support Info FREQ column being clipped now that it lists both COMM1 and COMM2 (the single-digit aircraft-count column no longer pads the row past the page edge).
* **[Comms]** Fix COMM1/COMM2 being swapped in the kneeboard for the Super Hornet family (EA-18G, F/A-18E/F and their tanker variants): align their radio indices to the F/A-18C so intra-flight is COMM2 and ATC/package are on COMM1.
* **[Mission Generation]** A malformed or unsupported aircraft payload file (e.g. a hand-written third-party mod file) no longer hides every payload for that airframe: the unparseable file is skipped and the rest -- including your own Mission-Editor-saved loadouts -- still load and are selectable. If none can be read, the aircraft falls back to an empty loadout instead of aborting turn generation, and the error is logged.
* **[Mission Generation]** Loadout payloads are saved atomically (write to a temp file, then rename), so mission generation or the payload editor never reads a half-written payload file.
* **[Mission Generation]** Fix the generated mission being rejected by DCS with "locked speed ... surrounded by waypoints ... with locked time" (e.g. carrier escorts).
* **[Mission Generation]** Anti-Ship flights now attack the carrier group the flight plan routes to instead of the control point's first ground object, so strikes against carrier groups no longer leave the AI without a target (it would fly to the ingress point and turn back without engaging).
* **[Mission Generation]** Anti-Ship flights now egress after expending their ordnance instead of continuing toward the enemy fleet (the attack task had no completion condition, so aircraft carrying only stand-off weapons such as the S-3B kept flying in after launching their missiles).
* **[Mission Generation]** Assign plane-specific laser codes to LGB weapons when building the mission
* **[Mission Planning]** Carrier/LHA targets now offer SEAD in the flight-task list and no longer list SEAD Escort twice (their escorts are SAM platforms, so they can be suppressed directly like any other naval group).
* **[Map]** Carrier/LHA control points now show their ship group on the map like other naval groups: the tooltip lists the carrier and escorts (with [DEAD] markers for losses), the surviving escorts' air-defense rings are drawn, and the status marker turns yellow while any ship survives instead of red as soon as the carrier itself is sunk.
* **[Flight Plans]** Player flights with a ground start (Cold/Warm/Runway) no longer spawn in the air when their computed startup time falls before mission start (e.g. due to a long player startup estimate); they now wait and start on the ground at mission start.
* **[Flight Plans]** Stabilized waypoint solver debug GeoJSON coordinate precision to avoid platform-specific floating point drift in debug output.
* **[Fast-forward]** Detect when the configured "Fast forward until" stop condition is unreachable for a player flight's start type (e.g. "Player startup time" with a runway or air start, which skip the Startup state) and prompt before launching the mission: per mismatched flight, the user can either downgrade the flight's start type to match the setting, or halt fast-forward at the flight's actual spawn instead, for this mission only. A hard tick ceiling also caps any remaining unreachable case as a back-stop, so the app can no longer hang on Take Off.
* **[Flight Plans]** Escorts assigned to an AWACS or tanker now hold on that flight's racetrack orbit instead of at the far-away target-relative escort-hold point, so they actually co-locate with and protect it.
* **[App]** Fix Escalation sometimes staying alive in the background after the window is closed.
* **[Performance]** Improved robustness w.r.t. state.json handling to avoid corruption and thus save loss.
* **[Performance]** Faster post-mission turn processing
* **[Engine]** Fixed a bug where squadrons could transfer to enemy owned control points
* **[Mission Generation]** Air assault drop-off zones are kept on land, so coastal objectives no longer drop the troops into the sea.
* **[Mission Generation]** Relocate ground units that spawn on inland water (ponds, rivers, lakes) to the nearest land at mission start, fixing armor and SAM sites spawning underwater (#59).
* **[Mission Generation]** Relocate ships that spawn on land (e.g. carrier escorts when the carrier hugs the shore) to the nearest deep water at mission start (#59).

# Escalation v1.5.0

## Features/Improvements
* **[Campaigns]** Ability to define invisible FOBs
* **[Campaigns]** Ability to define influence zones for Control Points
* **[Plugins]** Improvements to AI support for EW Script 2.0
* **[Plugins]** Add moose as a base plugin
* **[Config]** New preference setting to trigger the first-start window on every start (could help in scenarios multiple Escalation instances need to run concurrently)
* **[Modding]** Update Grinelli Designs F-22A Mod to 2.0.0 (May 2025)
* **[Campaign Design]** Added support for Germany Cold War terrain by Ugra Media
* **[Options]** New option to control EPLRS-task injection in mission generator
* **[Modding]** Add Tornado F3 ADV (v1.0, requires FC3 fix)
* **[Modding]** Add Military Aircraft Mod 1.7.2 (See VSN Discord)
* **[Payload Editor]** Add Sniper POD
* **[Modding]** Update SU-30 mod to v2.8.04 Beta + CWS 3.72
* **[Plugins]** EW Script - DEAD added to applicable flight types.
* **[Plugins]** EW Script - Offensive Jamming restricted to aircraft with ALQ99/249 pods, or "has_built_in_jamming: true" in aircarft yaml (AI and Player)
* **[Modding]** Update to CJS Super Hornet Mod v2.4.5
* **[Engine]** Support for DCS 2.9.20.15010, including MiG-29A Fulcrum support.
* **[Campaigns]** Ability to define neutral FOBs and Airfields
* **[Modding]** Add Airboss Moose Module
* **[AirWing]** Use aircraft display names for easier differentiation between modules
* **[Campaign]** Add ability to define livery overrides also for JTAC units
* **[Campaign]** Pretense generator now applies ground unit livery overrides to zone groups as well, such as SAM sites
* **[Plugins]** Added BigEye EWR Script
* **[Modding]** Update CurrentHill Russia Assets Pack to 2.0.0
* **[UI]** Add campaign name to escalation window name
* **[Plugins]** MooseAirboss - Added option to despawn stuck AI aircraft on the carrier
* **[Plugins]** MooseAirboss - Automatically set TACAN/ILS from escalation
* **[Modding]** Added VSN F-35A/B/C mod support
* **[Modding]** Add F-111C Aardvark by Warpig Productions (v2.260208)
* **[Data]** Added ability to restrict weapons usage for a faction to a different year from the nominal weapon introduction year. Updated faction data to restrict more advanced missiles from Soviet client states during the cold war. Updated Egypt 2000 faction to restrict AIM-120 usage.
* **[Modding]** Update OH-6A mod to v1.7
* **[Engine]** Support for custom weapon settings, including settings overrides per target.

## Fixes
* **[Flight Plans]** Fixed bugs wrt planning escort flights
* **[Flight Plans]** Added AntiShipStrike as a fallback task for OCA/Aircraft to fix a bug where the S-3B could not do OCA/Aircraft
* **[Squadrons]** Fixed a bug where loading an air wing config would not properly load all squadrons
* **[Flight Plans]** Fixed a bug where SEAD flights would fire one ARM and RTB
* **[Plugins]** EW Script - Fix radar detection routine.
* **[Campaign]** Fixed a bug where sinking a destroyer in a carrier group would cause squadrons to be removed from the carrier
* **[Engine]** Fixed a bug with transfers to Helipads
* **[Engine]** Fixed a bug with parking allocation
* **[Flight Plans]** Fixed a bug where divert airfield was broken for opfor
* **[Engine]** Fixed a bug with state.json loading wrt transfers
* **[Engine]** Fixed a bug wrt pretense generation and moose script conflicts
* **[Engine]** Fixed a bug where frontline debriefing was not properly calculated
* **[Mission Generation]** Fixed an issue where blue and red units spawned next to each other on frontlines
* **[Mission Generation]** Fixed an issue where kneeboards showed both opfor and ownfor support aircraft
* **[Campaigns]** Fixed a bug where off map spawns could own ground objects, causing them not to spawn
* **[Performance]** Adjusted state.json writes to batch processing to reduce CPU utilization
* **[Kneeboard]** Fixed bug where additional target points did not show on the kneeboard

# Escalation v1.4.1 (hotfix)

## Fixes
* **[Plugins]** Avoid injecting jamming-tasks for player-controller aircraft when EW-Jamming plugin is disabled


# Escalation v1.4.0

## Features/Improvements
* **[Payload Editor]** Ability to configure liveries on flight/flight-member level
* **[Factions]** Support for definitions in yml/yaml format
* **[Campaigns/Factions]** Support for inline recommended faction in campaign's yaml file
* **[Squadrons]** Ability to define a livery-set for each squadron from which Escalation will randomly choose during mission generation
* **[Modding]** Updated support for F/A-18E/F/G mod version 2.2.5
* **[Modding]** Added VSN F-106 Delta Dart mod support (v2.9.4.101)
* **[Modding]** Added OH-6 Cayuse (v1.2) mod support, including the Vietnam Asset Pack v1.0
* **[Modding]** Added VSN EA-6B Prowler mod support (v2.9.4.102)
* **[Modding]** Added tripod3 Cold War assets mod support (v1.2)
* **[Modding]** Added VSN Mirage III mod support (2.5.7.01)
* **[Campaign Setup]** Allow adjustments to naval TGOs (except carriers) on turn 0
* **[Campaign Design]** Ability to configure specific carrier names & types in campaign's yaml file 
* **[Mission Generation]** Ability to inject custom kneeboards
* **[Options]** Extend option (so it can be disabled when fixed in DCS) to force air-starts (except for the slots that work) at Ramon Airbase, similar to the Nevatim fix in Escalation 1.3.0
* **[Options]** New option in Settings: Default start type for Player flights.
* **[AirWing]** Expose OPFOR Squadrons, giving the ability to change liveries, auto-assignable mission types & an easy way to retrieve debug information.
* **[ATO]** Allow planning as OPFOR
* **[Campaign Design]** Support for latest maps (Kola, Afghanistan, Iraq)
* **[UI]** Zoom level retained when switching campaigns
* **[UX]** Allow changing squadrons in flight's edit dialog
* **[Cheats]** Sink/Resurrect carriers instead of showing an error during cheat-capture (use AWCD-cheat to add squadrons upon resurrection)
* **[UI/UX]** Allow changing conditions such as Time, Date & Weather
* **[Modding]** Added support for Su-15 Flagon mod (v1.0)
* **[Plugins]** Support for Carsten's Arty Spotter script
* **[Plugins]** Support for MBot's Call Artillery script (using on-map artillery)
* **[Modding]** Added support for SK-60 mod (v1.2.1)
* **[Mission Generation]** Introducing the Armed Recon flight plan, i.e. CAS against any Theater Ground Object
* **[Doctrine]** Ability to customize the startup time allocated to the player
* **[Mission Generation]** Ability to choose whether player flights can spawn on the sixpack or not
* **[Options]** New options in Mission Generator section: Limit AI radio callouts & Suppress AI radio callouts.
* **[Options]** New option to use the combat landing flag in the landing waypoint task for helicopters.
* **[UI/UX]** Sync package waypoints when primary flight's waypoints are updated and recreate other flights within the package to ensure JOIN, INGRESS & SPLIT are synced
* **[UI/UX]** Allow changing loadout on flight creation
* **[UI]** Display TOT for all waypoints in the flight plan
* **[UI]** Edit basic datalink properties for applicable aircraft
* **[Mission Generation]** Automatic datalink network setup for applicable aircraft (_should_ in theory avoid the need to re-save the mission)
* **[Options]** New option to force-enable deck-crew for super-carriers on dedicated server.
* **[Mission Generation]** Enable Supercarrier's LSO & Airboss stations
* **[UX]** Default settings are now loaded from Default.zip
* **[Autoplanner]** Plan Air-to-Air Escorts for AWACS & Tankers
* **[Package Planning]** Ability to plan recovery tanker flights
* **[Modding]** Support for Bandit's cloud presets mod (v15)
* **[UX]** Reduce size of save-file by loading landmap data on the fly, which also implies no new campaign needs to be started to benefit from an updated landmap
* **[New Game Wizard]** Ability to save an edited faction during new game creation
* **[Options]** New option to make AI helicopters prefer vertical takeoff and landing
* **[Campaign Design/Mission Generation]** Introduction of "rebel zones" which randomly spawn units according to the campaign's definitions.
* **[Mission Generation]** Missile sites now fire at random times instead of all at the beginning of the mission
* **[Modding]** Support for CurrentHill's Chinese Asset Pack (v1.1.4)
* **[Modding]** Updated support for CurrentHill's Swedish Asset Pack (v1.1.0)
* **[Modding]** Support for CurrentHill's Russian Asset Pack (v1.2.0)
* **[Modding]** Support for CurrentHill's USA Asset Pack (v1.1.5)
* **[Modding]** Update CJS Super Hornet to 2.4.2
* **[Modding]** Support for Cowboy's E-7A Wedgetail mod (Supports EW Script Offensive Jamming)
* **[Modding]** Support for szcz's MiG-31BM (v2.0)
* **[Plugins]** Added initial AI support for EW Script 2.0
* **[Options]** Ability to configure certain forced-options via a file (WIP: https://github.com/dcs-retribution/dcs-retribution/issues/490).

## Fixes
* **[UI/UX]** A-10A flights can be edited again
* **[Mission Generation]** IADS bug sometimes triggering "no skynet usable units" error during mission generation
* **[New Game Wizard]** Campaign errors show a dialog again and avoid CTDs
* **[UI]** Landmap wasn't updating when switching to a different theater
* **[Mission Results Processor]** Squadrons of a sunken carrier are now disbanded
* **[Mission Generation]** Introduced option to switch alt-type to AMSL during mission generation to avoid helicopters wanting to submerge over certain parts of the sea.

# Escalation v1.3.1
#### Note: Re-save your missions in DCS' Mission Editor to avoid possible crashes due to datalink (usually the case when F-16C blk50s are used) when hosting missions on a dedicated server.

## Fixes
* **[UX]** Fix save-compatibility issue
* **[UX]** Avoid crash on startup due to incompatible save


# Escalation v1.3.0
#### Note: Re-save your missions in DCS' Mission Editor to avoid possible crashes due to datalink (usually the case when F-16C blk50s are used) when hosting missions on a dedicated server.

## Features/Improvements
* **[Engine]** Support for DCS v2.9.3.51704
* **[Package Planning]** Option to "Auto-Create" package
* **[Modding]** Custom weapons injection system (definition in aircraft's yaml file)
* **[Payload Editor]** Ability to save/back-up payloads
* **[Options]** New option in Settings: CAS engagement range (nmi)
* **[Options]** New option in Settings: Convert untasked OPFOR aircraft into client slots
* **[Options]** Split the **Disable idle aircraft at airfields** setting into **Disable untasked BLUFOR aircraft at airfields** and **Disable untasked OPFOR aircraft at airfields**
* **[Options]** Split off the **Automatic AWACS package planning** and **Automatic Theater tanker package planning** settings from **Automatic package planning behavior** so players can choose to have AWACS and theater tankers auto-planned, while managing everything else themselves
* **[Modding]** Updated support for Su-30 mod to V2.7.3 Beta
* **[Modding]** Updated support for Su-57 mod to build-04
* **[Modding]** Updated support for F-4B/C Phantom mod to 2.8.7.204
* **[Modding]** Updated Community A-4E-C mod version support to 2.2.0 release.
* **[Modding]** Added F/A-18E/F Super Hornet AI Tanker mod support (Chiller Juice Studios SuperBug Tanker AI version 1.4)
* **[Modding]** Added VSN Super Étendard mod support (v2.5.5)
* **[Modding]** Added F9F Panther mod support (version v2.8.7.101)
* **[Modding]** Updated Irondome support to IDF Assets Pack V1.1, adding support for the David's Sling
* **[Radios]** Added HF-FM band for AN/ARC-222
* **[Radios]** Ability to define preset channels for radios on squadron level (for human pilots only)
* **[Mission Planning]** Avoid helicopters being assigned as escort to planes and vice-versa
* **[Mission Planning]** Allow attack helicopters to escort other helicopters
* **[UI]** Allow changing waypoint names in FlightEdit's waypoints tab
* **[Waypoints]** Allow user to add navigation waypoints where possible without degrading to a custom flight-plan
* **[Campaign Management]** Improve squadron retreat logic to account for parking-slot sizes
* **[Autoplanner]** Support for auto-planning Air Assaults
* **[UI]** Improved frequency selector to support all modeled bands for every aircraft's intra-flight radio
* **[Options]** New options in Settings: Helicopter waypoint altitude (feet AGL) for combat & cruise waypoints
* **[Options]** New options in Settings: Spawn ground power trucks at ground starts in airbases/roadbases
* **[Options]** Option for hiding TGOs (with IADS roles) on MFD
* **[Plugins]** Splash Damage 2.1 with Clusters and Ship Radar effects.
* **[COMMs]** Aircraft-specific callsigns will now also be used.
* **[COMMs]** Ability to set a specific callsign to a flight.
* **[Mission Generator]** Channel terrain fix on exclusion zones, sea zones and inclusion zones
* **[Options]** Cheat-option for accessing Air Wing Config Dialog after campaign start (re-initializes turn if applied, thus plan your mission ___after___ making changes)
* **[Options]** Option to enable unlimited fuel for AI (player and non-player flights)
* **[Mission Generator]** F-15E Strike targets are automatically added as Mission Set 1 
* **[Mission Generator]** Set F-14's IP waypoint according to the flight-plan's ingress point
* **[Mission Generator]** Automatically de-spawn aircraft when arrival/divert is an off-map spawn
* **[Options]** Option to de-spawn AI flights in the air if their start-type was manually set to In-Flight
* **[Campaign Design]** Ability to add separate ground spawns for C-130 and other large aircraft to campaigns.
* **[Config]** Preference setting to use custom Liberation payloads instead of prioritizing Escalation's default
* **[Config]** Preference setting to configure the server-port on which Escalation's back-end will run
* **[Options]** Made AI jettisoning empty fuel tanks optional (disabled by default)
* **[Options]** Add option (so it can be disabled when fixed in DCS) to force air-starts (except for the slots that work) at Nevatim due to https://forum.dcs.world/topic/335545-29-nevatim-ramp-starts-still-bugged/
* **[Cheat]** Add cheat option to manually manage REDFOR's TGOs
* **[UX]** Buy/Replace TGOs for free before the campaign has started
* **[Data]** Ability to define "cruise" & "combat" altitudes for airplanes
* **[Options]** Option to randomize altitudes for flights with airplanes
* **[Options]** Options to configure/override maximum mission distance for airplanes & helicopters 

## Fixes
* **[Mission Generation]** Anti-ship strikes should use "group attack" in their attack-task
* **[New Game Wizard]** Faction selection overview doesn't update when inverting map
* **[New Game Wizard]** Aircraft mods are now handled better when they are disabled
* **[Payloads]** Added/Updated (missing) payloads
* **[Aircraft Tasking]** Revised aircraft tasking, filtering out incompatible tasks for several aircraft
* **[Data]** Corrected the class of the USS Samuel Chase from Logistics to LandingShip, in order to prevent it being spawned as part of AAA sites.
* **[Mission Generation]** Helicopters oscillating due to over-speeding
* **[Mission Generation]** Fix infinite loop when using "Fast-Forward to first contact"
* **[Capture Logic]** Release all parking slots when an airbase is captured
* **[Modding]** Swedish Military Assets Pack air defence presets are now correctly removed from the faction when the mod is disabled.
* **[Mission Generation]** Naval aircraft not always returning to carrier
* **[Mission Generation]** AI AirLift aircraft crashing into terrain due to insufficient waypoints
* **[Mission Generation]** Fix friendly AI shooting at fires on the front-line

# Escalation v1.2.1 (hotfix)

## Fixes
* **[Flight Plans]** SEAD Sweep not being auto-planned
* **[Modding]** Python-4 no longer overwrites AIM-9X
* **[Modding]** Restore original amount of pylons to F-16C when "ejecting" sufa mod

# Escalation v1.2.0

## Features/Improvements
* **[Preset Groups]** Add SA-2 with ZSU-23/57
* **[Campaign Design]** Ability to define almost all possible settings in the campaign's yaml file.
* **[Campaign Design]** Ability to add roadbases and/or ground spawns to campaigns.
* **[Campaign Design]** Ability to define SCENERY REMOVE OBJECTS ZONE triggers with the roadbase objects in campaign miz. This might not work reliably in multiplayer due to DCS issues. FARPs can be used to remove scenery objects in multiplayer.
* **[Options]** Implemented an option in settings to disable the above SCENERY REMOVE OBJECTS ZONE triggers.
* **[Campaign Management]** Improved squadron retreat logic at longer ranges.
* **[Options]** Ability to load & save your settings.
* **[Options]** Added a separate Doctrine page in settings with the following new options:
  * Minimum number of aircraft for autoplanner to plan OCA packages against 
  * Airbase threat range (nmi)
  * SEAD Sweep threat buffer distance (nmi)
  * SEAD Escort/Sweep threat buffer distance (nmi)
  * TARCAP threat buffer distance (nmi)
  * AEW&C threat buffer distance (nmi)
  * Theater tanker threat buffer distance (nmi)
* **[Options]** Improved the option to configure OPFOR autoplanner aggressiveness. The AI might now take even more risks and plan missions against defended targets.
* **[Options]** Added three new options in Settings:
  * Autoplanner plans refueling flights for Strike packages
  * Autoplanner plans refueling flights for OCA packages
  * Autoplanner plans refueling flights for DEAD packages
* **[UI]** Added fuel selector in flight's edit window.
* **[Plugins]** Expose Splash Damage's "game_messages" option and set its default to false.
* **[Mission Generation]** Improved AI SEAD capabilities, allowing for mixed loadouts using Decoys, ARMs & ASMs.
* **[Modding]** Support for A-7E Corsair II (presumed latest available version)
* **[Squadrons]** Added many new squadron's by Adecarcer
* **[Plugins]** Updated 'expl_table' in Splash Damage script.
* **[Mission Generation]** Also save kneeboards in txt-format, found under "kneeboards" within Escalation's installation folder after pressing take-off.
* **[Modding]** Support for SW mod v2.55
* **[Modding]** Support for Spanish & Australian Naval Assets v3.2.0 by desdemicabina
* **[Modding]** Support for Iron Dome v1.2 by IDF Mods Project
* **[New Game Wizard]** Re-organized generator options & show the regular settings menu instead of the limited "Difficulty & Automation" page.
* **[Campaign Management]** Ability to operate harriers from FOBs/FARPs for <ins>__human pilots only__</ins>. Please note that the autoplanner won't generate flights for harriers at FOBs/FARPs, which means you need to plan your missions manually.
* **[Mission Planning]** Allow NAV/REFUEL/DIVERT waypoints to be deleted without degrading to a custom flight-plan, also warning the user before actually degrading the flight-plan.
* **[Campaign Generation]** Split "full-strength start" from "squadron aircraft limits" option.
* **[Mission Generation]** General improvement w.r.t. DCS tasking, including a check for incompatible tasking.
* **[Mission Generation]** OCA-Runway flights will remain at altitude when using guided bombs.
* **[UX]** Added error message to indicate save-compatibility issues + fix to avoid total crash upon loading of last save.
* **[UI]** Improved parking space information in air wing configuration dialog.
* **[Squadrons]** Warning messages when opening up a squadron through the air wing dialog, indicating squadrons that potentially won't fit w.r.t. parking space.
* **[Squadrons Transfers]** Determine number of available parking slots more accurately w.r.t. squadron transfers, taking aircraft dimensions into account which should prevent forced air-starts.
* **[UX]** Allow usage of CTRL/SHIFT modifiers in ground unit transfer window.
* **[Campaign Design]** Ability to define "spawn-routes" for convoys, allowing them to start from the road without having to edit the mission
* **[Plugins]** Added "DCS Dismount" plugin.
* **[Plugins]** Added "EWR Jammer" plugin (only for humans, may change in the future).
* **[Campaign]** New campaign (Operation Desert Sabre) by Chimiste
* **[Plugins]** Updated CTLD to latest released version
* **[Options]** Renamed Maximum frontline length -> Maximum frontline width.
* **[Squadrons]** Add livery selector in Squadron Dialog, allowing you to change the livery during the campaign.
* **[New Game Wizard]** Automatically invert factions when 'Invert Map' is selected.
* **[Flight Plans]** Added "SEAD Sweep" flight plan, which basically reintroduces the legacy "SEAD Escort" flight plan where the flight will engage whatever it can find without actually escorting the primary flight.
* **[Flight Plans]** Added SEAD capability to F-16A MLU and SEAD Escort & SEAD to F-16A. 
* **[Mission Generation]** Spawn unused helicopters or LHA-capable aircraft at helipads at FOBs
* **[Modding]** Support for F-15I Ra'am v1.0 by IDF Mods Project

## Fixes
* **[New Game Wizard]** Settings would not persist when going back to a previous page (obsolete due to overhaul).
* **[Mission Generation]** Unused aircraft are no longer claimed, fixing a bug where these aircraft would no longer be available after aborting the mission.
* **[Mission Generation]** Fixed (potential) bug in helipad assignments at FOBs/FARPs.
* **[Mission Generation]** Fix AI immediately returning to base when forced to air-start due to insufficient parking space.
* **[Modding]** Fixed a bug where F-16Ds were not correctly removed from the faction when the F-16I/F-16D mod was not selected
* **[UI]** Fixed F-16A MLU icon and banner.

# Escalation v1.1.1  (hotfix)

## Features/Improvements
* **[Modding]** Support for IDF Mod Project F-16I Sufa & F-16D v3.6 mod
* **[Modding]** Support for JAS-39 Gripen v1.8.5-beta mod

## Fixes
* **[Plugins]** Fix bug where changes to plugin options doesn't do anything.
* **[Campaign Management]** Fix bug in procurement when no squadrons are present.
* **[Layouts]** Fix edge-case bug layout's group size.
* **[Campaign Design]** Preset groups assigned to specific TGOs not working as intended.

# Escalation v1.1.0

## Features/Improvements
* **[Mission Generation]** Given a CAS flight was planned, delay ground force attack until first CAS flight is on station
* **[Mission Generation]** Add option to switch ATFLIR to LITENING automatically for ground based F/A-18C flights
* **[Mission Generation]** Add option to configure OPFOR autoplanner aggressiveness and have the AI take risks and plan missions against defended targets
* **[Mission Generation]** Add option to configure the desired tanker on-station time in settings
* **[Mission Generation]** Reserve GUARD frequency on VHF/UHF
* **[Mission Generation]** Randomization in radio frequency allocation
* **[Mission Generation]** Configurable number of Combined Arms slots
* **[Mission Generation]** Enable spectating & F11 free camera when the "Allow external views" option is selected
* **[Cheat Menu]** Option to instantly transfer squadrons across bases.
* **[Modding]** Support for IDF Mod Project F-16I Sufa & F-16D v3.2 mod
* **[Modding]** Support for F/A-18E/F/G mod version 2.1
* **[Modding]** Support for Swedish Military Assets for DCS by Currenthill Version 1.10
* **[UI]** Add selectable units in faction overview during campaign generation.
* **[UI]** Add button to rename pilots in Air Wing's Squadron dialog.
* **[UI]** Add clone buttons for flights & packages.
* **[UI]** Editing of flight's custom name.
* **[UI]** Introduce custom names for packages (purely for organizational purposes).
* **[UI]** Configurable UHF frequency (225-400MHz) for Packages, Carriers, LHAs, FOBs & FARPs.
* **[UI]** Configurable Intra-Flight frequency for Flights.
* **[UI]** Configurable TACAN for Carriers, LHAs & Tankers.
* **[UI]** Configurable ICLS for capable Carriers & LHAs.
* **[UI]** Configurable LINK4 for Carriers.
* **[Kneeboard]** Show package information in Support page
* **[Kneeboard]** Show extra weather information on 'Mission info' page
* **[Kneeboard]** Show BRC in 'RWY' column for aircraft carriers on 'Mission info' page
* **[Campaign Design]** Ability to define designated CTLD zones for Control Points (Airbases & FOBs/FARPs)
* **[Campaign Design]** Ability to define preset groups for specific TGOs, given the preset group is accessible for the faction and the task matches.
* **[Campaign Management]** Additional options for automated budget management.
* **[Campaign Management]** New options to allow more control of randomized flight sizes (applicable for BARCAP/CAS/OCA/ANTI-SHIP).
* **[Plugins]** Updated Splash Damage script to v2.0 by RotorOps.
* **[Mission Generation]** Improvements to DEAD & STRIKE flights, allowing AI to handle a larger variety of weapons.
* **[Campaign]** New campaign (1968 Yankee Station) by Adecarcer

## Fixes
* **[UI]** Removed deprecated options
* **[UI]** Add missing icon & banner for C130 Hercules mod
* **[Mission Generation]** Avoid aircraft from being assigned to helicopter parking spots, resulting into air starts that usually crash.
* **[Mission Generation]** Use stacking algorithm to create vertical separation between flights spawning mid-mission over their departure, usually resulting into mid-air collisions.
* **[Mission Generation]** Fixed all callsigns being "Enfield 1-1" on dedicated servers.
* **[Mission Generation]** Fixed AI ferry flights for helicopters when transferring to a FOB/FARP.
* **[Mission Generation]** Fixed 'Uninitialized flight' exception when adding flights after aborted take-off.
* **[Modding]** Fixed conflicts caused by HDS units
* **[UX]** Gracefully handle corrupted preferences file.
* **[Mission Generation]** Aircraft not using decoys during SEAD.

# Escalation v1.0.1 (hotfix)
* **[Mission Generation]** Fix serialization issue when STRIKE flight has no escorts

# Escalation v1.0.0

## Features/Improvements
* **[Engine]** Support for DCS v2.8.1.34437.
* **[Briefing]** Add tanker info to mission briefing
* **[Campaign]** Add 5 new campaigns by Oscar Juliet from WRL
* **[Campaign]** Add ability to define livery overrides also for ground/naval units
* **[Data]** Added data to support C-47 Skytrain.
* **[Data]** Added data to support F-16A MLU.
* **[Data]** Added data to support KS-19 & SON-9, including support for "AAA Site" layout.
* **[Mission Generation]** Add option to configure the maximum front-line length in settings
* **[Mission Generation]** Use Escort & SEAD tasks for Escort & SEAD Escort flights
* **[Mission Generation]** Variable flight-size (2/3/4-ship) for 
BAI/ANTISHIP/DEAD/STRIKE/BARCAP/CAS/OCA/AIR-ASSAULT (main) missions
* **[Mission Generation]** Add option to only generate night missions
* **[Modding]** Support for F-15D 'Baz' mod version 1.0
* **[Modding]** Support for Su-30 mod version 2.01B
* **[Modding]** Support for A-6A Intruder version 2.7.5.01
* **[Modding]** Support for F-4B Phantom II mod version v2.7.10.02, patch 2022.10.02
* **[Modding]** Support for F-100 Super Sabre mod versions v2.7.18.01 & 2.7.18.30765 and patch 20.10.22
* **[Modding]** Support for F-105 mod version 2.7.12.23x
* **[Modding]** Support IDF Mod Project F-16I Sufa & F-16D v2.2 mod
* **[Modding]** Support for F-84G mod version 2.5.7.01
* **[Modding]** Updated F-104 mod version support to 2.7.11.222.01
* **[Modding]** Updated Community A-4E-C mod version support to 2.1.0 release.
* **[UI]** Add livery selector to Air Wing Configurator's squadrons.
* **[Performance]** Added performance option: Maximum front-line unit supply per control point.
* **[Performance]** Added performance option: Disable convoys.
* **[Performance]** Added performance option: Front-line troops prefer roads.
* **[Performance]** Added performance option: Disable idle aircraft at airfields.
* **[Squadrons]** Squadron pilot limits enabled by default.
* **[UI]** Add livery selector to Air Wing Configurator's squadrons.

## Fixes

* **[Mission Generation]** Fixed issue where aircraft carriers would return after being killed.
* **[Mission Generation]** Kneeboard STRIKE coordinates would sometimes get clipped when not fitting.
* **[UI]** Fix exception when trying to add a waypoints to a flightplan.


# Liberation:
## Features/Improvements

* **[Data]** Added support for the ARA Veinticinco de Mayo.
* **[Data]** Changed display name of the AI-only F-15E Strike Eagle for clarity.
* **[Flight Planning]** Improved IP selection for targets that are near the center of a threat zone.
* **[Flight Planning]** Moved CAS ingress point off the front line so that the AI begins their target search earlier.
* **[Flight Planning]** Loadouts and aircraft properties can now be set per-flight member. Warning: AI flights should not use mixed loadouts.
* **[Flight Planning]** Laser codes that are pre-assigned to weapons at mission start can now be chosen from a list in the loadout UI. This does not affect the aircraft's TGP, just the weapons. Currently only implemented for the F-15E S4+ and F-16C.
* **[Mission Generation]** Configured target and initial points for F-15E S4+.
* **[Modding]** Factions can now specify the ship type to be used for cargo shipping. The Handy Wind will be used by default, but WW2 factions can pick something more appropriate.
* **[Modding]** Unit variants can now set a display name separate from their ID.
* **[UI]** An error will be displayed when invalid fast-forward options are selected rather than beginning a never ending simulation.
* **[UI]** Added cheats for instantly repairing and destroying runways.
* **[UI]** Improved usability of the flight properties UI. It now shows human-readable names and uses more appropriate UI elements.
* **[UI]** The map now shows the real front line bounds.

## Fixes

* **[Campaign]** Fixed error when canceling squadron transfer if the current location would be exactly full.
* **[Data]** Fixed the class of the Samuel Chase so it can't be picked for a AAA or SHORAD site.
* **[Data]** Allow CH-47D, CH-53E and UH-60A to operate from carriers and LHAs.
* **[Data]** Added the F-15E's LANTIRN to the list of known targeting pods. Player F-15E flight with TGPs will now be assigned laser codes.
* **[Flight Planning]** Patrolling flight plans (CAS, CAP, refueling, etc) now handle TOT offsets.
* **[Mission Generation]** Restored previous AI behavior for anti-ship missions. A DCS update caused only a single aircraft in a flight to attack. The full flight will now attack like they used to.
* **[Mission Generation]** Fix generation of OCA Runway missions to allow LGBs to be used.
* **[Mission Generation]** Fixed AI flights flying far too slowly toward NAV points.
* **[Mission Generation]** Fixed "division by zero" error on mission generation when a flight has an "In-Flight" start type and starts on top of a mission waypoint.
* **[Modding]** Unit variants can now actually override base unit type properties.
* **[Plugins]** Fixed Lua errors in Skynet plugin that would occur whenever one coalition had no IADS nodes.
* **[UI]** Fixed deleting waypoints in custom flight plans deleting the wrong waypoint.
* **[UI]** Fixed flight properties UI to support F-15E S4+ laser codes.
* **[UI]** Fixed UI bug where altering an "ahead of package" TOT offset would change the offset back to a "behind pacakge" offset.
* **[UI]** Fixed bug where changing TOT offsets could result in flight startup times that are in the past.
* **[UI]** Flight plan paths are now drawn behind all other map elements, fixing rare cases where they could prevent other UI elements from being clickable.

# 8.1.0

Saves from 8.0.0 are compatible with 8.1.0

## Features/Improvements

* **[Engine]** Support for DCS 2.8.6.41363, including F-15E support.
* **[UI]** Flight loadout/properties tab is now scrollable.

## Fixes

* **[Campaign]** Fixed liveries for premade squadrons all being off-by-one.
* **[UI]** Fixed numbering of waypoints in the map and flight dialog (first waypoint is now 0 rather than 1).

# 8.0.0

Saves from 7.x are not compatible with 8.0.

## Features/Improvements

* **[Engine]** Support for DCS 2.8.6.41066, including the new Sinai map.
* **[UI]** Limited size of overfull airbase display and added scrollbar.
* **[UI]** Waypoint altitudes can be edited in Waypoints tab of Edit Flight window.
* **[UI]** Moved air wing and transfer menus to the toolbar to improve UI fit on low resolution displays.
* **[UI]** Added basic game over dialog.

## Fixes

* **[Campaign]** Fix bug introduced in 7.0 where map strike target deaths are no longer tracked.
* **[Mission Generation]** Fix crash during mission generation caused by out of date DCS data for the Gazelle.
* **[Mission Generation]** Fix crash during mission generation when DCS beacon data is inconsistent.

# 7.1.0

Saves from 7.0.0 are compatible with 7.1.0

## Features/Improvements

* **[Factions]** Replaced Patriot STRs "EWRs" with AN/FPS-117 for blue factions 1980 or newer.
* **[Mission Generation]** Added option to prevent scud and V2 sites from firing at the start of the mission.
* **[Mission Planning]** Per-flight TOT offsets can now be set in the flight details UI. This allows individual flights to be scheduled ahead of or behind the rest of the package.
* **[UI]** Waypoint altitudes can be edited in Waypoints tab of Edit Flight window.
* **[UI]** Parking capacity of each squadron's base is now shown during air wing configuration to avoid overcrowding bases when beginning the game with full squadrons.

## Fixes

* **[Mission Planning]** BAI is once again plannable against missile sites and coastal defense batteries.
* **[UI]** Fixed formatting of departure time in flight details dialog.

# 7.0.0

Saves from 6.x are not compatible with 7.0.

## Features/Improvements

* **[Engine]** Support for DCS 2.8.3.37556.
* **[Engine]** Saved games are now a zip file of save assets for easier bug reporting. The new extension is .liberation.zip. Drag and drop that file into bug reports.
* **[Campaign]** Added options to limit squadron sizes and to begin all squadrons at maximum strength. Maximum squadron size is defined during air wing configuration with default values provided by the campaign.
* **[Campaign]** Added handling for more DCS death events. This probably does not catch any deaths that weren't previously tracked, but it should record them sooner, which will improve results for game crashes or other early exits.
* **[Campaign AI]** The campaign AI now prefers fulfilling missions with squadrons which have a matching primary task. Previously distance from target held a stronger influence than task preference. Primary tasks for squadrons are set by campaign designers but are user-configurable.
* **[Flight Planning]** Package TOT and composition can be modified after advancing time in Liberation.
* **[Mission Generation]** Units on the front line are now hidden on MFDs.
* **[Mission Generation]** Preset radio channels will now be configured for both A-10C modules.
* **[Mission Generation]** The A-10C II now uses separate radios for inter- and intra-flight comms (similar to other modern aircraft).
* **[Mission Generation]** Wind speeds no longer follow a uniform distribution. Median wind speeds are now much lower and the standard deviation has been reduced considerably at altitude but increased somewhat at MSL.
* **[Mission Generation]** Improved task generation for SEAD flights carrying TALDs.
* **[Mission Generation]** Added task timeout for SEAD flights with TALDs to prevent AI from overflying the target.
* **[Modding]** Updated Community A-4E-C mod version support to 2.1.0 release.
* **[Modding]** Add support for VSN F-4B and F-4C mod.
* **[Modding]** Aircraft task capabilities and preferred aircraft for each task are now moddable in the aircraft unit yaml files. Each aircraft has a weight per task. Higher weights are given higher preference.
* **[Modding]** The `mission_types` field in squadron files has been removed. Squadron task capability is now determined by airframe, and the auto-assignable list has always been overridden by the campaign settings.
* **[Modding]** Wind speed generation inputs are now moddable. See https://dcs-liberation.rtfd.io/en/latest/modding/weather.html.
* **[New Game Wizard]** Choices for some options will be remembered for the next new game. Not all settings will be preserved, as many are campaign dependent.
* **[New Game Wizard]** Lua plugins can now be set while creating a new game.
* **[New Game Wizard]** Squadrons can be directly replaced with a preset during air wing configuration rather than needing to remove and create a new squadron.
* **[New Game Wizard]** Squadron liveries can now be selected during air wing configuration.
* **[Squadrons]** Squadron-specific mission capability lists no longer restrict players from assigning missions outside the squadron's preferences.
* **[New Game Wizard]** Squadrons can be directly replaced with a preset during air wing configuration rather than needing to remove and create a new squadron.
* **[UI]** The orientation of objects like SAMs, EWRs, garrisons, and ships can now be manually adjusted.

## Fixes

* **[Campaign]** Fixed a longstanding bug where oversized airlifts could corrupt a save with empty convoys.
* **[Campaign]** Aircraft with built-in TGPs but without an external pod will no longer degrade automatic loadouts to iron bombs.
* **[Engine]** Fixed crash in startup caused by a corrupted Liberation preferences file.
* **[Flight Planning]** AEW&C missions are now plannable over FOBs and LHAs.
* **[Flight Planning]** BAI is no longer plannable against buildings.
* **[Modding]** Fixed an issue where Falklands campaigns created or edited with new versions of DCS could not be loaded.
* **[Modding]** Fixed decoding of campaign yaml files to use UTF-8 rather than the system locale's default. It's now possible to use "Bf 109 K-4 Kurfürst" as a preferred aircraft type.
* **[Mission Generation]** Planes will no longer spawn in helipads that are not also designated for fixed wing parking.
* **[Mission Generation]** Potentially an issue where ground war planning game state could become corrupted, preventing mission generation.
* **[Mission Generation]** Refueling tasks will now only be created for flights that have a tanker in their package.
* **[Mission Generation]** Fixed missing Tanker task on recovery tanker missions.
* **[UI]** Fixed error when resetting air wing configuration during game setup.
* **[UI]** Fixed flight plan recreation when changing mission type with "Recreate as" flight options.
* **[UI]** Fixed failure to launch UI when Liberation persistent preferences file was corrupt.


# 6.1.1

## Fixes

* **[Data]** Fixed unit ID for the KS-19 AAA. KS-19 would not previously generate correctly in missions. A new game is required for this fix to take effect.
* **[Flight Planning]** Automatic flight planning will no longer accidentally plan a recovery tanker instead of a theater refueling package. This fixes a potential crash during mission generation when opfor plans a refueling task at a sunk carrier. You'll need to skip the current turn to force opfor to replan their flights to get the fix.
* **[Mission Generation]** Using heliports (airports without any runways) will no longer cause mission generation to fail.

# 6.1.0

Saves from 6.0.0 are compatible with 6.1.0

## Features/Improvements

* **[Factions]** Defaulted bluefor modern to use Georgian and Ukrainian liveries for Russian aircraft.
* **[Factions]** Added Peru.
* **[Modding]** Added support for the HMS Ariadne, Achilles, and Castle class.

## Fixes

* **[Flight Planning]** Fixes CAS flights not having landing waypoints.
* **[Squadrons]** Fixed the livery for the VF-33 F-14A squadron.
* **[UI]** Fixed an issue where manual submit of mission results did not end the mission correctly.

# 6.0.0

Saves from 5.x are not compatible with 6.0.

## Features/Improvements

* **[Engine]** Support for DCS 2.8.0.33006.
* **[Factions]** Updated the Faction file structure. Older custom faction files will not work correctly and have to be updated to the new structure.
* **[Flight Planning]** Added preset formations for different flight types at hold, join, ingress, and split waypoints. Air to Air flights will tend toward line-abreast and spread-four formations. Air to ground flights will tend towards trail formation.
* **[Flight Planning]** Added the ability to plan tankers for recovery on package flights. This mission type will not be planned automatically.
* **[Flight Planning]** Air to Ground flights now have ECM enabled on lock at the join point, and SEAD/DEAD also have ECM enabled on detection and lock at ingress.
* **[Flight Planning]** AWACS flightplan changed from orbit to a racetrack to reduce data link disconnects which were caused by blind spots as a result of the bank angle. 
* **[Flight Planning]** Added a new helo mission type: AirAssault which can be used to load and transport infantry troops from a pickup zone or a carrier to an enemy CP to capture it.
* **[Flight Planning]** Improved the Airlift mission type so that it now can be enforced within the unit transfer dialog and implemented CTLD support. This allows user to spawn sling loadable crates at the pickup location and fly transport flights.
* **[Mission Generation]** Added an option to fast-forward mission generation until the point of first contact (WIP).
* **[Mission Generation]** Added performance option to not cull IADS when culling would affect how mission is played at target area.
* **[Mission Generation]** Reworked the ground object generation which now uses a new layout system
* **[Mission Generation]** Added information about the modulation (AM/FM) of the assigned frequencies to the kneeboard and assign AM modulation instead of FM for JTAC.
* **[Mission Generation]** Added ice halos.
* **[Mission Generation]** Adjusted wind speeds. Wind speeds at high altitude are generally higher now.
* **[Mission Generation]** Added turbulence. Higher in Summer and Winter, also higher at day time than at nighttime.
* **[Modding]** Updated UH-60L mod version support to 1.3.1
* **[Modding]** Updated the High Digit SAMs implementation and added the HQ-2 as well as the upgraded SA-2 and SA-3 Launchers from the mod. Threat range circles will now also be displayed correctly.
* **[Modding]** Theater information such as climate properties is now moddable.
* **[Modding]** Allow campaign designers to define default values for the economy settings (starting budget and multiplier).
* **[Modding]** Campaigns can now optionally define their start time by including a time in the `recommended_start_date` field. There is not currently a way to override the start time in the UI.
* **[Plugins]** Allow full support of the SkynetIADS plugin with all advanced features (connection nodes, power sources, command centers) if campaign supports it.
* **[Plugins]** Added support for the CTLD script by ciribob with many possible customization options and updated the JTAC Autolase to the CTLD included script.
* **[UI]** Added options to the loadout editor for setting properties such as HMD choice.
* **[UI]** Added separate images for the different carrier types.
* **[UI]** Add Accept/Reset buttons to Air Wing Configurator screen.

## Fixes

* **[Engine]** Fixed issue that prevented some weapon types like torpedoes from being recognized.
* **[Flight Planning]** Fixed a miscalculation of waypoint TOTs that would require time travel.
* **[Loadouts]** Improved the range of the F-16 CAS loadout by adding bags.
* **[Mission Generation]** AAA ground units now spawn correctly at the frontline
* **[Mission Generation]** Fixed SA-13 incorrectly created as SA-8 Loading Unit which will not be spawned in the generated mission.
* **[Mission Generation]** Fixed adding additional mission types for a squadron causing error messages when the mission type is not supported by the aircraft type by default
* **[Mission Generation]** Fixed an issue where SEAD/DEAD/BAI flights fired all missiles / bombs against a single unit in a group instead of targeting the whole group.
* **[Mission Generation]** Fixed an issue which generated the helipads at FARPs incorrectly and placed the helicopters within each other.
* **[Mission Generation]** Fixed an issue with SEAD missions flown by the AI when using the Skynet Plugin and anti-radiation missiles (ARM). The AI now correctly engages the SAM when it comes alive instead of diving into it.
* **[Mission Generation]** Fixed generation issue that would cause AI helicopters to get stuck after taking off from a FARP.
* **[Mission Generation]** Fixed mission scripting error caused by control points with apostrophes in their names, such as Tha'lah.
* **[Modding]** Campaigns that used quad zones for scenery targets will no longer load. Only circular zones were ever supported, but an implementation quirk allowed them to load in a way that would misbehave. A "No white triggerzones found" message during campaign generation is the sign of a broken campaign.
* **[Modding]** Loadouts with invalid weapons (typically new DCS weapons not yet available in Liberation) will be ignored rather than causing an error.
* **[Squadrons]** Fixed issue in air wing configuration that would allow squadrons to be created with no home base if no base was available.
* **[Squadrons]** Helicopter squadrons can no longer be assigned to FOBs that are not FARPs.
* **[UI]** Add vanilla theme weather and time of day icons
* **[UI]** Disable player slots for non-flyable aircraft.
* **[UI]** Fixed and issue where the liberation main exe was still running after application close.

# 5.2.0

Saves from 5.1.0 are compatible with 5.2.0

## Features/Improvements

* **[Engine]** Support for DCS 2.7.11.21408, including the new Apache AH-64D and the Syria map extension
* **[Mission Generation]** Improved FARP Helipad handling and creation (now includes windsocks)
* **[Modding]** Add UH-60L mod support
* **[Modding]** Updated Community A-4E-C mod version support to 2.0.0 release. Version 1.4.2 is no longer compatible, unless the mod default loadouts are deleted/modified.
* **[Modding]** Updated JAS-39-C mod support for v1.8.0-beta
* **[Campaign]** Peace Spring, Vectron's Claw, Vegas Nerve, Scenic Route 2 campaign update
* **[Campaign]** Added Tripoint Hostility campaign by Fuzzle
* **[Campaign]** Add 3 new campaigns from Sith1144

## Fixes

* **[Mission Generation]** Fixed incorrect SA-5 and NASAMS threat range when TR destroyed. It will not count as threat anymore when the TR is dead.
* **[Mission Generation]** Fixed "Max Threat Range" error
* **[Mission Generation]** Fix unculled zones not updating when needed
* **[Mission Planner]** Now allows squadron transfers to control points where the number of free slots matches exactly the expected size of the transferring squadron next turn.
* **[Data]** Removed Fw 190 A-8 and D-9 from Germany 1940 and 1942 faction list for historical accuracy.
* **[Data]** Updated Loadouts for Tornado GR4, F-15E and F-16C
* **[Data]** Corrected some unit data
* **[UI]** Fixed various UI issues (for example Scaling and HighDPI)
* **[UI]** Typhoon GR4 and IDS images

# 5.1.0

Saves from 5.0.0 are compatible with 5.1.0

## Features/Improvements

* **[Engine]** Support for DCS 2.7.9.17830 and newer, including the HTS and ECM pod.
* **[Campaign]** Add option to manually add and remove squadrons and different aircraft type in the new game wizard / air wing configuration dialog.
* **[Mission Generation]** Add Option to enforce the Easy Communication setting for the mission
* **[Mission Generation]** Add Option to select between only night missions, day missions or any time (default).
* **[Modding]** Add F-104 mod support

## Fixes

* **[Campaign]** Fixed some minor issues in campaigns which generated error messages in the log.
* **[Campaign]** Changed the way how map object / scenery kills where tracked. This fixes issues with kill recognition after map updates from ED which change the object ids and therefore prevent correct kill recognition.
* **[Mission Generation]** Fixed incorrect radio specification for the AN/ARC-222.
* **[Mission Generation]** Fixed mission scripting error when using a dedicated server.
* **[Mission Generation]** Fixed an issue where empty convoys lead to an index error when a point capture made a pending transfer of units not completable anymore.
* **[Mission Generation]** Corrected Viggen FR22 & FR24 preset channels for the DCS 2.7.9 update
* **[Mission Generation]** Fixed the SA-5 Generator to use the P-19 FlatFace SR as a Fallback radar if the faction does not have access to the TinShield SR.
* **[UI]** Enable / Disable the settings, save and stats actions if no game is loaded to prevent an error as these functions can only be used on a valid game.
* **[UI]** Added missing icons for Tornado GR4, and Tornado IDS.

# 5.0.0

Saves from 4.x are not compatible with 5.0.

## Features/Improvements

* **[Campaign]** Weather! Theaters now experience weather that is more realistic for the region and its current season. For example, Persian Gulf will have very hot, sunny summers and Marianas will experience lots of rain during fall. These changes affect pressure, temperature, clouds and precipitation. Additionally, temperature will drop during the night, by an amount that is somewhat realistic for the region.
* **[Campaign]** Weapon data such as fallbacks and introduction years is now moddable. Due to the new architecture to support this, the old data was not automatically migrated.
* **[Campaign]** Era-restricted loadouts will now skip LGBs when no TGP is available in the loadout. This only applies to default loadouts; buddy-lasing can be coordinated with custom loadouts.
* **[Campaign]** FOBs control point can have FARP/helipad slot and host helicopters. To enable this feature on a FOB, add "Invisible FARP" statics objects near the FOB location in the campaign definition file.
* **[Campaign]** Squadrons now have a home base and will not operate out of other bases. See https://github.com/dcs-liberation/dcs_liberation/issues/1145 for status.
* **[Campaign]** Aircraft now belong to squadrons rather than bases to support squadron location transfers.
* **[Campaign]** Skipped turns are no longer counted as defeats on front lines.
* **[Campaign AI]** Overhauled campaign AI target prioritization.
* **[Campaign AI]** Player front line stances can now be automated. Improved stance selection for AI.
* **[Campaign AI]** Reworked layout of hold, join, split, and ingress points. Should result in much shorter flight plans in general while still maintaining safe join/split/hold points.
* **[Campaign AI]** Auto-planning mission range limits are now specified per-aircraft. On average this means that longer range missions will now be plannable. The limit only accounts for the direct distance to the target, not the path taken.
* **[Campaign AI]** Transport aircraft will now be bought only if necessary at control points which can produce ground units and are capable to operate transport aircraft.
* **[Campaign AI]** Aircraft will now only be automatically purchased or assigned at appropriate bases. Naval aircraft will default to only operating from carriers, Harriers will default to LHAs and shore bases, helicopters will operate from anywhere. This can be customized per-squadron.
* **[Engine]** Support for DCS 2.7.7.14727 and newer, including support for F-16 CBU-105s, SA-5s, and the Forrestal.
* **[Kneeboard]** Minimum required fuel estimates have been added to the kneeboard for aircraft with supporting data (currently only the Hornet and Viper).
* **[Kneeboard]** QNH (pressure MSL) and temperature have been added to the kneeboard.
* **[Mission Generation]** EWRs are now also headed towards the center of the conflict
* **[Mission Generation]** FACs can now use FC3 compatible laser codes. Note that this setting is global, not per FAC.
* **[Modding]** Can now install custom campaigns to <DCS saved games>/Liberation/Campaigns instead of the Liberation install directory.
* **[Modding]** Campaigns can now define a default start date.
* **[Modding]** Campaigns now specify the squadrons that are present in the campaign, their roles, and their starting bases. Players can customize this at game start but the campaign will choose the defaults.
* **[New Game Wizard]** Can now customize the player's air wing before campaign start to disable, relocate, or rename squadrons.
* **[Plugins]** Updated SkynetIADS to 2.4.0 (adds SA-5 support).
* **[UI]** Sell Button for aircraft will be disabled if there are no units available to be sold or all are already assigned to a mission
* **[UI]** Enemy aircraft inventory now viewable in the air wing menu.

## Fixes

* **[Campaign]** Naval control points will no longer claim ground objectives during campaign generation and prevent them from spawning.
* **[Campaign]** Units aboard sunk cargo ships will now have their losses tracked properly.
* **[Mission Generation]** Mission results and other files will now be opened with enforced utf-8 encoding to prevent an issue where destroyed ground units were untracked because of special characters in their names.
* **[Mission Generation]** Fixed generation of landing waypoints so that the AI obeys them.
* **[Mission Generation]** AI carrier aircraft with a start time of T+0 will now start at T+1s to avoid traffic jams.
* **[Mission Generation]** Fixed cases of unused aircraft not being spawned at airfields as soon as any airport filled up.
* **[Mission Generation]** Fixed cases with multiple client flights of the same airframe all received the same preset channels.
* **[Mission Generation]** F-14A is now generated with stored alignment.
* **[Mission Generation]** Su-33s set to cold or warm start on the Kuznetsov will always be generated as runway starts to avoid the AI getting stuck.
* **[Mission Generation]** Fixed AI not receiving anti-ship tasks against carriers and LHAs.
* **[Mods]** Fixed broken A-4 support causing no weapons to be available.
* **[UI]** Selling of Units is now visible again in the UI dialog and shows the correct amount of sold units
* **[UI]** Fixed bug where an incompatible campaign could be generated if no action is taken on the campaign selection screen.

# 4.1.1

Saves from 4.1.0 are compatible with 4.1.1.

## Fixes

* **[Campaign]** Fixed broken support for Mariana Islands map.
* **[Mission Generation]** Fix SAM sites pointing towards the center of the conflict.
* **[Flight Planning]** No longer using Su-34 for CAP missions.

# 4.1.0

Saves from 4.0.0 are compatible with 4.1.0.

## Features/Improvements

* **[Campaign]** Air defense sites now generate a fixed number of launchers per type.
* **[Campaign]** Added support for Mariana Islands map.
* **[Campaign AI]** Adjustments to aircraft selection priorities for most mission types.
* **[Engine]** Support for DCS 2.7.4.9632 and newer, including the Marianas map, F-16 JSOWs, NASAMS, and Tin Shield EWR.
* **[Flight Planning]** CAP patrol altitudes are now set per-aircraft. By default the altitude will be set based on the aircraft's maximum speed.
* **[Flight Planning]** CAP patrol speeds are now set per-aircraft to be more suitable/sensible. By default the speed will be set based on the aircraft's maximum speed.
* **[Mission Generation]** Improvements for better support of the Skynet Plugin and long range SAMs are now acting as EWR
* **[Mission Generation]** SAM sites are now headed towards the center of the conflict
* **[Mods]** Support for latest version of Gripen mod. In-progress campaigns may need to re-plan Gripen flights to pick up updated loadouts.
* **[Plugins]** Increased time JTAC Autolase messages stay visible on the UI.
* **[Plugins]** Updated SkynetIADS to 2.2.0 (adds NASAMS support).  
* **[UI]** Added ability to take notes and have those notes appear as a kneeboard page.
* **[UI]** Hovering over the weather information now dispalys the cloud base (meters and feet).
* **[UI]** Google search link added to unit information when there is no information provided.
* **[UI]** Control point name displayed with ground object group name on map.
* **[UI]** Buy or Replace will now show the correct price for generated ground objects like sams.
* **[UI]** Improved logging for frontline movement to be more descriptive about what happened and why.
* **[UI]** Brought ruler map module into source, which should fix file integrity issues with the module.

## Fixes

* **[Campaign]** Fixed the Silkworm generator to include launchers and not all radars.
* **[Data]** Fixed Introduction dates for targeting pods (ATFLIR and LITENING were both a few years too early).
* **[Data]** Removed SA-10 from Syria 2011 faction.
* **[Economy]** EWRs can now be bought and sold for the correct price and can no longer be used to generate money
* **[Flight Planning]** Helicopters are now correctly identified, and will fly ingress/CAS/BAI/egress and similar at low altitude.
* **[Flight Planning]** Fixed potential issue with angles > 360° or < 0° being generated when summing two angles.
* **[Mission Generation]** The lua data for other plugins is now generated correctly
* **[Mission Generation]** Fixed problem with opfor planning missions against sold ground objects like SAMs
* **[Mission Generation]** The legacy always-available tanker option no longer prevents mission creation.
* **[Mission Generation]** Prevent the creation of a transfer order with 0 units for a rare situtation when a point was captured.
* **[Mission Generation]** Planned transfers which will be impossible after a base capture will no longer prevent the mission result submit.
* **[Mission Generation]** Fix occasional KeyError preventing mission generation when all units of the same type in a convoy were killed.
* **[Mission Generation]** Fix for AAA Flak generator using Opel Blitz preventing the mission from being generated because duplicate unit names were used.
* **[Mission Generation]** Fixed a potential bug with laser code generation where it would generate invalid codes.  
* **[UI]** Statistics window tick marks are now always integers.
* **[UI]** Statistics window now shows the correct info for the turn
* **[UI]** Toggling custom loadout for an aircraft with no preset loadouts no longer breaks the flight.

# 4.0.0

Saves from 3.x are not compatible with 4.0.

## Features/Improvements

* **[Engine]** Support for DCS 2.7.2.7910.1 and newer, including Cyprus, F-16 JDAMs, and the Hind.
* **[Campaign]** Squadrons now (optionally, off by default) have a maximum size and killed pilots replenish at a limited rate.
* **[Campaign]** Added an option to disable levelling up of AI pilots.
* **[Campaign]** Added Russian Intervention 2015 campaign on Syria, for a small and somewhat realistic Russian COIN scenario.
* **[Campaign]** Added Operation Atilla campaign on Syria, for a reasonably large invasion of Cyprus scenario.
* **[Campaign AI]** AI will plan Tanker flights.
* **[Campaign AI]** Removed max distance for AEW&C auto planning.
* **[Economy]** Adjusted prices for aircraft to balance out some price inconsistencies.
* **[Factions]** Added more tankers to factions.
* **[Flight Planner]** Added ability to plan Tankers.
* **[Modding]** Campaign format version is now 7.0 to account for DCS map changes that made scenery strike targets incompatible with existing campaigns.
* **[Mods]** Added support for the Gripen mod.
* **[Mods]** Removes MB-339PAN support, as the mod is now deprecated and no longer works with DCS 2.7+.
* **[Mission Generation]** Added support for "Neutral Dot" label options.
* **[New Game Wizard]** Mods are now selected via checkboxes in the new game wizard, not as separate factions.
* **[UI]** Ctrl click and shift click now buy or sell 5 or 10 units respectively.
* **[UI]** Multiple waypoints can now be deleted simultaneously if multiple waypoints are selected.
* **[UI]** Carriers and LHAs now match the colour of airfields, and their destination icons are translucent.
* **[UI]** Updated intel box text for first turn.
* **[UI]** Base Capture Cheat is now usable at all bases and can also be used to transfer player-owned bases to OPFOR.
* **[UI]** Pass Turn button is relabled as "Begin Campaign" on Turn 0.  
* **[UI]** Added a ruler to the map.
* **[UI]** Liberation now saves games to `<DCS user directory>/Liberation/Saves` by default to declutter the main directory.

## Fixes

* **[Campaign AI]** Fix procurement for factions that lack some unit types.
* **[Campaign AI]** Fix auto purchase of aircraft for factions that have no transport aircraft.
* **[Campaign AI]** Fix refunding of pending aircraft purchases when a side has no factory available.  
* **[Mission Generation]** Fixed problem with mission load when control point name contained an apostrophe.
* **[Mission Generation]** Fixed EWR group names so they contribute to Skynet again.
* **[Mission Generation]** Fixed duplicate name error when generating convoys and cargo ships when creating manual transfers after loading a game.
* **[Mission Generation]** Fixed empty convoys not being disbanded when all units are killed/removed.
* **[Mission Generation]** Fixed player losing frontline progress when skipping from turn 0 to turn 1.
* **[Mission Generation]** Fixed issue where frontline would only search to the right for valid locations.
* **[UI]** Made non-interactive map elements less obstructive.
* **[UI]** Added support for Neutral Dot difficulty label
* **[UI]** Clear skies at night no longer described as "Sunny" by the weather widget.
* **[UI]** Removed ability to buy (useless) ground units at carriers and LHAs.
* **[UI]** Fixed enable/disable of buy/sell buttons.
* **[UI]** EWRs now appear in the custom waypoint list.

# 3.0.0

Saves from 2.5 are not compatible with 3.0.

## Features/Improvements

* **[Campaign]** Ground units can now be transferred by road, airlift, and cargo ship. See https://github.com/dcs-liberation/dcs_liberation/wiki/Unit-Transfers for more information.
* **[Campaign]** Ground units can no longer be sold. To move units to a new location, transfer them.
* **[Campaign]** Ground units must now be recruited at a base with a factory and transferred to their destination. When buying units in the UI, the purchase will automatically be fulfilled at the closest factory, and a transfer will be created on the next turn.
* **[Campaign]** Non-control point FOBs will no longer spawn.
* **[Campaign]** Added squadrons and pilots. See https://github.com/dcs-liberation/dcs_liberation/wiki/Squadrons-and-pilots for more information.
* **[Campaign]** Capturing a base now depopulates all of its attached objectives with units: air defenses, EWRs, ships, armor groups, etc. Buildings are captured.
* **[Campaign]** Ammunition Depots determine how many ground units can be deployed on the frontline by a control point.
* **[Campaign AI]** AI now considers Ju-88s for CAS, strike, and DEAD missions.
* **[Campaign AI]** AI planned AEW&C missions will now be scheduled ASAP.
* **[Campaign AI]** AI now considers the range to the SAM's threat zone rather than the range to the SAM itself when determining target priorities.
* **[Campaign AI]** Auto purchase of ground units will now maintain unit composition instead of buying randomly. The unit composition is predefined.
* **[Campaign AI]** Auto purchase will aim to purchase enough ground units to support the frontline, plus 30% reserve units.
* **[Campaign AI]** Auto purchase will now adjust its air/ground balance to favor whichever is under-funded.
* **[Flight Planner]** Desired mission length is now configurable (defaults to 60 minutes). A BARCAP will be planned every 30 minutes. Other packages will simply have their takeoffs spread out or compressed such that the last flight will take off around the mission end time.
* **[Flight Planner]** Flight plans now include bullseye waypoints.
* **[Flight Planner]** Differentiated SEAD and SEAD escort. SEAD is tasked with suppressing the package target, SEAD escort is tasked with protecting the package from all SAMs along its route.
* **[Flight Planner]** Planned airspeed increased to 0.85 mach for supersonic airframes and 85% of max speed for subsonic.
* **[Flight Planner]** Taxi time estimation for airfields increased from 5 minutes to 8 minutes.
* **[Flight Planner]** Reduce expected error margin for flight plans from 10% to 5%.
* **[Flight Planner]** SEAD flights are scheduled one minute ahead of the package's TOT so that they can suppress the site ahead of the strike.
* **[Flight Planner]** Automatic ATO generation for the player's coalition can now be disabled in the settings.
* **[Payloads]** AI flights for most air to ground mission types (CAS excluded) will have their guns emptied to prevent strafing fully armed and operational battle stations. Gun-reliant airframes like A-10s and warbirds will keep their bullets.
* **[Kneeboard]** ATC table overflow alleviated by wrapping long airfield names and splitting ATC frequency and channel into separate rows.
* **[UI]** Overhauled the map implementation. Now uses satellite imagery instead of low res map images. Display options have moved from the toolbar to panels in the map.
* **[UI]** Campaigns generated for an older or newer version of the game will now be marked as incompatible. They can still be played, but bugs may be present.
* **[UI]** DCS loadouts are now selectable in the loadout setup menu.
* **[UI]** Added global aircraft inventory view under Air Wing dialog.
* **[UI]** Base menu now shows information about ground unit deployment limits.
* **[Modding]** Campaigns now choose locations for factories to spawn.
* **[Modding]** Campaigns now choose locations for ammunition depots to spawn.
* **[Modding]** Campaigns now use map structures as strike targets.
* **[Modding]** Campaigns may now set *any* objective type to be a required spawn rather than random chance. Support for random objective generation was removed.
* **[Modding]** Campaigns may now place AAA objectives.
* **[Modding]** Can now install custom factions to <DCS saved games>/Liberation/Factions instead of the Liberation install directory.
* **[Performance Settings]** Added a settings to lower the number of smoke effects generated on frontlines. Lowered default settings for frontline smoke generators, so less smoke should be generated by default.
* **[Configuration]** Liberation preferences (DCS install and save game location) are now saved to `%LOCALAPPDATA%/DCSLiberation` to prevent needing to reconfigure each new install.
* **[Skynet]** Updated to 2.1.0.

## Fixes

* **[Campaign AI]** Fix purchase of aircraft by priority (the faction's list was being used as the priority list rather than the game's).
* **[Campaign AI]** Fixed bug causing AI to over-purchase cheap aircraft.
* **[Campaign AI]** Auto planner will no longer attempt to plan missions for which the faction has no compatible aircraft.
* **[Campaign AI]** Stop purchasing aircraft after the first unaffordable package to attempt to complete more packages rather than filling airfields with cheap escorts that will never be used.
* **[Campaign]** Fixed bug where offshore strike locations were being used to spawn ship objectives.
* **[Campaign]** EWR sites are now purchasable.
* **[Flight Planner]** AI strike flight plans now include the correct target actions for building groups.
* **[Flight Planner]** AI BAI/DEAD/SEAD flights now have tasks to attack all groups at the target location, not just the primary group (for multi-group SAM sites).
* **[Flight Planner]** Fixed some contexts where damaged runways would be used. Destroying a carrier will no longer break the game.

# 2.5.1

## Features/Improvements

* **[UI]** Engagement ranges are now displayed by default.
* **[UI]** Engagement range display generalized to work for all patrolling flight plans (BARCAP, TARCAP, and CAS).
* **[Flight Planner]** Front lines no longer project threat zones to avoid pushing BARCAPs back so much. TARCAPs will be forcibly planned but strike packages will not route around front lines even if it is reasonable to do so.

## Fixes

* **[Campaigns]** EWRs associated with a base will now only be generated near the base.
* **[Flight Planner]** Fixed error when generating AEW&C flight plans in campaigns with no front lines.

# 2.5.0

Saves from 2.4 are not compatible with 2.5.

## Features/Improvements

* **[Engine]** DCS 2.7 Support
* **[UI]** Improved FOB menu, added a custom banner, and do not display aircraft recruitment menu
* **[Flight Planner]** Added AEW&C missions. (by siKruger)
* **[Kneeboard]** Added dark kneeboard option (by GvonH)
* **[Campaigns]** Multiple EWR sites may now be generated, and EWR sites may be generated outside bases (by SnappyComebacks)
* **[Mission Generation]** Cloudy and rainy (but not thunderstorm) weather will use the cloud presets from DCS 2.7.
* **[Plugins]** Added LotATC export plugin (by drsoran)
* **[Plugins]** Added Splash Damage Plugin (by Wheelijoe)
* **[Loadouts]** Replaced Litening with ATFLIR for all default F/A-18C loadouts.

## Fixes

* **[Flight Planner]** Front lines now project threat zones, so TARCAP/escorts will not be pruned for flights near the front. Packages may also route around the front line when practical.
* **[Flight Planner]** Fixed error when planning BAI at SAMs with dead subgroups.
* **[Flight Planner]** Mig-19 was not allowed for CAS roles fixed
* **[Flight Planner]** Increased size of navigation planning area to avoid plannign failures with distant waypoints.
* **[Flight Planner]** Fixed UI refresh when unchecking the "default loadout" box in the loadout editor.
* **[Objective names]** Fixed typos in objective name : ARMADILLLO -> ARMADILLO (by SnappyComebacks)
* **[Payloads]** F-86 Sabre was missing a custom payload
* **[Payloads]** Added GAR-8 period restrictions (by Mustang-25)
* **[Campaign]** Date now progresses.
* **[Campaign]** Added game over message when a coalition runs out of functioning airbases.
* **[Mission Generation]** Fixed "invalid face handle" error in kneeboard generation that occurred on some machines.

## Regressions

* **[Mod Support]** Stopped support for 2.5.5 Rafale Mode, and removed factions that were using it
* **[Mod Support]** Su-57 mod support might be out of date

# 2.4.3

## Features/Improvements

* **[New Game Wizard]** Added the possibility to setup custom start date

## Fixes

* **[Mods]** Updated C-130J mod data to version 6.4
* **[Mods]** Updated F-22A mod to latest version

# 2.4.2

## Features/Improvements

* **[Factions]** Introduction dates and fallback weapons added for US, Russian, UK, and French weapons. Huge thanks to @TheCandianVendingMachine for the massive amount of data entry!
* **[Campaigns]** Added 1995 start dates.

## Fixes

* **[Economy]** Pending ground unit purchases will also be transferred when a connected base is captured.
* **[UI]** Fixed rounding of budget in recruitment menu.

# 2.4.1

## Fixes

* **[Units]** Fixed syntax error with the SH-60B payload file.
* **[Culling]** Missile sites generate reasonably sized non-cull zones rather than 100km ones.
* **[UI]** Budget display is also now rounded to 2 decimal places.
* **[UI]** Fixed some areas where the old, non-pretty name was displayed to users.

# 2.4.0

Saves from 2.3 are not compatible with 2.4.

## Highlights

* Improved flight plan generation to avoid loitering in or traveling through threatened areas when practical.
* Improved AI aircraft purchasing behavior.
* Era-restricted weapons (work in progress).
* Tons of UI polish.
* Rebalanced economy to keep opfor competitive over the course of the game.

## Features/Improvements

* **[Flight Planner]** Air-to-air and SEAD escorts will no longer be automatically planned for packages that are not in range of threats.
* **[Flight Planner]** Non-custom flight plans will now navigate around threat areas en route to the target area when practical.
* **[Flight Planner]** Flight plans along front lines now ensure that the race track start is closer to the departure airfield than the race track end.
* **[Campaign AI]** Auto-purchase now prefers airfields that are not within range of the enemy.
* **[Campaign AI]** Auto-purchase now prefers the best aircraft for the task, but will attempt to maintain some variety.
* **[Campaign AI]** Opfor now sells off odd aircraft since they're unlikely to be used.
* **[Campaign AI]** Multiple rounds of CAP will be planned (roughly 90 minutes of coverage). Default starting budget has increased to account for the increased need for aircraft.
* **[Mission Generator]** Multiple groups are created for complex SAM sites (SAMs with additional point defense or SHORADS), improving Skynet behavior.
* **[Mission Generator]** Default start type can now be chosen in the settings. This replaces the non-functional "AI Parking Start" option. **Selecting any type other than cold will break OCA/Aircraft missions.**
* **[Cheat Menu]** Added ability to toggle base capture and frontline advance/retreat cheats.
* **[Skynet]** Updated to 2.0.1.
* **[Skynet]** Point defenses are now configured to remain on to protect the site they accompany.
* **[Hercules]** Updated the Hercules Cargo list file.
* **[Balance]** Opfor now gains income using the same rules as the player, significantly increasing their income relative to the player for most campaigns.
* **[Balance]** Units now retreat from captured bases when able. Units with no retreat path will be captured and sold.
* **[Economy]** FOBs generate only $10M per turn (previously $20M like airbases).
* **[Economy]** Carriers and off-map spawns generate no income (previously $20M like airbases).
* **[Economy]** Sales of aircraft and ground vehicles can now be cancelled before the next turn begins.
* **[UI]** Multi-SAM objectives now show threat and detection rings per group.
* **[UI]** New icon for AA sites with no active threat.
* **[UI]** Unit names are now prettier and more accurate, and can now be set per-country for added historical flavour.
* **[UI]** Default loadout is now shown for flights with no custom loadout selected.
* **[UI]** Aircraft for a new flight are now only selectable if they match the task type for that flight.
* **[UI]** WIP - There is now a unit info button for each unit in the recruitment list, that should help newer players learn what each unit does.
* **[UI]** Docs for time-on-target and creating new theaters/factions/loadouts are now linked in the UI at the appropriate places.
* **[UI]** ASAP is now a checkbox rather than a button. Enabling this will disable the TOT selector but changes to the package structure will automatically re-ASAP the package.
* **[UI]** Arrival airfield is now shown in the flight list if it differs from the departure airfield.
* **[UI]** Start type can now be selected when creating a flight.
* **[UI]** Arrival and divert airfields can be edited after the flight is created.
* **[Factions]** Added option for date-based loadout restriction. Active radar homing missiles are handled, patches welcome for the other thousand weapons.
* **[Factions]** Added Poland 2010 faction.
* **[Factions]** Added Greece 2005 faction.
* **[Factions]** Added Iran 1988 faction.
* **[Units]** Support for E-2 Hawkeye, SH-60B Seahawk, S-3B Viking (thanks to awinterquest) and SpGH Dana - these are now being used by appropriate factions.
* **[Culling]** Missile sites are no longer culled.
* **[Campaigns]** Added campaign "Black Sea Lite" by Starfire
* **[Campaigns]** Added campaign "Exercise Vegas Nerve" by Starfire 
* **[New game Wizard]** The theater page is now the first page of the campaign wizard, recommended factions will be selected automatically on the faction selection page
* **[New game Wizard]** Added information text about the selected campaign performance.
* **[Mod Support]** Added support for High Digit SAMs mod 1.4.0
* **[Mod Support]** Added SAMs sites generator : KS19Generator, SA10BGenerator, SA12Generator, SA17Generator, SA20Generator, SA20BGenerator, SA23Generator    

## Fixes

* **[Hercules]** Updated the default Hercules radio frequency.
* **[Economy]** Pending unit orders at captured bases will be refunded.
* **[UI]** Carrier group SAM threat rings now move with the carrier.
* **[UI]** Base intel menu no longer compresses text, and is now scrollable.
* **[UI]** Edit Flight window is now dynamically sized to adapt to the width of waypoint names, so they no longer get truncated.
* **[UI]** Budget income display is now rounded to 2 decimal places.
* **[UI]** Fixed incorrect income per turn displayed for strike target tooltip.
* **[Factions]** USA with C-130 faction now links to the required mod.
* **[Campaign]** Fixed issue where destroyed buildings would sometimes not count as destroyed and thus respawn.
* **[Campaign]** Fixed issue where destroyed runways were not registered.
* **[Units]** J-11A is no longer spawned with empty loadout.
* **[Units]** F-14B is no longer spawned with empty loadout for fighter sweep tasks.
* **[Units]** Pyotr Velikiy cruiser has been removed for now as it's nearly unkillable.
* **[Units]** Submarines have been removed for now as they aren't wholly functional.
* **[Units]** Fixed "FACTION ERROR : Unable to find OliverHazardPerryGroupGenerator in pydcs" error at startup.
* **[Mission Generator]** Fixed a bug where units set to Aggressive stance sometimes did not move.
* **[Mission Generator]** Flyover points for OCA/Aircraft missions are now generated correctly.
* **[Flight Planner]** Fixed not being able to create custom waypoints for buildings.
* **[Flight Planner]** Strike missions will no longer be automatically planned against SAMs.
* **[Flight Planner]** Strike missions will no longer be automatically planned against FOB structures.

# 2.3.4

## Fixes:
[Mission Generator] Mission generator would crash when generating fire missions for destroyed SCUD sites - fixed

# 2.3.3

## Features/Improvements
* **[Campaigns]** Reworked Golan Heights campaign on Syria, (Added FOB and preset locations for SAMS)
* **[Campaigns]** Added a lite version of the Golan Heights campaign
* **[Campaigns]** Reworked Syrian Civil War campaign (Added FOB and preset locations for SAMS)
* **[Campaigns]** Reworked Emirates campaign
* **[Campaigns]** AA units added to frontlines and updated all factions to include some frontline AA units.
* **[Mission Generator]** Infantry will only be generated for APC and IFV groups
* **[Mission Generator]** Infantry squads size is not randomized anymore
* **[Mission Generator]** Infantry squads can have a mortar. 
* **[Mission Generator]** SCUD missiles sites will now fire on enemy controls points in range when possible
* **[Factions]** Updated Nato Desert Storm to include F-14A
* **[Factions]** Updated Iraq 1991 factions to include Zsu-57 and Mig-29A
* **[Factions]** Germany 1944, added Stug III and Stug IV
* **[Factions]** Added factions Insurgents (Hard) with better and more weapons
* **[Plugins]** [The EWRS plugin](https://github.com/Bob7heBuilder/EWRS) is now included.
* **[UI]** Added enemy intelligence summary and details window.

## Fixes:
* **[Factions]** AI would never buy artillery units for the frontline - fixed
* **[Factions]** Removed the F-111 unit from the NATO desert storm faction. (Recruiting it would cause crashes in DCS, since it is not a valid unit)
* **[Campaign]** Automatic redeployment of ground units would sometimes fail - fixed
* **[Mission Generator]** Artillery groups would retreat in the wrong direction - fixed
* **[Units]** Fixed SPG_Stryker_M1128_MGS not being in db
* **[UI]** Fixed and added many missing ground units icons
* **[UI]** Ship groups could be replaced by SAM sites in the UI, which would lead to broken mission being generated - fixed 
* **[New Game Wizard]** Removed the "mid game" campaign generator option which is currently broken
* **[Mission Generator]** Empty navy groups will no longer be generated
* **[Mission Generator]** Fixed BAI, SEAD, and DEAD flights ocassionally being assigned the wrong targets.
* **[Flight Planner]** Fixed not being able to plan packages against opfor carriers
* **[UI]** Repaired SAMs no longer show as dead.
* **[UI]** Fixed not being able to manage a disbanded site after disbanding and closing the base menu.

# 2.3.2

## Features/Improvements
* **[Units]** Support for newly added BTR-82A, T-72B3
* **[Units]** Added ZSU-57 AAA sites
* **[Culling]** BARCAP missions no longer create culling exclusion zones.
* **[Flight Planner]** Improved TOT planning. Negative start times no longer occur with TARCAPs and hold times no longer affect planning for flight plans without hold points.
* **[Factions]** Added Iraq 1991 faction (thanks again to Hawkmoon!)

## Fixes:
* **[Mission Generator]** Fix mission generation error when there are too many radio frequency to setup for the Mig-21
* **[Mission Generator]** Fix ground units not moving forward
* **[Mission Generator]** Fixed assigned radio channels overlapping with beacons.
* **[Flight Planner]** Fix creation of custom waypoints.
* **[Campaigns]** Fixed many cases of SAMs spawning on the runways/taxiways in Syria Full.

# 2.3.1

## Features/Improvements
* **[UX]** Added a warning message when the player is attempting to buy more planes at an already full airbase. 
* **[Campaigns]** Migrated Syria full map to new format. (Thanks to Hawkmoon)
* **[Faction]** Added NATO desert Storm faction (Thanks to Hawkmoon)

## Fixes:
* **[AI]** CAP flights will engage enemies again.
* **[Campaigns]** Fixed a missing path on the Caucasus Full Map campaign

# 2.3.0

## Features/Improvements
* **[Campaign Map]** Overhauled the campaign model
* **[Campaign Map]** Possible to add FOB as control points
* **[Campaign Map]** Added off-map spawn locations
* **[Campaign AI]** Overhauled AI recruiting behaviour
* **[Campaign AI]** Added AI procurement for Blue
* **[Campaign]** New Campaign: "Black Sea"
* **[Mission Planner]** Possible to move carrier and tarawa on the campaign map
* **[Mission Generator]** Infantry squads on frontline can have manpads
* **[Mission Generator]** Unused aircraft now spawned to allow for OCA strikes
* **[Mission Generator]** Opfor now obeys parking limits
* **[Mission Generator]** Support for Anubis C-130 Hercules mod
* **[Flight Planner]** Added fighter sweep missions.
* **[Flight Planner]** Added BAI missions.
* **[Flight Planner]** Added anti-ship missions.
* **[Flight Planner]** Differentiated BARCAP and TARCAP. TARCAP is now for hostile areas and will arrive before the package.
* **[Flight Planner]** Added OCA missions
* **[Flight Planner]** Added Alternate/divert airfields
* **[Culling]** Added possibility to include/exclude carriers from culling zones
* **[QOL]** On liberation startup, your latest save game is loaded automatically
* **[Units]** Reduced starting fuel load for C101
* **[UI]** Inform the user of the weather
* **[UI]** Added toolbar buttons to change map display settings
* **[Game]** Added new Economy options for adjusting income multipliers and starting budgets.

## Fixes :
* **[Map]** Missiles sites now have a proper icon and will not re-use the SAM sites icon
* **[Mission Generator]** Ground unit waypoints improperly set to "On Road" - fixed
* **[Mission Generator]** Target waypoints not at ground level - fixed
* **[Mission Generator]** Selected skill not applied to Helicopters - fixed
* **[Mission Generator]** Ground units do not always spawn - fixed
* **[Kneeboard]** Briefing waypoints off by one - fixed
* **[Game]** Destroyed buildings still granting budget - fixed

# 2.2.1

## Features/Improvements
* **[Factions]** Added factions : Georgia 2008, USN 1985, France 2005 Frenchpack by HerrTom
* **[Factions]** Added map Persian Gulf full by Plob
* **[Flight Planner]** Player flights with start delays under ten minutes will spawn immediately.
* **[UI]** Mission start screen now informs players about delayed flights.
* **[Units]** Added support for F-14A-135-GR
* **[Modding]** Possible to setup liveries overrides in factions definition files

## Fixes :
* **[Flight Planner]** Hold, join, and split points are planned cautiously near enemy airfields. Ascend/descend points are no longer planned.
* **[Flight Planner]** Custom waypoints are usable again. Not that in most cases custom flight plans will revert to the 2.1 flight planning behavior.
* **[Flight Planner]** Fixed UI bug that made it possible to create empty flights which would throw an error.
* **[Flight Planner]** Player flights from carriers will now be delayed correctly according to the player's settings.
* **[Misc]** Spitfire variant with clipped wings was not seen as flyable by DCS Liberation (hence could not be setup as client/player slot)
* **[Misc]** Updated Syria terrain parking slots database, the out-of-date database could end up generating aircraft in wrong slots (We are still experiencing issues with somes airbases, such as Khalkhalah though)

# 2.2.0

## Features/Improvements :
* **[Campaign Generator]** Added early warning radar generation
* **[Campaign Generator]** Added scud launcher sites
* **[Cheat Menu]** Added ability to capture base from mission planner
* **[Cheat Menu]** Added ability to show red ATO
* **[Factions]** Added WW2 factions that do not depend on WW2 asset pack
* **[Factions]** Cold War / Middle eastern factions will use Flak sites
* **[Flight Planner]** Flight planner overhaul, with package and TOT system
* **[Flight Planner]** Pick runways and ascent/descent based on headwind
* **[Map]** Added polygon debug mode display
* **[Map]** Highlight the selected flight path on the map
* **[Map]** Improved SAM display settings
* **[Map]** Improved flight plan display settings
* **[Map]** Caucasus and The Channel map use a new system to generate SAM and strike target location to reduce probability of targets generated in the middle of a forests
* **[Misc]** Flexible Dedicated Hosting Options for Mission Files via environment variables
* **[Moddability]** Custom campaigns can be designed through json files
* **[Moddability]** LUA plugins can now be injected into Liberation missions.
* **[Moddability]** Optional Skynet IADS lua plugin now included
* **[New Game]** Starting budget can be freely selected
* **[New Game]** Exanded information for faction and campaign selection in the new game wizard
* **[UI]** Add double and right click actions to many UI elements.
* **[UI]** Add polygon drawing mode for map background
* **[UI]** Added a warning if you press takeoff with no player enabled flights
* **[UI]** Packages and flights now visible in the main window sidebar
* **[Units/Factions]** Added bombers to some coalitions
* **[Units/Factions]** Added support for SU-57 mod by Cubanace
* **[Units]** Added Freya EWR sites to german WW2 factions
* **[Units]** Added support for many bombers (B-52H, B-1B, Tu-22, Tu-142)
* **[Units]** Added support for new P-47 variants

## Fixes :
* **[Campaign Generator]** Big airbases could end up without any airbase defense.
* **[Campaign generator]** Ship group and offshore buildings should not be generated on land anymore
* **[Flight Planner]** Fix waypoint alitudes for helicopters
* **[Flight Planner]** Fixed CAS aircraft wandering away from frontline
* **[Maps]** Incirlik airbase was missing exclusions zones, so SAMS could end up being generated on the runway
* **[Mission Generator]** Fixed player/client confusion when a flight had only one player slot.
* **[Radios]** Fix A-10C radio
* **[UI]** Many missing unit icons were added
* **[UI]** Missing TER weapons in custom payload now selectable.

# 2.1.5

## Features/Improvements :
* **[Units/Factions]** Enabled EPLRS for ground units that supports it (so they appear on A-10C II TAD and Helmet)

## Fixes :
* **[UI]** Fixed an issue that prevent saving after aborting a mission
* **[Mission Generator]** Fixed aircraft landing point type being wrong

# 2.1.4

## Fixes :
* **[UI]** Fixed an issue that prevented generating the mission (take off button no working) on old savegames.

## Features/Improvements :
* **[Units/Factions]** Added A-10C_2 to USA 2005 and Bluefor modern factions
* **[UI]** Limit number of aircraft that can be bought to the number of available parking slots.
* **[Mission Generator]** Use inline loading of the JSON.lua library, and save to either %LIBERATION_EXPORT_DIR%, or to DCS working directory

## Changes :
* **[Units/Factions]** Bluefor generic factions will now use the new "Combined Joint Task Forces Blue" country in the generated mission instead of "USA"

## Fixes :
* **[UI]** Fixed icon for Viggen
* **[UI]** Added icons for some ground units
* **[Misc]** Fixed issue with Chinese characters in pydcs preventing generating the mission. (Take Off button not working) (thanks to spark135246)
* **[Misc]** Fixed an error causing with ATC frequency preventing generating the mission. (Take Off button not working) (thanks to danalbert)

# 2.1.2

## Fixes :
* **[Mission Generator]** Fix mission generation issues with radio frequencies (Thanks to contributors davidp57 and danalbert)
* **[Mission Generator]** AI should now properly plan flights for Tornados

# 2.1.1

## Features/Improvements :
* **[Other]** Added an installer option (thanks to contributor parithon)
* **[Kneeboards]** Generate mission kneeboards for player flights. Kneeboards include
  airfield/carrier information (ATC frequencies, ILS, TACAN, and runway
  assignments), assigned radio channels, waypoint lists, and AWACS/JTAC/tanker
  information. (Thanks to contributor danalbert)
* **[Radios]** Allocate separate intra-flight channels for most aircraft to reduce global
  chatter. (Thanks to contributor danalbert)
* **[Radios]** Configure radio channel presets for most aircraft. Currently supported are:
  * AJS37
  * AV-8B
  * F-14B
  * F-16C
  * F/A-18C
  * JF-17
  * M-2000C (Thanks to contributor danalbert)
* **[Base Menu]** Added possibility to repair destroyed SAM and base defenses units for the player (Click on a SAM site to fix it)
* **[Base Menu]** Added possibility to buy/sell/replace SAM units
* **[Map]** Added recon images for buildings on strike targets, click on a Strike target to get detailled informations
* **[Units/Factions]** Added F-16C to USA 1990
* **[Units/Factions]** Added MQ-9 Reaper as CAS unit for USA 2005
* **[Units/Factions]** Added Mig-21, Mig-23, SA-342L to Syria 2011
* **[Cheat Menu]** Added buttons to remove money

## Fixed issues :
* **[UI/UX]** Spelling issues (Thanks to contributor steveveepee)
* **[Campaign Generator]** LHA was placed on land in Syrian Civil War campaign
* **[Campaign Generator]** Fixed inverted configuration for Syria full map
* **[Campaign Generator]** Syria "Inherent Resolve" campaign, added Incirlik Air Base
* **[Mission Generator]** AH-1W was not used by AI to generate CAS mission by default
* **[Mission Generator]** Fixed F-16C targeting pod not being added to payload
* **[Mission Generator]** AH-64A and AH-64D payloads fix. 
* **[Units/Factions]** China will use KJ-2000 as awacs instead of A-50

# 2.1.0

## Features/Improvements :

* **[Campaign Generator]** Added Syria map
* **[Campaign Generator]** Added 5 campaigns for the Syria map
* **[Campaign Generator]** Added 2 small scale campaign for Persian Gulf map
* **[Units/Factions]** Added factions for Syria map : Syria 2011, Arab Armies 1982, 1973, 1968, 1948, Israel 1982, 1973, 1948
* **[Base Menu]** Budget is visible in recruitment menu. (Thanks to Github contributor root0fall)
* **[Misc]** Added error message in mission when the state file can not be written
* **[Units/Factions]** China, Pakistan, UAE will now use the new WingLoong drone as JTAC instead of the MQ-9 Reaper
* **[Units/Factions]** Minor changes to Syria 2011 and Turkey 2005 factions
* **[UI]** Version number is shown in about dialog

## Fixed issues :

* **[Mission Generator]** Caucasus terrain improvement on exclusions zone (added forests between Vaziani and Beslan to exclusion zones)
* **[Mission Generator]** The first unit of every base defenses group could not be controlled with Combined Arms.
* **[Mission Generator]** Reduced generated helicopter altitude for CAS missions
* **[Mission Generator]** F-16C default CAS payload was asymmetric, fixed.
* **[Mission Generator]** AH-1W couldn't be bought, and added default payloads.
* **[UI/UX]** Fixed Mi-28N missing thumbnail
* **[UI/UX]** Fixed list of flights not refreshing when changing the mission departure (T+).

# 2.0.11

## Features/Improvements :

* **[Units/Factions]** Added Mig-31, Su-30, Mi-24V, Mi-28N to Russia 2010 faction.
* **[Units/Factions]** Added F-15E to USA 2005 and USA 1990 factions.
* **[Mission Generator]** Added a parameter to choose whether the JTACs should use smoke markers or not

## Fixed issues : 

* **[Units/Factions]** Fixed big performance issue in new release UI that occurred only when running the .exe
* **[Units/Factions]** Fixed mission generation not working with Libya faction
* **[Units/Factions]** Fixed OH-58D not being used by AI
* **[Units/Factions]** Typo in UK 1990 name (fixed by bwRavencl)
* **[Units/Factions]** Fixed Tanker Tacan channel not being the same as the briefing one. (Sorry)
* **[Mission Generator]** Neutral airbases services will now be disabled. (Not possible to refuel or re-arm there)
* **[Mission Generator]** AI will be configured to limit afterburner usage
* **[Mission Generator]** JTAC will not use laser codes above 1688 anymore
* **[Mission Generator]** JTAC units were misconfigured and would not be invisible/immortal. 
* **[Mission Generator]** Increased JTAC status message duration to 25s, so you have more time to enter coordinates;
* **[Mission Generator]** Destroyed units carcass will not appear on airfields to avoid having a destroyed vehicle blocking a runway or taxiway.


# 2.0.10

## Features/Improvements :
* **[Misc]** Now possible to save game in a different file, and to open DCS Liberation savegame files. (You are not restricted to a single save file anymore)
* **[UI/UX]** New dark UI Theme and default theme improvement by Deus
* **[UI/UX]** New "satellite" map backgrounds
* **[UX]** Base menu is opened with a single mouse click
* **[Units/Factions/Mods]** Added Community A-4E-C support for faction Bluefor Cold War
* **[Units/Factions/Mods]** Added MB-339PAN support for faction Bluefor Cold War  
* **[Units/Factions/Mods]** Added Rafale AI mod support
* **[Units/Factions/Mods]** Added faction "France Modded" with units from frenchpack v3.5 mod
* **[Units/Factions/Mods]** Added faction "Insurgent modded" with Insurgent units from frenchpack v3.5 mod (Toyota truck)
* **[Units/Factions/Mods]** Added factions Canada 2005, Australia 2005, Japan 2005, USA Aggressors, PMC
* **[New Game Wizard]** Added the list of required mods for modded factions.
* **[New Game Wizard]** No more RED vs BLUE opposing faction restrictions.
* **[New Game Wizard]** New campaign generation settings added : No aircraft carrier, no lha, no navy, invert map starting positions.
* **[Mission Generator]** Artillery units will start firing mission after a random delay. It should reduces lag spikes induced by artillery strikes by spreading them out.
* **[Mission Generator]** Ground units will retreat after taking too much casualties. Artillery units will retreat if engaged.
* **[Mission Generator]** The briefing will now contain the carrier ATC frequency
* **[Mission Generator]** The briefing contains a small situation update.
* **[Mission Generator]** Previously destroyed units are visible in the mission. (And added a performance settings to disable this behaviour)
* **[Mission Generator]*c* Basic JTAC on Frontlines
* **[Campaign Generator]** Added Tarawa in caucasus campaigns
* **[Campaign Generator]** Tuned the various existing campaign parameters
* **[Campaign Generator]** Added small campaign : "Russia" on Caucasus Theater 

## Fixed issues :
* **[Mission Generator]** Carrier will sail into the wind, not in the same direction
* **[Mission Generator]** Carrier cold start was not working (flight was starting warm even when cold was selected)
* **[Mission Generator]** Carrier group ships are more spread out
* **[Mission Generator]** Fixed wrong radio frequency for german WW2 warbirds
* **[Mission Generator]** Fixed FW-190A8 spawning with bomb rack for CAP missions
* **[Mission Generator]** Fixed A-20G spawning with no payload
* **[Mission Generator]** Fixed Su-33 spawning too heavy to take off from carrier
* **[Mission Generator]** Fixed Harrier AV-8B spawning too heavy to take off from tarawa
* **[Mission Generator]** Base defense units were not controllable with Combined Arms
* **[Mission Generator]** Tanker speed was too low
* **[Mission Generator]** Tanker TACAN settings were wrong
* **[Mission Generator]** AI aircraft should start datalink ON (EPLRS)
* **[Mission Generator]** Base defense units should not spawn on runway and or taxyway. (The chance for this to happen should now be really really low)
* **[Mission Generator]** Fixed all flights starting "In flight" after playing a few missions (parking slot reset issue)
* **[Mission Script/Performance]** Mission lua script will not listen to weapons fired event anymore and register every fired weapons. This should improve performance especially in WW2 scenarios or when rocket artillery is firing. 
* **[Campaign Generator]** Carrier name will now not appear for faction who do not have carriers
* **[Campaign Generator]** SA-10 sites will now have a tracking radar.
* **[Units/Factions]** Remove JF-17 from USA 2005 faction
* **[Units/Factions]** Remove AJS-37 from Russia 2010
* **[Units/Factions]** Removed Oliver Hazard Perry from cold war factions (too powerful sam system for the era)
* **[Bug]** On the persian gulf full map campaign, the two carriers were sharing the same id, this was causing a lot of bugs
* **[Performance]** Tuned the culling setting so that you cannot run into situation where no friendly or enemy AI flights are generated
* **[Other]** Application doesn't gracefully exit.
* **[Other]** Other minor fixes, and multiples factions small changes

# 2.0 RC 9

## Features/Improvements :
* **[UI/UX]** New icons from contributor Deus

## Fixed issues :
* **[Mission Generator]** Carrier TACAN was wrongfully set up as an A/A TACAN
* **[Campaign Generator]** Fixed issue with Russian navy group generator causing a random crash on campaign creation.

# 2.0 RC 8

## Fixed issues :
* **[Mission Generator]** Frequency for P-47D-30 changed to 124Mhz (Generated mission with 251Mhz would not work)
* **[Mission Generator]** Reduced the maximum number of uboat per generated group
* **[Mission Generator]** Fixed an issue with the WW2 LST groups (superposed units).
* **[UI]** Fixed issue with the zoom

# 2.0 RC 7

## Features/Improvements :

* **[Units/Factions]** Added P-47D-30 for factions allies_1944
* **[Units/Factions]** Added factions : Bluefor Coldwar, Germany 1944 Easy

* **[Campaign/Map]** Added a campaign in the Channel map
* **[Campaign/Map]** Changed the Normandy campaign map
* **[Campaign/Map]** Added new campaign Normandy Small

* **[Mission Generator]** AI Flight generator has been reworked
* **[Mission Generator]** Add PP points for JF-17 on STRIKE missions
* **[Mission Generator]** Add ST point for F-14B on STRIKE missions
* **[Mission Generator]** Flights with client slots will never be delayed
* **[Mission Generator]** AI units can start from parking (With a new setting in Settings Window to disable it)
* **[Mission Generator]** Tacan for carrier will only be in Mode X from now
* **[Mission Generator]** RTB waypoints for autogenerated flights

* **[Flight Planner]** Added CAS mission generator
* **[Flight Planner]** Added CAP mission generator
* **[Flight Planner]** Added SEAD mission generator
* **[Flight Planner]** Added STRIKE mission generator
* **[Flight Planner]** Added buttons to add autogenerated waypoints (ASCEND, DESCEND, RTB)
* **[Flight Planner]** Improved waypoint list
* **[Flight Planner]** WW2 factions uses different parameters for flight planning.

* **[Settings]** Added settings to disallow external views
* **[Settings]** Added settings to choose F10 Map mode (All, Allies only, Player only, Fog of War, Map Only)
* **[Settings]** Added settings to choose whether to auto-generate objective marks on the F10 map

* **[Info Panel]** Added information about destroyed buildings in info panel
* **[Info Panel]** Added information about destroyed units at SAM site in info panel
* **[Debriefing]** Added information about units destroyed outside the frontline in the debriefing window
* **[Debriefing]** Added destroyed buildings in the debriefing window

* **[Map]** Tooltip now contains the list of building for Strike targets on the map
* **[Map]** Added "Oil derrick" building
* **[Map]** Added "ww2 bunker" building (WW2)
* **[Map]** Added "ally camp" building (WW2)
* **[Map]** Added "V1 Site" (WW2)

* **[Misc]** Made it possible to setup DCS Saved Games directory and DCS installation directory manually at first start
* **[Misc]** Added culling performance settings 

## Fixed issues :

* **[Units/Factions]** Replaced S3-B Tanker by KC130 for most factions (More fuel)
* **[Units/Factions]** WW2 factions will not have offshore oil station and other modern buildings generated. No more third-reich operated offshore stations will spawn on normandy's coast. 
* **[Units/Factions]** Aircraft carrier will try to move in the wind direction
* **[Units/Factions]** Missing icons added for some aircraft

* **[Mission Generator]** When playing as RED the activation trigger would not be properly generated
* **[Mission Generator]** FW-190A8 is now properly considered as a flyable aircraft
* **[Mission Generator]** Changed "strike" payload for Su-24M that was ineffective
* **[Mission Generator]** Changed "strike" payload for JF-17 to use LS-6 bombs instead of GBU
* **[Mission Generator]** Change power station template. (Buildings could end up superposed).

* **[Maps/Campaign]** Now using Vasiani airbase instead of Soganlung airport in Caucasus campaigns (more parking slot)
* **[Info Panel]** Message displayed on base capture event stated that the enemy captured an airbase, while it was the player who captured it.
* **[Map View]** Graphical glitch on map when one building of an objective was destroyed, but not the others 
* **[Mission Planner]** The list of flights was not updated on departure time change. 


# 2.0 RC 6

Saves file from RC5 are not compatible with the new version. 
Sorry :(

## Features/Improvements :
* **[Units/Factions]** Supercarrier support (You have to go to settings to enable it, if you have the supercarrier module)
* **[Units/Factions]** Added 'Modern Bluefor' factions, containing all most popular DCS flyable units
* **[Units/Factions]** Factions US 2005 / 1990 will now sometimes have Arleigh Burke class ships instead of Perry as carrier escorts 
* **[Units/Factions]** Added support for newest WW2 Units
* **[Campaign logic]** When a base is captured, refill the "base defenses" group with units for the new owner.
* **[Mission Generator]** Carrier ICLS channel will now be configured (check your briefing)
* **[Mission Generator]** SAM units will spawn on RED Alarm state
* **[Mission Generator]** AI Flight planner now creates its own STRIKE flights
* **[Mission Generator]** AI units assigned to Strike flight will now actually engage the buildings they have been assigned.
* **[Mission Generator]** Added performance settings to allow disabling : smoke, artillery strike, moving units, infantry, SAM Red alert mode.
* **[Mission Generator]** Using Late Activation & Trigger in attempt to improve performance & reduce stutter (Previously they were spawned through 'ETA' feature)
* **[UX]** : Improved flight selection behaviour in the Mission Planning Window
 
## Fixed issues :
* **[Mission Generator]** Payloads were not correctly assigned in the release version. 
* **[Mission Generator]** Game generation does not work when "no night mission" settings was selected and the current time was "day"
* **[Mission Generator]** Game generation does not work when the player selected faction has no AWACS
* **[Mission Generator]** Planned flights will spawn even if their home base has been captured or is being contested by enemy ground units. 
* **[Campaign Generator]** Base defenses would not be generated on Normandy map and in some rare cases on others maps as well
* **[Mission Planning]** CAS waypoints created from the "Predefined waypoint selector" would not be at the exact location of the frontline
* **[Naming]** CAP mission flown from airbase are not named BARCAP anymore (CAP from carrier is still named BARCAP)
