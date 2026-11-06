# In-Mission Air Commander (IMAC)

IMAC provides optional in-mission scripted air coordination, without an LLM. Enable it in the campaign's plugin settings and regenerate the mission. BLUE and RED have independent commanders and enable switches. It is off by default.

## Authority and intelligence

Each side needs a live, airborne AWACS with an operating radar, or a live command centre with working power. Command centres do not create contacts: IMAC fuses observations from that side's aircraft and ground/naval sensors. It assumes coalition-wide radio sharing; it does not simulate regional radio coverage between aircraft and command centres. Losing authority releases temporary orders rather than replacing the original missions.

A standalone command centre can provide authority without IADS membership or a radio-antenna link. This does not provide detection: an aircraft, ground radar or naval sensor still needs to observe the hostile aircraft. Explicit power dependencies and definite IADS power failures are respected.

Air tracks come from unit-controller visual, optical, radar and IRST detections and require known range. DCS reports four flags for a currently visible contact, without memory vectors; only after that positional detection is confirmed does IMAC sample its current position and velocity. For a contact no longer visible, IMAC uses only the sensor's last-known position, velocity and timestamp. Observations expire after 30 seconds. It does not sample undetected aircraft, infer their mission from names, or use their exported flight plans to classify them. Bombers, fighters and other broad classes are used only when the detector knows the type. Weapons and ground contacts are excluded. An interceptor's own reports are ignored while assigned, because DCS's `AttackGroup` task itself grants detection of its target.

SAM avoidance uses campaign-known sites, known naval air defences and currently shared Realistic CAS discoveries. Hidden ground units are not sampled before discovery. Ground threat heights are measured above the launcher's MSL elevation, using the same verified ceiling data as AFAC navigation. Unknown ceilings remain unsafe at every height. Destroyed launchers, missing compatible tracking radars and definite IADS power failures remove threats; radar silence alone does not. Verified mobile transit defences count only while the transit script reports them deployed.

Inactive late-activation units are excluded from flight control, command authority, sensor reports, new air tracks and active SAM envelopes. DCS can report these units as existing and airborne before activation; existence alone is not treated as participation in the mission.

## Decisions

| Flight | Temporary response | Return condition |
| --- | --- | --- |
| BARCAP / TARCAP on station | Nearest available patrol intercepts an approaching bomber/attack aircraft or a threat to a vulnerable friendly flight, including outside the native 50-NM radius | Contact expiry, withdrawal, fuel/ammunition/damage limits, unsafe pursuit, original station end or loss of command |
| AWACS, tankers, transports, ferry, attack and DEAD flights | Move to a safe orbit away from closing fighters or nearby unclassified contacts | At least 30 seconds clear of the danger radius plus 10 NM, including the first three minutes of the return leg, with sufficient fuel and time remaining |
| Attack flight before ingress | Hold in a safe area if a known SAM blocks the immediate route and a viable DEAD flight is working nearby or in the same package | Original blocked corridor becomes clear; otherwise cancel after the wait limit or loss of DEAD |

One patrol is assigned per detected hostile group. Assignment considers distance, fuel for the detour and return, air-to-air ammunition, damage, the original station deadline, predicted target movement and terrain/SAM corridors. Maximum intercept range defaults to 120 NM, distance from the patrol anchor to 80 NM, and withdrawal pursuit to 180 seconds. Every intercept also has a 15-minute hard deadline. These are constraints, not a promise to engage every contact inside the outer range.

Evasion samples several directions, rejects corridors that cross known SAM rings, checks room for the turn and favours increasing separation from all nearby threats. The commander does not move ground units, attack ground targets itself, or order emergency scrambles.

Evasion does not end merely because escaping has stopped the closure. IMAC checks the planned return leg and observed hostile motion before resuming. Its temporary evasion lease can renew while danger persists; native BINGO, station deadlines and loss of command still release it.

An attack holding for DEAD can also evade approaching fighters, then resume only the remainder of its original waiting allowance. An airborne human DEAD flight can provide support without receiving IMAC orders.

## Route and task ownership

Interception and orbit orders are native `ControlledTask` leases pushed above the existing mission. Ending a lease does not call `popTask`, restart the flight at waypoint one, extend a patrol's station time or repeat completed attack waypoints. Native BINGO behaviour remains enabled. IMAC yields to planned refuelling and the reactive BARCAP refuelling controller. Player/Client groups, including mixed groups, never receive route hooks or orders, but can be protected by AI patrols. Runtime player takeover also releases the lease.

Cancellation uses the final generated recovery waypoints, retaining carrier links and off-map/despawn actions. The recovery search checks known threats and terrain and can add a bounded detour. If it cannot find a corridor, it keeps an existing safe hold, reports the problem and retries; it never substitutes an unchecked direct route. BINGO, player control and loss of command still take precedence. This is not a full terrain-following pathfinder.

AFAC and escort navigation remain under their existing controllers; IMAC can send a patrol to protect them but does not reroute them. Air-assault navigation is also left alone. Manual F10 orders cannot be reliably distinguished from other native tasks: use **F10 → Other → IMAC → Pause / release flights for manual control** first. Coalition-wide resume and status controls, plus per-flight pause/resume controls, are available. Pausing releases only IMAC's leases.

## Settings and validation

Both commanders and coalition order reports are enabled inside the opt-in plugin. The default decision interval is 10 seconds; the maximum DEAD wait is 600 seconds. Intercept range, patrol leash, pursuit time, danger radius and waiting time are configurable. AWACS and long-range radars are sampled every cycle; up to 64 other sensors per side rotate fairly. A source processes at most 512 detection entries per pass. Short-lived local-only contacts may be missed between scans. The event history is capped at 128 entries. Native-query errors are rate-limited in the log, and a decision-cycle failure stops automatic command and releases its leases.

**Enable BLUE commander** and **Enable RED commander** are independent campaign plugin settings. **Debug messages and decision logging** is off by default. When enabled, the owning coalition sees command-source changes, orders and rejection reasons, limited to four debug messages per minute. Detailed `IMAC|DEBUG|` log entries also include active-order fuel, waypoint and remaining lease time. Repeated messages and active-order snapshots are throttled to one per minute per flight/topic. Debug is independent of normal order reports and does not show disabled-side diagnostics or reveal undetected enemies. F10 commander status includes the current source of command authority.

Tests execute the production scripts in Lua 5.1 and verify detection, authority, fuel limits, task ownership, geometry, recovery and `.miz` generation. Native DCS tests have verified both-side CAP redirection beyond 50 NM, bounded pursuit and return, known-SAM interception limits, vulnerable-AWACS evasion and return, attack holding and resumption, DEAD waiting expiry, standalone command-centre authority, independent coalition switches, inactive-unit exclusion, F10 controls, native refuelling and carrier landing. Campaign-scale interactions still need observation. IMAC does not change DCS's native engagement or reaction options; its safety buffers are conservative estimates, not a guarantee that native AI will never enter a threat envelope. Logs use the `IMAC|` prefix.

Native task and observation contracts: [unit-controller detection](https://wiki.hoggitworld.com/view/DCS_func_isTargetDetected), [pushed tasks](https://wiki.hoggitworld.com/view/DCS_func_pushTask), [orbit](https://wiki.hoggitworld.com/view/DCS_task_orbit), and [AttackGroup's detection effect](https://wiki.hoggitworld.com/view/DCS_task_attackGroup).
