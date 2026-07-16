"""本地控制台 Web 服务配置与启动。"""

from __future__ import annotations

import asyncio
import os
import sys

from src.app_paths import is_frozen

DASHBOARD_HOST = "127.0.0.1"
DEV_DASHBOARD_PORT = 8787
PACKAGED_DASHBOARD_PORT = 8181


def get_dashboard_port() -> int:
    """源码/开发模式用 8787，Windows 安装包用 8181。"""
    return PACKAGED_DASHBOARD_PORT if is_frozen() else DEV_DASHBOARD_PORT


def get_dashboard_url() -> str:
    return f"http://{DASHBOARD_HOST}:{get_dashboard_port()}"


# 模块导入时按当前运行形态解析（开发进程与打包进程各自固定）
DASHBOARD_PORT = get_dashboard_port()
DASHBOARD_URL = get_dashboard_url()


def _ensure_stdio() -> None:
    """无控制台子进程（如 Windows CREATE_NO_WINDOW）下 stdout/stderr 可能为 None。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def run_dashboard_server(*, log_level: str = "info") -> None:
    import uvicorn

    _ensure_stdio()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(
        "web.app:app",
        host=DASHBOARD_HOST,
        port=get_dashboard_port(),
        reload=False,
        log_level=log_level,
    )
