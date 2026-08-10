"""Binggo 启动器：启动本地控制台并打开浏览器。"""

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

# 非 Windows 文件锁句柄，进程存活期间保持打开
_LOCK_FH = None


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
        return
    if sys.platform == "darwin":
        # 经 argv 传文案，避免路径/引号破坏 AppleScript
        try:
            script = (
                "on run argv\n"
                '  display dialog (item 1 of argv) with title "Binggo 启动失败" '
                'buttons {"好"} default button 1 with icon stop\n'
                "end run"
            )
            subprocess.run(
                ["osascript", "-e", script, message[:1200]],
                check=False,
                capture_output=True,
                timeout=30,
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


def _acquire_windows_mutex() -> bool:
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


def _acquire_file_lock() -> bool:
    """非 Windows：fcntl 文件锁，避免双开竞态。失败则打开浏览器并退出。"""
    global _LOCK_FH
    if sys.platform == "win32":
        return True
    try:
        import errno
        import fcntl

        from src.app_paths import data_dir, ensure_user_dirs

        ensure_user_dirs()
        lock_path = data_dir() / ".instance.lock"
        fh = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            # 仅「已被占用」视为单实例冲突；其它锁错误不阻断启动
            busy = isinstance(exc, BlockingIOError) or getattr(exc, "errno", None) in {
                errno.EAGAIN,
                errno.EWOULDBLOCK,
                errno.EACCES,
            }
            if busy:
                webbrowser.open(DASHBOARD_URL)
                return False
            return True
        _LOCK_FH = fh
        return True
    except Exception:
        return True


def _acquire_single_instance() -> bool:
    if not _acquire_windows_mutex():
        return False
    return _acquire_file_lock()


def _wait_for_server(timeout_sec: float = STARTUP_TIMEOUT_SEC) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _port_open(DASHBOARD_HOST, DASHBOARD_PORT):
            return True
        time.sleep(0.25)
    return False


def _spawn_server_process() -> subprocess.Popen[bytes]:
    from src.app_paths import bundle_root, data_dir

    args = [sys.executable, SERVE_FLAG]
    kwargs: dict = {"cwd": str(bundle_root())}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
        # 子进程 stderr/stdout 重定向到数据目录，便于排查启动失败
        logs_dir = data_dir() / "logs"
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            err_file = (logs_dir / "server-stderr.log").open("ab", buffering=0)
            out_file = (logs_dir / "server-stdout.log").open("ab", buffering=0)
            kwargs["stdout"] = out_file
            kwargs["stderr"] = err_file
        except OSError:
            pass
    return subprocess.Popen(args, **kwargs)


def _stop_process(proc: subprocess.Popen[bytes]) -> int | None:
    exit_code = proc.poll()
    if exit_code is not None:
        return exit_code
    try:
        proc.terminate()
        return proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            return proc.wait(timeout=2)
        except Exception:
            return proc.poll()


def _startup_failure_message(*, log_path: Path, data_root: Path, exit_code: int | None) -> str:
    code_text = str(exit_code) if exit_code is not None else "仍在运行"
    return (
        "控制台服务启动超时。\n\n"
        f"请查看日志：{log_path}\n"
        f"数据目录：{data_root}\n"
        f"服务进程退出码：{code_text}\n\n"
        f"可尝试关闭占用 {DASHBOARD_PORT} 端口的程序后重试。\n"
        "若控制台曾能打开，可在概览导出诊断包。"
    )


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
    except RuntimeError as exc:
        _show_error(str(exc))
        return 1
    except Exception:
        try:
            get_logger("launcher").exception("Binggo 服务进程异常退出")
        except Exception:
            pass
        return 1


def main() -> int:
    from src.app_logging import setup_logging
    from src.app_paths import ensure_user_dirs, runtime_label, user_home

    if not _acquire_single_instance():
        return 0

    if not _port_available(DASHBOARD_HOST, DASHBOARD_PORT):
        webbrowser.open(DASHBOARD_URL)
        _show_error(
            f"控制台已在运行中。\n\n若页面打不开，请关闭占用 {DASHBOARD_PORT} 端口的程序后重试。\n\n{DASHBOARD_URL}"
        )
        return 0

    try:
        ensure_user_dirs()
    except RuntimeError as exc:
        _show_error(str(exc))
        return 1

    home = user_home()
    log_path = setup_logging(console=False)
    print(f"Binggo 运行模式: {runtime_label()}")
    print(f"数据目录: {home}")
    print(f"日志文件: {log_path}")
    print(f"控制台: {DASHBOARD_URL}")

    proc = _spawn_server_process()
    if not _wait_for_server():
        exit_code = _stop_process(proc)
        _show_error(
            _startup_failure_message(
                log_path=Path(log_path),
                data_root=home,
                exit_code=exit_code,
            )
        )
        return 1

    webbrowser.open(DASHBOARD_URL)

    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        _stop_process(proc)
    return 0


if __name__ == "__main__":
    if SERVE_FLAG in sys.argv:
        raise SystemExit(run_server_mode())
    raise SystemExit(main())
