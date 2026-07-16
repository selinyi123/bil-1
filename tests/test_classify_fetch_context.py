from __future__ import annotations

from src.pipeline.classify_fetch_context import ClassifyFetchContext


def test_classify_context_reuses_detail_api_for_additional_and_detail(monkeypatch) -> None:
    calls = {"detail_api": 0, "opus": 0, "notice": 0}

    class _Client:
        pass

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_dynamic": {
                "desc": {"text": "转发本条动态参与抽奖"},
            }
        },
    }

    def fake_get_json(url, params, *, referer, retries=1):
        if "web-dynamic/v1/detail" in url and "opus" not in url:
            calls["detail_api"] += 1
            return {"code": 0, "data": {"item": raw_item}}
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.is_detail_api_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context._fetch_opus_detail_item",
        lambda client, dynamic_id: calls.__setitem__("opus", calls["opus"] + 1) or None,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.fetch_lottery_notice",
        lambda *args, **kwargs: calls.__setitem__("notice", calls["notice"] + 1) or None,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context._has_reserve_from_page",
        lambda client, dynamic_id: True,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.resolve_reserve_business",
        lambda *args, **kwargs: None,
    )

    client = _Client()
    client.get_json = fake_get_json  # type: ignore[method-assign]
    ctx = ClassifyFetchContext(client, "123")

    additional = ctx.get_additional()
    assert additional == {}
    detail = ctx.get_detail_item()
    assert detail is not None
    assert calls["detail_api"] == 1
    assert calls["opus"] == 0

    outcome = ctx.classify_reserve_candidate(additional)
    assert outcome == "not_reserve"
    assert calls["detail_api"] == 1
    assert calls["notice"] == 0


def test_classify_context_reserve_notice_called_once(monkeypatch) -> None:
    notice_calls = {"n": 0}

    class _Client:
        pass

    reserve = {
        "title": "直播预约：测试",
        "jump_url": "https://live.bilibili.com/1",
        "desc1": {"text": "直播中"},
        "desc2": {"text": "9人看过"},
        "rid": 99,
    }
    raw_item = {
        "modules": {
            "module_dynamic": {
                "additional": {"reserve": reserve, "type": "ADDITIONAL_TYPE_RESERVE"},
            }
        }
    }

    def fake_get_json(url, params, *, referer, retries=1):
        return {"code": 0, "data": {"item": raw_item}}

    def fake_notice(*args, **kwargs):
        notice_calls["n"] += 1
        return None

    monkeypatch.setattr("src.pipeline.classify_fetch_context.is_detail_api_enabled", lambda: True)
    monkeypatch.setattr("src.pipeline.classify_fetch_context._has_reserve_from_page", lambda *args: False)
    monkeypatch.setattr("src.pipeline.classify_fetch_context._fetch_opus_detail_item", lambda *args: None)
    monkeypatch.setattr("src.pipeline.classify_fetch_context.fetch_lottery_notice", fake_notice)

    client = _Client()
    client.get_json = fake_get_json  # type: ignore[method-assign]
    ctx = ClassifyFetchContext(client, "123")
    additional = ctx.get_additional()
    assert ctx.classify_reserve_candidate(additional) == "skip"
    assert notice_calls["n"] == 1


def test_fetch_content_reuses_detail_api_item_without_second_request(monkeypatch) -> None:
    calls = {"detail_api": 0, "opus": 0, "html": 0}

    class _Client:
        pass

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_dynamic": {
                "desc": {"text": "转发本条动态参与抽奖，正文长度足够用于分类判断"},
            }
        },
    }

    def fake_probe(client, dynamic_id, *, retries=2):
        calls["detail_api"] += 1
        return raw_item, 0, "0"

    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.is_detail_api_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.probe_dynamic_detail_api",
        fake_probe,
    )
    monkeypatch.setattr(
        "src.lottery_api._fetch_opus_detail_item",
        lambda client, dynamic_id: calls.__setitem__("opus", calls["opus"] + 1) or None,
    )
    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: calls.__setitem__("html", calls["html"] + 1) or "",
    )

    ctx = ClassifyFetchContext(_Client(), "123")
    ctx.get_additional()
    assert calls["detail_api"] == 1

    text = ctx.resolve_classify_content()
    assert "转发本条动态参与抽奖" in text
    assert calls == {"detail_api": 1, "opus": 0, "html": 0}


def test_resolve_classify_content_skips_fetch_when_detail_has_text(monkeypatch) -> None:
    calls = {"fetch_retry": 0}

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {"module_dynamic": {"desc": {"text": "转"}}},
    }

    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.is_detail_api_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.probe_dynamic_detail_api",
        lambda *args, **kwargs: (raw_item, 0, "0"),
    )
    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.fetch_dynamic_content_with_retry",
        lambda *args, **kwargs: calls.__setitem__("fetch_retry", calls["fetch_retry"] + 1) or "不应调用",
    )

    ctx = ClassifyFetchContext(object(), "123")
    ctx.get_additional()
    assert ctx.resolve_classify_content() == "转"
    assert calls["fetch_retry"] == 0


def test_fetch_content_retry_single_attempt_for_forward_empty_detail(monkeypatch) -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []
    try_html_flags: list[bool] = []

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {"module_dynamic": {"desc": {"text": ""}}},
    }

    from src.forward_parser import DynamicContentFetchError, fetch_dynamic_content_with_retry

    def _fetch(client, dynamic_id, *, detail_item=None, try_html=True):
        attempts["n"] += 1
        try_html_flags.append(try_html)
        if try_html:
            return "HTML 正文足够长用于转发抽奖分类判断测试内容"
        raise DynamicContentFetchError("empty", dynamic_id="123")

    monkeypatch.setattr("src.forward_parser.fetch_dynamic_content", _fetch)
    monkeypatch.setattr("src.forward_parser.time.sleep", lambda sec: sleeps.append(sec))

    class _Client:
        pass

    text = fetch_dynamic_content_with_retry(_Client(), "123", initial_detail_item=raw_item)
    assert "HTML 正文足够长" in text
    assert attempts["n"] == 1
    assert try_html_flags == [True]
    assert sleeps == []


def test_fetch_content_retry_forward_short_preview_skips_html(monkeypatch) -> None:
    try_html_flags: list[bool] = []

    raw_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {"module_dynamic": {"desc": {"text": "短正文"}}},
    }

    from src.forward_parser import fetch_dynamic_content_with_retry

    def _fetch(client, dynamic_id, *, detail_item=None, try_html=True):
        try_html_flags.append(try_html)
        return "短正文"

    monkeypatch.setattr("src.forward_parser.fetch_dynamic_content", _fetch)
    monkeypatch.setattr("src.forward_parser.time.sleep", lambda sec: None)

    class _Client:
        pass

    text = fetch_dynamic_content_with_retry(_Client(), "123", initial_detail_item=raw_item)
    assert text == "短正文"
    assert try_html_flags == [False]
