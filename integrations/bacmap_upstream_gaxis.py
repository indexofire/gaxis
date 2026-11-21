"""Reference upstream adapter: expose gaxis as ``bacmap_chart_*`` MCP tools.

Copy this file unchanged into ``bacmap/src/bacmap/interfaces/mcp/upstream/gaxis.py``
and register it where bacmap assembles its server:

    from bacmap.interfaces.mcp.upstream.gaxis import GaxisUpstream
    GaxisUpstream(
        url=cfg.gaxis_url,                  # http://127.0.0.1:8770/mcp
        token=os.environ["GAXIS_MCP_TOKEN"],
        max_data_class=profile.max_data_class,   # D1 for the cloud profile
    ).register(server)

Design constraints (see gaxis AGENTS.md, ADR-03/ADR-05):
  * thin: no paper/chart business logic lives here, only mapping and gating;
  * fail-closed: a tool whose data class exceeds the profile ceiling is never
    registered at all, and a second check runs at call time;
  * bacmap habit: handlers return JSON strings, errors are ``{"error": ...}``;
  * no cache: reproduction is expensive, caching belongs to the knowledge base.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
from typing import Any
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, create_model

from gaxis.client import DEFAULT_URL, GaxisClient
from gaxis.errors import GaxisError
from gaxis.models.tools import TOOL_SPECS, ToolSpec

RANK = {"D1": 1, "D2": 2, "D3": 3, "D4": 4}
JSON_TYPES: dict[str, Any] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _input_model(spec: ToolSpec) -> type[BaseModel]:
    """JSON Schema -> pydantic model, so the MCP SDK can rebuild the same schema."""
    properties = spec.input_schema.get("properties", {}) or {}
    required = set(spec.input_schema.get("required", []) or [])
    fields: dict[str, Any] = {}
    for name, prop in properties.items():
        base = JSON_TYPES.get(str(prop.get("type", "string")), str)
        fields[name] = (base, ...) if name in required else (base | None, prop.get("default"))
    return create_model(f"{re.sub(r'\\W', '_', spec.name)}Input", **fields)


class GaxisUpstream:
    """Maps one gaxis server into the tools visible under a bacmap profile."""

    def __init__(
        self,
        *,
        url: str = DEFAULT_URL,
        token: str | None = None,
        max_data_class: str = "D1",
        prefix: str = "bacmap_chart_",
        timeout_s: float = 600.0,
    ) -> None:
        self.url = url
        self.token = token
        self.max_data_class = max_data_class
        self.prefix = prefix
        self.timeout_s = timeout_s
        if max_data_class not in RANK:
            raise ValueError(f"unknown data class {max_data_class!r}")

    def visible_specs(self) -> list[ToolSpec]:
        ceiling = RANK[self.max_data_class]
        return [spec for spec in TOOL_SPECS if RANK[str(spec.data_class)] <= ceiling]

    def allows(self, spec: ToolSpec) -> bool:
        return RANK[str(spec.data_class)] <= RANK[self.max_data_class]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one gaxis tool by its bare name; always returns a JSON string."""
        upstream_name = name.removeprefix(self.prefix)
        spec = next((s for s in TOOL_SPECS if s.name == upstream_name), None)
        if spec is None:
            return json.dumps({"error": f"unknown gaxis tool {upstream_name!r}"})
        if not self.allows(spec):
            return json.dumps(
                {
                    "error": (
                        f"{spec.name} is {spec.data_class}, above the profile ceiling "
                        f"{self.max_data_class}"
                    )
                }
            )
        try:
            self.preflight()
        except OSError as exc:
            return json.dumps({"error": f"gaxis unreachable at {self.url}: {exc}"})
        try:
            async with GaxisClient(self.url, token=self.token, timeout_s=self.timeout_s) as client:
                payload = await client.call_tool(upstream_name, arguments)
        except GaxisError as exc:
            return json.dumps({"error": exc.message, **exc.as_dict()}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - transport failures must not kill a host turn
            return json.dumps({"error": f"gaxis unreachable at {self.url}: {exc}"})
        return json.dumps(payload, ensure_ascii=False)

    def preflight(self, timeout_s: float = 2.0) -> None:
        """Cheap TCP probe: an unreachable gaxis must fail cleanly, not inside anyio teardown."""
        parsed = urlparse(self.url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_s):
            return

    def call_sync(self, name: str, arguments: dict[str, Any]) -> str:
        """Sync wrapper for bacmap's sync tool handlers."""
        return asyncio.run(self.call(name, arguments))

    def _handler(self, spec: ToolSpec, tool_name: str) -> Any:
        def handler(params: Any) -> str:
            return self.call_sync(tool_name, params.model_dump(exclude_none=True))

        # The MCP SDK reads the runtime annotation to build the JSON Schema.
        handler.__annotations__["params"] = _input_model(spec)
        handler.__name__ = re.sub(r"\W", "_", tool_name)
        handler.__doc__ = f"[gaxis/{spec.data_class}] {spec.summary}"
        return handler

    def register(self, server: MCPServer) -> list[str]:
        registered: list[str] = []
        for spec in self.visible_specs():
            tool_name = f"{self.prefix}{spec.name}"
            description = f"[gaxis/{spec.data_class}] {spec.summary}"
            server.tool(name=tool_name, description=description)(self._handler(spec, tool_name))
            registered.append(tool_name)
        return registered
