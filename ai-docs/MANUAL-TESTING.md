# OPFOR-AI — manual test checklist

The OPFOR-AI rework is now **merged to `master` and the dist is rebuilt** (full client
+ python build). Copy-paste was removed — the feature is **REST + MCP only** (those are
interactive; the LLM can query and now dry-run a package's TOT). Everything was verified
**headless** (saves via the venv / FastAPI `TestClient`); the in-game Qt + runtime items
below still need a real session. Work top to bottom. `chinos2` is backed up to
`chinos2.retribution.20260630.bak`. Note: saves made with the now-removed EW jamming
feature (e.g. marianas2/siria2) no longer load — that's the EW removal, not this.

Legend: 🔴 = could break things / pay attention · ⚙️ = setup · ✅ = expected result.

---

## 0. Build / run the new code  ⚙️🔴

The rework is merged to `master` and the **dist is already rebuilt** (full client +
python) — just launch the new `dist_full_fork` exe (or run from source).

- [X] **Close retribution_main.exe** before rebuilding.
- [X] Make sure you're on the branch with the work: `git -C "<repo>" status` → `experiment-mcp`.
- [X] **Rebuild** with your usual full-fork process (`pyinstaller pyinstaller.spec` → `dist_full_fork`). The spec was updated to bundle `game/agent/docs/*.md` and the `mcp` + `sse_starlette` submodules.
  - 🔴 The build now pulls in **`mcp`** and bumps **`anyio` 3.7.1 → 4.14.1**. Watch the PyInstaller output for missing-module warnings about `mcp`, `sse_starlette`, `httpx`, `pydantic`. If the built exe crashes on start with an `mcp`/`anyio` import error, add the offending module to `hiddenimports` in `pyinstaller.spec` and rebuild.
  - [X] Preserve `state.json` as usual.
- [ ] **Faster alternative for testing (no rebuild):** run from source —
  `& "<repo>\.venv\Scripts\python.exe" "<repo>\qt_ui\main.py"`.
- [X] ✅ The game starts normally with the feature OFF (regression: nothing changed for normal play).

## 1. Enable the feature  ⚙️

- [X] Settings → **Campaign Management → "OPFOR AI commander"** → tick **"Allow OPFOR AI control"**. Close settings.
- [X] ✅ No crash; the setting sticks after closing/reopening settings.
- [X] Load an **old save** (e.g. the chinos2 backup). ✅ It loads (the new `stored_context` / setting back-fill is save-safe).

## 2. Find the connect URL + token, and choose REST vs MCP  ⚙️

- [X] Settings → **Campaign Management → "OPFOR AI commander"**. With **"Allow OPFOR AI control" ON**, a **"Connect your LLM"** block shows **two URLs** with **Copy** buttons:
  - **REST** (`…/retribution-ai/start?token=…`) — for Claude Code or curl.
  - **MCP** (`…/mcp?token=…`) — for claude.ai connectors or `claude mcp add`.
  - 👉 **There is no REST-vs-MCP toggle** — both are always live when the feature is on. You pick by which URL you give your client. (Answers "how do I use MCP instead of REST".)
- [ ] (The URLs are also in the status window: click the **"OPFOR AI"** button in the top panel.)
- [ ] (The connect URL is still logged once at startup, but settings is the place to grab it.)

## 3. Auth  🔴

- [ ] `curl "http://[::1]:<PORT>/retribution-ai/turn_context"` (no token) → ✅ **403 Forbidden**.
- [ ] `curl "http://[::1]:<PORT>/retribution-ai/turn_context?token=<KEY>"` → ✅ **200** + JSON.
- [ ] `curl -H "X-API-Key: <KEY>" "http://[::1]:<PORT>/retribution-ai/turn_context"` → ✅ 200 (header auth works too).
- [ ] `curl "http://[::1]:<PORT>/mcp"` (no token) → ✅ **403**.
- [ ] 🆕 **Stable per-campaign token:** note the token in the OPFOR AI button's connect URL, save + quit, relaunch and reload the **same** save → ✅ the token/URL is **unchanged** (the LLM reconnects with the same URL). Loading a **different** campaign → a **different** token. (Pre-feature saves mint one on first load; it sticks once that save is written.)

## 4. Reads (REST)  

(Use `?token=<KEY>` on each.)

- [ ] `GET /retribution-ai/start` → ✅ markdown briefing; **`{BASE_URL}` is filled in** (no literal `{BASE_URL}`), no `<!-- -->` header.
- [ ] `GET /retribution-ai/howtoplay` → ✅ briefing with **your red faction name/country filled in** (no `{RED_FACTION}`).
- [ ] `GET /retribution-ai/turn_context?side=red` → ✅ `situation`, `economy` (budget/income), `control_points` (with lat/lng + owner), `air_wing` (squadrons with ids), **`targets`** (SAMs/ships/buildings with ids + `threat_nm`). Numbers look sane vs the in-game map.
- [ ] 🆕 In `turn_context`, spot-check the new structured fields: a red `control_point` shows `parking_free`/`parking_total` (room to buy aircraft), `can_recruit_ground` (where `buy/ground` works), `links` (adjacent base ids) and `ground` (armor on hand); ships in `targets` share a `group_id` (their naval group) and a hit target shows `damage`. (Fields are omitted when empty/zero.)
- [ ] 🆕 `turn_context.threats` → ✅ blue's strongest air-defense umbrellas **ranked by reach** (largest `threat_nm` first), incl. **SAM-armed ships** (a Constellation/SM-6 frigate shows up as an ~80+ nm threat, not just an ANTISHIP target). Each entry's `id` matches a `targets[]` id so DEAD/ANTISHIP can remove it. Cross-check the top threat's `threat_nm`/`pos` against the SAM ring on the map.
- [ ] `GET /retribution-ai/settings` → ✅ aggressiveness %, map visibility, mission-window minutes, income multipliers.
- [ ] `GET /retribution-ai/packages?side=red` → ✅ current red packages (likely **empty** if the feature is ON and you haven't planned — see §8).
- [ ] 🆕 `GET /retribution-ai/validate?side=red` → ✅ a whole-plan health check: `{ok, mission_window_min, packages:[…within_window, uncrewed?], issues?}`. With a plan that has a late strike, `ok:false` and `issues` names it. (Read-only — makes no changes.)
- [ ] 🆕 `GET /retribution-ai/capabilities` → ✅ a manifest listing the reads/writes (so the LLM stops probing 404s like `validate`/`capabilities` did before).
- [ ] `GET /retribution-ai/prev_turns?n=3` → ✅ force totals (blue/red aircraft + vehicles) for recent turns.
- [ ] `GET /retribution-ai/turn_status` → ✅ `{active, status, cancelled, turn}`.
- [ ] 🔴 Cross-check: a target id from `turn_context.targets` matches a real SAM/ship on the map; lat/lng put bases in the right place.

## 5. Writes (REST)  🔴

- [ ] `POST /retribution-ai/packages` with body
  `{"side":"red","packages":[{"target_id":"<a target id from §4>","flights":[{"task":"DEAD","count":2}],"rationale":"test DEAD"}]}`
  → ✅ `[{"ok":true,...,"package":{...}}]`.
- [ ] `GET /packages?side=red` → ✅ the new package is there. On the **map**, red now has a package aimed at that target.
- [ ] 🆕 `POST /retribution-ai/packages/evaluate` `{"side":"red","package":{"target_id":"<a target id>","flights":[{"task":"DEAD","count":2}]}}` → ✅ a **dry run**: `ok:true` with `package` (its `tot`), `tot_minutes_into_mission`, `mission_window_min`, `within_window`. 🔴 It must **NOT** create a package — `GET /packages` is unchanged and squadron `untasked` counts are unchanged afterwards. A far target should report `within_window:false`; an unfulfillable one `ok:false`.
- [ ] 🆕 **ignore_range parity:** find a target only a long-range platform can auto-reach (e.g. an anti-ship target with the long-range ASM bomber tasked/sold off). `POST /packages` with a normal spec → `ok:false` and the error suggests `ignore_range:true`. Re-POST the SAME spec with `"ignore_range":true` in the package → ✅ `ok:true`, planned with a shorter-legged but capable airframe (parity with what the human could task manually). Confirm a normal in-range package is unaffected.
- [ ] 🔴 **Crewing:** open the red flight — ✅ it has pilots (no empty seats). At Take Off there should be **no "missing pilots"** block for red.
- [ ] Try a bad target (carrier for OCA, or a nonsense id) → ✅ `{"ok":false,"error":"..."}` (graceful, no crash).
- [ ] `POST /retribution-ai/buy/aircraft` `{"side":"red","squadron_id":"<id>","quantity":2}` → ✅ ok; **budget drops**, `pending_deliveries` +2 (check `turn_context` again or the Air Wing window).
- [ ] `POST /retribution-ai/sell/aircraft` `{"side":"red","squadron_id":"<id of a squadron with untasked aircraft>","quantity":1}` → ✅ ok; budget rises.
- [ ] `POST /retribution-ai/stances` `{"side":"red","friendly_cp_id":"<red cp>","enemy_cp_id":"<blue cp>","stance":"breakthrough"}` → ✅ ok (only meaningful where a front line connects them).
- [ ] 🆕 `POST /retribution-ai/squadron/relocate` `{"side":"red","squadron_id":"<id>","dest_cp_id":"<another red cp>"}` → ✅ ok; the squadron shows a relocation order (arrives over turns). Relocating to a non-friendly base → `ok:false`.
- [ ] 🆕 `POST /retribution-ai/ground/transfer` `{"side":"red","origin_cp_id":"<red cp with `ground`>","dest_cp_id":"<connected red cp>","unit_name":"<a unit from that base's `ground`>","quantity":1}` → ✅ ok by land; the unit count at the origin drops. 🔴 An unreachable destination (e.g. a carrier, or no land route) → `ok:false` and the origin **keeps** its units (no leak). Add `"by_air":true` to airlift.
- [ ] 🆕 `turn_context.repairs` lists **red's own damaged assets** (dead SAM/EWR units, buildings, cratered runways) with `id`, `kind`, `cost`, `dead_units?`. `POST /retribution-ai/repair` `{"side":"red","id":"<id from repairs>"}` → ✅ ok; budget drops by `cost`; on the **map / ground-object menu** that asset shows "Repairing (N turns)" (or revives instantly if the campaign's repair-turns is 0). 🔴 A **blue** asset id → `ok:false` (not yours); an undamaged/zero-cost id → `ok:false`; over-budget → `ok:false` (no partial debit beyond what it could afford). For a runway, pass the **control-point** id.
- [ ] 🆕 `turn_context.naval` lists **red's own movable naval groups** — ship groups (`kind:ship`) AND carriers/LHAs (`kind:carrier`) — with id, pos, `move_range_nm`~80, `threat_nm`?. `POST /retribution-ai/naval/move` `{"side":"red","ship_id":"<id from naval>","lat":<lat>,"lng":<lng>}` with a point a few nm away over water → ✅ ok; re-reading `naval` shows that group's `destination`. ✅ Works for both a `kind:ship` id and a `kind:carrier` id (a carrier's id == its control-point id). 🔴 A point >80 nm away → `ok:false` (range); a point across land → `ok:false` (over land); a **blue** naval id → `ok:false` (not yours). Omit `lat`/`lng` → cancels the pending move (`destination` clears). After a Take Off + turn, the group has actually moved on the map.
- [ ] `DELETE /retribution-ai/packages/0?side=red` → ✅ that package is gone (map updates).
- [ ] `DELETE /retribution-ai/packages?side=red` → ✅ all red packages cleared.

## 6. Take-Off gate + indicator (Qt — never tested in-game)  🔴

- [ ] `POST /retribution-ai/ai/active?active=true` → ✅ the **"OPFOR AI"** button in the **Misc** box (top panel) turns green/active and shows status.
- [ ] Click **Take Off** → ✅ a popup blocks it: *"OPFOR AI is planning…"*.
- [ ] `POST /retribution-ai/ai/status?text=Planning%20packages` → ✅ the button text updates.
- [ ] Click the **"OPFOR AI"** button → ✅ a status window opens; **"Cancel AI turn"** sets `cancelled` (check `turn_status`).
- [ ] `POST /retribution-ai/ai/active?active=false` → ✅ button goes idle; **Take Off now proceeds**.
- [ ] 🔴 With the setting OFF, the "OPFOR AI" button should be **hidden**.

## 7. Memory (stored_context + human_notes)

- [ ] `PUT /retribution-ai/stored_context` body `{"strategy":"hit the carrier group"}` → `GET /stored_context` returns it.
- [ ] `POST /retribution-ai/stored_context` `{"player":"rushes north"}` → ✅ both keys present (merge).
- [ ] `DELETE /retribution-ai/stored_context/player` → ✅ only `strategy` left.
- [ ] **Save the campaign, reload it** → ✅ `GET /stored_context` still returns `strategy` (persists in the save).
- [ ] Write something in the in-game **Notes** panel → `GET /retribution-ai/human_notes` returns it.

## 8. Autonomous wiring + scripted fallback (Phase 5 — core turn logic)  🔴🔴

- [ ] With **"Allow OPFOR AI control" ON**, advance/begin a turn (Pass Turn). Then `GET /packages?side=red` → ✅ **empty** (red's auto-planning was suppressed, left for the LLM).
- [ ] 🔴 **Fallback:** WITHOUT planning red (don't call the LLM at all), click **Take Off**. ✅ Red is **not empty** in the mission — the scripted commander filled it (a fallback log line / red flights appear). The mission should play normally with a scripted red.
- [ ] Now **plan red via the LLM** (create some packages), then Take Off → ✅ red flies **the LLM's** plan (the fallback does NOT overwrite it).
- [ ] Turn the setting **OFF**, advance a turn → ✅ red auto-plans as before (scripted), `GET /packages?side=red` is **populated**. (Regression — confirms we didn't break normal OPFOR.)
- [ ] 🔴 Confirm red still **buys/reinforces** automatically with the setting ON (procurement is intentionally NOT suppressed) — budget changes turn to turn.

## 9. MCP transport

### Claude Code (localhost, no tunnel)
- [ ] `claude mcp add --transport http "http://[::1]:<PORT>/mcp?token=<KEY>"`.
- [ ] In Claude Code, ✅ the OPFOR tools appear (`turn_context`, `create_packages`, `evaluate_package`, `buy_aircraft`, `relocate_squadron`, `transfer_ground`, `set_ai_status`, `stored_context`, …).
- [ ] Ask it to read `turn_context` and create a package → ✅ same effect as the REST writes.

### claude.ai web (needs a tunnel)  🔴
- [ ] Expose the port (e.g. `cloudflared tunnel --url http://localhost:<PORT>` or ngrok).
- [ ] Add a **custom connector** in claude.ai pointing at `https://<tunnel>/mcp?token=<KEY>`.
- [ ] ✅ Tools load; reads/writes work.
- [ ] 🔴 **Security:** the token gates `/mcp`, but keep the tunnel URL private — anyone with `…/mcp?token=<KEY>` can command red. Close the tunnel when done.

## 10. Full "play a turn against the LLM" (the real goal)

- [ ] Connector configured (REST or MCP). Tell your LLM **"your turn"**.
- [ ] ✅ It: reads `turn_context`/`prev_turns`/`stored_context` → creates packages (open SAMs with DEAD, escort strikers, anti-ship the fleet…), maybe buys/sets stances → saves a note → stops.
- [ ] While it plans, ✅ you can keep planning blue (not blocked); **only Take Off is gated**. ✅ The robot lights up automatically on each call (no on/off) and Take Off unblocks ~5 s after its last call.
- [ ] **View red's plan** (the button), sanity-check the rationales, then Take Off and fly. ✅ Red executes the LLM's plan.
- [ ] Next turn: ✅ the LLM references its `stored_context` note and `prev_turns` (reacts to losses).

## 11. Regression (the anyio 4 / mcp changes)  🔴

- [ ] The **map web view** loads and updates (the in-process server still works under anyio 4).
- [ ] A **normal mission** (feature OFF) plans, launches, and debriefs as before.
- [ ] No new errors in the log on startup/shutdown (the MCP lifespan + the server thread shut down cleanly on exit).

## Previously-pending items, now built (validate in-game)

All headless/syntax-checked only:

- **Settings URL panel**: in the **OPFOR AI commander** section, the "Connect your LLM"
  block (REST + MCP URLs, Copy buttons) shows when the master is on (see §2). The status
  window also shows both URLs.
- **Front-line targets**: in a **land** campaign, `turn_context.targets` includes
  `kind:"front"` (suggested_task CAS) with `friendly_cp_id`/`enemy_cp_id`; `POST /packages`
  with a front id plans CAS, and the cp pair drives `/stances`. (chinos2 is naval → no
  fronts; validate with a land campaign — e.g. start a quick Syria/Caucasus one.)
- **Detailed debrief**: after a flown mission, `prev_turns` entries gain `blue_air_lost` /
  `red_air_lost` / `blue_ground_lost` / `red_ground_lost` for that turn.

- **High Command**: with the High Command and GeneraLLM on, pass a turn and ask it for
  `high_command`: three requests against blue objectives, each with a `target_id` that
  `POST /packages` accepts. Destroy one in a mission: the next turn it is gone from
  `requests`, its prize is paid (a ticket in `tickets`, or the effect of an instant one),
  and with "Report enemy completed High Command requests" on, the debriefing lists it
  under ENEMY. Spend a ticket through `ticket_choices` + `spend`.

## Still not done
- **Nothing is validated in a real Qt/game session yet** — all the Qt (the Take-Off
  gate/indicator §6, the settings URL block §2) is syntax/import-checked only. The dist
  **is** rebuilt — this is what you're testing now.

## If something is broken
- REST 500s on `/start` or `/howtoplay` in the **built exe** → the docs weren't bundled; confirm `game/agent/docs` is in `pyinstaller.spec` datas (it is) and rebuild.
- `/mcp` 404/500 in the exe → an `mcp` submodule wasn't bundled; add it to `hiddenimports`.
- Old save won't load → tell me the `KeyError`/`AttributeError`; the `stored_context`/setting back-fill should cover it, but report any other missing field.
