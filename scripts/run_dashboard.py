"""启动本地控制面板。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app_logging import setup_logging


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("请先安装依赖: pip install -r requirements.txt", file=sys.stderr)
        return 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    log_path = setup_logging()
    print(f"日志文件: {log_path}")
    print("控制台地址: http://127.0.0.1:8787")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8787, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
