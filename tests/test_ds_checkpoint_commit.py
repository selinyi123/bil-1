from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.refresh_all_pipeline import PipelineResult
from src.sources.common import CheckResult, commit_source_checkpoint, load_source_fingerprint
from src.state_store import get_last_container, get_last_cv_id, save_state
from web.actions import run_action


def _updated_result(*, source_id: str = "DS-2", cv_id: str | None = None) -> CheckResult:
    return CheckResult(
        source_id=source_id,
        updated=True,
        container_url="https://www.bilibili.com/read/cv999001",
        container_id="999001" if cv_id is None else "opus-123",
        title="新专栏",
        published_at=1_700_000_000,
        previous_container_url="https://www.bilibili.com/read/cv888001",
        activity_links=["https://www.bilibili.com/opus/1220000000000000001"],
        checked_at=1_700_000_100,
        link_hints={},
        cv_id=cv_id,
    )


def test_commit_source_checkpoint_writes_only_when_updated(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = isolated_home
    save_state({"sources": {}})

    unchanged = _updated_result()
    unchanged.updated = False
    commit_source_checkpoint(unchanged)
    assert get_last_container("DS-2") is None

    commit_source_checkpoint(_updated_result())
    assert get_last_container("DS-2") == "https://www.bilibili.com/read/cv999001"


def test_commit_source_checkpoint_keeps_cv_id(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = isolated_home
    save_state({"sources": {}})

    commit_source_checkpoint(
        _updated_result(source_id="DS-5", cv_id="555001"),
    )
    assert get_last_container("DS-5") == "https://www.bilibili.com/read/cv999001"
    assert get_last_cv_id("DS-5") == "555001"


def test_ds2_check_update_does_not_write_checkpoint(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.sources.ds2_fanqiao.DATA_DIR", isolated_home / "data")
    monkeypatch.setattr(
        "src.sources.ds2_fanqiao.OUTPUT_PATH", isolated_home / "data" / "ds2_latest.json"
    )
    save_state(
        {
            "sources": {
                "DS-2": {"container_url": "https://www.bilibili.com/read/cv888001"},
            }
        }
    )

    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get_latest_article.return_value = {
        "id": 999001,
        "title": "新专栏",
        "publish_time": 1_700_000_000,
    }
    fake_client.get_article_detail.return_value = {
        "title": "新专栏",
        "publish_time": 1_700_000_000,
        "opus": {"content": {"paragraphs": []}},
    }

    with (
        patch("src.sources.ds2_fanqiao.BilibiliClient", return_value=fake_client),
        patch(
            "src.sources.ds2_fanqiao.extract_opus_links_with_hints",
            return_value=(["https://www.bilibili.com/opus/1220000000000000001"], {}),
        ),
    ):
        from src.sources import ds2_fanqiao

        assert "set_last_container" not in ds2_fanqiao.__dict__
        result = ds2_fanqiao.check_update()

    assert result.updated is True
    assert result.container_url == "https://www.bilibili.com/read/cv999001"
    assert get_last_container("DS-2") == "https://www.bilibili.com/read/cv888001"


def test_refresh_source_commits_checkpoint_only_after_pipeline_success(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_home
    save_state(
        {
            "sources": {
                "DS-3": {"container_url": "https://www.bilibili.com/read/cv888001"},
            }
        }
    )

    check_result = _updated_result(source_id="DS-3")
    pipeline_ok = PipelineResult(
        ok=True,
        pipeline_skipped=False,
        raw_link_count=1,
        new_link_count=1,
        classified_count=1,
        skipped_count=0,
        enriched_count=1,
        persisted_count=1,
        message="流水线完成",
    )

    def fake_run_ds_check(index, source_id, check_update, save_result):
        payload = {
            "source_id": source_id,
            "updated": True,
            "link_count": 1,
            "saved": True,
            "status_text": "发现新专栏，已爬取",
        }
        return index, payload, "log", check_result

    with (
        patch("web.actions._run_ds_check", side_effect=fake_run_ds_check),
        patch("web.actions.run_refresh_all_pipeline", return_value=pipeline_ok) as pipeline_mock,
        patch("web.actions.set_last_pipeline_persisted"),
    ):
        payload = run_action("refresh_source", {"source_id": "DS-3"})

    assert payload["ok"] is True
    pipeline_mock.assert_called_once()
    assert get_last_container("DS-3") == "https://www.bilibili.com/read/cv999001"


def test_refresh_source_keeps_checkpoint_when_pipeline_fails(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_home
    save_state(
        {
            "sources": {
                "DS-3": {"container_url": "https://www.bilibili.com/read/cv888001"},
            }
        }
    )

    check_result = _updated_result(source_id="DS-3")

    def fake_run_ds_check(index, source_id, check_update, save_result):
        payload = {
            "source_id": source_id,
            "updated": True,
            "link_count": 1,
            "saved": True,
            "status_text": "发现新专栏，已爬取",
        }
        return index, payload, "log", check_result

    with (
        patch("web.actions._run_ds_check", side_effect=fake_run_ds_check),
        patch(
            "web.actions.run_refresh_all_pipeline",
            side_effect=RuntimeError("无法获取动态正文: 1220000000000000001"),
        ),
        patch("web.actions.set_last_pipeline_persisted"),
    ):
        with pytest.raises(RuntimeError, match="无法获取动态正文"):
            run_action("refresh_source", {"source_id": "DS-3"})

    assert get_last_container("DS-3") == "https://www.bilibili.com/read/cv888001"


def test_ds8_checkpoint_advances_fingerprint_only_after_commit(
    isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """增量 fingerprint 复用 cv_id 列：check_update 判定变化但不落库，
    只有 commit_source_checkpoint（成功路径）才推进。"""
    f = tmp_path / "manual_dyids.txt"
    f.write_text("1224962472871460885", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    from src.sources.ds8_manual import check_update

    r1 = check_update()
    assert r1.updated is True
    assert r1.cv_id  # fingerprint 承载于 cv_id
    assert load_source_fingerprint("DS-8") is None  # 检查阶段不落库
    commit_source_checkpoint(r1)
    assert load_source_fingerprint("DS-8") == r1.cv_id
    assert get_last_cv_id("DS-8") == r1.cv_id

    # 同内容再查：fingerprint 相同 → 无更新
    assert check_update().updated is False

    # 内容变化：新 fingerprint，但 commit 前 DB 仍是旧值（pipeline 失败不丢更新）
    f.write_text("1224962472871460885\n1224962472871460886", encoding="utf-8")
    r3 = check_update()
    assert r3.updated is True
    assert load_source_fingerprint("DS-8") == r1.cv_id
    commit_source_checkpoint(r3)
    assert load_source_fingerprint("DS-8") == r3.cv_id


def test_ds10_checkpoint_persists_per_source_fingerprints(
    isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DS-10 按源 fingerprint 以 JSON 存于 cv_id 列，commit 后整体持久化。"""
    import json as _json

    src_a = tmp_path / "a.json"
    src_a.write_text(_json.dumps({"dynamic_ids": ["1224962472871460885"]}), encoding="utf-8")
    conf = tmp_path / "api_sources.txt"
    conf.write_text(f"file://{src_a.as_posix()}\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", conf)
    from src.sources.ds10_api import check_update

    r1 = check_update()
    assert r1.updated is True
    assert load_source_fingerprint("DS-10") is None
    commit_source_checkpoint(r1)
    stored = load_source_fingerprint("DS-10")
    assert stored == r1.cv_id
    parsed = _json.loads(stored)
    assert isinstance(parsed, dict) and len(parsed) == 1

    # 相同内容再查 → 无更新（按源指纹判定）
    assert check_update().updated is False
