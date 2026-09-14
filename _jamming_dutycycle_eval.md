# EW Jamming Duty-Cycle — Design Evaluation

**Scope:** read-only design eval of Juanjo's proposed duty-cycle replacement for the offensive-jamming success/fail in the `ewrj` plugin. No files changed, no PR. Source verified against `resources/plugins/ewrj/EW script 2.1.lua` and the two Python touch-points.

**File of record:** `C:\Users\juanj\Saved Games\DCS\dcs-retribution-juanjux\resources\plugins\ewrj\EW script 2.1.lua` (canonical; the `dist\`, `dist_full_fork\`, and `.claude\worktrees\*` copies are build/worktree duplicates).

---

## 1. Verdict

**DEFER. Soak-test the current blend before building anything; if you build, start with the cheaper graded-missile-delete option, not the WEAPON_HOLD duty-cycle.**

The proposal is *implementable* and three of four lenses rate it "viable-with-caveats." But the adversarial lens lands real, code-grounded hits, and the honest synthesis is:

- The shipped stack **already delivers Juanjo's stated intent** ("Harpoon stream + EW escort → fleet intercepts some but fewer") through **two independent continuous levers**: always-on engine ECM (radar-lock degradation, `aircraftbehavior.py` L508) and the per-shot SARH delete (`checkMis` L1204-1219) gated by `JammedLaunchers`. The duty-cycle tries to recreate graded leakage a third time, via a coarse, latency-bound, race-prone ROE toggle.
- The duty-cycle's *only* genuinely new capability is reducing **new defensive launches** during hold sub-windows. But the headline scenario is a *stream of incoming Harpoons* — and **ROE does not abort a missile already in flight**. The thing that actually reduces interception of in-flight rounds is the `JammedLaunchers` delete path, which works **today** under RETURN_FIRE and needs no WEAPON_HOLD.
- The proposal is **not a tweak to `check()`** — it is a rewrite. It requires: a new WEAPON_HOLD setter (partially reverting the deliberate L732-738 realism decision), a single per-SAM window owner (the current per-`(jammer,sam)` `check()` chains cannot produce a coherent duty cycle), original-ROE capture (doesn't exist anywhere today), cancellation of three uncancellable `samON` timers, and a guaranteed restore-on-teardown (the new dominant failure mode is a SAM stuck silent forever).

**Condition to proceed (in order):**
1. **Soak-test the shipped blend** for the anti-ship case. The current model's leakage is real but opaque; it may already feel right.
2. If it still feels binary, **first try graded `JammedLaunchers`** (Alternative D below) — minimal risk, no strobing, no rewrite.
3. **Only if that is still insufficient**, build the full duty-cycle per Section 3, with the Section 4 mitigations as hard requirements (not nice-to-haves).

Do **not** ship the duty-cycle blind. It re-opens the exact "whole fleet goes dark" behavior the L732-738 comment was written to kill.

---

## 2. Recommended mechanism (if built)

A **single per-SAM windowed driver** that owns ROE, replacing the JAMMED/PEEKING state machine for the offensive path.

### Quality → hold-fraction
- Derive quality `q ∈ [0,1]` from the **deterministic geometry margin only** — `conditiondist` (L432-433, capped 60), angle/bank/pitch gates (L602-607), height terms — **NOT** from the per-call `dice` (L429). Reason: `prob` contains a fresh dice every call; folding it into `q` makes hold-fraction flicker wildly window-to-window even with a stationary jammer. Let dice jitter the *window outcome*, never the *quality scalar*.
- **Direction matters (sign bug risk):** today success is `prob <= probsectorN`, i.e. quality is HIGH when `prob` is LOW relative to threshold. A naive `q = prob/probsectorN` is **backwards**. Correct: `q = clamp01((probsectorN_band - detProb) / band_ceiling)` — how comfortably the deterministic roll clears the threshold.
- **Gates are boolean.** If any of `anglecondition < TargetandOffsetJamSam`, `anglesamjam >= bank`, `anglesamjam > pitch` fails → `q = 0` → full OPEN_FIRE window. Don't try to soften near-misses; hard-zero is faithful to current behavior.
- `OFFENSIVE_POWER` (0.8) becomes a **literal multiplier on `q`** → scales hold seconds. This is a semantic upgrade: "0.8 = degraded" becomes literally true instead of opaquely scaling a probability threshold.

### Window size
- `W ≈ 10s`, but **jittered** `random(8,12)` so SAM boundaries don't synchronize across hulls.
- **Critical constraint from the adversarial lens (code-grounded):** the OPEN_FIRE sub-window must be **≥ the SAM's commit latency or the SAM never fires**. The current code already measured this: `samCommitDelay` (L209-215) floors at 1.2s and scales to ~4.5s; `peekDuration = random(5,8)` (L245) exists precisely because shorter peeks produced no shot. **A 4s OPEN_FIRE sub-window (the proposal's "regular roll") is at or below commit time** → for common/weak rolls the SAM spends the active window spinning up and never launches → you accidentally rebuild full suppression for low rolls while believing you made it gentler. **Therefore the OPEN_FIRE sub-window must be ≥ ~5s.** This directly contradicts the proposal's "weak = 2s hold + 8s fire / great = 10s hold" granularity at the fine end. Build the window math around commit latency, and expect to **bias paper hold-fractions DOWN ~20%** (after each hold, the SAM re-acquires, partly wasting the fire sub-window → effective suppression > nominal).

### Multi-jammer combination + cap
- The existing `jammerScale = 1/sqrt(count)` (L297, L594) **reduces** per-jammer effect — the OPPOSITE of "more jammers → more hold." Do **not** reuse it for the offensive path.
- Combine per-(sam,jammer) qualities as a **probabilistic OR**: `q_sam = 1 − Π(1 − q_j)`. Monotonically increasing with jammer count, naturally saturating, never exceeds 1. (Not `max()` — ignores extra jammers; not raw sum — saturates at 100% with 2 jammers.)
- **Explicit union cap:** clamp final hold-fraction to **≤ ~0.7** independent of jammer count. `1/sqrt` caps *probability*, never an *interval union* — without a hard union cap, a line of 8 jammers drives hold → ~100% (the original full-suppression bug in fractional clothing). This is **new state the proposal does not specify** and is mandatory.

### ROE states
- **Hold sub-window → `WEAPON_HOLD`** (new `samHOLD` setter). RETURN_FIRE keeps intercepting incoming missiles, so it cannot reduce launches — the proposal is correct here. This **partially reverts the L732-738 realism decision, on purpose, for hold sub-windows only**. Keep `samOFF`/`samON` for the baseline.
- **Fire sub-window / failed roll / between windows → restore to captured ORIGINAL ROE**, not a forced OPEN_FIRE. Today `samON` unconditionally stamps OPEN_FIRE (L700) and there is **no `getOption` read anywhere** — a duty-cycle that stamps OPEN_FIRE every window would progressively corrupt any campaign-set ROE. Capture origROE once at first-touch.

---

## 3. Implementation sketch (Lua only — no Python change)

Both Python touch-points (`configure_ewar` L472-508, `offensive_jamming` L180-200) only emit `RunScript("startEWjamm(...)" / "stopEWjamm(...)")` and append `OptECMUsing.AlwaysUse`. They carry **no suppression logic** → the duty-cycle is entirely in the Lua.

**New state (near L220):**
```lua
SamQuality = SamQuality or {}   -- [samunit][jammer] = {q, t}   per-jammer deterministic quality + timestamp
SamWindow  = SamWindow  or {}   -- [samunit] = {driving=true, origROE=..., windowEnd=, holdUntil=, phase=, epoch=}
```

**New setter `samHOLD(groupsam)`** — clone of `samOFF` (L707-745) but `setOption(...ROE, ...ROE.WEAPON_HOLD)`.

**Capture origROE once** — at first-touch read the group controller's current ROE (add a `getOption` near the controller fetch at L724) and store in `SamWindow[samunit].origROE`. Restore to THAT, never OPEN_FIRE.

**Shrink `check()` to a quality-feeder.** Rip out the JAMMED/PEEKING machine (L240-274, L436-461, L484-531) and the three terminal `probsector` branches (L602-659). Replace the decision with:
```lua
-- reuse conditiondist (L432-433), angles (L539-548), bank/pitch (L551-561), anglesamjam (L572-578)
local q = 0
local gatesOk = (anglecondition < TargetandOffsetJamSam)
            and (anglesamjam >= bank) and (anglesamjam > pitch)
if gatesOk then
    local band = (conditiondist > 40.5) and (110 - 2.5*conditiondist)
              or (conditiondist > 13.33) and (95  - 1.5*conditiondist)
              or (80  - 0.8*conditiondist)
    band = (ewrj_options.OFFENSIVE_POWER or 1.0) * band   -- OFFENSIVE_POWER now literally scales hold
    local detProb = _height/5000 + (_height - t_height)/5000   -- geometry only; NO dice (L429)
    q = math.max(0, math.min(1, (band - detProb)/100))
end
SamQuality[samunit] = SamQuality[samunit] or {}
SamQuality[samunit][jammer] = {q=q, t=now}
ensureWindowDriver(samunit)
mist.scheduleFunction(check, {jammer, samunit}, now + 2)   -- keep quality fresh
return
```

**Single per-SAM owner `windowDriver(samunit)`** (replaces the active-jamming `samON` restores at L342/L379/L926):
```lua
local now = timer.getTime()
local u = Unit.getByName(samunit)
if not u or not u:isExist() then SamWindow[samunit]=nil; SamQuality[samunit]=nil; return end  -- dead: stop, no reschedule

-- combine fresh per-jammer qualities (probabilistic OR; expire stale >3s)
local qsam, any = 0, false
for jname, rec in pairs(SamQuality[samunit] or {}) do
    if ActiveJammers[jname] and rec and (now - rec.t) < 3 then
        qsam = 1 - (1 - qsam)*(1 - rec.q); any = true
    else SamQuality[samunit][jname] = nil end
end
if not any then restoreSAM(samunit); SamWindow[samunit]=nil; return end  -- no live jammers → restore origROE, stop

qsam = math.min(qsam, 0.7)                       -- UNION CAP (mandatory)
local W    = math.random(8,12)                    -- jittered window
local hold = math.max(0, math.min(W-5, qsam*W))   -- ensure OPEN_FIRE sub-window >= ~5s (commit floor)
if hold > 1.0 then
    samHOLD(samunit)
    markLauncherJammedByUnit(u, "ew", hold)        -- feed SARH-delete ONLY for the hold span
    if hold < W then mist.scheduleFunction(restoreSAM, {samunit}, now + hold) end
else
    restoreSAM(samunit)
end
-- SAFETY: absolute deadline so a lost tick can't leave it stuck in WEAPON_HOLD
SamWindow[samunit].holdUntil = now + hold
mist.scheduleFunction(windowDriver, {samunit}, now + W)   -- re-roll next window
```

**`restoreSAM(samunit)`** — single guarded restore that sets ROE back to `SamWindow[samunit].origROE` (fallback OPEN_FIRE), checked against the current epoch so a stale call is a no-op.

**Wire-up / deletions:**
- `startEWjamm` (L838-894): unchanged — still calls `check(jammer, radarName)` per `(jammer,sam)`; `check()` now only feeds quality and ensures the driver, which dedups per SAM.
- `stopEWjamm` (L899-934): keep the "no jammers left → restore" path but also clear `SamQuality`/`SamWindow` per sam; the driver's `not any` branch already restores.
- **Delete/retire:** JAMMED & PEEKING states, `samPEEK` (L747), `samCommitDelay` (L209), `samHesitateDelay` (L197), and route the three uncancellable `mist.scheduleFunction(samON,...)` at **L342, L379, L926** through `restoreSAM` (epoch-guarded) — otherwise a stale 25-40s `samON` from a transient LOS break slams OPEN_FIRE mid-hold.
- **Couple `JammedLaunchers` to the hold span:** today `markLauncherJammedByUnit(...,10)` (L611/630/648) stamps a flat 10s; in the duty-cycle stamp `untilT = now + hold` so the SARH-delete (L1204-1219) and the ROE-hold agree on the same sub-window. **Note the missile-type asymmetry:** that path is gated on `guidance == 3` (SARH) only; **ARH interceptors (`guidance == 4`) are untouched** by either the old or new design — document this in the changelog.

**New knobs (`ewrj_options` L40):** `EW_WINDOW` (W), `EW_HOLD_CAP` (0.7), `EW_MIN_DWELL` (≥3s); reuse `OFFENSIVE_POWER` as the quality multiplier.

---

## 4. Top risks & mitigations

| # | Risk (code-grounded) | Mitigation |
|---|---|---|
| **R1** | **SAM stuck in WEAPON_HOLD forever.** Today nothing can stick — no code sets WEAPON_HOLD, and even stale `samON` timers force OPEN_FIRE. The proposal inverts that safety: a dropped tick / Lua error before reschedule / save-load leaves the SAM silent permanently. **This is the dominant new failure mode.** | Treat WEAPON_HOLD as exceptional and time-boxed; OPEN_FIRE/origROE as the default the system relaxes to. Carry an absolute `holdUntil`; any tick past `holdUntil + grace` forces restore. Wrap the tick body in `pcall` so an error can't skip the reschedule. |
| **R2** | **OPEN_FIRE sub-window < commit latency → no fire → accidental full suppression for weak/common rolls.** `samCommitDelay` floors 1.2s→~4.5s; `peekDuration = random(5,8)`. A 4s active window is too short. | OPEN_FIRE sub-window **≥ ~5s** (`hold = min(W-5, qsam*W)`). Accept that fine-grained "2s/8s" granularity is not achievable at the weak end. **Has the 4s assumption ever been measured in-game? No — and the existing constants strongly suggest it's too short.** Measure before trusting any paper fraction. |
| **R3** | **Multi-jammer union → ~100% hold.** `1/sqrt(count)` caps probability, not interval union. | Hard union cap ≤ 0.7 (Section 2). New state, mandatory. |
| **R4** | **ROE races between jammers.** `SamState`/ROE keyed per-SAM but written by N per-`(jammer,sam)` chains; with a toggle, jammer A's "fire" stomps jammer B's "hold." | Single per-SAM `windowDriver` owns the toggle; per-jammer `check()` only writes `SamQuality`. (Biggest structural change; the proposal's per-jammer framing hides it.) |
| **R5** | **Progressive ROE corruption.** No `getOption` read exists; restoring to OPEN_FIRE every window overrides campaign-set ROE. | Capture origROE once at first-touch; restore to it. On save-load first-touch, if current ROE looks like a plugin HOLD with no state, treat origROE as the configured default, not the stale HOLD. |
| **R6** | **Performance.** `startEWjamm` seeds one `check()` per radar in the GLOBAL `radarList` (every armed ship/SAM/EWR on the map, `getRadars` L810-831). Duty-cycle toggles ROE ≥2×/window/SAM; 8 jammers × large OB = hundreds of extra `setOption` calls/min. `setOption` is not free. | Throttle toggles to ≥ window length; never the 0.8s fast-poll cadence (PEEK-only today). Per-SAM single owner already collapses N jammer chains to one toggle stream. |
| **R7** | **CIWS dip is un-realism, not realism.** WEAPON_HOLD is group-level/weapon-agnostic; a ship is one unit → its autonomous Phalanx/SeaRAM also goes silent during holds. Real point-defense is closed-loop and a standoff jammer does **not** switch it off. | Accept it as a deliberate gameplay liberty for the fleet-leak case and **say so in the changelog** — do not call it realistic. Note it stacks badly with engine ECM (both radar degraded AND last-ditch guns periodically off → survivability swings *low* in the very windows you wanted "some" interception). |
| **R8** | **Strobing / robotic AI.** 10s window with sub-second hold/fire flips reads as a blinking light, worst at close range on a single launcher (land SEAD). | Jitter window length + flip point; min-dwell ≥3s per sub-state; full-hold on great rolls, full-fire on weak rolls so pure strobe only happens in the mushy middle. Restrict the duty-cycle to the **fleet/anti-ship case** where averaging across many hulls smooths it; leave lone land-SAM SEAD on the shipped RETURN_FIRE + ECM blend. |
| **R9** | **MP visual jank.** SAM ROE flickers every few seconds for all clients. No save-incompat (runtime globals only), but cosmetically worse than today's slow changes. | Accept, or scope to anti-ship only. |

---

## 5. Alternatives considered

**A. Do nothing (RECOMMENDED FIRST STEP).** The shipped blend — engine ECM (continuous radar-lock degradation) + RETURN_FIRE on success (self-defends, CIWS/AAA keep swatting) + SARH in-flight delete via `JammedLaunchers` + `OFFENSIVE_POWER` 0.8 intermittency — already produces graded leakage through two continuous levers. Cost: zero. The leakage is *opaque* (you can't see why a Harpoon got through), which is the only real complaint, and that is a UX issue, not a behavior gap. **Soak-test this first.**

**B. Tune `OFFENSIVE_POWER` only.** One-line change (L42). Lowering it makes suppression rarer/shorter (`samHesitateDelay` scales with it, L199) → more launches leak. But it scales *frequency of binary suppression*, not a smooth per-salvo fraction, and does nothing about the RETURN_FIRE "doesn't reduce launches against incoming" gap. Cheap A/B knob for the soak test; not a substitute for graded behavior.

**C. Lean harder on engine ECM.** Engine ECM is radar-selective (the realistic part) and already always-on for EW flights. But it's a per-aircraft engine effect with a fixed AlwaysUse value — no Escalation-side dial for "how much," and it does nothing to IR/gun/CIWS. Can't be metered to "X% fewer launches." Complementary, not a lever you can turn up for this purpose.

**D. Graded `JammedLaunchers` delete (RECOMMENDED over the full duty-cycle if A/B aren't enough).** Extend the EXISTING mechanism: make `markLauncherJammedByUnit`'s duration/refresh a function of the continuous jam-quality roll, and optionally extend the in-flight delete path (L1204-1219) to cover ARH (`guidance == 4`) at a lower probability. This meters interception continuously, **abort-in-flight actually works there** (it deletes the round — which ROE never does), needs **no** ROE strobing, **no** CIWS dropout, **no** union-cap problem, **no** per-SAM timer-ownership rewrite, **no** stuck-in-HOLD risk, and keeps the RETURN_FIRE realism win. It sits cleanly on top of engine ECM. This is the strongest "if we must improve graded leakage" option and is far lower risk than the WEAPON_HOLD duty-cycle. Its limitation: it reduces *successful interceptions* but not *number of launches* — but for the Harpoon-stream scenario, fewer successful interceptions IS the goal.

**E. Full WEAPON_HOLD duty-cycle (the proposal).** Only genuinely needed if Juanjo specifically wants to suppress *new defensive launches* (not just kill incoming rounds) AND options A/B/D still feel too binary after the soak test. Highest risk/reward. If built, it is a rewrite (Section 3) with Section 4 mitigations as hard requirements, scoped to the anti-ship case, and honest in the changelog about the CIWS liberty.

---

### Bottom line
The duty-cycle is buildable and would be a *cleaner* state machine than today's smeared JAMMED/PEEKING dance — but it solves a problem two shipped levers already address, it re-introduces the "fleet goes dark" behavior the L732-738 comment killed, its fine-grained granularity is blocked by the SAM commit-latency floor the code itself measured, and it adds a brand-new "stuck silent forever" failure class. Soak-test the current blend; if graded leakage is still wanted, do graded `JammedLaunchers` (Alt D) before the WEAPON_HOLD duty-cycle.