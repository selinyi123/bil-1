from __future__ import annotations

from src.forward_parser import (
    INITIAL_STATE_RE,
    _fetch_html_dynamic_text,
    fetch_dynamic_content,
)


def test_fetch_dynamic_content_tries_opus_when_dynamic_text_empty(monkeypatch) -> None:
    class _Client:
        pass

    calls = {"dynamic": 0, "opus": 0, "html": 0}

    def fake_dynamic(client, dynamic_id):
        calls["dynamic"] += 1
        return {
            "type": "DYNAMIC_TYPE_DRAW",
            "modules": {"module_dynamic": {"desc": {"text": ""}}},
        }

    def fake_opus(client, dynamic_id):
        calls["opus"] += 1
        return {
            "modules": [
                {
                    "module_content": {
                        "paragraphs": [
                            {
                                "text": {
                                    "nodes": [
                                        {"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "足够长的正文来自 opus/detail"}},
                                    ]
                                }
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr("src.lottery_api._fetch_dynamic_api_item", fake_dynamic)
    monkeypatch.setattr("src.lottery_api._fetch_opus_detail_item", fake_opus)
    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda *args, **kwargs: calls.__setitem__("html", calls["html"] + 1) or "",
    )

    text = fetch_dynamic_content(_Client(), "123")
    assert "足够长的正文来自 opus/detail" in text
    assert calls == {"dynamic": 1, "opus": 1, "html": 0}


def test_fetch_html_skips_retry_when_no_initial_state(monkeypatch) -> None:
    class _Client:
        pass

    calls = {"n": 0}

    def fake_get_text(url, *, referer, retries=1):
        calls["n"] += 1
        return "<html><body>验证码</body></html>"

    client = _Client()
    client.get_text = fake_get_text  # type: ignore[method-assign]

    text = _fetch_html_dynamic_text(client, "123")
    assert text == ""
    assert calls["n"] == 1


def test_fetch_html_extracts_when_initial_state_present(monkeypatch) -> None:
    class _Client:
        pass

    state = (
        'window.__INITIAL_STATE__={"detail":{"modules":{"module_dynamic":'
        '{"desc":{"text":"HTML 正文足够长用于分类"}}}}};'
    )

    client = _Client()
    client.get_text = lambda *args, **kwargs: f"<html>{state}</html>"  # type: ignore[method-assign]

    text = _fetch_html_dynamic_text(client, "123")
    assert "HTML 正文足够长" in text
    assert INITIAL_STATE_RE.search(state)


def test_classify_reserve_skips_html_when_api_additional_empty(monkeypatch) -> None:
    from src.pipeline.classify_fetch_context import ClassifyFetchContext

    class _Client:
        pass

    html_calls = {"n": 0}

    def fake_has_reserve_from_page(client, dynamic_id):
        html_calls["n"] += 1
        return False

    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context._has_reserve_from_page",
        fake_has_reserve_from_page,
    )

    ctx = ClassifyFetchContext(_Client(), "123")
    assert ctx.classify_reserve_candidate({}) == "not_reserve"
    assert html_calls["n"] == 0


def test_fetch_dynamic_content_forward_skips_opus_and_html(monkeypatch) -> None:
    class _Client:
        pass

    calls = {"dynamic": 0, "opus": 0, "html": 0}

    def fake_dynamic(client, dynamic_id):
        calls["dynamic"] += 1
        return {
            "type": "DYNAMIC_TYPE_FORWARD",
            "modules": {
                "module_dynamic": {
                    "desc": {"text": "纯转发动态正文足够长，不需要 opus 或 HTML 兜底"},
                }
            },
        }

    monkeypatch.setattr("src.lottery_api._fetch_dynamic_api_item", fake_dynamic)
    monkeypatch.setattr(
        "src.lottery_api._fetch_opus_detail_item",
        lambda client, dynamic_id: calls.__setitem__("opus", calls["opus"] + 1) or None,
    )
    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: calls.__setitem__("html", calls["html"] + 1) or "",
    )

    text = fetch_dynamic_content(_Client(), "123")
    assert "纯转发动态正文足够长" in text
    assert calls == {"dynamic": 1, "opus": 0, "html": 0}


def test_fetch_dynamic_content_forward_empty_uses_html_when_enabled(monkeypatch) -> None:
    class _Client:
        pass

    forward_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {"module_dynamic": {"desc": {"text": ""}}},
    }
    html_calls = {"n": 0}

    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: html_calls.__setitem__("n", html_calls["n"] + 1)
        or "HTML 正文足够长用于转发抽奖分类判断测试内容",
    )

    text = fetch_dynamic_content(_Client(), "123", detail_item=forward_item, try_html=True)
    assert "HTML 正文足够长" in text
    assert html_calls["n"] == 1


def test_fetch_dynamic_content_forward_short_detail_returns_without_html(monkeypatch) -> None:
    class _Client:
        pass

    forward_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {"module_dynamic": {"desc": {"text": "短正文"}}},
    }
    html_calls = {"n": 0}

    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: html_calls.__setitem__("n", html_calls["n"] + 1) or "不应调用",
    )

    text = fetch_dynamic_content(_Client(), "123", detail_item=forward_item, try_html=True)
    assert text == "短正文"
    assert html_calls["n"] == 0
