# Aircraft maintenance telemetry probe

This standalone Caucasus diagnostic checks the DCS data needed by the proposed
aircraft workshop. It does not implement maintenance, classify recoverable aircraft,
or modify a campaign. Mocked tests validate the recorder and mission packaging;
only a real DCS run can establish how an aircraft's damage model changes its life.

## Generate and run

From the repository root:

```powershell
python tools/aircraft_maintenance_probe.py C:\path\probe-a10.miz --aircraft a10
python tools/aircraft_maintenance_probe.py C:\path\probe-hornet.miz --aircraft hornet
python tools/aircraft_maintenance_probe.py C:\path\probe-off-field.miz --aircraft a10 --scenario off-field
```

Existing output files are never overwritten. Open either mission in DCS and unpause.
The player starts hot at Batumi. At 20, 40, 60 and 80 seconds after script startup,
four parked AI aircraft at Kobuleti receive real explosions of increasing strength.
These are A-10C II, F/A-18C, F-16C and UH-1H units, separated by at least 100 metres.
The player and the returning AI A-10 never receive automatic test explosions.
The returning A-10 attempts a normal landing at Batumi; allow up to ten minutes.

At 100 seconds the diagnostic displays current health readings. Earlier readings
remain in the log, including fractional health and readings before terminal events.
The **F10 > Aircraft maintenance probe** menu can show readings on demand or stop
the automated blasts. It also offers two optional player checks:

- Compare health before and after visually jettisoning the canopy, then use the
  canopy marker. A marker records an observation, not proof of damage.
- Apply a small blast near the player, then attempt a return or forced landing.
  Crash and ejection checks should use separate mission runs. The blast can cause
  damage or destruction; this is deliberately confined to a diagnostic mission.

## Recorded evidence

Records in `Saved Games/DCS/Logs/dcs.log` start with
`ESCALATION_AIRCRAFT_PROBE ` followed by one JSON object. If the mission already has
file access, a separate JSONL copy is written under `Saved Games/DCS/_debug_logs/`.
No security settings need to be changed; sanitized missions still use `dcs.log`.

The recorder captures current and initial life, raw and clamped life ratios,
position, airborne state, and relevant events. Hits and kills include the attacker
even when it is a ground unit. Crash, ejection and loss events retain the latest
live reading and its timestamp. Landing records include `event.place` when DCS
supplies it, plus distances to the nearest friendly and enemy probe bases.
Only Batumi, Kobuleti, Sochi-Adler and Gudauta enter this diagnostic's distance
comparison; it is not a campaign-wide recovery classification.

A missing landing place does not prove an emergency landing. Likewise, a HIT event
or a canopy marker does not prove a numerical loss of life. Missing, zero-denominator
or invalid health readings remain unknown. No native life setter is used: the
experiment must measure what physical damage actually reports.

The live checks should establish whether sublethal damage produces fractional
life, whether canopy damage changes that value, which landing events and place
information are emitted, and whether damage readings survive immediately before a
crash or player departure. Until these checks pass, workshop recovery and repair
duration remain unverified.

## First live run

The first A-10 player run recorded A-10C II life changing from 32 to 31,
Hornet and Viper life from 20 to 19, and Huey life from 12 to 11 and then 4.
Numerical fractional health is therefore available on these probe units, although
this does not establish coverage of every subsystem or equivalence across types.
Scripted explosions did not produce HIT records: periodic health sampling is
needed in addition to event handlers. Missing units remain unknown, not recovered
on the strength of their last positive health reading.

The AI return control crashed shortly after startup, so this run provided no
landing evidence. Version 2 moves its low-altitude start to the sea-side approach,
records terrain height/AGL when available, and samples all units immediately at
script startup. A new live run is still needed to validate the landing control.

## Second live run

The version 2 AI A-10 reached Batumi alive. DCS emitted RUNWAY_TOUCH at 288.5
seconds and LAND at 307.5 seconds, both with Batumi's place ID and coalition.
The player Hornet's life remained 20/20 before and after a confirmed canopy
jettison. Canopy removal therefore does not require a special workshop rule.
These observations validate normal arrival and numerical health, not off-field
recovery or the damage state of every aircraft component.

## Off-field landing check

The first version 3 off-field A-10 run produced an airborne-to-ground transition
at 333.801 seconds, RUNWAY_TOUCH at 334.86 and LAND at 346.86. The aircraft stopped
by 357.801 seconds and remained alive at 32/32 life through the marker at 444.73.
Its final position was 3,066.6 metres from Batumi and 185,991.3 metres from Gudauta.
DCS still attributed both landing events to Batumi despite the off-airfield
touchdown. This validates touchdown/survival observations in that case, not a native
"emergency" flag, remote off-field behavior or a damaged emergency return.

Version 3 adds an `off-field` scenario with all automatic explosions disabled.
Take off from Batumi and land on suitable dry, flat terrain outside an airport,
not a runway or taxiway. Remain alive, stopped and in the cockpit for at least
30 seconds, then select **Mark off-field landing attempt** and show readings.
The marker is an observation label, never synthetic landing evidence. A first
undamaged run isolates native touchdown reporting. A separate optional damaged
run can then test the combination; the player blast may destroy the aircraft.

The recorder also samples speed and vertical speed when available, logs airborne
transitions independently of native landing events, and includes nearest-base
distances in periodic samples. Missing units or unavailable speed remain unknown,
never stationary or landed. A surviving off-field landing is not automatically
classified as an emergency: its raw telemetry must be examined alongside the
operator's account and any crash, kill, ejection or later takeoff events.
