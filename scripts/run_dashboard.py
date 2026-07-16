"""启动本地控制面板。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app_logging import setup_logging
from src.app_paths import ensure_user_dirs
from src.dashboard_server import DASHBOARD_URL, run_dashboard_server


def main() -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("请先安装依赖: pip install -r requirements.txt", file=sys.stderr)
        return 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    ensure_user_dirs()
    log_path = setup_logging()
    print(f"日志文件: {log_path}")
    print(f"控制台地址: {DASHBOARD_URL}")
    run_dashboard_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
