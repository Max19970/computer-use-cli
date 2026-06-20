from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult

from computer_use_cli import policy as safety_policy
from computer_use_cli.mcp_server import (
    ComputerUseService,
    ServerConfig,
    create_server,
    sanitize_observation,
)


def config(tmp_path: Path, mode: str = "guarded") -> ServerConfig:
    return ServerConfig(
        mode=mode,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=7678,
        local_base_url="http://127.0.0.1:7678",
        oauth_resource_url="https://example.test/v1/mcp/tunnel_test",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
        oauth_owner_token="owner-token-that-is-long-enough",
    )


def test_act_rejects_batches(tmp_path: Path) -> None:
    service = ComputerUseService(config(tmp_path))
    with pytest.raises(Exception, match="batches"):
        service.act({"type": "position", "actions": []})


def test_observe_only_blocks_mutation(tmp_path: Path) -> None:
    service = ComputerUseService(config(tmp_path, "observe-only"))
    with pytest.raises(Exception, match="blocked"):
        service.act({"type": "move", "x": 1, "y": 1})


def test_move_between_is_supported_without_running_in_dry_run(tmp_path: Path) -> None:
    service = ComputerUseService(config(tmp_path, "guarded"))
    result = service.act(
        {
            "type": "moveBetween",
            "fromX": 10,
            "fromY": 20,
            "toX": 30,
            "toY": 40,
            "speed": 500,
            "hold": True,
        },
        dry_run=True,
    )
    assert result.structuredContent is not None
    assert result.structuredContent["actionType"] == "moveBetween"
    assert result.structuredContent["result"]["wouldRun"]["hold"] is True


def test_move_between_policy_checks_start_and_end_regions() -> None:
    policy = safety_policy.SafetyPolicy(allowed_regions=[(0, 0, 100, 100)])
    safety_policy.validate_action(
        policy,
        {"type": "moveBetween", "fromX": 10, "fromY": 20, "toX": 30, "toY": 40},
    )
    with pytest.raises(PermissionError, match="outside allowedRegions"):
        safety_policy.validate_action(
            policy,
            {"type": "moveBetween", "fromX": 10, "fromY": 20, "toX": 300, "toY": 40},
        )


def test_scroll_amount_alias_is_policy_checked() -> None:
    policy = safety_policy.preset_policy("guarded")
    safety_policy.validate_action(policy, {"type": "scroll", "amount": -10})
    with pytest.raises(PermissionError, match="scroll amount"):
        safety_policy.validate_action(policy, {"type": "scroll", "amount": -11})


def test_scroll_steps_is_not_rejected_as_batch(tmp_path: Path) -> None:
    service = ComputerUseService(config(tmp_path, "guarded"))
    result = service.act(
        {"type": "scroll", "amount": 3, "steps": 3, "interval": 0.05},
        dry_run=True,
    )
    assert result.structuredContent is not None
    assert result.structuredContent["actionType"] == "scroll"
    assert result.structuredContent["result"]["wouldRun"]["steps"] == 3


def test_mode_is_immutable_and_returned(tmp_path: Path) -> None:
    service = ComputerUseService(config(tmp_path, "guarded"))
    result = service.act({"type": "position"})
    assert isinstance(result, CallToolResult)
    assert result.structuredContent is not None
    assert result.structuredContent["accessMode"] == "guarded"
    assert result.structuredContent["nextStep"].startswith("Call observe")


def test_sanitize_observation_removes_local_screenshot_path() -> None:
    state = {
        "screenshot": {
            "ok": True,
            "value": {"path": "C:/secret/runtime/observe.png", "size": {"width": 1}},
        }
    }
    sanitized = sanitize_observation(state)
    assert "path" not in sanitized["screenshot"]["value"]
    assert json.dumps(sanitized)


def test_tool_annotations(tmp_path: Path) -> None:
    server, _service = create_server(config(tmp_path))
    tools = server._tool_manager._tools  # noqa: SLF001 - verify registered MCP metadata.
    assert set(tools) == {"observe", "act"}
    assert tools["observe"].annotations.readOnlyHint is True
    assert tools["observe"].annotations.destructiveHint is False
    assert tools["act"].annotations.readOnlyHint is False
    assert tools["act"].annotations.destructiveHint is True
