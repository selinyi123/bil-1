from __future__ import annotations

import json

from web.activity_service import get_summary


def test_get_summary_counts_are_consistent(tmp_path, monkeypatch) -> None:
    path = tmp_path / "activities_latest.json"
    path.write_text(
        json.dumps(
            {
                "updated_at": 1,
                "activities": [
                    {
                        "dynamic_id": "1",
                        "lottery_type": "转发抽奖",
                        "draw_status": "active",
                        "activity_status": "未参加",
                    },
                    {
                        "dynamic_id": "2",
                        "lottery_type": "互动抽奖",
                        "draw_status": "ended",
                        "activity_status": "已结束",
                    },
                    {
                        "dynamic_id": "3",
                        "lottery_type": "充电抽奖",
                        "skipped": True,
                        "draw_status": "active",
                        "activity_status": "未参加",
                    },
                    {
                        "dynamic_id": "4",
                        "lottery_type": "转发抽奖",
                        "skipped": True,
                        "skip_reason": "非抽奖活动",
                        "draw_status": "active",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("web.activity_service.ACTIVITIES_OUTPUT_PATH", path)
    monkeypatch.setattr("web.activity_service.load_participations", lambda: {})
    monkeypatch.setattr("web.activity_service._load_json", lambda p: json.loads(path.read_text(encoding="utf-8")))

    summary = get_summary()
    status = summary["user_status_counts"]
    draw = summary["counts"]

    assert summary["total_count"] == 2
    assert status["未参加"] + status["已参加"] + status["已结束"] == 2
    assert draw["active"] + draw["ended"] == 2
    assert draw == {"active": 1, "ended": 1}
