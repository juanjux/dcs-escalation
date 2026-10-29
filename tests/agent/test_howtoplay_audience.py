"""Keep the OPFOR briefing focused on agent actions, not player-only controls."""

from types import SimpleNamespace

import pytest

from game.agent import service
from game.server.dependencies import GameContext


def test_briefing_renders_agent_context_without_player_control_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = SimpleNamespace(
        red=SimpleNamespace(
            faction=SimpleNamespace(
                name="Test OPFOR", country=SimpleNamespace(name="Test country")
            )
        )
    )
    monkeypatch.setattr(GameContext, "get", lambda: game)
    text = service.howtoplay_doc()
    assert "Test OPFOR" in text and "Test country" in text
    assert "{RED_FACTION}" not in text and not text.startswith("<!--")
    for player_instruction in (
        "Choose on map",
        "Hover **WEATHER**",
        "Ground transport card",
        "Campaign Management >",
        "F10 Map User Marks",
        "by clicking the robot icon",
        "Future CSAR work",
        "Waypoints tab",
        "Untick both automatic modes",
        "Minutes on the tanker",
        "Hornet COMM presets",
        "CAP_PTS",
        "optional YAML",
        "Older saved search-time values",
        "next navigation tick",
        "only the last corner loops back",
        "Rebuilding is free",
    ):
        assert player_instruction not in text


def test_briefing_retains_operational_rules_and_real_agent_commands() -> None:
    text = service._render_doc("howtoplay.md", {})
    for command in (
        "POST /retribution-ai/ground/transfer",
        "GET /retribution-ai/workshops",
        "POST /retribution-ai/workshops/hire",
        "POST /waypoints/edit",
        "confirm_damaged_sale: true",
        "turn_context.ground_convoys",
        "turn_status",
        "stop planning gracefully",
    ):
        assert command in text
    assert "remain BLUE-only; never use them for RED" in text
    assert "RED-only `/retribution-ai/ground/movement`" in text
    assert "same request plus its" in text and "`preview_token`" in text
    assert "120 statute miles" in text
    assert "surplus retained" in text


def test_briefing_states_api_boundary_and_preserves_planning_constraints() -> None:
    text = " ".join(service._render_doc("howtoplay.md", {}).split())
    assert "Use the OPFOR API or its MCP tools" in text
    assert "Settings are read-only" in text
    assert "Read `/capabilities`" in text
    assert "Audience rule:" not in text
    for rule in (
        "emergency landing",
        "strictly closer",
        "pilot survival and status still follow Live Pilots rules",
        "known ground air defences",
        "20% fuel",
        "turns_remaining",
        "loans",
        "stock",
    ):
        assert rule in text
