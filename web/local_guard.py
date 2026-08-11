"""localhost 控制面防护中间件（P0/P1 #2）。

背景：Binggo 严格绑定 127.0.0.1，但 loopback ≠ CSRF 防护。恶意网页受 SOP
限制无法读取 localhost API 响应，但仍可对无自定义头的 simple request
（如 POST /api/auto/start、POST /api/logout）发跨站请求——浏览器会先发出
请求，只是读不到响应。因此这里做两层防护：

1. **Host 校验（DNS rebinding 防护）**：Host 必须解析为回环地址。
   恶意域名即使被解析到 127.0.0.1，Host 头仍保留恶意域名，会被拒绝。
2. **Origin 校验（mutation 方法）**：POST/PUT/DELETE/PATCH 且携带 Origin 头
   时，Origin 必须来自本机（http://127.0.0.1:* / http://localhost:*）。
   无 Origin 的请求（curl/CLI/MCP/同源无 Origin 场景）放行，保持兼容。

注：`testserver` 是 Starlette TestClient 的占位 Host，非真实域名，攻击者
无法让浏览器以该 Host 访问 127.0.0.1（DNS rebinding 不可利用），故放行。
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "testserver"})
ALLOWED_ORIGIN_HOSTS = frozenset({"127.0.0.1", "localhost"})
MUTATION_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
GUARDED_PREFIXES = ("/api/",)

_FORBIDDEN_BODY = (
    '{"error":{"code":"FORBIDDEN","message":"跨站请求被拒绝"},'
    '"detail":"跨站请求被拒绝"}'
).encode("utf-8")


def _host_allowed(host: str) -> bool:
    host = (host or "").strip().lower()
    if not host:
        # 缺 Host（HTTP/1.0 或非标准客户端）：不校验，交由其他层
        return True
    if host.startswith("["):
        # IPv6 字面量：[::1] 或 [::1]:port
        bare = host.split("]")[0] + "]"
        return bare in ALLOWED_HOSTS
    bare = host.rsplit(":", 1)[0] if ":" in host else host
    return bare in ALLOWED_HOSTS


def _origin_allowed(origin: str) -> bool:
    origin = (origin or "").strip().lower()
    if not origin:
        return True
    if not origin.startswith(("http://", "https://")):
        return False
    _scheme, _, rest = origin.partition("://")
    host_port = rest.split("/", 1)[0]
    if host_port.startswith("["):
        host = host_port.split("]")[0] + "]"
    else:
        host = host_port.rsplit(":", 1)[0] if ":" in host_port else host_port
    return host in ALLOWED_ORIGIN_HOSTS


def _get_header(scope: Scope, name: str) -> str:
    target = name.lower().encode()
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode("latin-1")
    return ""


class LocalControlPlaneGuard:
    """纯 ASGI 中间件：对 /api/* 请求做 Host/Origin 校验，不缓冲 body。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not any(path.startswith(prefix) for prefix in GUARDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        host = _get_header(scope, "host")
        if not _host_allowed(host):
            await self._reject(send)
            return

        method = str(scope.get("method") or "GET").upper()
        if method in MUTATION_METHODS:
            origin = _get_header(scope, "origin")
            if origin and not _origin_allowed(origin):
                await self._reject(send)
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(_FORBIDDEN_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _FORBIDDEN_BODY})
