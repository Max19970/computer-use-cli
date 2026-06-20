from __future__ import annotations

import asyncio
import base64
import hashlib
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from computer_use_cli.mcp_server import ServerConfig, create_server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pkce() -> tuple[str, str]:
    verifier = "computer-use-mcp-integration-verifier"
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def test_oauth_and_streamable_http_tools(tmp_path: Path) -> None:
    port = _free_port()
    local_base = f"http://127.0.0.1:{port}"
    resource = "https://example.test/v1/mcp/tunnel_integration"
    owner_token = "owner-token-that-is-long-enough"
    config = ServerConfig(
        mode="guarded",
        host="127.0.0.1",
        port=port,
        local_base_url=local_base,
        oauth_resource_url=resource,
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
        oauth_owner_token=owner_token,
    )
    mcp, _service = create_server(config)
    server = uvicorn.Server(
        uvicorn.Config(
            mcp.streamable_http_app(),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _attempt in range(50):
            try:
                if httpx.get(f"{local_base}/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("test MCP server did not start")

        redirect_uri = "http://127.0.0.1:9999/callback"
        registered = httpx.post(
            f"{local_base}/register",
            json={
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "client_secret_post",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "computer.use",
                "client_name": "integration-test",
            },
        ).raise_for_status().json()

        verifier, challenge = _pkce()
        authorize = httpx.get(
            f"{local_base}/authorize",
            params={
                "response_type": "code",
                "client_id": registered["client_id"],
                "redirect_uri": redirect_uri,
                "scope": "computer.use",
                "state": "test-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": resource,
            },
            follow_redirects=False,
        )
        assert authorize.status_code == 302
        approve_url = authorize.headers["location"]
        request_id = parse_qs(urlparse(approve_url).query)["request_id"][0]
        approval = httpx.post(
            f"{local_base}/oauth/approve",
            data={"request_id": request_id, "owner_token": owner_token},
            follow_redirects=False,
        )
        assert approval.status_code == 302
        callback = urlparse(approval.headers["location"])
        code = parse_qs(callback.query)["code"][0]

        token = httpx.post(
            f"{local_base}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": registered["client_id"],
                "client_secret": registered["client_secret"],
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": resource,
            },
        ).raise_for_status().json()

        async def use_tools() -> None:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            async with httpx.AsyncClient(headers=headers) as http_client:
                async with streamable_http_client(
                    f"{local_base}/mcp",
                    http_client=http_client,
                ) as (read_stream, write_stream, _session_id):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        assert {tool.name for tool in listed.tools} == {"observe", "act"}

                        acted = await session.call_tool(
                            "act",
                            {"action": {"type": "position"}},
                        )
                        assert acted.isError is False

                        observed = await session.call_tool(
                            "observe",
                            {"include_windows": False},
                        )
                        assert observed.isError is False
                        assert any(
                            content.type == "image" for content in observed.content
                        )

        asyncio.run(use_tools())
    finally:
        server.should_exit = True
        thread.join(timeout=5)
