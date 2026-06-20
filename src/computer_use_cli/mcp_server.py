from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from computer_use_cli import actions, capture
from computer_use_cli import observe as observe_module
from computer_use_cli import policy as safety_policy
from computer_use_cli.mcp_oauth import OAuthConfig, SingleUserOAuthProvider

AccessMode = Literal["observe-only", "guarded", "permissive"]
ACCESS_MODES: tuple[AccessMode, ...] = ("observe-only", "guarded", "permissive")
INSTRUCTIONS = (
    "Call observe before the first action. Call act for exactly one action only after "
    "user confirmation. Then call observe again and verify the result. Never assume an "
    "action succeeded from the act result alone. The access policy selected at server "
    "startup cannot be changed by tool input."
)


@dataclass(frozen=True, slots=True)
class ServerConfig:
    mode: AccessMode
    host: str
    port: int
    local_base_url: str
    oauth_resource_url: str
    state_dir: Path
    runtime_dir: Path
    oauth_owner_token: str

    @classmethod
    def from_env(cls, mode: str) -> ServerConfig:
        if mode not in ACCESS_MODES:
            raise ValueError(f"mode must be one of: {', '.join(ACCESS_MODES)}")
        host = os.environ.get("COMPUTER_USE_MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("COMPUTER_USE_MCP_PORT", "7678"))
        local_base_url = os.environ.get(
            "COMPUTER_USE_MCP_PUBLIC_BASE_URL",
            f"http://{host}:{port}",
        ).rstrip("/")
        oauth_resource_url = os.environ.get(
            "COMPUTER_USE_MCP_OAUTH_RESOURCE_URL",
            f"{local_base_url}/mcp",
        ).rstrip("/")
        state_dir = Path(
            os.environ.get(
                "COMPUTER_USE_MCP_STATE_DIR",
                str(Path.home() / ".local" / "share" / "computer-use-mcp"),
            )
        ).resolve()
        runtime_dir = Path(
            os.environ.get(
                "COMPUTER_USE_MCP_RUNTIME_DIR",
                str(Path(tempfile.gettempdir()) / "computer-use-mcp"),
            )
        ).resolve()
        owner_token = os.environ.get("COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN", "")
        if len(owner_token) < 24:
            raise ValueError(
                "COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN must contain at least 24 characters"
            )
        return cls(
            mode=mode,  # type: ignore[arg-type]
            host=host,
            port=port,
            local_base_url=local_base_url,
            oauth_resource_url=oauth_resource_url,
            state_dir=state_dir,
            runtime_dir=runtime_dir,
            oauth_owner_token=owner_token,
        )


class ComputerUseService:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.policy = safety_policy.preset_policy(config.mode)
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)

    def observe(
        self,
        *,
        include_windows: bool = True,
        include_uia: bool = False,
        uia_depth: int = 1,
        uia_title: str | None = None,
    ) -> CallToolResult:
        depth = max(0, min(int(uia_depth), 3))
        monitor = primary_monitor_index()
        screenshot_path = self.config.runtime_dir / f"observe-{uuid4().hex}.png"
        try:
            state = observe_module.observe_state(
                screenshot_path=screenshot_path,
                backend="mss",
                monitor=monitor,
                include_screenshot=True,
                include_windows=include_windows,
                include_uia=include_uia,
                uia_depth=depth,
                uia_title=uia_title,
                uia_backend="uia",
                include_minimized=False,
            )
            screenshot = state.get("screenshot", {})
            if not screenshot.get("ok") or not screenshot_path.is_file():
                raise RuntimeError(
                    str(screenshot.get("error") or "Primary-monitor screenshot failed")
                )
            image_content = Image(path=screenshot_path).to_image_content()
            structured = sanitize_observation(state)
            structured["accessMode"] = self.config.mode
            summary = {
                "status": "observed",
                "accessMode": self.config.mode,
                "monitor": monitor,
                "includeUia": include_uia,
            }
            return CallToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(summary, ensure_ascii=False)),
                    image_content,
                ],
                structuredContent=structured,
            )
        except Exception as exc:  # noqa: BLE001 - convert desktop errors to MCP errors.
            raise ToolError(f"observe failed: {exc}") from exc
        finally:
            screenshot_path.unlink(missing_ok=True)

    def act(self, action: dict[str, Any], *, dry_run: bool = False) -> CallToolResult:
        if not isinstance(action, dict):
            raise ToolError("act accepts exactly one JSON action object")
        if any(key in action for key in ("actions", "sequence", "steps")):
            raise ToolError("action batches and sequences are not supported")
        kind = action.get("type") or action.get("action")
        if not isinstance(kind, str) or kind not in actions.supported_actions():
            raise ToolError(
                f"unsupported action type: {kind!r}. Supported: "
                f"{', '.join(actions.supported_actions())}"
            )
        action_copy = copy.deepcopy(action)
        try:
            result = actions.run_action(
                action_copy,
                dry_run=bool(dry_run),
                policy=self.policy,
            )
        except Exception as exc:  # noqa: BLE001 - preserve policy and automation errors.
            raise ToolError(f"act blocked or failed: {exc}") from exc
        structured = {
            "status": "completed",
            "accessMode": self.config.mode,
            "actionType": kind,
            "dryRun": bool(dry_run),
            "result": result,
            "nextStep": "Call observe and verify the desktop state before another action.",
        }
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(structured, ensure_ascii=False),
                )
            ],
            structuredContent=structured,
        )


def primary_monitor_index() -> int:
    monitors = capture.list_monitors()
    for monitor in monitors:
        if int(monitor.get("index", 0)) > 0 and bool(monitor.get("is_primary", False)):
            return int(monitor["index"])
    return 1 if len(monitors) > 1 else 0


def sanitize_observation(state: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(state)
    screenshot = sanitized.get("screenshot")
    if isinstance(screenshot, dict):
        value = screenshot.get("value")
        if isinstance(value, dict):
            value.pop("path", None)
    return sanitized


def create_server(config: ServerConfig) -> tuple[FastMCP, ComputerUseService]:
    oauth_provider = SingleUserOAuthProvider(
        OAuthConfig(
            owner_token=config.oauth_owner_token,
            issuer_url=config.local_base_url,
            resource_url=config.oauth_resource_url,
            state_dir=config.state_dir,
        )
    )
    local_mcp_url = f"{config.local_base_url}/mcp"
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(config.local_base_url),
        resource_server_url=AnyHttpUrl(local_mcp_url),
        required_scopes=["computer.use"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["computer.use"],
            default_scopes=["computer.use"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    server = FastMCP(
        name="Computer Use MCP",
        instructions=INSTRUCTIONS,
        auth_server_provider=oauth_provider,
        auth=auth_settings,
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
        json_response=True,
        log_level="INFO",
    )
    service = ComputerUseService(config)

    @server.tool(
        name="observe",
        title="Observe primary screen",
        description=(
            "Capture the primary Windows monitor and return the screenshot plus cursor, "
            "active-window, screen, window-list, and optional UI Automation state. Call "
            "this before the first act and after every act."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={
            "securitySchemes": [{"type": "oauth2", "scopes": ["computer.use"]}],
            "openai/toolInvocation/invoking": "Observing the primary screen…",
            "openai/toolInvocation/invoked": "Desktop observation ready",
        },
        structured_output=False,
    )
    def observe(
        include_windows: bool = True,
        include_uia: bool = False,
        uia_depth: int = 1,
        uia_title: str | None = None,
    ) -> CallToolResult:
        return service.observe(
            include_windows=include_windows,
            include_uia=include_uia,
            uia_depth=uia_depth,
            uia_title=uia_title,
        )

    @server.tool(
        name="act",
        title="Perform one computer action",
        description=(
            "Perform exactly one structured computer-use action under the immutable "
            "startup policy. This changes or interacts with the local desktop and must "
            "always be confirmed by the user. Call observe immediately afterward."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
        meta={
            "securitySchemes": [{"type": "oauth2", "scopes": ["computer.use"]}],
            "openai/toolInvocation/invoking": "Performing one confirmed desktop action…",
            "openai/toolInvocation/invoked": "Desktop action finished; verify with observe",
        },
        structured_output=False,
    )
    def act(action: dict[str, Any], dry_run: bool = False) -> CallToolResult:
        return service.act(action, dry_run=dry_run)

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> Response:
        return JSONResponse(
            {
                "ok": True,
                "name": "computer-use-mcp",
                "mode": config.mode,
            }
        )

    @server.custom_route(
        "/.well-known/oauth-authorization-server/",
        methods=["GET", "OPTIONS"],
        include_in_schema=False,
    )
    async def oauth_metadata_with_trailing_slash(_request: Request) -> Response:
        """Avoid a redirect that Secure MCP Tunnel intentionally blocks."""
        metadata = build_metadata(
            auth_settings.issuer_url,
            auth_settings.service_documentation_url,
            auth_settings.client_registration_options
            or ClientRegistrationOptions(),
            auth_settings.revocation_options or RevocationOptions(),
        )
        return JSONResponse(metadata.model_dump(mode="json", exclude_none=True))

    @server.custom_route(
        "/oauth/approve",
        methods=["GET", "POST"],
        include_in_schema=False,
    )
    async def oauth_approve(request: Request) -> Response:
        return await oauth_provider.approval_route(request)

    return server, service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Computer Use MCP for ChatGPT.")
    parser.add_argument("--mode", choices=ACCESS_MODES, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ServerConfig.from_env(args.mode)
    server, _service = create_server(config)
    print(
        f"Computer Use MCP listening on {config.local_base_url}/mcp "
        f"with immutable mode {config.mode}",
        flush=True,
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
