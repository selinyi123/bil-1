"""跨进程写者锁：保证同一时刻只有一个进程在写 B 站 / 本地持久状态。

**为什么需要它。** `web/job_runner.py` 的单任务槽只是 Web 进程内的互斥，
它管不到 `scripts/` 下的 CLI（`docs/cli.md` 里是正式入口，且会真实参与抽奖、
改 checkpoint 与活动库）。因此「同一时刻只有一个写者」这个不变量此前是假的：
Web 看得见的并发会被拒绝，看不见的 CLI 并发则当作没发生。

本模块用一把文件锁把该不变量变成真的。它是**无记忆**的——用完即释放，
不因一次撞车而让任何组件进入长期降级状态（见 AGENTS.md 的机制判据）。

与 `binggo_launcher.py` 的单实例锁是两件事：那把锁答的是「只跑一个 launcher」，
这把锁答的是「只有一个写者」。两者互不替代。
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

from src.app_paths import data_dir

WRITER_LOCK_FILENAME = "binggo.writer.lock"
WRITER_LOCK_BUSY_MESSAGE = "已有写任务正在运行，请稍后再试。"


class WriterLockBusy(RuntimeError):
    """锁已被本机另一个进程持有（Web 任务或另一个 CLI）。"""

    def __init__(self, message: str = WRITER_LOCK_BUSY_MESSAGE) -> None:
        super().__init__(message)


def writer_lock_path() -> Path:
    """动态解析锁路径，尊重当前 BINGGO_HOME。"""
    return data_dir() / WRITER_LOCK_FILENAME


if os.name == "nt":  # pragma: no cover - 平台分支
    import msvcrt

    def _try_lock(handle: IO[str]) -> bool:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(handle: IO[str]) -> None:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _try_lock(handle: IO[str]) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(handle: IO[str]) -> None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


class WriterLock:
    """非阻塞写者锁。acquire() 失败即返回 False，绝不等待。

    不提供 force / 超时等待：一把可以绕过的锁在事故复盘时提供不了任何保证。
    """

    def __init__(self, *, owner: str = "") -> None:
        self.owner = owner
        self._handle: IO[str] | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        path = writer_lock_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+", encoding="utf-8")
        except OSError:
            # 建不出锁文件时不阻断业务：退化为无锁，与加锁前的行为一致。
            return True
        # Windows 的 msvcrt.locking 锁字节区间，保证文件至少 1 字节。
        try:
            if handle.tell() == 0:
                handle.write("binggo\n")
                handle.flush()
        except OSError:
            pass
        if not _try_lock(handle):
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            _unlock(handle)
        finally:
            handle.close()

    @property
    def held(self) -> bool:
        return self._handle is not None


@contextmanager
def writer_lock(*, owner: str = "") -> Iterator[None]:
    """持有写者锁执行；已被占用时抛 WriterLockBusy。"""
    lock = WriterLock(owner=owner)
    if not lock.acquire():
        raise WriterLockBusy()
    try:
        yield
    finally:
        lock.release()


@contextmanager
def cli_writer_lock(owner: str) -> Iterator[None]:
    """CLI 专用：拿不到锁就打印提示并以非零退出码退出，不等待。

    try/except 只包住获取阶段，避免把被包裹代码抛出的 WriterLockBusy
    误判成"锁被占用"。
    """
    lock = WriterLock(owner=owner)
    if not lock.acquire():
        print(WRITER_LOCK_BUSY_MESSAGE, file=sys.stderr)
        raise SystemExit(2)
    try:
        yield
    finally:
        lock.release()
