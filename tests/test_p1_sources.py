"""P1 新增数据源（DS-8 手动清单 / DS-9 话题 / DS-10 外部 API）回归测试。"""
from __future__ import annotations

import json

import pytest

from src.sources.ds10_api import _extract_dynamic_ids as api_extract
from src.sources.ds8_manual import _read_manual_ids, check_update as manual_check
from src.sources.ds9_tags import _extract_dynamic_ids as tag_extract

VALID_ID = "1224962472871460885"
VALID_ID2 = "1224962472871460886"


def test_ds8_read_manual_ids(tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(
        f"{VALID_ID}\nhttps://www.bilibili.com/opus/{VALID_ID2}\n"
        f"{VALID_ID},bad_id\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    ids = _read_manual_ids()
    assert ids == [VALID_ID, VALID_ID2]


def test_ds8_check_update_empty(tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text("  \n# 注释\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    result = manual_check()
    assert result.updated is False


def test_ds8_check_update_links(tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(VALID_ID, encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    result = manual_check()
    assert result.updated is True
    assert result.activity_links == [f"https://www.bilibili.com/opus/{VALID_ID}"]


def test_ds9_extract_dynamic_ids_cards() -> None:
    data = {
        "cards": [
            {"desc": {"dynamic_id": VALID_ID}},
            {"id_str": VALID_ID2},
            {"item": {"id_str": VALID_ID}},
            {"desc": {"dynamic_id": "not-a-number"}},
        ]
    }
    ids = tag_extract(data)
    assert VALID_ID in ids
    assert VALID_ID2 in ids
    assert len(ids) == 2


def test_ds9_extract_dynamic_ids_news() -> None:
    data = {
        "hot_list": [
            {"card": {}, "desc": {"dynamic_id": VALID_ID2}},
        ],
        "items": [{"id_str": VALID_ID}],
    }
    ids = tag_extract(data)
    assert ids == [VALID_ID, VALID_ID2]


def test_ds9_check_update_empty_tags(tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)
    result = None
    from src.sources.ds9_tags import check_update

    result = check_update()
    assert result.updated is False


def test_ds9_check_update_fetches(tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_topic_new(self, tag):
            return {"hot_list": [{"desc": {"dynamic_id": VALID_ID}}]}

        def get_topic_history(self, tag, offset_dynamic_id=""):
            return {"cards": [{"desc": {"dynamic_id": VALID_ID2}}], "offset": ""}

    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: _FakeClient())
    from src.sources.ds9_tags import check_update

    result = check_update()
    assert result.updated is True
    assert VALID_ID in " ".join(result.activity_links)
    assert len(result.activity_links) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"lottery_info": [{"dyid": VALID_ID}, {"dyid": VALID_ID2}]},
        {"dynamic_ids": [VALID_ID, VALID_ID2]},
        {"links": [f"https://www.bilibili.com/opus/{VALID_ID}", VALID_ID2]},
        [VALID_ID, f"https://www.bilibili.com/opus/{VALID_ID2}"],
    ],
)
def test_ds10_extract_dynamic_ids_formats(payload) -> None:
    ids = api_extract(payload)
    assert VALID_ID in ids
    assert VALID_ID2 in ids


def test_ds10_check_update_file_source(tmp_path, monkeypatch) -> None:
    source_file = tmp_path / "feed.json"
    source_file.write_text(json.dumps({"lottery_info": [{"dyid": VALID_ID}]}), encoding="utf-8")
    conf = tmp_path / "api_sources.txt"
    conf.write_text(f"file://{source_file.as_posix()}\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", conf)
    from src.sources.ds10_api import check_update

    result = check_update()
    assert result.updated is True
    assert result.activity_links == [f"https://www.bilibili.com/opus/{VALID_ID}"]
