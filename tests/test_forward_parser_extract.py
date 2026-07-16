from src.forward_parser import (
    DynamicContentFetchError,
    _extract_from_detail_item,
    fetch_dynamic_content,
    fetch_dynamic_content_with_retry,
)


def test_forward_dynamic_extracts_desc_and_orig() -> None:
    item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_dynamic": {
                "desc": {
                    "rich_text_nodes": [
                        {"orig_text": "毕业不散场！@Kawasaki川崎运动 "},
                        {"orig_text": "#互动抽奖#"},
                    ]
                },
                "major": {"type": "MAJOR_TYPE_DRAW"},
            }
        },
        "orig": {
            "type": "DYNAMIC_TYPE_DRAW",
            "modules": {
                "module_dynamic": {
                    "desc": {
                        "text": "转发有礼！开奖日期为【2026年7月15日】一等奖川崎巧克力88D羽毛球拍",
                    }
                }
            },
        },
    }
    text = _extract_from_detail_item(item)
    assert "毕业不散场" in text
    assert "互动抽奖" in text
    assert "开奖日期" in text
    assert "川崎巧克力" in text


def test_api_code_zero_is_success() -> None:
    from src.bilibili_client import api_code

    assert api_code({"code": 0, "message": "0"}) == 0
    assert api_code({"code": None}) == -1


def test_dict_modules_module_content_paragraphs() -> None:
    item = {
        "type": "DYNAMIC_TYPE_DRAW",
        "modules": {
            "module_dynamic": {"major": {"type": "MAJOR_TYPE_DRAW"}},
            "module_content": {
                "paragraphs": [
                    {
                        "para_type": 1,
                        "text": {
                            "nodes": [
                                {"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "转发有礼！"}},
                            ]
                        },
                    },
                    {
                        "para_type": 1,
                        "text": {
                            "nodes": [
                                {"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "开奖日期为7月15日"}},
                            ]
                        },
                    },
                ],
            },
        },
    }
    text = _extract_from_detail_item(item)
    assert "转发有礼" in text
    assert "开奖日期" in text


def test_fetch_dynamic_content_returns_empty_when_detail_accessible(monkeypatch) -> None:
    class _Client:
        pass

    monkeypatch.setattr(
        "src.lottery_api._fetch_dynamic_api_item",
        lambda client, dynamic_id: {"type": "DYNAMIC_TYPE_DRAW", "modules": {}},
    )
    monkeypatch.setattr(
        "src.lottery_api._fetch_opus_detail_item",
        lambda client, dynamic_id: None,
    )
    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: "",
    )

    text = fetch_dynamic_content(_Client(), "1222177457169235975")
    assert text == ""


def test_fetch_dynamic_content_raises_when_detail_unresolved(monkeypatch) -> None:
    class _Client:
        pass

    monkeypatch.setattr(
        "src.lottery_api._fetch_dynamic_api_item",
        lambda client, dynamic_id: None,
    )
    monkeypatch.setattr(
        "src.lottery_api._fetch_opus_detail_item",
        lambda client, dynamic_id: None,
    )
    monkeypatch.setattr(
        "src.forward_parser._fetch_html_dynamic_text",
        lambda client, dynamic_id: "",
    )

    try:
        fetch_dynamic_content(_Client(), "1222177457169235975")
        assert False, "expected DynamicContentFetchError"
    except DynamicContentFetchError as exc:
        assert exc.dynamic_id == "1222177457169235975"
        assert exc.retryable


def test_fetch_dynamic_content_with_retry_succeeds_after_transient_failure(monkeypatch) -> None:
    class _Client:
        pass

    calls = {"n": 0}

    def _flaky(client, dynamic_id, *, detail_item=None, try_html=True):
        calls["n"] += 1
        if calls["n"] < 2:
            raise DynamicContentFetchError("network", dynamic_id=dynamic_id)
        return "足够长的正文内容用于分类判断"

    monkeypatch.setattr("src.forward_parser.fetch_dynamic_content", _flaky)
    monkeypatch.setattr("src.forward_parser.time.sleep", lambda _: None)

    text = fetch_dynamic_content_with_retry(_Client(), "123")
    assert "足够长的正文" in text
    assert calls["n"] == 2


def test_fetch_dynamic_content_with_retry_keeps_cached_detail(monkeypatch) -> None:
    class _Client:
        pass

    cached_item = {
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_dynamic": {
                "desc": {"text": "缓存正文足够长用于分类判断与重试复用"},
            }
        },
    }
    seen_detail_items: list[dict | None] = []

    def _flaky(client, dynamic_id, *, detail_item=None, try_html=True):
        seen_detail_items.append(detail_item)
        if len(seen_detail_items) < 2:
            raise DynamicContentFetchError("network", dynamic_id=dynamic_id)
        return "缓存正文足够长用于分类判断与重试复用"

    monkeypatch.setattr("src.forward_parser.fetch_dynamic_content", _flaky)
    monkeypatch.setattr("src.forward_parser.time.sleep", lambda _: None)

    text = fetch_dynamic_content_with_retry(_Client(), "123", initial_detail_item=cached_item)
    assert "缓存正文足够长" in text
    assert seen_detail_items == [cached_item, cached_item]
