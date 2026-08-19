"""跨进程写者锁：保证同一时刻只有一个进程在写 B 站 / 本地持久状态。

**为什么需要它。** `web/job_runner.py` 的单任务槽只是 Web 进程内的互斥，
它管不到 `scripts/` 下的 CLI（`docs/cli.md` 里是正式入口，且会真实参与抽奖、
改 checkpoint 与活动库）。因此「同一时刻只有一个写者」这个不变量此前是假的：
Web 看得见的并发会被拒绝，看不见的 CLI 并发则当作没发生。

本模块用一把文件锁把该不变量变成真的。它是**无记忆**的——用完即释放，
不因一次撞车而让任何组件进入长期降级状态（见 AGENTS.md 的机制判据）。

**覆盖范围（不要过度解读）。** 本锁仲裁的是**任务级写者**：`JobRunner` 启动的
任务，以及 `docs/cli.md` 里会写 B 站或改活动库/checkpoint 的 CLI。它**不**覆盖：

- Web GET 路径的维护性写入（`_load_activities_payload` → `seed_activities_if_empty`
  / `refresh_expired_activity_statuses`，会 UPDATE 过期活动）；
- `GET /api/watch-users` 的 `seed_from_candidates_if_empty()`；
- `GET /api/accounts` 的 `ensure_legacy_account()`；
- Settings / Data Sources / Proxy 等配置类 mutation 端点。

这些路径靠 SQLite 事务 + WAL + `busy_timeout` 保证不损坏数据，但**不与任务写者
互斥**。因此持有本锁**不能**推出"此刻 DB 绝对不会被别人改"——按那个假设写
read-modify-write 会产生 TOCTOU 缺陷。GET 顺手做维护性写入本身是个已知设计问题，
记录在 SPEC.md 已知 gap，应由"读时派生状态或后台周期维护"解决，而不是给 GET 加锁
（那会让任何任务运行期间的页面访问全部失败）。

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

    语义保证：`acquire()` 返回 True 当且仅当 `held` 为 True。没有"返回成功但
    实际没持锁"的中间态——那会让调用方在最需要互斥时以为自己受保护。
    因此任何无法建立锁的情形都返回 False（fail-closed）。
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
            # fail-closed：建不出锁文件时**不能**假装拿到了独占权。
            # 这类故障（只读目录/权限/句柄耗尽）恰好发生在系统状态已经异常、
            # 最不能可信假定互斥的时候；此时放行等于在最危险的时刻关闭保护。
            # 且数据目录不可写时 SQLite 本身也无法工作，fail-closed 不会额外
            # 剥夺任何本来可用的能力。
            return False
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
