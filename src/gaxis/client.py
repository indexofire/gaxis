"""Thin typed client for hosts (bacmap upstream adapter, notebooks, smoke tests).

Hosts should not re-implement JSON plumbing per tool:

    async with GaxisClient(token=os.environ["GAXIS_MCP_TOKEN"]) as gaxis:
        schema = await gaxis.describe_data_schema("/abs/results.tsv")
        figure = await gaxis.render_chart_from_data(
            RenderRequest(data_path=schema.data_schema.path)
        )
        print(figure.code_path, figure.lint.ok)
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack, suppress
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from .errors import GaxisError
from .models.composition import CompositionManifest
from .models.tools import (
    AdaptChartCodeRequest,
    AdaptChartCodeResult,
    ComposePanelsRequest,
    DescribeDataResult,
    GetChartManifestResult,
    HealthStatus,
    IngestPaperRequest,
    IngestPaperResult,
    PlanChartRequest,
    PlanChartResult,
    RenderRequest,
    RenderResult,
    ReproduceChartCodeRequest,
    ReproduceChartCodeResult,
    SearchChartAssetsRequest,
    SearchChartAssetsResult,
)

DEFAULT_URL = "http://127.0.0.1:8770/mcp"


def _payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if structured:
        return dict(structured)
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            try:
                return dict(json.loads(text))
            except json.JSONDecodeError:
                return {"text": text}
    return {}


class GaxisClient:
    """One connection, seven typed calls. Use as an async context manager."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        *,
        token: str | None = None,
        timeout_s: float = 600.0,
    ) -> None:
        self.url = url
        self.token = token
        self.timeout_s = timeout_s
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> GaxisClient:
        stack = AsyncExitStack()
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            http = await stack.enter_async_context(create_mcp_http_client(headers=headers))
            read, write = await stack.enter_async_context(
                streamable_http_client(self.url, http_client=http)
            )
            # mcp 2.x adds this budget to a monotonic float, so it takes seconds, not timedelta.
            session = await stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=float(self.timeout_s))
            )
            await session.initialize()
        except BaseException:
            # A failed handshake must not leak anyio task groups into the caller's loop.
            # Cleanup itself can surface CancelledError from the aborted task group, which
            # would mask the real cause, so suppression here is deliberate.
            with suppress(BaseException):
                await stack.aclose()
            raise
        self._stack = stack
        self._session = session
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("GaxisClient must be used as 'async with GaxisClient(...)'")
        return self._session

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call any tool; kernel error payloads become ``GaxisError``."""
        result = await self.session.call_tool(name, arguments or {})
        payload = _payload(result)
        if payload.get("status") == "error":
            raise GaxisError(
                str(payload.get("code", "remote_error")),
                str(payload.get("message", "remote call failed")),
                str(payload.get("hint", "")),
            )
        if getattr(result, "is_error", False):
            raise GaxisError("remote_error", json.dumps(payload, ensure_ascii=False)[:500])
        return payload

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: Any = await self.session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ]

    async def health(self) -> HealthStatus:
        return HealthStatus.model_validate(await self.call_tool("health"))

    async def describe_data_schema(self, data_path: str) -> DescribeDataResult:
        payload = await self.call_tool("describe_data_schema", {"data_path": data_path})
        return DescribeDataResult.model_validate(payload)

    async def render_chart_from_data(self, request: RenderRequest) -> RenderResult:
        payload = await self.call_tool(
            "render_chart_from_data", request.model_dump(mode="json", exclude_none=True)
        )
        return RenderResult.model_validate(payload)

    async def plan_chart_from_brief(self, request: PlanChartRequest) -> PlanChartResult:
        payload = await self.call_tool(
            "plan_chart_from_brief", request.model_dump(mode="json", exclude_none=True)
        )
        return PlanChartResult.model_validate(payload)

    async def ingest_paper(self, request: IngestPaperRequest) -> IngestPaperResult:
        payload = await self.call_tool(
            "ingest_paper", request.model_dump(mode="json", exclude_none=True)
        )
        return IngestPaperResult.model_validate(payload)

    async def adapt_chart_code(self, request: AdaptChartCodeRequest) -> AdaptChartCodeResult:
        payload = await self.call_tool(
            "adapt_chart_code", request.model_dump(mode="json", exclude_none=True)
        )
        return AdaptChartCodeResult.model_validate(payload)

    async def compose_panels(self, request: ComposePanelsRequest) -> CompositionManifest:
        payload = await self.call_tool(
            "compose_panels", request.model_dump(mode="json", exclude_none=True)
        )
        return CompositionManifest.model_validate(payload)

    async def search_chart_assets(
        self, request: SearchChartAssetsRequest
    ) -> SearchChartAssetsResult:
        payload = await self.call_tool(
            "search_chart_assets", request.model_dump(mode="json", exclude_none=True)
        )
        return SearchChartAssetsResult.model_validate(payload)

    async def get_chart_manifest(self, manifest_id: str) -> GetChartManifestResult:
        payload = await self.call_tool("get_chart_manifest", {"manifest_id": manifest_id})
        return GetChartManifestResult.model_validate(payload)

    async def reproduce_chart_code(
        self, request: ReproduceChartCodeRequest
    ) -> ReproduceChartCodeResult:
        payload = await self.call_tool(
            "reproduce_chart_code", request.model_dump(mode="json", exclude_none=True)
        )
        return ReproduceChartCodeResult.model_validate(payload)
