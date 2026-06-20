from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from computer_use_cli.mcp_oauth import OAuthConfig, SingleUserOAuthProvider


def oauth_config(tmp_path: Path) -> OAuthConfig:
    return OAuthConfig(
        owner_token="owner-token-that-is-long-enough",
        issuer_url="http://127.0.0.1:7678",
        resource_url="https://example.test/v1/mcp/tunnel_test",
        state_dir=tmp_path,
    )


def client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="client-test",
        client_secret="secret",
        client_id_issued_at=1,
        redirect_uris=[AnyUrl("https://chatgpt.com/connector/oauth/test")],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="computer.use",
    )


@pytest.mark.asyncio
async def test_clients_persist_across_restarts(tmp_path: Path) -> None:
    first = SingleUserOAuthProvider(oauth_config(tmp_path))
    await first.register_client(client())
    second = SingleUserOAuthProvider(oauth_config(tmp_path))
    assert await second.get_client("client-test") is not None


@pytest.mark.asyncio
async def test_authorize_requires_exact_hosted_resource(tmp_path: Path) -> None:
    provider = SingleUserOAuthProvider(oauth_config(tmp_path))
    registered = client()
    await provider.register_client(registered)
    params = AuthorizationParams(
        state="state",
        scopes=["computer.use"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("https://chatgpt.com/connector/oauth/test"),
        redirect_uri_provided_explicitly=True,
        resource="https://wrong.example/mcp",
    )
    with pytest.raises(Exception, match="OAuth resource"):
        await provider.authorize(registered, params)
