"""Binggo Windows 启动器：启动本地控制台并打开浏览器。"""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_server import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_URL

MUTEX_NAME = "Global\\BilibiliBinggoDashboard"
SERVE_FLAG = "--serve"
STARTUP_TIMEOUT_SEC = 45.0
CREATE_NO_WINDOW = 0x08000000


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


def _port_open(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _port_available(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _acquire_single_instance() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already_exists = kernel32.GetLastError() == 183
        if already_exists:
            webbrowser.open(DASHBOARD_URL)
            return False
        return True
    except Exception:
        return True


def _wait_for_server(timeout_sec: float = STARTUP_TIMEOUT_SEC) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _port_open(DASHBOARD_HOST, DASHBOARD_PORT):
            return True
        time.sleep(0.25)
    return False


def _spawn_server_process() -> subprocess.Popen[bytes]:
    from src.app_paths import bundle_root

    args = [sys.executable, SERVE_FLAG]
    kwargs: dict = {"cwd": str(bundle_root())}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.Popen(args, **kwargs)


def run_server_mode() -> int:
    from src.app_logging import get_logger, setup_logging
    from src.app_paths import ensure_user_dirs
    from src.dashboard_server import run_dashboard_server

    try:
        ensure_user_dirs()
        setup_logging(console=False)
        logger = get_logger("launcher")
        logger.info("Binggo 服务进程启动，监听 %s", DASHBOARD_URL)
        run_dashboard_server()
        return 0
    except Exception:
        try:
            get_logger("launcher").exception("Binggo 服务进程异常退出")
        except Exception:
            pass
        return 1


def main() -> int:
    from src.app_paths import DATA_DIR, ensure_user_dirs, runtime_label
    from src.app_logging import setup_logging

    if not _acquire_single_instance():
        return 0

    if not _port_available(DASHBOARD_HOST, DASHBOARD_PORT):
        webbrowser.open(DASHBOARD_URL)
        _show_error(
            f"控制台已在运行中。\n\n若页面打不开，请关闭占用 {DASHBOARD_PORT} 端口的程序后重试。\n\n{DASHBOARD_URL}"
        )
        return 0

    ensure_user_dirs()
    log_path = setup_logging(console=False)
    print(f"Binggo 运行模式: {runtime_label()}")
    print(f"数据目录: {DATA_DIR}")
    print(f"日志文件: {log_path}")
    print(f"控制台: {DASHBOARD_URL}")

    proc = _spawn_server_process()
    if not _wait_for_server():
        exit_code = proc.poll()
        proc.terminate()
        _show_error(
            "控制台服务启动超时。\n\n"
            f"请查看日志：{log_path}\n"
            f"服务进程退出码：{exit_code if exit_code is not None else '仍在运行'}\n"
            "可尝试关闭占用 8181 端口的程序后重试。"
        )
        return 1

    webbrowser.open(DASHBOARD_URL)

    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        proc.terminate()
    return 0


if __name__ == "__main__":
    if SERVE_FLAG in sys.argv:
        raise SystemExit(run_server_mode())
    raise SystemExit(main())
