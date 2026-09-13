# `ai-docs/` — MCP/REST OPFOR-AI feature design (branch `experiment-mcp`)

> **Status:** Design / planning only. **No production code has been written yet.**
> This directory is the complete hand-off package for a second Claude Code session
> (running on juanjux's desktop) to implement the feature. Read the docs in order.
>
> Produced on branch `experiment-mcp` (cut from `master`).

## The feature in one paragraph

A setting **"Allow OPFOR AI control"** lets an external LLM plan the enemy's
(OPFOR / red) turns, so the human plays against a competent, adaptive opponent
instead of the rigid scripted commander. When enabled, Escalation exposes its
**live game** over a small HTTP API. The user points an LLM at a single URL; the
LLM reads the turn context, plans red's missions/purchases, and writes them back —
**without ever touching the disk**. The same API is reachable two ways from one
shared service layer:

- **REST** — for desktop agents (Claude Code, etc.): just GET/POST the endpoints
  (curl). No MCP config files, no connectors. Paste the URL and go.
- **MCP over HTTP** — for **web** LLMs (claude.ai custom connector) so they can
  **POST** (create packages), which plain web-browsing can't do.

The scripted commander stays as a **fallback** so an OPFOR turn is never empty.

## The model (architecture in a nutshell)

```
Qt process  ── holds the ONE live Game ──
  └─ FastAPI app (game/server/, already runs in a background thread)
       ├─ existing map/render routers (unchanged)
       ├─ NEW REST routers   ─┐
       │   /retribution-ai/*  │   both transports call the SAME
       └─ NEW MCP sub-app    ─┤── service layer ──▶ engine (GameContext.require())
           mounted at /mcp   ─┘   game/agent/service.py  (single source of truth)
```

No file juggling, no headless bootstrap, no "one game per process" — there is
exactly one live game, in the running app.

## Read in this order

| # | Doc | What it covers |
|---|-----|----------------|
| 0 | [`00-vision-and-scope.md`](00-vision-and-scope.md) | Goal, the "decent OPFOR" thesis, the user-facing UX, full-autonomy model, fallback |
| 1 | [`01-architecture.md`](01-architecture.md) | The live dual-transport server: one service layer, REST + MCP, auth, exposure, concurrency |
| 2 | [`02-codebase-map.md`](02-codebase-map.md) | Engine reference (`file:line`) for every subsystem the feature touches |
| 3 | [`03-opfor-planner.md`](03-opfor-planner.md) | **The centerpiece** — the scripted commander and exactly where/how the LLM plugs in |
| 4 | [`04-api-reference.md`](04-api-reference.md) | The endpoint/tool catalog (turn_context, packages, prev_turns, stored_context, …), REST **and** MCP, one backing each |
| 5 | [`05-context-and-persistence.md`](05-context-and-persistence.md) | Where stored_context / human_notes / AI-intel (map visibility) / prev-turn data live |
| 6 | [`06-implementation-plan.md`](06-implementation-plan.md) | Phased plan, file layout, deps, registration (desktop URL vs web connector), testing |
| 7 | [`07-branching-pr-and-risks.md`](07-branching-pr-and-risks.md) | Branch strategy (master → dev PR), isolation, risks, open decisions |
| — | [`start.md`](start.md) | The `GET /start` welcome doc draft — role, first steps, endpoint catalog, workflow (the first thing the LLM loads) |
| — | [`howtoplay.md`](howtoplay.md) | The OPFOR commander's briefing — the draft document served by `GET /howtoplay` (the LLM's playbook) |

## Key facts (verified against `master` @ `7f063a0`)

- **The engine already supports the exact hook:** `Game.initialize_turn(events,
  for_red=True, for_blue=False)` (`game/game.py:398`) re-plans **only OPFOR**,
  leaving the player's plan intact — documented in its own docstring. The LLM
  plugs in at `TheaterCommander.plan_missions` (`game/commander/theatercommander.py:95`).
- **The server already exists:** `game/server/` runs a FastAPI app in-process on a
  thread (`qt_ui/main.py:522`), bound to the live `Game` via `GameContext`
  (`game/server/dependencies.py:13`), with a Qt-UI action bridge
  (`QtContext`/`QtCallbacks`) and `X-API-Key` auth. We extend it; we don't invent it.
- **Reuse, don't rebuild:** create missions via `PackageFulfiller.plan_mission(...)`
  and buy via the `PurchaseAdapter` classes — validation, flight planning and
  budgeting come for free.
- **FastMCP composes with the existing FastAPI app:** mount `mcp.streamable_http_app()`
  and run `mcp.session_manager.run()` in the app lifespan (verified 2026-06).
  Pin `mcp[cli]<2` (v2 is in alpha).

Line numbers are accurate as of `7f063a0`; **symbol names are the stable contract.**
