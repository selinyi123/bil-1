"""API 契约代常量与响应头中间件。"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CONTRACT_VERSION = 1
API_CONTRACT_HEADER = "X-Api-Contract"


def should_attach_contract_header(path: str, content_type: str) -> bool:
    if not path.startswith("/api/"):
        return False
    lowered = (content_type or "").lower()
    return "application/json" in lowered or "text/event-stream" in lowered


def attach_contract_header_to_raw(headers: MutableHeaders) -> None:
    headers[API_CONTRACT_HEADER] = str(API_CONTRACT_VERSION)


def attach_contract_header(response) -> None:
    """给已构造的 Response / JSONResponse 写入契约头。"""
    response.headers[API_CONTRACT_HEADER] = str(API_CONTRACT_VERSION)


class ApiContractMiddleware:
    """纯 ASGI 中间件：只改响应头，不缓冲 body（避免打断 SSE）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                if should_attach_contract_header(path, content_type):
                    attach_contract_header_to_raw(headers)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def patch_openapi_schema(schema: dict) -> dict:
    info = schema.setdefault("info", {})
    info["x-api-contract"] = API_CONTRACT_VERSION
    description = str(info.get("description") or "").strip()
    contract_note = (
        f"契约代 X-Api-Contract / API_CONTRACT_VERSION = {API_CONTRACT_VERSION}。"
        "失败响应统一为 ErrorBody（error.code / error.message / detail）。"
    )
    if contract_note not in description:
        info["description"] = f"{description}\n\n{contract_note}".strip()

    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.setdefault(
        "ErrorObject",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "detail": {},
            },
            "required": ["code", "message"],
        },
    )
    schemas.setdefault(
        "ErrorBody",
        {
            "type": "object",
            "properties": {
                "error": {"$ref": "#/components/schemas/ErrorObject"},
                "detail": {
                    "type": "string",
                    "description": "兼容字段，等于 error.message",
                },
            },
            "required": ["error", "detail"],
        },
    )
    return schema
