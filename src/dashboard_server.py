"""本地控制台 Web 服务配置与启动。"""

from __future__ import annotations

import asyncio
import sys

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8181
DASHBOARD_URL = f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"


def run_dashboard_server(*, log_level: str = "info") -> None:
    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(
        "web.app:app",
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        reload=False,
        log_level=log_level,
    )
