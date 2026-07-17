from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.refresh_all_pipeline import PipelineResult
from src.sources.common import CheckResult, commit_source_checkpoint
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


def test_commit_source_checkpoint_writes_only_when_updated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.state_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", tmp_path / "state.json")
    save_state({"sources": {}})

    unchanged = _updated_result()
    unchanged.updated = False
    commit_source_checkpoint(unchanged)
    assert get_last_container("DS-2") is None

    commit_source_checkpoint(_updated_result())
    assert get_last_container("DS-2") == "https://www.bilibili.com/read/cv999001"


def test_commit_source_checkpoint_keeps_cv_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.state_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", tmp_path / "state.json")
    save_state({"sources": {}})

    commit_source_checkpoint(
        _updated_result(source_id="DS-5", cv_id="555001"),
    )
    assert get_last_container("DS-5") == "https://www.bilibili.com/read/cv999001"
    assert get_last_cv_id("DS-5") == "555001"


def test_ds2_check_update_does_not_write_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.sources.ds2_fanqiao.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.sources.ds2_fanqiao.OUTPUT_PATH", tmp_path / "ds2_latest.json")
    monkeypatch.setattr("src.state_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", tmp_path / "state.json")
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.state_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", tmp_path / "state.json")
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
        patch("web.actions.invalidate_activity_cache"),
        patch("web.actions.set_last_pipeline_persisted"),
    ):
        payload = run_action("refresh_source", {"source_id": "DS-3"})

    assert payload["ok"] is True
    pipeline_mock.assert_called_once()
    assert get_last_container("DS-3") == "https://www.bilibili.com/read/cv999001"


def test_refresh_source_keeps_checkpoint_when_pipeline_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.state_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.state_store.STATE_PATH", tmp_path / "state.json")
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
        patch("web.actions.invalidate_activity_cache"),
        patch("web.actions.set_last_pipeline_persisted"),
    ):
        with pytest.raises(RuntimeError, match="无法获取动态正文"):
            run_action("refresh_source", {"source_id": "DS-3"})

    assert get_last_container("DS-3") == "https://www.bilibili.com/read/cv888001"
