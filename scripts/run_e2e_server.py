#!/usr/bin/env python3
"""隔离 HOME 的 E2E 后端（127.0.0.1:8791）。须在 import web.app 前设置 BINGGO_HOME。"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E2E_HOST = "127.0.0.1"
E2E_PORT = 8791


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    os.environ["BINGGO_E2E"] = "1"
    home_env = os.environ.get("BINGGO_HOME", "").strip()
    if home_env:
        home = Path(home_env)
        home.mkdir(parents=True, exist_ok=True)
    else:
        home = Path(tempfile.mkdtemp(prefix="binggo-e2e-"))
        os.environ["BINGGO_HOME"] = str(home)

    home = home.resolve()
    # 延迟 import：保证先写入 BINGGO_HOME 再加载 app_paths
    from web.e2e_seed import assert_safe_e2e_home, seed_e2e_home

    try:
        assert_safe_e2e_home(home, ROOT)
    except ValueError as exc:
        print(f"拒绝：{exc}", file=sys.stderr)
        return 2

    dist_index = ROOT / "web" / "static" / "dist" / "index.html"
    if not dist_index.is_file():
        print(
            "未找到 web/static/dist/index.html。请先执行：cd web/frontend && npm ci && npm run build",
            file=sys.stderr,
        )
        return 4

    if not _port_free(E2E_HOST, E2E_PORT):
        print(
            f"端口 {E2E_HOST}:{E2E_PORT} 已被占用，请结束占用进程后重试",
            file=sys.stderr,
        )
        return 3

    try:
        seed_e2e_home(home)
    except Exception as exc:
        print(f"E2E 种子失败：{exc}", file=sys.stderr)
        return 5

    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    print(f"E2E server on http://{E2E_HOST}:{E2E_PORT} HOME={home}", flush=True)
    uvicorn.run(
        "web.app:app",
        host=E2E_HOST,
        port=E2E_PORT,
        reload=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
