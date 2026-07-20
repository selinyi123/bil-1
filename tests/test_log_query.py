from __future__ import annotations

import json

import pytest

from src.log_query import clamp_limit, query_log_lines


def test_clamp_limit() -> None:
    assert clamp_limit(None) == 200
    assert clamp_limit(10) == 10
    with pytest.raises(ValueError):
        clamp_limit(0)
    with pytest.raises(ValueError):
        clamp_limit(501)


def test_query_filters_job_id(isolated_home, monkeypatch) -> None:
    log_path = isolated_home / "data" / "logs" / "binggo.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"v": 1, "job_id": 1, "msg": "a"},
        {"v": 1, "job_id": 2, "msg": "b"},
        {"v": 1, "job_id": 1, "msg": "c"},
        "not-json-line",
        {"v": 1, "msg": "no-job"},
    ]
    lines = []
    for row in rows:
        if isinstance(row, dict):
            lines.append(json.dumps(row, ensure_ascii=False))
        else:
            lines.append(row)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setattr("src.log_query.log_file", lambda: log_path)
    monkeypatch.setattr("src.log_query.log_dir", lambda: log_path.parent)

    payload = query_log_lines(job_id=1, limit=10)
    assert payload["count"] == 2
    assert [item["msg"] for item in payload["lines"]] == ["a", "c"]

    leak_path = isolated_home / "data" / "logs" / "binggo.log"
    leak_path.write_text(
        '{"v":1,"job_id":1,"msg":"x SESSDATA=plain-secret"}\n',
        encoding="utf-8",
    )
    leaked = query_log_lines(job_id=1, limit=10)
    assert "plain-secret" not in str(leaked["lines"])

    empty = query_log_lines(job_id=9, limit=10)
    assert empty["count"] == 0
    assert empty["lines"] == []
