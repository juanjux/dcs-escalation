# 07 — Branching, PR Strategy, Risks & Open Decisions

## Branch reality

- This work lives on **`experiment-mcp`**, cut from **`master`** (juanjux's fork —
  `origin` is `juanjux/dcs-escalation`; there is **no `upstream` remote** in this
  clone). Base commit: `7f063a0`.
- Repo branch roles (from the fork README):
  - **`dev`** — pristine mirror of upstream `dcs-retribution/dev`.
  - **`juanjux-dev`** — curated line; features land via PR after testing.
  - **`master`** — live "buffed" build, ahead of `juanjux-dev`, carries WIP; the
    desktop Claude Code builds the playable binary from here.
- **Eventual PR target for this feature: `dev`** (per juanjux) — a clean,
  upstream-shaped contribution.

## The tension to design around

`experiment-mcp` is cut from `master`, which contains fork-specific features and
WIP **not present in `dev`**. But the PR goes to `dev`. So the feature must be
**cleanly separable from everything master-only**.

### Rules to keep it separable

1. **New code in new modules:** `game/agent/`, `game/server/retributionai/`,
   `game/mcp/`. New files cherry-pick onto `dev` trivially.
2. **Minimise edits to existing files.** Unavoidable touch-points:
   - `game/server/app.py` — add lifespan + REST router + `/mcp` mount.
   - `game/server/security.py` — accept `?token=`.
   - `game/commander/theatercommander.py` — the OPFOR hook (small, guarded wrapper).
   - `game/settings/settings.py` — feature flags + `human_notes`.
   - `game/game.py` / `game/migrator.py` — `stored_context` (+ after-action) field
     with a backfill.
   - `requirements.txt` — `mcp[cli]<2`.
   Keep each edit small and dependent only on code that **also exists in `dev`**.
3. **Don't build on master-only APIs.** The engine seams used (`initialize_turn`,
   `TheaterCommander`, `PackageFulfiller`, `PurchaseAdapter`, the FastAPI server,
   `GameContext`, `QtCallbacks`, the `waypoints` set-position route) are
   core/upstream — good. Fork-only dependencies to **degrade gracefully** on `dev`
   rather than hard-depend:
   - **kill-attribution** detail used by `prev_turns` ("who killed it");
   - **movable ships** (the `tgos` `target_position`/`moveable` reposition) — juanjux
     is upstreaming it; if the target branch lacks it, hide/no-op the `move_ship`
     op rather than break the build;
   - the **air-wing cheat** (`enable_air_wing_adjustments`, fork PR #41): the
     *mid-campaign* squadron create/delete gate depends on it. Turn-0 air-wing
     config (create/delete via `AirWingConfigurationDialog`) is upstream and fine;
     guard the cheat-flag reference so it no-ops where the flag is absent.
4. **Isolate the `mcp` dependency** to `game/mcp/` + the mount, so it's a small,
   self-contained part of the single PR.

### Suggested PR path (one PR — decided)

- Develop & soak-test on `experiment-mcp` (from `master`) in the real binary.
- For the `dev` PR, cut a clean branch from `dev` and apply the feature's commits
  (new modules + small guarded edits). Isolation makes this a clean cherry-pick.
- **One PR** containing service layer + REST + MCP transport + the engine OPFOR
  hook. (The isolation rules keep it reviewable; no need to split.)

## Verification status of this design

- **First-hand verified** (`7f063a0`): game core/turn loop, the OPFOR commander/HTN
  seam, ATO/package creation, the FastAPI server + `GameContext` + `QtCallbacks`,
  economy/purchase adapters, theater/map model + coordinate conversion,
  coalition/air-wing read model, logging, settings/cheat flags, persistence.
- **Verified current (web, 2026-06):** FastMCP API, mounting into FastAPI
  (`streamable_http_app()` + `session_manager.run()` lifespan), `mcp[cli]`
  packaging, v2-alpha timing.
- **NOT deeply verified — confirm at implementation time:**
  - **Debrief shape** (`game/debriefing.py`, `MissionResultsProcessor`): exact
    stored structure for `prev_turns` (losses, kill attribution, captures).
  - **`MissionTarget.mission_types`** (per theater target class) — enumerate valid
    task/target pairs from there for `create_packages` validation.
  - **Red auto-plan gating** vs. the LLM (so the scripted red planner and the LLM
    don't clobber each other; blue is gated by `AutoAtoBehavior.Disabled`).
  - **Mounting MCP into the thread-started uvicorn** — confirm the lifespan runs;
    sibling-port fallback if not.

## Risks

| Risk | Mitigation |
|------|-----------|
| **Plan quality** — incoherent/illegal red turns | Reuse fulfilment (can't emit invalid missions); scripted **fallback** if red's turn is empty; rich context + memory so the LLM plans well |
| **Exposure** — port forwarded for a web LLM is internet-reachable | Mandatory long **token** (URL + header); bind localhost by default; tunnel terminates TLS; document clearly |
| **Concurrency** — UI/sim/API touch one `Game` | Writes only at the planning boundary (sim paused); lock around `initialize_turn`+ATO; push `GameUpdateEvents` after |
| **Logic duplication** across REST/MCP | Single `game/agent/service.py`; transports are thin shims; parity test |
| **MCP mount/lifespan** quirks in the existing server | Verified pattern; sibling-port fallback; pin `mcp<2` |
| **Save-compat** — new persisted fields (`stored_context`, after-action) | Default + `Migrator`/`__setstate__` backfill |
| **`dev` PR drags in master-only code** | Isolation rules above; degrade gracefully on the kill-attribution dependency |
| **Latency/cost** of LLM planning | Borne by the **chat client** (the user's own agent); the server calls no LLM. Keep `turn_context` compact to limit the client's token use |

## Decisions already made (juanjux)

- **Mode:** live-over-HTTP (no headless / save-file mode).
- **API scope:** only player-legal actions, through the same endpoints — incl.
  buy/sell aircraft, buy/transfer ground units, **moving movable ships**, and
  **dragging flight/package waypoints**; plus a rendered **map image** for
  multimodal models. **No cheats** (budget/base-capture/unit-placement). The AI
  reads settings (`map_coalition_visibility`, `enemy_income_multiplier`, …) but
  never changes them; those are normal per-campaign, player-alterable settings.
- **AI intel:** driven by the existing `map_coalition_visibility` (the "Fog of war"
  map mode) — mirror the player's setting; don't invent a flag. See [`05`](05-context-and-persistence.md).
- **Air wings:** at **turn 0** the AI configures OPFOR's air wings like the player
  (create/delete squadrons, initial size). Mid-campaign it may create/delete
  squadrons **only when `enable_air_wing_adjustments`** (the air-wing cheat) is on,
  and fills them by **buying** — never the free aircraft +/-. It cannot change the
  faction's allowed airframes (asks the human). See [`04`](04-api-reference.md) §G.
- **`stored_context`:** stored **in the save** (new `Game` field + migrator backfill).
- **Autonomy:** **full autonomy only — no intermediate "strategy hook" level, and
  no embedded/in-engine LLM.** The AI plans the whole red turn like a human player,
  and the **brain is the chat LLM** (Claude Code / claude.ai) driving via the API.
  When OPFOR-AI is on, the engine doesn't auto-plan red; the scripted commander is
  **fallback** if red's turn is empty. (An embedded LLM is explicitly out of scope
  until local models are far cheaper/better.) See [`03`](03-opfor-planner.md).
- **Turn trigger (v1):** the **human says "your turn" in chat**; the `/howtoplay`
  briefing makes the LLM teach the player this on first contact (incl. the first
  turn). Long-poll / eventstream `new_turn` push remain documented as future
  upgrades. See [`04`](04-api-reference.md) §E.
- **Parallel operation:** the AI plans red **in parallel** with the human (no
  blocking modal). A **toolbar robot icon** (grayscale↔colour) shows activity and
  exposes the status on click; **Take Off is blocked** (popup) until the AI is done.
  See [`04`](04-api-reference.md) §E.
- **MCP mount:** into the **existing FastAPI app (one port)** — simplest; sibling
  port only as a last-resort if the lifespan won't wire. See [`01`](01-architecture.md).
- **PR:** **one** PR to `dev`.

## Open decisions for juanjux

**None outstanding** — the design is fully decided (see above). What remains is
implementation, starting at Phase 0 in [`06`](06-implementation-plan.md).

## Enhancements (approved — fold in during implementation)

Quality/robustness/UX additions agreed with juanjux. The cheap, high-value ones
(#1–#4) are worth doing alongside the MVP; the rest layer on.

1. **Per-package/flight `rationale`** → reuse `Package.custom_name` / `Flight.custom_name`
   (already exist + serialized). The LLM writes "why" on each package; shows in the
   human's review + kneeboards; powers the review/reflection loops. ([`04`](04-api-reference.md) §C)
2. **Post-mission reflection** — at turn start the LLM reads `prev_turns`/debrief,
   compares to last turn's intent + rationales, and writes lessons to `stored_context`.
   The real cross-campaign learning loop. ([`05`](05-context-and-persistence.md), howtoplay §5)
3. **`GET /capabilities`** — feature discovery so the LLM adapts and never calls an
   unsupported op (gates fork-vs-`dev`). ([`04`](04-api-reference.md) §A)
4. **`POST /plan/validate`** — dry-run lint (TOT window, SAM coverage, pilots, budget,
   undefended bases…); the LLM self-corrects, the human sanity-checks. ([`04`](04-api-reference.md) §C)
5. **Computed decision-support in `turn_context`** — affordability, force-ratio trend,
   threatened bases, ranked threats — so weak/cheap models don't do raw bookkeeping. ([`04`](04-api-reference.md) §B)
6. **Visualize the plan** — `map/image?plan=red` overlay of red's packages/routes for
   a visual sanity-check before Take Off. ([`04`](04-api-reference.md) §B)
7. **Single-writer guard** — a planning-session token so only one agent edits red at a
   time (no clobbering by a second session / zombie agent). ([`04`](04-api-reference.md) §E)
8. **AI action log** (`GET /ai_log`) — audit of what red did + rationale; behind the
   robot window's **"View red's plan"** button (disabled w/ spinner while the LLM is
   working, enabled when done). Trust + debugging. ([`04`](04-api-reference.md) §E)
9. **Fake-LLM test harness** — scripted client + "plan must pass `validate_plan`" test;
   CI/dev without spending tokens. ([`06`](06-implementation-plan.md))

*(Item numbers here are this roadmap's own; in the API docs they're tagged "enh. #N"
matching the brainstorm order.)*

### Considered and declined

- **A persona / difficulty "knob" for the AI.** Not needed: (a) the game already has
  **`opfor_autoplanner_aggressiveness`** (`settings.py:333`) which the LLM reads via
  `/settings` and can interpret as it likes; (b) the player can just tell the AI in
  chat what kind of campaign they want; and (c) part of the LLM's value is being
  **unpredictable** — a fixed persona knob works against that.

## Future directions (not now — keep the door open)

Out of scope for v1, but worth not precluding architecturally:

- **Turn triggers:** long-poll (`wait_for_opfor_turn`) / eventstream `new_turn`
  push, beyond the v1 "human says your turn" ([`04`](04-api-reference.md) §E).
- **Engine-driven brain:** an embedded LLM that plans red with no human in the loop
  (dropped for now until local models are cheap/good — [`03`](03-opfor-planner.md)).
- **Blue-assist (enh. #11).** The API is coalition-agnostic, so the same machinery
  could *suggest* (or pre-fill) the player's own blue plan as an advisor. Note that
  Escalation's scripted commander **already auto-plans blue** too — the player just
  prunes it (typically keeping BARCAP and replacing the rest); an LLM blue-assist
  would be an opt-in upgrade to that. Architecturally free; out of scope for v1.
- **In-mission control via Combined Arms.** If the player owns the DCS **Combined
  Arms** DLC, a later evolution could let the LLM **command units in real time
  *during* the DCS mission** (e.g. OPFOR ground units / JTAC), not just plan the
  strategic turn between missions. Design implications to keep in mind now:
  - it's a **separate, real-time channel** from this strategic-turn API — it would
    run **DCS-side** (mission Lua / CA scripting bridge), with a different timing
    model (live, continuous) and different state (in-mission unit positions/orders),
    so don't assume the between-turns request/response API covers it;
  - the **agent-core/service layer** and the "the AI is a player" framing should
    stay the reusable part — the in-mission channel reuses game/faction context and
    the same agent identity, but adds its own live transport;
  - gate it on **CA ownership** (it's a paid DLC), and keep it strictly optional.
