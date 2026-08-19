"""跨进程写者锁（PR-3 / Q7 + Q11）。

不变量：同一时刻本机只有一个进程在写 B 站 / 本地持久状态。
JobRunner 的单任务槽只覆盖 Web 进程；CLI 是 docs/cli.md 里的正式入口，
必须共用同一把锁，否则该不变量是假的。
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src.writer_lock import (
    WRITER_LOCK_BUSY_MESSAGE,
    WriterLock,
    WriterLockBusy,
    cli_writer_lock,
    writer_lock,
    writer_lock_path,
)

ROOT = Path(__file__).resolve().parents[1]


def _run_child(code: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, BINGGO_HOME=str(home), PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )


def test_lock_path_follows_binggo_home(isolated_home: Path) -> None:
    assert writer_lock_path() == isolated_home / "data" / "binggo.writer.lock"


def test_acquire_release_roundtrip(isolated_home: Path) -> None:
    _ = isolated_home
    lock = WriterLock(owner="test")
    assert lock.acquire() is True
    assert lock.held is True
    lock.release()
    assert lock.held is False
    # 释放后可再次获取
    assert lock.acquire() is True
    lock.release()


def test_release_is_idempotent(isolated_home: Path) -> None:
    _ = isolated_home
    lock = WriterLock(owner="test")
    lock.acquire()
    lock.release()
    lock.release()  # 不应抛错
    assert lock.held is False


def test_second_process_cannot_acquire_while_held(isolated_home: Path) -> None:
    """真跨进程互斥——这是整把锁存在的理由，必须用子进程验证。"""
    lock = WriterLock(owner="holder")
    assert lock.acquire() is True
    try:
        busy = _run_child(
            """
            from src.writer_lock import WriterLock
            lock = WriterLock(owner="child")
            print("ACQUIRED" if lock.acquire() else "BUSY")
            lock.release()
            """,
            isolated_home,
        )
        assert busy.stdout.strip() == "BUSY", busy.stderr
    finally:
        lock.release()

    freed = _run_child(
        """
        from src.writer_lock import WriterLock
        lock = WriterLock(owner="child")
        print("ACQUIRED" if lock.acquire() else "BUSY")
        lock.release()
        """,
        isolated_home,
    )
    assert freed.stdout.strip() == "ACQUIRED", freed.stderr


def test_writer_lock_contextmanager_raises_when_busy(isolated_home: Path) -> None:
    _ = isolated_home
    holder = WriterLock(owner="holder")
    assert holder.acquire() is True
    try:
        child = _run_child(
            """
            from src.writer_lock import WriterLockBusy, writer_lock
            try:
                with writer_lock(owner="child"):
                    print("ENTERED")
            except WriterLockBusy as exc:
                print("BUSY:" + str(exc))
            """,
            isolated_home,
        )
        assert child.stdout.strip() == f"BUSY:{WRITER_LOCK_BUSY_MESSAGE}", child.stderr
    finally:
        holder.release()


def test_cli_writer_lock_exits_2_with_message(isolated_home: Path) -> None:
    """CLI 拿不到锁：打印固定提示 + 非零退出码，绝不阻塞等待。"""
    holder = WriterLock(owner="holder")
    assert holder.acquire() is True
    try:
        child = _run_child(
            """
            from src.writer_lock import cli_writer_lock
            with cli_writer_lock("cli:test"):
                print("SHOULD NOT RUN")
            """,
            isolated_home,
        )
        assert child.returncode == 2
        assert WRITER_LOCK_BUSY_MESSAGE in child.stderr
        assert "SHOULD NOT RUN" not in child.stdout
    finally:
        holder.release()


def test_cli_writer_lock_releases_on_exception(isolated_home: Path) -> None:
    _ = isolated_home
    with pytest.raises(RuntimeError):
        with cli_writer_lock("cli:test"):
            raise RuntimeError("boom")
    # 异常路径也必须释放，否则后续任何写操作都被永久挡住
    after = WriterLock(owner="after")
    assert after.acquire() is True
    after.release()


def test_cli_writer_lock_does_not_swallow_inner_busy(isolated_home: Path) -> None:
    """被包裹代码自己抛 WriterLockBusy 时，不得被误判成"锁被占用"。"""
    _ = isolated_home
    with pytest.raises(WriterLockBusy):
        with cli_writer_lock("cli:test"):
            raise WriterLockBusy("来自业务代码的异常")


def test_real_cli_script_refuses_to_run_while_locked(isolated_home: Path) -> None:
    """端到端：真实 CLI 脚本在锁被占用时拒绝执行。"""
    holder = WriterLock(owner="web:refresh_all")
    assert holder.acquire() is True
    try:
        env = dict(os.environ, BINGGO_HOME=str(isolated_home))
        proc = subprocess.run(
            [sys.executable, "scripts/purge_all_dead_links.py"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
        )
        assert proc.returncode == 2
        assert WRITER_LOCK_BUSY_MESSAGE in proc.stderr
    finally:
        holder.release()


def test_job_runner_refuses_start_when_lock_held_by_other_process(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Web 侧同样受锁约束：CLI 持锁时 try_start 必须拒绝。

    否则 CLI 检查的是一把没人持有的锁，整套机制等于没加。
    """
    from src.db import init_db
    from web.job_runner import JobRunner

    init_db()
    holder = WriterLock(owner="cli:participate")
    assert holder.acquire() is True
    try:
        runner = JobRunner()
        assert runner.try_start("refresh_status", {}, source="ui") is None
        assert runner.is_running() is False
    finally:
        holder.release()


def test_job_runner_releases_lock_after_job_terminal(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任务终态后必须释放锁，否则 Web 跑过一次任务就永久挡住所有 CLI。"""
    import time as _time

    from src.db import init_db
    from web.job_runner import JobRunner

    init_db()
    runner = JobRunner()
    monkeypatch.setattr("web.job_runner.run_action", lambda *a, **k: {"ok": True, "message": "done"})

    job_id = runner.try_start("refresh_status", {}, source="ui")
    assert job_id is not None

    deadline = _time.time() + 10
    while runner.is_running() and _time.time() < deadline:
        _time.sleep(0.05)
    assert runner.is_running() is False

    after = WriterLock(owner="cli:after")
    assert after.acquire() is True, "任务结束后写者锁未释放"
    after.release()


def test_acquire_fails_closed_when_lock_file_cannot_be_created(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """建不出锁文件时必须 fail-closed。

    只读目录 / 权限错误 / 句柄耗尽恰好发生在系统状态已异常、最不能可信假定
    互斥的时候；此时返回 True 等于在最危险的时刻关闭保护。
    """
    _ = isolated_home

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "open", _boom)
    lock = WriterLock(owner="test")
    assert lock.acquire() is False
    assert lock.held is False


def test_acquire_result_always_matches_held(isolated_home: Path) -> None:
    """acquire() 返回 True 当且仅当 held 为 True——不存在"成功但没持锁"的中间态。"""
    _ = isolated_home
    lock = WriterLock(owner="test")
    assert lock.acquire() == lock.held
    lock.release()
    assert lock.held is False


def test_thread_start_failure_rolls_back_job_and_lock(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """线程起不来时，DB 行 / 内存槽 / 写者锁必须一起回滚。

    否则会留下永远不会终止的 running job，并把写者锁挂到进程退出。
    """
    import threading as _threading

    from src.db import init_db
    from src.job_store import get_job
    from web.job_runner import JobRunner

    init_db()
    runner = JobRunner()

    def _boom(self: object) -> None:
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(_threading.Thread, "start", _boom)

    with pytest.raises(RuntimeError):
        runner.try_start("refresh_status", {}, source="ui")

    assert runner.is_running() is False
    latest = get_job(1)
    assert latest is not None
    assert latest["state"] == "error"

    after = WriterLock(owner="cli:after")
    assert after.acquire() is True, "启动失败后写者锁未释放"
    after.release()
