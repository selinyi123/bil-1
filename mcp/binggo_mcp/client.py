"""HTTP client for the local Binggo dashboard API."""

from __future__ import annotations

import json
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8787"
DASHBOARD_HINT = "请先启动控制台（开发：python scripts/run_dashboard.py），并确保监听 8787 端口。"

_TERMINAL_JOB_STATES = frozenset({"success", "error", "cancelled", "interrupted"})


class BinggoApiError(Exception):
    """API or connectivity error surfaced to MCP tools."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _format_error_body(status_code: int, body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code") or ""
            message = err.get("message") or body.get("detail") or ""
            if code and message:
                return f"{code}: {message}"
            if message:
                return str(message)
        detail = body.get("detail")
        if detail:
            return str(detail)
    if isinstance(body, str) and body.strip():
        return body.strip()
    return f"HTTP {status_code}"


class BinggoClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.ConnectError as exc:
            raise BinggoApiError(f"无法连接 Binggo API（{self.base_url}）。{DASHBOARD_HINT}") from exc
        except httpx.TimeoutException as exc:
            raise BinggoApiError(f"请求超时：{method} {path}") from exc
        except httpx.HTTPError as exc:
            raise BinggoApiError(f"HTTP 错误：{exc}") from exc

        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
            except Exception:
                payload = response.text
            raise BinggoApiError(
                _format_error_body(response.status_code, payload),
                status_code=response.status_code,
                payload=payload,
            )

        if not expect_json:
            return response.content

        if not response.content:
            return {}
        try:
            return response.json()
        except Exception as exc:
            raise BinggoApiError(f"响应不是合法 JSON：{method} {path}") from exc

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        clean = None
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", path, params=clean)

    async def post_json(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", path, json_body=json_body)

    async def put_json(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        return await self.request("PUT", path, json_body=json_body)

    async def delete_json(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def get_bytes(self, path: str, *, params: dict[str, Any] | None = None) -> bytes:
        clean = None
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", path, params=clean, expect_json=False)


def as_tool_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2)


def is_terminal_job_state(state: str | None) -> bool:
    return str(state or "") in _TERMINAL_JOB_STATES
