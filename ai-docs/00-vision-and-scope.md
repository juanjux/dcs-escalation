# 00 — Vision & Scope

## The problem

Between missions, each coalition's turn is planned by an **automated commander**
(`game/commander/`, an HTN planner). For the human this is optional (they plan
their own ATO in the UI); for **OPFOR (red) it is the only planner** — it decides
every enemy package, target, stance and purchase.

That commander is **weak and predictable** by structure:
`PlanNextAction.each_valid_method` (`game/commander/tasks/compound/nextaction.py:27`)
walks the **same fixed task-priority list every turn**, driven by local
preconditions, with **no model of the player**, no memory, no concentration of
force, no operational shape. It is trivial to read after a few turns.

## The idea

Put an **LLM in the commander's seat for OPFOR**. Escalation exposes its live
game over an HTTP API; an LLM reads a rich turn context (front lines, threats,
IADS, what red has, what the player did last turn) and produces an **operational
plan** — what to prioritise, where to concentrate, what to fly, what to buy. The
engine turns that intent into concrete, validated missions.

> **Design principle: replace the brain, reuse the hands.**
> The LLM decides *what to do*. The engine's `PackageFulfiller`, flight-plan
> builders, `MissionScheduler` and `PurchaseAdapter` decide *how* and guarantee
> the result is valid. We never ask the LLM for waypoints or raw unit data.

## The user-facing experience 

1. **A setting "Allow OPFOR AI control"**, with help text roughly:
   > *Allow an external LLM to control OPFOR. Once checked, give this URL to your
   > desktop agent (or add it as a connector in a web LLM):*
   > `http://127.0.0.1:8322/retribution-ai/start?token=…`
2. The user hands that URL to their LLM:
   - **Desktop agent** (Claude Code): it `GET`s the start URL, receives a
     bootstrap document (what DCS/Escalation are, its role as OPFOR planner, the
     API list and the workflow), then calls the endpoints (GET to read, POST to
     write packages) over plain HTTP. **No config files, no connector setup.**
   - **Web LLM** (claude.ai): the user adds the **MCP** URL as a custom connector,
     and the same bootstrap is an MCP resource; the LLM calls the same operations
     as MCP tools (so it can **write**, which plain web-browsing can't).
3. The AI learns it's its turn when **the player says "your turn" in chat** (the v1
   trigger; the AI teaches the player this on first contact, including the first
   turn). The AI then plans red **in parallel** — the player keeps working, never
   waiting. It reads `turn_context`/`prev_turns`/`stored_context`, then writes
   packages and purchases. A **robot icon in the toolbar** (grayscale→colour +
   animation) shows it's active; clicking it shows the live status ("Evaluating last
   turn… / Buying aircraft… / Planning packages…"). The only hard sync is **Take
   Off**, which is blocked (with a popup) until the AI finishes; then the player can
   review red's plan and, while the AI is learning, flag mistakes.
4. **No disk access required** — the LLM only ever talks to the live game over the
   API or via the copy-paste channel. (Crucial so the feature works for remote/web
   LLMs and for free accounts with no API access.)
5. **Escape hatch — advise the human:** for anything outside its player-legal action
   set (a cheat, fixing an engine bug that lost aircraft, changing the faction's
   airframes), the AI **recommends it to the human in chat**; the human decides and
   does it. Documented in `/howtoplay`.

## Goals

1. **A competent, adaptive OPFOR** planned by an LLM over the API — meaningfully
   harder and more interesting than the scripted AI.
2. **Three zero-friction ways in:** REST for desktop agents, MCP over HTTP for web
   LLMs with connectors, and **Copy-Paste mode** for free/restricted accounts with
   no API access. One shared service layer.
3. **Live, disk-free operation** against the running game, so the port can be
   exposed for a remote LLM.
4. **Memory across turns/sessions** via a `stored_context` scratchpad and
   human-authored `human_notes`.

## Core constraint: the AI plays by the player's rules

The API exposes **exactly the actions a human player can take**, through the **same
endpoints** — plan packages/flights, buy/sell aircraft, buy/transfer ground units,
set stances, **move movable ships**, **drag flight/package waypoints on the map**
(within the game's normal limits), run procurement, **configure OPFOR's air wings**
(create/delete squadrons at **turn 0** like the player, or mid-campaign **if the
air-wing cheat is on** — filling them by *buying*, never the free +/-), read state
(incl. a rendered **map image** for multimodal models), keep notes. What's excluded
is **cheats / god-mode**: setting budgets, capturing bases, creating/teleporting
units beyond legal limits, editing TGO unit composition, the free aircraft +/-, or
changing which airframes the faction may field (ask the human for that). Settings like `enemy_income_multiplier`
and `map_coalition_visibility` are normal per-campaign, player-alterable settings —
the AI **reads** them, it doesn't change them. OPFOR is a fair opponent, not a
cheater.

## Non-goals (initial)

- Replacing the **player's** planning UX (the human still plans blue in the UI).
- Driving the in-DCS mission in real time (we plan the **strategic turn**; DCS
  runs the generated `.miz`). *(A future evolution could add real-time in-mission
  control for players who own the **Combined Arms** DLC — see Future directions in
  [`07`](07-branching-pr-and-risks.md). Out of scope for v1.)*
- Rewriting the HTN — it stays as **fallback/baseline** and a source of reusable
  primitive tasks.
- A standalone headless / save-file mode. (Earlier drafts explored this; it's
  **out** — the model is live-over-HTTP only.)
- **Cheats / god-mode** — out by the core constraint above. (Moving movable ships
  and dragging waypoints are player actions, so they're **in**, not cheats.)

## Full autonomy — the AI plays like a human player

**Decision: no intermediate "levels" — go straight to full autonomy.** The AI
plans the **whole** red turn exactly as the human plans theirs: it authors the
entire OPFOR plan (packages, flights, buys, stances, transfers, ship/waypoint
moves) through the API. We do **not** build a half-measure where the LLM only nudges
the scripted planner — that wastes time and reuses the weak HTN as the brain.

**The brain is the chat LLM** (Claude Code / claude.ai), driving via the API during
the OPFOR window (human says "your turn"). The engine doesn't auto-plan red; it
leaves the turn for the AI, like it leaves blue's turn for the human. There is **no
embedded/in-engine LLM** — deliberately out of scope until local models are far
cheaper/better; the chat-driven path is simple and enough.

See [`03-opfor-planner.md`](03-opfor-planner.md) for the hook.
*(For development only, you can run "review-only" — generate a plan but apply
nothing — to vet quality. That's a test aid, not a product mode.)*

## The fallback guarantee

**An OPFOR turn must never come out empty.** If the AI is disabled, unavailable,
errors, times out, or leaves red's turn empty, the scripted `TheaterCommander`
runs as **fallback**. This keeps the game playable regardless of the agent and
makes the feature safe behind a setting.

## Success criteria

- LLM-planned red turns are **valid** (no engine exceptions; missions fly) —
  guaranteed by reusing the fulfilment path.
- Red is **visibly more coherent**: concentration of force, DEAD-before-strike
  sequencing, reactions to the player's last turn.
- Works for **both** a desktop agent (REST) and a **web** LLM (MCP), from one URL.
- Toggleable; **falls back cleanly**.
