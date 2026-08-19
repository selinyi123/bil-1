from __future__ import annotations

import threading

_user_data_thread_lock = threading.RLock()


def user_data_thread_lock() -> threading.RLock:
    """用户数据读写的**进程内**可重入锁。

    它只串行同一 Python 进程内的线程，**不提供跨进程互斥**。
    跨进程的"同一时刻只有一个写者"由 data/binggo.writer.lock 保证
    （见 docs/cli.md）；本锁不承担该职责。
    """
    return _user_data_thread_lock
