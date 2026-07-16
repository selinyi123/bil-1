from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: dict[str, Any], *, indent: int = 2) -> None:
    """原子写入 JSON。Windows 下并发 replace 可能短暂 PermissionError，自动重试。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    last_error: PermissionError | None = None
    try:
        for attempt in range(8):
            try:
                tmp_path.write_text(content, encoding="utf-8")
                os.replace(tmp_path, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
