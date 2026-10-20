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
