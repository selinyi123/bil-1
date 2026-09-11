"""MCP 调用的每个 `/api/*` 路径必须对应真实路由，且 MCP 不得直接 import 领域层。

MCP 是本项目 API 的**唯一外部消费者**：独立进程、跨 HTTP、与后端分开发布。
PR #5 删掉 `X-Api-Contract` 的理由是「前端与 MCP 都不做版本协商」——这句话是对的，
但它描述的是风险不是理由。没有版本协商**又**没有契约测试，改一个路由名就会让 MCP
在用户机器上静默失效，而 CI 全绿。

本测试纯静态：解析 MCP 源码取出 (method, path)，与 `web.app` 的真实路由表比对。
不启动服务、不 import MCP（它有自己的依赖树）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "mcp" / "binggo_mcp"

# client.py 的薄封装：方法名即 HTTP 方法。
_HELPER_METHODS = {
    "get_json": "GET",
    "get_bytes": "GET",
    "post_json": "POST",
    "put_json": "PUT",
    "delete_json": "DELETE",
}
_PARAM_RE = re.compile(r"\{[^}]*\}")


def _path_literal(node: ast.expr) -> str | None:
    """取出字符串字面量；f-string 里的插值归一成 `{}`，好与路由模板对齐。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def _mcp_calls() -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for source in sorted(MCP_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            name = node.func.attr
            if name in _HELPER_METHODS and node.args:
                path = _path_literal(node.args[0])
                if path and path.startswith("/api/"):
                    calls.add((_HELPER_METHODS[name], path))
            elif name == "request" and len(node.args) >= 2:
                method = _path_literal(node.args[0])
                path = _path_literal(node.args[1])
                if method and path and path.startswith("/api/"):
                    calls.add((method.upper(), path))
    return calls


def _app_routes() -> set[tuple[str, str]]:
    from web.app import app

    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            routes.add((method.upper(), _PARAM_RE.sub("{}", path)))
    return routes


def test_every_mcp_call_hits_a_real_route() -> None:
    calls = _mcp_calls()
    assert calls, "未从 MCP 源码解析到任何 /api 调用——解析器失效比契约漂移更危险"

    routes = _app_routes()
    missing = sorted(call for call in calls if call not in routes)
    assert not missing, f"MCP 调用了不存在的路由（改名/删除后未同步）：{missing}"


def test_mcp_does_not_import_the_domain_layer() -> None:
    """MCP 声明只打 HTTP。直接 import src/ 会让它绕过整个控制面与写者锁。"""
    leaks: list[str] = []
    for source in sorted(MCP_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "src" or name.startswith(("src.", "web.")):
                    leaks.append(f"{source.name}:{node.lineno} {name}")
    assert not leaks, f"MCP 直接导入了领域层/控制面：{leaks}"
