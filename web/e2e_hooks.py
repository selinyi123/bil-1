"""仅在 BINGGO_E2E=1 时由 run_e2e_server / app 安装的测试钩子。

生产路径（run_dashboard）不得设置该环境变量，因而不会注册路由或 patch。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

AccountMode = Literal["logged_out", "logged_in"]
LlmMode = Literal["not_ready", "ready"]

_STATE: dict[str, str] = {
    "account": "logged_out",
    "llm": "not_ready",
}

_INSTALLED = False
_ORIGINALS: dict[str, Callable[..., Any]] = {}

# TestClient 与本机 loopback；拒绝非本机访问测试后门
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "testclient", "localhost"})


class E2EStateRequest(BaseModel):
    account: AccountMode | None = None
    llm: LlmMode | None = None


def e2e_enabled() -> bool:
    return os.environ.get("BINGGO_E2E", "").strip().lower() in {"1", "true", "yes"}


def get_e2e_state() -> dict[str, str]:
    return dict(_STATE)


def set_e2e_state(*, account: AccountMode | None = None, llm: LlmMode | None = None) -> dict[str, str]:
    if account is not None:
        _STATE["account"] = account
    if llm is not None:
        _STATE["llm"] = llm
    return get_e2e_state()


def _default_at_alert() -> dict[str, Any]:
    # 与 web.account_service._default_at_alert 字段对齐，避免前端读到未知键
    return {
        "increased": False,
        "delta": 0,
        "previous": 0,
        "current": 0,
    }


def _mock_account_profile() -> dict[str, Any]:
    from src.message_watch import BILIBILI_AT_NOTIFY_URL

    if _STATE["account"] != "logged_in":
        return {
            "logged_in": False,
            "expired": False,
            "message": "请使用侧边栏扫码登录",
            "uname": "",
            "face": "",
            "mid": None,
            "following": None,
            "dynamic_count": None,
            "unread_messages": None,
            "unread_at": None,
            "extras_loading": False,
            "at_alert": _default_at_alert(),
            "at_notify_url": BILIBILI_AT_NOTIFY_URL,
        }
    return {
        "logged_in": True,
        "expired": False,
        "message": "已登录",
        "uname": "E2E User",
        "face": "",
        "mid": 999001,
        "following": 0,
        "dynamic_count": 0,
        "unread_messages": 0,
        "unread_at": 0,
        "extras_loading": False,
        "vip": {"status": 0, "label": ""},
        "level": 0,
        "at_alert": _default_at_alert(),
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }


def _mock_account_extras() -> dict[str, Any]:
    from src.message_watch import BILIBILI_AT_NOTIFY_URL

    return {
        "unread_messages": 0,
        "unread_at": 0,
        "extras_loading": False,
        "at_alert": _default_at_alert(),
        "at_notify_url": BILIBILI_AT_NOTIFY_URL,
    }


def _mock_is_llm_ready() -> bool:
    return _STATE["llm"] == "ready"


def _client_is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in _LOOPBACK_HOSTS


def install_e2e_hooks(app: FastAPI) -> None:
    """Patch 门禁相关函数并注册 /api/testing/e2e-state。幂等。"""
    global _INSTALLED
    if not e2e_enabled():
        return
    if _INSTALLED:
        return

    import web.account_service as account_service
    import web.api_errors as api_errors

    # 用 sys.modules 取已加载的 web.app，避免在 app 模块体尾部安装时二次 import 踩坑
    web_app = sys.modules.get("web.app")

    _ORIGINALS["account_service.get_account_profile"] = account_service.get_account_profile
    _ORIGINALS["account_service.get_account_extras"] = account_service.get_account_extras
    _ORIGINALS["api_errors.is_llm_ready"] = api_errors.is_llm_ready

    account_service.get_account_profile = _mock_account_profile  # type: ignore[assignment]
    account_service.get_account_extras = _mock_account_extras  # type: ignore[assignment]
    api_errors.is_llm_ready = _mock_is_llm_ready  # type: ignore[assignment]

    if web_app is not None:
        _ORIGINALS["web_app.get_account_profile"] = web_app.get_account_profile
        _ORIGINALS["web_app.get_account_extras"] = web_app.get_account_extras
        web_app.get_account_profile = _mock_account_profile
        web_app.get_account_extras = _mock_account_extras

    def _reject_non_loopback(request: Request) -> None:
        if not _client_is_loopback(request):
            raise HTTPException(status_code=403, detail="e2e hooks are loopback-only")

    @app.get("/api/testing/e2e-state", tags=["internal"], include_in_schema=False)
    def api_e2e_state_get(request: Request) -> dict[str, Any]:
        _reject_non_loopback(request)
        return {"ok": True, "state": get_e2e_state()}

    @app.post("/api/testing/e2e-state", tags=["internal"], include_in_schema=False)
    def api_e2e_state_set(request: Request, body: E2EStateRequest) -> dict[str, Any]:
        _reject_non_loopback(request)
        state = set_e2e_state(account=body.account, llm=body.llm)
        return {"ok": True, "state": state}

    _INSTALLED = True


def uninstall_e2e_hooks() -> None:
    """还原 patch（供单测使用；不移除已挂路由）。"""
    global _INSTALLED
    if not _ORIGINALS:
        _INSTALLED = False
        return

    import web.account_service as account_service
    import web.api_errors as api_errors

    account_service.get_account_profile = _ORIGINALS["account_service.get_account_profile"]  # type: ignore[assignment]
    account_service.get_account_extras = _ORIGINALS["account_service.get_account_extras"]  # type: ignore[assignment]
    api_errors.is_llm_ready = _ORIGINALS["api_errors.is_llm_ready"]  # type: ignore[assignment]

    web_app = sys.modules.get("web.app")
    if web_app is not None and "web_app.get_account_profile" in _ORIGINALS:
        web_app.get_account_profile = _ORIGINALS["web_app.get_account_profile"]
        web_app.get_account_extras = _ORIGINALS["web_app.get_account_extras"]

    _ORIGINALS.clear()
    _INSTALLED = False
