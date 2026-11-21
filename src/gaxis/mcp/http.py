"""Streamable HTTP transport with mandatory bearer auth (ADR-02, ADR-12).

Mirrors the policy bacmap enforces on its own server: loopback bind, DNS-rebinding
protection, constant-time bearer comparison, security headers, fail-closed.
"""

from __future__ import annotations

import hmac
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
]


class BearerAuthMiddleware:
    """Reject anything without the shared token, before the MCP app sees it."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        scheme, _, value = headers.get(b"authorization", b"").partition(b" ")
        if scheme.lower() != b"bearer" or not hmac.compare_digest(value.strip(), self._token):
            await _send_401(send)
            return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + _SECURITY_HEADERS
            await send(message)

        await self.app(scope, receive, _send)


async def _send_401(send: Any) -> None:
    body = b'{"error": "unauthorized"}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="gaxis"'),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def allowed_hosts(host: str, port: int | None) -> list[str]:
    hosts = [host, f"{host}:*", "127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"]
    if port is not None:
        hosts.append(f"{host}:{port}")
    return list(dict.fromkeys(hosts))


def build_http_app(
    server: MCPServer, *, token: str, host: str = "127.0.0.1", port: int | None = 8770
) -> Any:
    if not token:
        raise ValueError("gaxis MCP over HTTP requires a non-empty bearer token")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts(host, port),
    )
    app = server.streamable_http_app(host=host, transport_security=security)
    return SecurityHeadersMiddleware(BearerAuthMiddleware(app, token))


def run_http(
    server: MCPServer,
    *,
    token: str,
    host: str = "127.0.0.1",
    port: int = 8770,
    uds: str | None = None,
) -> None:
    import uvicorn

    app = build_http_app(server, token=token, host=host, port=None if uds else port)
    if uds:
        uvicorn.run(app, uds=uds)
    else:
        uvicorn.run(app, host=host, port=port)
