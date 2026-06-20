from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response


@dataclass(frozen=True, slots=True)
class OAuthConfig:
    owner_token: str
    issuer_url: str
    resource_url: str
    state_dir: Path
    scopes: tuple[str, ...] = ("computer.use",)
    allowed_redirect_hosts: tuple[str, ...] = ("chatgpt.com",)
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60


@dataclass(slots=True)
class _PendingAuthorization:
    client_id: str
    params: AuthorizationParams
    expires_at: float


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_resource(value: str) -> str:
    return value.rstrip("/")


def _redirect_host_allowed(uri: str, allowed_hosts: tuple[str, ...]) -> bool:
    try:
        parsed = urlparse(uri)
    except ValueError:
        return False
    return parsed.hostname in {"localhost", "127.0.0.1", "::1", *allowed_hosts}


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class SingleUserOAuthProvider:
    """Persistent single-owner OAuth provider for a private ChatGPT MCP app."""

    def __init__(self, config: OAuthConfig) -> None:
        self.config = config
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self._clients_path = self.config.state_dir / "oauth-clients.json"
        self._tokens_path = self.config.state_dir / "oauth-tokens.json"
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _PendingAuthorization] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._access: dict[str, dict[str, Any]] = {}
        self._refresh: dict[str, dict[str, Any]] = {}
        self._load()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise RegistrationError("invalid_client_metadata", "client_id is required")
        redirect_uris = [str(uri) for uri in client_info.redirect_uris or []]
        if not redirect_uris or not all(
            _redirect_host_allowed(uri, self.config.allowed_redirect_hosts)
            for uri in redirect_uris
        ):
            raise RegistrationError("invalid_redirect_uri", "redirect_uri is not allowed")
        self._clients[client_info.client_id] = client_info
        self._save_clients()

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        requested_scopes = params.scopes or list(self.config.scopes)
        if not set(requested_scopes).issubset(self.config.scopes):
            raise AuthorizeError("invalid_scope", "Requested scope is not supported")
        if not params.resource or (
            _normalize_resource(params.resource)
            != _normalize_resource(self.config.resource_url)
        ):
            raise AuthorizeError("invalid_request", "Invalid or missing OAuth resource")

        request_id = secrets.token_urlsafe(32)
        self._pending[request_id] = _PendingAuthorization(
            client_id=str(client.client_id),
            params=params,
            expires_at=time.time() + 300,
        )
        approval_query = urlencode({"request_id": request_id})
        return f"{self.config.issuer_url.rstrip('/')}/oauth/approve?{approval_query}"

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        record = self._codes.get(authorization_code)
        if record is None or record.client_id != client.client_id:
            return None
        return record

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        current = self._codes.pop(authorization_code.code, None)
        if current is None or current.client_id != client.client_id:
            raise TokenError("invalid_grant", "Invalid authorization code")
        return self._issue_tokens(
            str(client.client_id),
            authorization_code.scopes,
            authorization_code.resource,
        )

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        record = self._refresh.get(_token_hash(refresh_token))
        if not self._valid_token_record(record, str(client.client_id)):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=record["client_id"],
            scopes=record["scopes"],
            expires_at=record["expires_at"],
            subject="owner",
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        hashed = _token_hash(refresh_token.token)
        record = self._refresh.get(hashed)
        if not self._valid_token_record(record, str(client.client_id)):
            raise TokenError("invalid_grant", "Invalid refresh token")
        if not set(scopes).issubset(record["scopes"]):
            raise TokenError("invalid_scope", "Refresh token cannot grant requested scopes")
        self._refresh.pop(hashed, None)
        return self._issue_tokens(
            str(client.client_id),
            scopes,
            record.get("resource"),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        record = self._access.get(_token_hash(token))
        if not self._valid_token_record(record):
            return None
        if _normalize_resource(str(record.get("resource", ""))) != _normalize_resource(
            self.config.resource_url
        ):
            return None
        return AccessToken(
            token=token,
            client_id=record["client_id"],
            scopes=record["scopes"],
            expires_at=record["expires_at"],
            resource=record.get("resource"),
            subject="owner",
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        hashed = _token_hash(token.token)
        self._access.pop(hashed, None)
        self._refresh.pop(hashed, None)
        self._save_tokens()

    async def approval_route(self, request: Request) -> Response:
        if request.method == "POST":
            form = await request.form()
            request_id = str(form.get("request_id", ""))
            owner_token = str(form.get("owner_token", ""))
        else:
            request_id = str(request.query_params.get("request_id", ""))
            owner_token = ""

        pending = self._pending.get(request_id)
        if pending is None or pending.expires_at < time.time():
            self._pending.pop(request_id, None)
            return HTMLResponse(
                self._approval_html(request_id, "Authorization request expired."),
                400,
            )

        if request.method != "POST":
            return HTMLResponse(self._approval_html(request_id))

        if not hmac.compare_digest(owner_token, self.config.owner_token):
            return HTMLResponse(
                self._approval_html(request_id, "Owner password was not accepted."),
                401,
            )

        self._pending.pop(request_id, None)
        code_value = f"code-{secrets.token_urlsafe(32)}"
        params = pending.params
        self._codes[code_value] = AuthorizationCode(
            code=code_value,
            scopes=params.scopes or list(self.config.scopes),
            expires_at=time.time() + 300,
            client_id=pending.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="owner",
        )
        query: dict[str, str] = {"code": code_value}
        if params.state:
            query["state"] = params.state
        separator = "&" if "?" in str(params.redirect_uri) else "?"
        return RedirectResponse(f"{params.redirect_uri}{separator}{urlencode(query)}", 302)

    def _issue_tokens(
        self,
        client_id: str,
        scopes: list[str],
        resource: str | None,
    ) -> OAuthToken:
        if not resource or (
            _normalize_resource(resource) != _normalize_resource(self.config.resource_url)
        ):
            raise TokenError("invalid_grant", "Invalid OAuth resource")
        now = int(time.time())
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        self._access[_token_hash(access_token)] = {
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": now + self.config.access_token_ttl_seconds,
            "resource": resource,
        }
        self._refresh[_token_hash(refresh_token)] = {
            "client_id": client_id,
            "scopes": scopes,
            "expires_at": now + self.config.refresh_token_ttl_seconds,
            "resource": resource,
        }
        self._save_tokens()
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self.config.access_token_ttl_seconds,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )

    @staticmethod
    def _valid_token_record(
        record: dict[str, Any] | None,
        client_id: str | None = None,
    ) -> bool:
        return bool(
            record
            and int(record.get("expires_at", 0)) > int(time.time())
            and (client_id is None or record.get("client_id") == client_id)
        )

    def _load(self) -> None:
        if self._clients_path.exists():
            payload = json.loads(self._clients_path.read_text(encoding="utf-8"))
            for raw in payload:
                client = OAuthClientInformationFull.model_validate(raw)
                if client.client_id:
                    self._clients[client.client_id] = client
        if self._tokens_path.exists():
            payload = json.loads(self._tokens_path.read_text(encoding="utf-8"))
            self._access = dict(payload.get("access", {}))
            self._refresh = dict(payload.get("refresh", {}))
            self._drop_expired_tokens()

    def _drop_expired_tokens(self) -> None:
        now = int(time.time())
        self._access = {
            key: value
            for key, value in self._access.items()
            if int(value.get("expires_at", 0)) > now
        }
        self._refresh = {
            key: value
            for key, value in self._refresh.items()
            if int(value.get("expires_at", 0)) > now
        }

    def _save_clients(self) -> None:
        self._atomic_json(
            self._clients_path,
            [
                client.model_dump(mode="json", exclude_none=True)
                for client in self._clients.values()
            ],
        )

    def _save_tokens(self) -> None:
        self._drop_expired_tokens()
        self._atomic_json(
            self._tokens_path,
            {"access": self._access, "refresh": self._refresh},
        )

    @staticmethod
    def _atomic_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        _secure_file(temporary)
        temporary.replace(path)
        _secure_file(path)

    @staticmethod
    def _approval_html(request_id: str, error: str | None = None) -> str:
        error_html = f'<p class="error">{escape(error)}</p>' if error else ""
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Connect Computer Use MCP</title>
<style>
body{{font-family:system-ui;background:#0f172a;color:#e2e8f0}}
main{{max-width:500px;margin:12vh auto;padding:32px;background:#111827;border-radius:18px}}
input,button{{box-sizing:border-box;width:100%;padding:12px;margin-top:12px}}
input{{background:#020617;color:#e2e8f0;border:1px solid #475569;border-radius:10px}}
button{{border:0;border-radius:10px;background:#38bdf8;font-weight:700}}
.error{{color:#fecaca}}
</style></head><body><main>
<h1>Connect Computer Use MCP</h1>
<p>This grants ChatGPT access to observe and, after confirmation, control the current
Windows desktop under the access mode selected at server startup.</p>
{error_html}
<form method="post">
<input type="hidden" name="request_id" value="{escape(request_id)}">
<label>Owner password
<input name="owner_token" type="password" autocomplete="current-password" required autofocus>
</label>
<button type="submit">Authorize Computer Use MCP</button>
</form></main></body></html>"""
