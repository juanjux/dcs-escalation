# Realistic CAS — experimental campaign plugin

The plugin is **experimental and OFF by default**. Both sides discover ground
groups through visual, optical, thermal and eligible ground-radar observations,
with terrain LOS and approximate weather, daylight and cover effects. Firing
reveals a managed group immediately. The separate AFAC option adds airborne
search and marking missions; existing campaign settings are not enabled on load.

Campaign injection and final-pydcs environment export now have automated coverage,
including saving/reloading a MIZ and compiling its scripts. This is NOT yet a
full generated-campaign DCS acceptance or campaign-scale performance measurement.
Adapters for arbitrary TIC/CTLD/MOOSE runtime-created units remain unsupported.

## Enabling the plugin

- Select **Realistic CAS (experimental)** in Mission Plugins. Initial options:
  immediate discovery attempts, detection rolls on, contact lifetime600s,
  approximate theater cover,
  debug off. The plugin itself remains off by default.
- Disable **TIC and Moose Autolase**. TIC has a separate visibility/clone conflict.
  **CTLD logistics may stay enabled**: turn off its **JTAC autolase targets**
  option. This also prevents autolase from deployed troops/vehicles, not just
  generated JTACs. Smoke and laser-code settings do nothing with autolase off.
  Runtime-created CTLD units are not yet registered as fog targets/observers;
  this remains a documented limitation, not a generation blocker.
- Combined Arms **Number of JTAC controllers** is a human slot count, not an AI
  autolase switch; zero is fine but is not required by this compatibility check.
- Generated legacy JTACs are omitted while Realistic CAS is enabled. Use the
  separate **Enable AFAC missions (experimental)** option for airborne JTACs.
  Turning the plugin off restores the original JTAC generator path.
- Fixed map SAM groups remain known; frontline SAMs participate in fog. F10
  visibility is unchanged unless its separate frontline option is enabled.
  Weapon accuracy is unchanged. AI CAS and Armed Recon receive
  moving search routes, and AFACs receive known-threat avoidance.
- Terrain profile0 selects an explicit approximate biome by theater;1..5 override
  it (desert, grassland, tundra, forest, city). This is currently homogeneous,
  not a real per-position cover map. Unknown theaters require a manual profile.
- Uses final generated date/time, campaign reference latitude/longitude/timezone,
  three daily solar schedules (including midnight and polar handling), final
  visibility, fog/dust and cloud metadata. Native automatic fog density is unknown;
  uniform manual fog, polar brightness and cloud slabs are declared approximations.
  Preset descriptions select a cloud approximation; reused `PresetNN` names and
  zero numeric density/thickness do not mean a clear sky. Warnings are logged.
- This snapshot does not claim support for other scripts that create units or
  control visibility. Declared late starts work; arbitrary runtime clones need
  adapters.

## F10 frontline contacts

Contact pins include the unit types actually observed during the current contact,
for example `Frontline contact: BMP-2, T-72B`. They do not list unseen members of
the group. Rediscovery after expiry starts this identification history again.
The pin remains a map marker, not a native vehicle icon.

**Hide frontline contacts on the F10 map until discovered** is optional and off by
default. It hides RED frontline native icons, including support infantry and MANPADS, and draws
BLUE-only contact pins from the existing Realistic CAS observations and lifetime.
Pins retain their last observed position until another observation updates it;
reading the map does not renew contacts. Expiry removes the pin, and rediscovery
creates a new one. BLUE friendly icons and non-frontline groups keep their normal
visibility; this does not enable global Fog of War or depend on AFAC missions.

The option enables F10 Map User Marks for the generated mission. Native hidden
flags also hide those groups from RED players, so this version is for BLUE play.
Pins replace enemy-front icons and cannot provide native Combined Arms selection
of those groups. Updates are processed in bounded batches with fresh marker IDs;
unchanged observed positions do not recreate pins. Regenerate the mission after
changing the option.

## Contact reports

The separate **Contact reports** options control notices when an enemy group is
discovered, reveals itself by firing, or is forgotten after its contact expires.
They are enabled by default, with a configurable 15-second duration. Reports go
only to the coalition observing that enemy and use its last observed position.
Contact renewals do not repeat announcements. Disabling them also silences AFAC
discovery notices; marking and safety reports remain active. These options work
independently of F10 pins, AFAC mission activation and diagnostic logging. AFAC
coordinate format applies when AFAC is enabled; otherwise reports use degrees
and decimal minutes. The contact service retains only types actually observed,
including a firing unit's type, and never reads a hidden group's full composition
to describe it.

## Airborne forward air control (AFAC)

Recovery preserves native RADIO waypoints as terrain-following AGL legs instead
of rejecting their planned low height against the generic 150 m diversion margin.
Known-AA checks use a conservative low altitude, including intervening valleys;
BARO legs and invented diversion points retain their sampled terrain checks.

AFAC missions currently support AI pilots only. Player checkboxes are disabled
and player pilots are excluded from their rosters. Replace any player pilots in
older AFAC flights before mission generation; their global player flags are kept.

Enable **Realistic CAS (experimental)** and, in its **Airborne forward air control
(AFAC)** section, **Enable AFAC missions (experimental)**. Reopen the flight
creation dialog after changing these settings. Choose **AFAC — Frontline** for a
frontline segment or **AFAC — Area** for an area target. Compatible drones, scout
aircraft and helicopters use normal squadrons, aircraft inventories and pilots;
remote UAV operators cannot be killed, wounded or go missing with their aircraft.
Eligible transport helicopters carry a thermal-equipped JTAC. Aircraft without
thermal observation show a warning when creating a night flight.

The A-10 family can also perform both AFAC roles. Its default AFAC payload has
14 smoke rockets, plus a LITENING pod on A-10C variants. As with the other AFAC
families, capabilities combine the best-equipped variants for gameplay; the
A-10A shares the family's optical, thermal, laser and IR marking profile.
Illumination rockets and countermeasure flares do not supply ground-marker smoke.

AFACs search without attacking and prefer marking observed contacts. They report
coordinates, designate with laser and night IR where equipped, and use finite
payload smoke in green, red, orange or blue. Each aircraft keeps its assigned
smoke colour; colours repeat if necessary. Only one AFAC reserves an enemy group
at a time. Discovery and effective marking award separate pilot experience.
AI flights climb above verified threat ceilings when aircraft and cloud limits
permit, otherwise keep lateral separation. Newly revealed threats can trigger an
urgent escape outside the patrol zone; recovery legs are also checked. A blocked
recovery causes a warning and a safe hold where possible, with fuel still burning.
Player flights are not automatically steered. These approximate threat envelopes
do not guarantee safety from hidden defences, interceptors or terrain.

| AFAC option | Default |
| --- | --- |
| Maximum on-station time | 60 minutes; Bingo fuel ends the patrol earlier |
| Marking time per group | 5 minutes |
| Message duration | 15 seconds, addressed to the AFAC's coalition |
| Shared laser code | 1688 |
| Coordinate format | Degrees and decimal minutes; DMS and MGRS also available |

## Options and behaviour

### Option help

Hover an option's label or control for its explanation.

- **Probabilistic detection** is on by default when this plugin is used. A failed
  roll retains the search and retries on a later valid scan, no faster than every
  the configured retry interval (five simulated seconds by default). Turn it off
  for discovery on the first valid sensor/LOS observation. There is no preliminary
  continuous-observation wait. Old saved search-time values are ignored. Firing reveals
  immediately, **without any roll**.
- **Contact lifetime** starts again after an observation or shot. It is how long
  the whole group stays revealed, not the time needed to find it.
- **Cover: Automatic (by map)** chooses one homogeneous approximation:
  desert for Nevada, Iraq, Syria, Persian Gulf, Sinai and Afghanistan; grassland
  for Caucasus, Normandy, The Channel, Germany and Falklands; tundra for Kola;
  forest for Marianas. It does not sample forests, cities or vegetation at each
  target. The drop-down also offers Desert, Grassland, Tundra, Forest and City;
  their saved numeric IDs remain 0–5 for compatibility. Manual profiles apply everywhere;
  unsupported maps require a manual choice. Terrain LOS remains a separate check.
- **Debug** adds verbose detection/contact diagnostics to `dcs.log`, not F10
  markers. Errors and scheduler-overload warnings are logged even when it is off.

### Visibility rules

- Effective visibility unit: a DCS ground GROUP. Revealing one member exposes its
  whole group. Native per-unit SetInvisible affected the whole group in engine tests.
- Blue/red symmetric, neutral groups excluded. Own-side observations cannot reveal
  a target to the opponent. `fire` automatically reveals to the opposing coalition.
- SHOT plus SHOOTING_START, not per-projectile gun sampling. Repeated fire renews the
  exposure but does not repeatedly change native visibility.
- Default TTL 600 seconds, renewed by a genuine observe/fire call. Reading or copying
  a contact never renews it. Snapshot positions do not track the hidden live object.
- Expired positions remain in private contact memory until unregister; callers see
  `revealed=false`. DCS sees live positions only while physically revealed.
- One indexed expiry-heap entry per exposed group: O(log N) renewal, bounded expiry
  work per tick, no unbounded timer allocation per shot. At most `expiryBudget`
  expirations are processed each interval; logical visibility expires immediately,
  physical concealment may lag under backlog. Measure/tune this in campaign tests.
- Explicit visibility ownership: targets require `originalInvisible=false`.
  The adapter cannot query original invisibility from DCS; the caller/generator
  must certify it. Never list TIC helpers or protected groups. No scan of all groups.
- Expiry visibility errors are logged and retried on a bounded timer. Initial
  registration/reveal failures return failure and require a new registration/event
  or observation; shutdown restoration failures require another `stop()` call.
  A failed hide is NOT reported as confirmed
  concealment: diagnostics/contact expose `backendVisible`. Acceptance of setCommand
  is the strongest API acknowledgement, not a DCS getter of physical invisibility.
- No destruction/respawn, immortality or radar changes. The optional F10 layer
  changes only explicitly registered RED frontline icons and its own contact pins.
  AFAC avoidance may replace native AI routes while preserving recovery tasks.
  AI CAS and Armed Recon routes include a moving
  four-leg search circuit in their assigned area while the plugin is enabled.
  Native search-and-engage tasks remain responsible for detecting/attacking
  revealed contacts; the circuit never reads hidden target positions. Human or
  mixed player flights are not automatically steered. CAS uses its
  scheduled end time; Armed Recon allows the doctrine's CAS duration after TOT.
  Native engagement tasks have matching time and 20% fuel stop conditions, so
  combat cannot leave an unlimited search-and-engage order active after exit.
  Search corners check those limits before resuming the original exit route.
  Only the last corner loops; intermediate legs use ordinary native navigation.
  Small zones use a minimum 250 m standoff
  half-width, without enlarging the native engagement zone. A standalone Cobra
  engine probe validated hidden-target search, revealed-target engagement and
  departure after station time. Full campaign and other-aircraft acceptance remain
  separate checks; this does not guarantee that native AI destroys every contact.

## Detection rolls

All existing range, orientation, role, equipment, radar-on, weather and terrain-LOS
gates still apply. A random roll never overrides a failed gate. For each eligible
sensor channel, let `q = 1 - slant_distance / effective_range` (0 at the edge,
1 at zero distance). Default per-attempt gameplay probabilities are:

| Channel | Chance before optical altitude factor |
| --- | --- |
| Visual | 0.10 + 0.70q |
| EO / IR | 0.20 + 0.70q |
| Ground radar (RBM) | 0.50 + 0.45q |
| Moving-target radar (GMTI) | 0.75 + 0.23q |

Both endpoints for every channel are editable percentages in the plugin options.
Chance interpolates linearly from the far endpoint to the near endpoint; the
near chance must be at least the far chance. Percentages can be 0–100.

For airborne visual/EO/IR only, by default multiply by
`1 - 0.60 * min(1, AGL / channel_altitude_ceiling)`.
Slant distance already includes vertical separation; the extra AGL factor models
the difficulty of identifying small ground targets from altitude. Lower is better
only if LOS and the other gates still pass. Ground observers and radar do not get
this altitude factor. GMTI still needs target ground speed and radial motion.
The best eligible channel supplies one probability, not independent sensor rolls.
Targets moving horizontally at least 0.5 m/s receive a 50% relative increase in
that probability, after altitude and AFAC skill factors, capped at 100%: a 40%
chance becomes 60%. Slower motion is ignored to avoid stationary physics jitter.
The bonus uses the observed unit's current velocity, applies to both coalitions
and every sensor channel, and does not bypass sensor/LOS gates or add rolls.
These numbers are **tuning starting points, not real sensor specifications**.

One observer makes at most one roll for its focused group per scan and per retry
interval, regardless of member count. The first valid member supplies the sample.
Already shared contacts refresh without rolls; shots bypass both search and rolls.
Missed scans do not accumulate catch-up rolls. This uses simulated time rather
than frames or wall-clock time; scheduler overload can still delay attempts.
No new global scans or engine/LOS calls are added. The random source is not reseeded.
With debug enabled, `DETECTION_ROLL` logs observer/group, channel, distance, range,
AGL, chance, draw and result; `SEARCH_STATS` includes roll/pass/miss counts.

The earlier in-engine acceptance predates these rolls; the probability curves
need campaign tuning. The altitude penalty (default 60%) and airborne observation
ceilings (visual about 11,483 ft AGL; EO/IR 23,000 ft AGL) are also options. The ceiling both
limits observation and defines where the full altitude penalty applies; ceiling
changes therefore also affect deterministic mode. Ground and radar are unaffected.
The configurable retry interval defaults to 5 seconds (range 5–300); a scan may
delay an attempt further. Settings are checked before generation and Lua startup,
and the exported values are logged as `CONFIG` entries.

Standalone callers opt in with `probabilisticDetection=true` and can use
`acquisitionSeconds=0` for an immediate first attempt. Omitted probability mode
keeps the existing deterministic behaviour.
The optional `probability` table accepts the option names from `plugin.json`
(percentages, seconds and metres, not fractions); omitted fields keep defaults.

## Standalone mission usage (after loading both Lua files)

```lua
local fog = RealisticCAS.start({
    enabled = true, -- absent/false is inert
    ttl = 60,       -- short only for prototype tests; campaign default is 600
    debug = true,
    targets = {
        { name = "RED_ARMOUR", originalInvisible = false },
        { name = "BLUE_ARMOUR", originalInvisible = false },
    },
})
-- An approved observation supplies the observed point; do NOT poll hidden objects
-- here and call that a sensor. Attach the perception pipeline described below.
fog:observe("RED_ARMOUR", coalition.side.BLUE, observedPoint, "test observation")
-- Stops handler/scheduler and restores original visibility; retry if false.
fog:stop()
```

Allowlisted late births register on BIRTH; a new group incarnation with the same
name replaces its old registration without touching unrelated IDs. This is not
yet a TIC clone adapter. Unregistered/dead-group lifecycle pruning beyond explicit
unregister/replacement is left to the forthcoming generator/lifecycle integration.

Revealing a group is not a guarantee that a terminated AttackUnit task restarts.
In engine CAS resumed about three minutes after re-exposure in the tested profile;
direct-task resumption still needs an adapter-specific test.

Tests use Lua 5.1 via lupa, independent of the campaign Python import graph. They
validate state and DCS wiring with doubles, not the actual DCS sensor/AI simulation.

```text
python -B -m unittest discover -s tools/realistic_cas_tests -p test_contact_core.py -v
```

`tools/realistic_cas_tests/build_core_smoke.py` builds one 480-second AI-only mission
using these exact source files. It records real firing events, native detection and
core state, then restores visibility. Manual observations in that scenario are
test injections, not implemented sensors. See its generated `LEEME.md`.

## Observer pipeline

Load `core.lua`, `dcs.lua`, `sensors.lua`, `environment.lua`, `detection.lua`, then
`detectors-dcs.lua`. Attach to an active `fog` with `RealisticCAS.startDetection`:

```lua
local conditions = RealisticCAS.newEnvironment({
    defaultCover = "desert", -- explicit theatre metadata, NOT land.getSurfaceType
    startTime = 12 * 3600,   -- local mission start time, not script attachment time
    sunrise = 6 * 3600, sunset = 18 * 3600, -- example; export correct date/place
    weather = 1, visibility = 30000, -- normalized weather factor, metres visibility
    zones = {{x = 1000, z = 2000, radius = 500, cover = "city"}},
    -- Optional approximate MSL cloud slab. IR attenuation is NOT a universal veto.
    clouds = {base = 2000, top = 4000, visualTransmission = 0.05, irTransmission = 0.5},
})
local detection = RealisticCAS.startDetection(fog, {
    targets = {{name = "RED_ARMOUR-1", groupName = "RED_ARMOUR"}},
    observers = {{name = "HORNET-1", typeName = "FA-18C_hornet", category = "air",
                  role = "CAS", equipment = {targetingPod = true}}},
    environment = conditions,
    targetBudget = 64, workBudget = 128, interval = 1, revisit = 5,
    debug = false,
})
```

Declare **every member** of target groups; any observed member reveals the group.
Observers can be `air` or `ground`. The bridge resolves live units by name, rejects
dead/neutral units and type changes, and skips aircraft on the ground. Human slots
are excluded unless that observer explicitly has `allowPlayer=true`.

The small curated capability table is augmented by explicit `equipment` booleans:
`ir`, `eo`, `rbm`, `gmti`, `targetingPod`. Unknown types get visual detection only.
Do not interpret arbitrary radar/IRST presence as ground radar/FLIR. The registry
exporter reads exact per-aircraft pod CLSIDs and injects them with the registry.
The campaign bridge does **not** infer a mounted pod from an aircraft name.
The Hornet/A-10 tests showed why native getSensors alone cannot provide that fact.

Starting ranges (metres; adjustable model constants, not hardware specifications):

| Channel | Air | Ground |
| --- | ---: | ---: |
| Visual | 9260 | 3000 |
| EO | 12000 | 4000 |
| IR | 12000 | 4500 |
| RBM / GMTI | 12000 / 24000 | None |

Only declared capabilities enable their channel. Visual/EO use light, cover,
weather, visibility and cloud transmission; IR uses its separate attenuation and
is useful at night. Airborne visual height cap is about 11,483 ft AGL, optics
23,000 ft AGL. Both height controls display and accept feet. Saved settings and
Lua retain metres (3500 and 7010.4 respectively), preserving existing overrides
without changing their physical height or rounding them on opening the UI.
These are tunable initial approximations. Radar requires CAS/BAI/Armed Recon and
the native getRadar on flag, within a 120-degree horizontal forward cone and at
most 80-degree depression. This approximates search, **not actual radar mode or
pod direction**. GMTI requires >=2m/s target ground speed and >=1m/s radial speed.
AWACS/EWR receive no ground-radar power just because they have an air-search radar.

The optical ceiling is a conservative, shared search-model approximation, not a
published specification for every pod or integrated sensor. The
[USAF describes tank identification from 30,000 feet with targeting pods](https://www.barksdale.af.mil/News/Article/320706/let-the-bombs-hit-the-floor/)
in a discussion of LITENING II and Sniper; it does not specify AGL altitude,
viewing geometry or which imaging channel was used for that example.
[Raytheon's ATFLIR release](https://raytheon.mediaroom.com/index.php?item=70&s=43)
reports laser effectiveness above 50,000 feet, not a universal IR vehicle
discovery threshold. The chosen 23,000 ft default is a gameplay setting, not a
hardware limit inferred from those sources; they do not calibrate the discovery
probabilities. The unchanged 12000m optical
**slant** search range still applies: greater height leaves less horizontal
reach. Weather, cover, LOS and search/roll requirements still apply. Finding an
unknown vehicle is not equivalent to identifying an already cued target.

Terrain LOS is checked last and blocks every channel. Cover is a 250m grid with a
bounded 4096-cell cache over at most 128 configured circular zones. Illumination
uses exported sunrise/sunset with twilight ramps, cached for 30s. Clouds are a
simple slab intersection. Campaign dates and final weather are exported, with
explicit approximation warnings; detailed spatial cover and native cloud layers
remain unavailable in this first integration.

Spatial indexing is incrementally refreshed. Each tick uses at most `targetBudget`
index reads plus `workBudget` search steps (including empty cells/candidates), and
at most two observer reads. Candidates are re-read before reveal, so stale index
positions never grant a contact at an old geometry. Index/search latency can delay
discovery, especially with dense cells, moving targets or many observers. Work is
bounded, **not a guarantee of constant detection latency or measured DCS FPS**.
Scans use a bounded revisit period; optional probability rolls are not per-frame.
No native isTargetDetected query is required to discover an invisible target.

### Discovery timing

Campaigns use `acquisitionSeconds=0`: the first valid sensor/LOS observation can
reveal an unknown group immediately, subject to the optional detection roll.
Failed rolls retry on later valid scans without adding a new observation delay.
Known contacts refresh without rolls. Firing reveals immediately. The former
search-time UI option is removed, and older saved values do not affect generation.

### Legacy delayed-acquisition diagnostics

Standalone `startDetection` controls still accept a positive `acquisitionSeconds`
to isolate timing and fire-discovery behaviour in diagnostic missions. The
following delay rules and older combat measurements concern those controls,
not the current campaign discovery setting.

Each observer examines at most one unknown group at a time, using one bounded
record per observer rather than an observer × target history. A group containing
many vehicles can contribute only one sample per sweep. Progress is capped to a
revisit interval per sample; long scheduler gaps do not count as eyes-on time.
Missing an observation sweep or losing the observer resets acquisition. Shared
contacts bypass new acquisition, but renewing them still requires a fresh valid
sensor/LOS observation. Fire reveals immediately through the existing event path.

The maximum observation gap defaults to max(60s, twice the revisit interval).
This tolerates ordinary scheduler rotation with many observers without granting
the whole gap as search time. Only at most one revisit interval is credited per
sample. A longer gap still resets search; it does not reveal anything for free.

The matched combat harness 38 completed without script errors, but is **not a
balance acceptance**: its packed ground geometry and blue-side orbit were poor
proxies for campaign CAS. Replacement 39 uses the campaign's per-role spawn-depth
bands, a 24km lateral segment, and a plain central FLOT START/END route followed
by egress. CAS is not an OrbitAction in the campaign generator. Both use native
EngageTargetsInZone; version 39 uses the campaign's default 10NM zone. See the
combat results note for casualties, repeated runs, and attribution limitations.

This limits discovery, not shooting accuracy, ammunition or number of kills.
It has automated coverage including the DCS bridge and subsequent in-engine
combat trials40–43. The earlier31–37 passes used instantaneous acquisition and
must not be cited as proof of gradual search. The isolated combat test series is
closed; it does not establish a fixed casualty-reduction percentage. In43 an A-10
crashed in ON, which confounds that pair's casualty comparison. Further calibration
belongs in campaign-scale validation, not another fixed-target kill-ratio test.

Declared lists are bounded snapshots for now: dead units stop contributing, late
births with declared names can appear, but dynamic clone enumeration/removal is
not yet implemented. Logs prefix `REALISTIC_CAS_SENSOR`; contact transitions retain
`REALISTIC_CAS`. `detection:getDiagnostics()` reports work/LOS/reveals/errors and
rejected sensor envelopes. Stopping detection leaves existing contacts to expire;
stopping the fog owner restores visibility and terminates detection on its next tick.

Run all tests with `python -B -m unittest discover -s tools/realistic_cas_tests -p "test_*.py" -v`.

Before opening or updating a PR, also run the repository-wide CI lint commands:

```text
python -m black --check .
python -m mypy game
python -m mypy tests
```

Use the versions used by CI (Black26.3.1 and mypy1.15.0 at the time of this
integration). Black checks the diagnostic builders too, not only runtime code.
Passing the Lua/functional tests is not a substitute for these checks. Resolve
typing errors in the code rather than weakening the repository's mypy rules.

## Exported mission entry point

Load the filenames in Python `SCRIPT_ORDER`, then call
`RealisticCAS.startMission(config)` with `enabled=true`, schema-1 `registry`, an
explicit `environment`, and nonnegative `acquisitionSeconds`. Merely loading
`bootstrap.lua` does nothing. Disabled startup creates no handlers, timers or
visibility changes. The Python `render_startup` helper preserves booleans/numbers
and displays a visible error if startup fails.

The bootstrap checks that known fixed SAM objectives never appear in the managed
ground list, validates the environment before hiding groups, and rolls back
visibility if sensor startup fails. `RealisticCAS.mission:stop()` and the native
mission-end event stop detectors and restore visibility. A failed restoration
keeps the recovery handle for a later retry; it is not silently reported as success.
Lua integration tests cover these paths using DCS doubles, not native engine
acceptance. The experimental campaign hook rejects active CTLD autolase, Moose
Autolase and TIC, not CTLD logistics. AFAC search and marking use the same
visibility and compatibility rules.
In-engine controls 35–37 additionally passed night/IR, controlled cloud
transmission, and RBM/GMTI with live DCS radar-on/target velocities. These validate
the model/bridge, not native radar-mode telemetry or physical cloud calibration.
Development trial notes are kept locally, outside the repository.

## Campaign registry boundary

`game/missiongenerator/realisticcasluadata.py` collects final pydcs group/unit
names, real blue/red coalition, per-unit payload CLSIDs and roles from FlightData
or explicit JTAC records. Mixed-flight human slots do not become AI observers;
AI wingmen do. Unknown/unmapped aircraft are warned about rather than assigned an
invented role. Integrated sensor capabilities remain in the Lua profile table.

`enabled=False` returns before reading mission data. Collection and typed Lua
serialization do not mutate the mission or activate scripts. Explicitly excluded
groups and ground groups with waypoint visibility commands remain outside its
ownership. Arbitrary script/trigger visibility ownership still needs integration;
this inspection is not a certificate of universal compatibility. TIC campaigns
are rejected at this boundary until the clone/visibility adapter exists.

`LuaGenerator.generate` now preflights the registry/environment/options and injects
the source files in `SCRIPT_ORDER`, then the typed startup action. Missing
source files fail generation before partial plugin injection. Off returns before
reading mission metadata. No new standalone mission is needed just to validate
this Python serialization boundary. AFACs coordinate their own target-group
reservations; other scripts' runtime visibility ownership still needs adapters.

Confirmed scope: map SAM objectives (`SamGroundObject`, category `aa`) are never
concealed, including their generated support groups. UnitMap campaign membership
identifies them; neither vehicle type nor group name does. A SA-13 on the frontline
remains subject to fog. Buildings are not collected at all. BAI assignments grant
no automatic initial reveal; their native routes/tasks stay unchanged. The
collector requires UnitMap when enabled, so missing ownership metadata cannot
silently hide a known SAM site. Exempt sites may still provide ground observations.

## Campaign scheduling and limits

Ground combat is intentionally subject to the same fog. Both sides can start
hidden: scripted ground observers use geometry, environment and terrain LOS,
not native AI detection of invisible targets, to reveal each other. Only the
opposing coalition may reveal a managed group; there is no third-side visibility
contract. Fixed SAM objectives remain exempt.

At 0.25-second intervals the campaign scheduler shares a budget of 1,024 work
steps, 64 observer slots and **64 terrain LOS calls** across all observers. Each
observer gets at most 128 work steps before yielding; unfinished scans resume
round-robin. Budgets are not multiplied by observer count. The LOS ceiling is
256 calls per simulated second, not a measured CPU-time guarantee. Native DCS
cost and campaign frame-time impact still require in-engine measurement.

A 25-km coalition occupancy grid conservatively rejects observers with no indexed
enemy in their maximum-range bounding box before fine-cell/sensor/LOS work. The
coarse checks count against the same work budget. Target movement/coalition and
removal update occupancy during the bounded index refresh; culled observers retry
after the normal revisit delay. This can delay discovery until the index refresh
and revisit, but is not permanent culling or an assertion that a target is visible.

The legacy diagnostic acquisition gap limit remains 60 seconds: stalls do not earn continuous
observation credit. Overdue scans/gap resets emit rate-limited warnings even with
debug off. Debug counters include maximum sweep gap, overdue visits, budget hits
and culling. Overloaded missions can still suffer delayed detection; warnings
are not automatic load shedding or a guarantee for arbitrarily dense missions.

CI runs `pytest --cov --cov-report=xml tests tools/realistic_cas_tests`, including
Lua 5.1 regressions for 729 independently acquiring observers, dense-observer
fairness, per-tick limits, culling re-entry and two hidden opposing ground groups.
These use engine doubles, not a native weapon/CPU simulation. Take Off shows an
actionable warning for incompatible plugins before planning or simulation starts;
non-UI generation retains the same preflight guard.
