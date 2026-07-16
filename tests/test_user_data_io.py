from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.user_data_io import atomic_write_json


def test_atomic_write_json_retries_permission_error(tmp_path: Path) -> None:
    target = tmp_path / "sample.json"
    target.write_text('{"old": true}', encoding="utf-8")
    attempts = {"count": 0}
    real_replace = __import__("os").replace

    def flaky_replace(src: str | Path, dst: str | Path) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError("locked")
        real_replace(src, dst)

    with patch("src.user_data_io.os.replace", side_effect=flaky_replace):
        atomic_write_json(target, {"ok": True})

    assert attempts["count"] == 2
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
