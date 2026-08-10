"""多线路容灾（源自 LAS lib/net/bili.js 的 Line 类）。

同一操作提供多条 API 备选线路：当前线路返回 None/False 或抛异常即自动切下一条，
全部失败返回兜底值；成功后记住当前线路，下次从成功线路开始。
"""
from __future__ import annotations

from typing import Any, Callable


class Line:
    def __init__(
        self,
        name: str,
        requests: list[Callable[..., Any]],
        *,
        fallback: Any = None,
    ) -> None:
        self.name = name
        self.requests = list(requests)
        self.valid_line = 0
        self.fallback = fallback
        if not self.requests:
            raise ValueError(f"Line({name}) 需要至少一条线路")

    def store_line(self, index: int) -> None:
        self.valid_line = index

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """执行线路：成功（非 None 且非 False）立即返回并记住线路。"""
        for _ in range(len(self.requests)):
            try:
                result = self.requests[self.valid_line](*args, **kwargs)
            except Exception:
                result = None
            if result is not None and result is not False:
                self.store_line(self.valid_line)
                return result
            self.valid_line = (self.valid_line + 1) % len(self.requests)
        return self.fallback
