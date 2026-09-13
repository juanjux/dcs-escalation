# 01 — Architecture

## One service layer, three transports, one live game

The whole feature is built on **infrastructure that already exists**. The Qt app
already runs a FastAPI server in-process on a background thread
(`qt_ui/main.py:522` → `Server(...).run_in_thread()`), bound to the **live `Game`**
via `GameContext` (`game/server/dependencies.py:13`). We add to it.

```
Qt process (exactly ONE live Game)
└─ FastAPI app  (game/server/app.py — already started in a thread)
     ├─ existing map/render routers + /eventstream            (unchanged)
     ├─ NEW REST routers     /retribution-ai/*   ─┐
     │      (desktop agents curl GET/POST)         │  all three delegate to the
     ├─ NEW MCP sub-app      mounted at /mcp      ─┤  SAME service layer
     │      (web LLMs via connector; enables POST) │
     └─ NEW Copy-Paste bridge  (Qt dialog)        ─┘
            (free/restricted accounts; human carries
             compressed blobs between the UI and the LLM)
                                                   │
                                                   ▼
                              game/agent/service.py   ← single source of truth
                              (pure Python; operates on GameContext.require())
                                                   │
                                                   ▼
                 engine: PackageFulfiller, PurchaseAdapter, initialize_turn,
                         ObjectiveFinder, theater, debrief, QtCallbacks…
```

**The non-duplication rule:** all logic lives in `game/agent/service.py`. A REST
route handler and the matching MCP tool are each a 3-line shim that calls the same
service function. Add an operation once; both transports get it.

### Why three transports

| | REST (`/retribution-ai/*`) | MCP over HTTP (`/mcp`) | Copy-Paste (Qt dialog) |
|---|---|---|---|
| Audience | Desktop agents (Claude Code, curl) | Web LLMs with connectors (claude.ai, etc.) | **Free/restricted accounts** — no API, no connector install |
| Setup | Paste URL; agent curls it. **No config files.** | Add URL as a custom connector once. | Enable setting; follow on-screen instructions. |
| Reads | GET | tools/resources | Compressed blob → user pastes to LLM |
| **Writes** | POST | **tools** | LLM generates response blob → user pastes back |
| Network required | Yes (localhost or tunnel) | Yes (tunnel for web LLMs) | **No — human is the transport** |

Same data, same operations, served from the same service layer. The copy-paste
transport calls the same `game/agent/service.py` functions; it just serialises the
input/output as a compressed blob rather than an HTTP request.

### Copy-Paste mode — design

**Setting:** "Copy-Paste mode, no API or MCP (use this for free AI accounts)"
— shown under the main "Allow OPFOR AI control" toggle in the same settings group.

**Activation flow:**
1. Player checks the setting and **closes the settings dialog**.
2. Escalation immediately generates an **initial briefing blob** — the
   equivalent of `start` + a condensed `howtoplay` + copy-paste protocol
   instructions (how to decode the turn blob, how to format the response blob).
   This is shown in a Qt dialog with a read-only text area and a **Copy** button.
   Player pastes it into their LLM chat once. The LLM acknowledges and waits.

**Per-turn flow:**
1. At the start of each OPFOR turn Escalation serialises the full turn context
   (same data as `GET /turn_context` + `prev_turns` + `stored_context`) into a
   **compressed+encoded turn blob** (zlib → base64, or msgpack → base64 — whichever
   is smallest). A dialog opens with this blob in a read-only text area + **Copy**
   button. Label: *"Paste this into your LLM chat"*.
2. The decoding instructions are embedded in the initial briefing, so the LLM
   knows how to parse it and what format to reply in.
3. The LLM processes the blob and generates a **response blob** (same
   compress+encode scheme) containing the planned actions (packages, flights, buys,
   transfers, `stored_context` update, optional status message).
4. Below the outgoing blob, the same dialog shows a **text input area** labelled
   *"Paste the LLM's response here"* and an **OK** button.
5. Escalation decodes the response blob, validates all actions through the normal
   service layer (budget, inventory, range, etc.), and applies the valid ones.
6. **On validation error:** a new dialog shows the error description formatted as
   a human-readable + pasteable snippet, with instructions for the LLM to correct
   it, plus another text input area for the corrected blob. This loop repeats until
   the plan is clean or the player cancels.

**Blob format (design intent — exact format TBD in implementation):**
- Outgoing: `zlib.compress(json.dumps(turn_context_dict).encode()) |> base64.b64encode`
- Response: same scheme; JSON schema defined in `game/agent/schemas.py`
- The initial briefing includes the schema and a worked example so the LLM can
  produce a valid response on the first try.
- Compact, not human-readable — the human never needs to read it, only copy it.

**What the copy-paste transport does NOT do:**
- No live API calls — the server endpoints are irrelevant when this mode is on.
- No streaming — each turn is one outgoing blob, one response blob.
- No parallel operation — while the player is manually shuttling blobs the game
  is effectively paused at the planning screen (same as if the player were planning
  themselves). The robot-icon parallel flow is an API/MCP-only feature.

**Implementation note:** the Qt dialog logic lives in a new
`qt_ui/windows/copypaste_ai_dialog.py`; serialisation/deserialisation in
`game/agent/copypaste.py` (calls `service.py`, returns the same DTOs).

## How the two transports compose (verified 2026-06)

FastMCP can be mounted into the existing FastAPI/Starlette app, sharing the
process and the live `Game`:

```python
# game/server/app.py (sketch of the additions)
from contextlib import asynccontextmanager, AsyncExitStack
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DCS Escalation OPFOR AI", stateless_http=True, json_response=True)
# ... register MCP tools/resources in game/mcp/, all delegating to game/agent/service ...

@asynccontextmanager
async def lifespan(app):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())   # REQUIRED
        yield

app = FastAPI(lifespan=lifespan)
app.include_router(...)                     # existing routers
app.include_router(retribution_ai_router)   # NEW REST
app.mount("/mcp", mcp.streamable_http_app())  # NEW MCP (endpoint ends up at /mcp)
```

- `mcp.session_manager.run()` **must** be in the host app's lifespan or the MCP
  endpoint won't work. The existing `app` has no lifespan today, so this is new.
- `stateless_http=True, json_response=True` keep it simple (no long-lived SSE
  session needed; one request/response per tool call).
- **Decided: mount into the existing FastAPI app (one port)** — simplest, one
  process, one URL. Only if wiring the lifespan into the thread-started uvicorn
  proves impossible would you fall back to a sibling port in the same process
  (non-duplication still holds, since both call `game/agent/service`); but mount is
  the plan.

> The service layer is the contract; the two transports share one ASGI app on one
> port.

## New code layout

```
game/
  agent/                 # NEW — pure Python, no mcp/http/Qt deps where avoidable
    __init__.py
    service.py           # the single source of truth: turn_context, packages,
                         #   prev_turns, stored_context, settings, human_notes,
                         #   ai-activity/status, turn-trigger, howtoplay, map-visibility (intel) filter
    views.py             # pydantic read-models (DTOs returned to the LLM)
    planner.py           # write ops over PackageFulfiller / PurchaseAdapter / stances
    schemas.py           # pydantic: package/flight specs, plan intents, DTOs
  server/
    retributionai/       # NEW REST routers (thin shims → game/agent/service)
      routes.py
      models.py
  mcp/                   # NEW — FastMCP tools/resources (thin shims → service)
    __init__.py
    server.py            # FastMCP instance + tool/resource registration
```

Only `game/mcp/` (and the mount in `game/server/app.py`) import `mcp`. Keeping the
dependency isolated matters for the eventual `dev` PR ([`07`](07-branching-pr-and-risks.md)).

## The bootstrap URL & "start" document

`GET /retribution-ai/start` (and the MCP equivalent resource/prompt) returns the
**bootstrap document** the LLM reads first: what DCS World and Escalation are, the
LLM's role as OPFOR planner, the list of operations, and the recommended workflow
(read `howtoplay` once → read `turn_context` + `prev_turns` + `stored_context` →
plan → POST packages/buys → optionally update `stored_context`). It's served from
`game/agent/service.py` so REST and MCP return identical content.

The **Settings panel** shows this URL (with the token) and one line each for the
desktop-paste and web-connector flows.

## Auth & exposure (bake in from day 1)

- **Token, always.** Reuse the per-process `X-API-Key` pattern
  (`game/server/security.py`) but also accept it as a **URL query token** so the
  user can hand a single clickable URL to an agent: `…/start?token=<KEY>`. The
  moment the port is exposed, the URL is the only thing standing between the
  internet and the player's game — make the token mandatory and long.
- **Localhost vs. exposed.** `127.0.0.1` works for a desktop agent on the same
  machine over plain HTTP (no TLS needed locally). For a **web** LLM the user must
  expose the port (port-forward or a tunnel like cloudflared/ngrok); the tunnel
  terminates TLS, so we don't need self-signed certs in-app. Document this; don't
  bind to `0.0.0.0` by default.
- **CORS:** the existing app locks CORS to `file://`. The new MCP/REST surface for
  external agents needs its own allowance; scope it as tightly as the chosen
  client requires.

## Concurrency (simpler than it sounds here)

The Qt UI, the server thread, and the sim (`GameLoopTimer`, a real
`threading.Timer`) all touch the one `Game`. But the feature's **writes happen at
one safe moment: the OPFOR-planning step**, between missions, when the sim isn't
advancing flights. So:

- Allow **mutating** calls (POST packages, buys, `plan_opfor_turn`) only when the
  game is at a turn/planning boundary (sim paused); reject mid-sim with a clear
  error. Reads are always fine.
- Put a lock around the planning mutations (`initialize_turn` + ATO edits) so a UI
  action and an API call can't interleave.
- Push a `GameUpdateEvents` onto `EventStream` after mutations so the web map UI
  refreshes (mirror `Game.pass_turn`, `game/game.py:367`).

## Security note on inputs

External LLM input only ever flows through the service layer, which routes it into
**validated engine calls** (task/target compatibility, range, inventory, budget).
A malformed request fails that one operation; it cannot corrupt the turn. Never
`eval`/`pickle` anything from the API. (Pickle only appears in normal save/load,
not in this API.)
