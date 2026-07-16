"""Binggo Windows 启动器：启动本地控制台并打开浏览器。"""

from __future__ import annotations

import asyncio
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = 8787
MUTEX_NAME = "Global\\BilibiliBinggoDashboard"
DASHBOARD_URL = f"http://{HOST}:{PORT}"


def _show_error(message: str) -> None:
    print(message, file=sys.stderr)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                None,
                message,
                "Binggo 启动失败",
                0x10,
            )
        except Exception:
            pass


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _acquire_single_instance() -> bool:
    """若已有实例在运行则返回 False。"""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already_exists = kernel32.GetLastError() == 183
        if already_exists:
            webbrowser.open(DASHBOARD_URL)
            return False
        return True
    except Exception:
        return True


def _run_server() -> None:
    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("web.app:app", host=HOST, port=PORT, reload=False, log_level="info")


def _wait_for_server(timeout_sec: float = 20.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            try:
                sock.connect((HOST, PORT))
                return True
            except OSError:
                time.sleep(0.25)
    return False


def main() -> int:
    from src.app_paths import DATA_DIR, ensure_user_dirs, runtime_label
    from src.app_logging import setup_logging

    if not _acquire_single_instance():
        return 0

    if not _port_available(HOST, PORT):
        webbrowser.open(DASHBOARD_URL)
        _show_error(
            f"控制台已在运行中。\n\n若页面打不开，请关闭占用 {PORT} 端口的程序后重试。\n\n{DASHBOARD_URL}"
        )
        return 0

    ensure_user_dirs()
    log_path = setup_logging(console=False)
    print(f"Binggo 运行模式: {runtime_label()}")
    print(f"数据目录: {DATA_DIR}")
    print(f"日志文件: {log_path}")
    print(f"控制台: {DASHBOARD_URL}")

    server_thread = threading.Thread(target=_run_server, name="binggo-uvicorn", daemon=True)
    server_thread.start()

    if not _wait_for_server():
        _show_error(
            "控制台服务启动超时。\n\n"
            f"请查看日志：{log_path}\n"
            "或尝试以管理员身份运行 / 检查防火墙是否拦截本机访问。"
        )
        return 1

    webbrowser.open(DASHBOARD_URL)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
