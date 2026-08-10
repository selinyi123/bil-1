from web.actions import (
    DS_HANDLERS,
    REFRESH_ALL_TOTAL,
    _format_subprogress_message,
    _pipeline_substep_index,
)


def test_format_subprogress_message_strips_duplicate_suffix() -> None:
    assert _format_subprogress_message("分类进度 (30/236)", 30, 236) == "分类进度 (30/236)"
    assert _format_subprogress_message("分类进度 (30/236) (30/236)", 30, 236) == "分类进度 (30/236)"


def test_format_subprogress_message_appends_once() -> None:
    assert _format_subprogress_message("分类进度", 30, 236) == "分类进度 (30/236)"


def test_pipeline_substep_index_from_message() -> None:
    assert _pipeline_substep_index("分类进度 (30/236)") == 1
    assert _pipeline_substep_index("正在分类 236 条新链接…") == 1
    assert _pipeline_substep_index("详情进度 (3/10)") == 2
    assert _pipeline_substep_index("正在拉取 10 条活动详情…") == 2
    assert _pipeline_substep_index("正在写入活动库…") == 3


def test_refresh_all_total_matches_handlers() -> None:
    assert REFRESH_ALL_TOTAL == len(DS_HANDLERS) + 3


def test_refresh_all_all_sources_failed_returns_failure(monkeypatch) -> None:
    """核心不变量：全部数据源失败时 refresh_all 必须返回 ok=False，不得伪装成"无更新"。"""
    from web.actions import run_action

    def fail_check(force=False):
        raise RuntimeError("网络挂了")

    monkeypatch.setattr("web.actions.DS_HANDLERS", [("DS-X", fail_check, lambda r: None)])
    payload = run_action("refresh_all", {})
    assert payload["ok"] is False
    assert "全部" in payload["message"] and "失败" in payload["message"]
    assert payload["result"]["sources_failed"] == 1


def test_refresh_all_partial_failure_is_degraded_not_silent(monkeypatch) -> None:
    """部分数据源失败时即使无更新也要在消息中明示失败数量。"""
    from web.actions import run_action

    def fail_check(force=False):
        raise RuntimeError("网络挂了")

    def ok_check(force=False):
        from src.sources.common import CheckResult

        return CheckResult(
            source_id="DS-Y",
            updated=False,
            container_url="https://example.com/c",
            container_id="c",
            title="t",
            published_at=0,
            previous_container_url="https://example.com/c",
            activity_links=[],
            checked_at=0,
        )

    monkeypatch.setattr(
        "web.actions.DS_HANDLERS",
        [("DS-X", fail_check, lambda r: None), ("DS-Y", ok_check, lambda r: None)],
    )
    payload = run_action("refresh_all", {})
    assert payload["ok"] is True
    assert "均无新专栏" in payload["message"]
    assert "1 个数据源检查失败" in payload["message"]
    assert payload["result"]["sources_failed"] == 1
