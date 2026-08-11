"""P1 新增数据源（DS-8 手动清单 / DS-9 话题 / DS-10 外部 API）回归测试。

覆盖 P2 #11 增量语义：内容未变 → updated=False；首次/内容变化/force → True。
"""
from __future__ import annotations

import json

import pytest

from src.sources.common import commit_source_checkpoint, load_source_fingerprint
from src.sources.ds10_api import _extract_dynamic_ids as api_extract
from src.sources.ds8_manual import _read_manual_ids, check_update as manual_check
from src.sources.ds9_tags import _extract_dynamic_ids as tag_extract

VALID_ID = "1224962472871460885"
VALID_ID2 = "1224962472871460886"
VALID_ID3 = "1224962472871460887"


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


def test_ds8_check_update_empty(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text("  \n# 注释\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    result = manual_check()
    assert result.updated is False


def test_ds8_check_update_links(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(VALID_ID, encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    result = manual_check()
    assert result.updated is True
    assert result.activity_links == [f"https://www.bilibili.com/opus/{VALID_ID}"]


def test_ds8_incremental_same_list_no_update(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(f"{VALID_ID}\n{VALID_ID2}\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)

    r1 = manual_check()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # 同一清单（含顺序变化）：指纹相同 → 无更新
    f.write_text(f"{VALID_ID2}\n{VALID_ID}\n", encoding="utf-8")
    r2 = manual_check()
    assert r2.updated is False


def test_ds8_incremental_list_changed(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(VALID_ID, encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)

    r1 = manual_check()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    f.write_text(f"{VALID_ID}\n{VALID_ID2}\n", encoding="utf-8")
    r2 = manual_check()
    assert r2.updated is True
    assert VALID_ID2 in " ".join(r2.activity_links)


def test_ds8_force_bypasses_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "manual_dyids.txt"
    f.write_text(VALID_ID, encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)

    r1 = manual_check()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # force=True 必须强制 updated=True（check_cli 用）
    r2 = manual_check(force=True)
    assert r2.updated is True


def test_ds8_empty_batch_advances_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    """#23：清空清单后旧快照被覆盖清空——先有 ID（commit）→ 清空 → updated=True
    + 空 activity_links + cv_id 推进 → 再查（仍空）→ updated=False。"""
    f = tmp_path / "manual_dyids.txt"
    f.write_text(VALID_ID, encoding="utf-8")
    monkeypatch.setattr("src.sources.ds8_manual.CONFIG_FILE", f)
    from src.sources.ds8_manual import save_result as ds8_save

    r1 = manual_check()
    assert r1.updated is True
    commit_source_checkpoint(r1)
    ds8_save(r1)  # 落库旧快照（含链接）

    # 清空配置 → 空批次推进：updated=True + 空链接 + 指纹推进
    f.write_text("", encoding="utf-8")
    r2 = manual_check()
    assert r2.updated is True
    assert r2.activity_links == []
    assert r2.cv_id and r2.cv_id != r1.cv_id  # 指纹推进（空清单指纹）
    commit_source_checkpoint(r2)
    ds8_save(r2)  # 覆盖旧快照（清空）

    # 仍空 → 收敛为无更新
    r3 = manual_check()
    assert r3.updated is False


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


def test_ds9_check_update_empty_tags(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)
    result = None
    from src.sources.ds9_tags import check_update

    result = check_update()
    assert result.updated is False


class _FakeTopicClient:
    """可配置的假 B 站客户端：记录历史页抓取次数。"""

    def __init__(self, latest_ids: list[str], history_ids: list[str] | None = None) -> None:
        self.latest_ids = list(latest_ids)
        self.history_ids = list(history_ids or [])
        self.history_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get_topic_new(self, tag):
        return {"hot_list": [{"desc": {"dynamic_id": did}} for did in self.latest_ids]}

    def get_topic_history(self, tag, offset_dynamic_id=""):
        self.history_calls += 1
        if not self.history_ids:
            return None
        return {"cards": [{"desc": {"dynamic_id": did}} for did in self.history_ids], "offset": ""}


def test_ds9_check_update_fetches(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    fake = _FakeTopicClient(latest_ids=[VALID_ID], history_ids=[VALID_ID2])
    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: fake)
    from src.sources.ds9_tags import check_update

    result = check_update()
    assert result.updated is True
    assert VALID_ID in " ".join(result.activity_links)
    assert len(result.activity_links) == 2


def test_ds9_incremental_same_content_no_update(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    fake = _FakeTopicClient(latest_ids=[VALID_ID], history_ids=[VALID_ID2])
    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: fake)
    from src.sources.ds9_tags import check_update

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    r2 = check_update()
    assert r2.updated is False
    # 指纹未变时不得再抓多页历史（省网络）
    assert fake.history_calls == 1


def test_ds9_incremental_new_content(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    fake = _FakeTopicClient(latest_ids=[VALID_ID])
    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: fake)
    from src.sources.ds9_tags import check_update

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    fake.latest_ids = [VALID_ID, VALID_ID3]
    r2 = check_update()
    assert r2.updated is True
    assert VALID_ID3 in " ".join(r2.activity_links)


def test_ds9_force_bypasses_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    fake = _FakeTopicClient(latest_ids=[VALID_ID])
    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: fake)
    from src.sources.ds9_tags import check_update

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    r2 = check_update(force=True)
    assert r2.updated is True


def test_ds9_empty_batch_advances_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    """#23：清空话题配置后旧快照被覆盖清空——先有话题（commit）→ 清空 →
    updated=True + 空 activity_links + cv_id 推进 → 再查（仍空）→ updated=False。"""
    f = tmp_path / "topic_tags.txt"
    f.write_text("转发抽奖\n", encoding="utf-8")
    monkeypatch.setattr("src.sources.ds9_tags.CONFIG_FILE", f)

    fake = _FakeTopicClient(latest_ids=[VALID_ID], history_ids=[VALID_ID2])
    monkeypatch.setattr("src.sources.ds9_tags.BilibiliClient", lambda: fake)
    from src.sources.ds9_tags import check_update

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # 清空话题配置 → 空批次推进：updated=True + 空链接 + 指纹推进
    f.write_text("", encoding="utf-8")
    r2 = check_update()
    assert r2.updated is True
    assert r2.activity_links == []
    assert r2.cv_id and r2.cv_id != r1.cv_id  # 指纹推进（空配置指纹）
    commit_source_checkpoint(r2)

    # 仍空 → 收敛为无更新
    r3 = check_update()
    assert r3.updated is False


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


def _write_ds10_conf(tmp_path, *lines: str):
    conf = tmp_path / "api_sources.txt"
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_ds10_check_update_file_source(isolated_home, tmp_path, monkeypatch) -> None:
    source_file = tmp_path / "feed.json"
    source_file.write_text(json.dumps({"lottery_info": [{"dyid": VALID_ID}]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{source_file.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    result = check_update()
    assert result.updated is True
    assert result.activity_links == [f"https://www.bilibili.com/opus/{VALID_ID}"]


def test_ds10_file_same_content_no_update(isolated_home, tmp_path, monkeypatch) -> None:
    source_file = tmp_path / "feed.json"
    source_file.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{source_file.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # 相同内容 → 无更新
    r2 = check_update()
    assert r2.updated is False

    # 内容变化 → 更新
    source_file.write_text(json.dumps({"dynamic_ids": [VALID_ID, VALID_ID2]}), encoding="utf-8")
    r3 = check_update()
    assert r3.updated is True
    assert VALID_ID2 in " ".join(r3.activity_links)


def test_ds10_http_etag_conditional_requests(isolated_home, tmp_path, monkeypatch) -> None:
    """HTTP 源 ETag 条件请求：304 → 无更新；内容变化 → 更新。"""
    import httpx as _httpx

    _write_ds10_conf(tmp_path, "https://example.com/feed.json")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    state = {
        "v1": json.dumps({"dynamic_ids": [VALID_ID]}),
        "v2": json.dumps({"dynamic_ids": [VALID_ID, VALID_ID3]}),
        "current": None,
        "headers_seen": [],
    }
    state["current"] = state["v1"]

    class _Resp:
        def __init__(self, status_code: int, text: str, headers: dict | None = None) -> None:
            self.status_code = status_code
            self.text = text
            self.headers = headers or {}

    def fake_get(url, timeout, follow_redirects, proxy, headers=None):
        state["headers_seen"].append(dict(headers or {}))
        # 真实服务器语义：ETag 随内容变化；条件头命中当前 ETag 才回 304
        current_etag = '"etag-v1"' if state["current"] == state["v1"] else '"etag-v2"'
        if headers and headers.get("If-None-Match") == current_etag:
            return _Resp(304, "")
        return _Resp(200, state["current"], {"ETag": current_etag})

    monkeypatch.setattr(_httpx, "get", fake_get)

    r1 = check_update()
    assert r1.updated is True
    assert r1.activity_links == [f"https://www.bilibili.com/opus/{VALID_ID}"]
    commit_source_checkpoint(r1)

    # 第二次带 If-None-Match，命中 304 → 无更新
    r2 = check_update()
    assert r2.updated is False
    assert state["headers_seen"][1].get("If-None-Match") == '"etag-v1"'

    # 服务器内容变化（200 + 新载荷 + 新 ETag）→ 更新
    state["current"] = state["v2"]
    r3 = check_update()
    assert r3.updated is True
    assert VALID_ID3 in " ".join(r3.activity_links)


def test_ds10_empty_batch_advances_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    """空批次收敛：内容变化但提取不到新动态时，updated=True 推进指纹（空链接），
    下轮同内容即 updated=False，不再每轮重复全量拉取。"""
    src_a = tmp_path / "a.json"
    src_a.write_text(json.dumps({"irrelevant": "no dynamic ids"}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_a.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    monkeypatch.setattr("src.sources.ds10_api.OUTPUT_PATH", tmp_path / "ds10_latest.json")
    from src.sources.ds10_api import check_update

    r1 = check_update()  # 首次：内容有变化（无动态 id）
    assert r1.updated is True
    assert r1.activity_links == []
    assert r1.cv_id  # 指纹随 updated=True 落库
    commit_source_checkpoint(r1)

    # 内容未再变化 → 收敛为无更新（不再重复全量拉取/空跑）
    r2 = check_update()
    assert r2.updated is False


def test_ds10_etag_rotation_advances_fingerprint(isolated_home, tmp_path, monkeypatch) -> None:
    """etag 轮换收敛：内容相同但服务器轮换 ETag 时，updated=True 推进新 etag（空链接），
    下轮携带新条件头命中 304，不再每轮全量下载。"""
    import httpx as _httpx

    _write_ds10_conf(tmp_path, "https://example.com/feed.json")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    body = json.dumps({"dynamic_ids": [VALID_ID]})
    state = {"etag": '"etag-v1"', "headers_seen": []}

    class _Resp:
        def __init__(self, status_code: int, text: str, headers: dict) -> None:
            self.status_code = status_code
            self.text = text
            self.headers = headers

    def fake_get(url, timeout, follow_redirects, proxy, headers=None):
        state["headers_seen"].append(dict(headers or {}))
        if headers and headers.get("If-None-Match") == state["etag"]:
            return _Resp(304, "", {})
        return _Resp(200, body, {"ETag": state["etag"]})

    monkeypatch.setattr(_httpx, "get", fake_get)

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # 服务器轮换 etag（内容不变）
    state["etag"] = '"etag-v2"'
    r2 = check_update()
    assert r2.updated is True  # 内容未变但条件头变化 → 推进指纹
    assert r2.activity_links == []  # 无新链接，流水线空跑跳过
    commit_source_checkpoint(r2)

    # 新 etag 已落库 → 下轮条件请求命中 304，真正收敛
    r3 = check_update()
    assert r3.updated is False
    assert state["headers_seen"][-1].get("If-None-Match") == '"etag-v2"'


def test_ds10_links_only_from_changed_sources(isolated_home, tmp_path, monkeypatch) -> None:
    """任一源变化 → updated=True，activity_links 只含变化源的链接。"""
    src_a = tmp_path / "a.json"
    src_a.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    src_b = tmp_path / "b.json"
    src_b.write_text(json.dumps({"dynamic_ids": [VALID_ID2]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_a.as_posix()}", f"file://{src_b.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    r1 = check_update()
    assert r1.updated is True
    assert len(r1.activity_links) == 2
    commit_source_checkpoint(r1)

    # 仅 b 变化：a 的链接不应出现（a 未变化，已在库/已处理）
    src_b.write_text(json.dumps({"dynamic_ids": [VALID_ID2, VALID_ID3]}), encoding="utf-8")
    r2 = check_update()
    assert r2.updated is True
    assert VALID_ID2 in " ".join(r2.activity_links)
    assert VALID_ID3 in " ".join(r2.activity_links)
    assert VALID_ID not in " ".join(r2.activity_links)


def test_ds10_all_sources_failed_raises(isolated_home, tmp_path, monkeypatch) -> None:
    """核心不变量：DS-10 全部源失败必须抛错（refresh_all 才能计入失败），
    绝不能静默伪装成"没有更新"。"""
    import pytest

    missing = tmp_path / "missing.json"
    _write_ds10_conf(tmp_path, f"file://{missing.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    from src.sources.ds10_api import check_update

    with pytest.raises(RuntimeError, match="全部外部源失败"):
        check_update()


def test_ds10_partial_failure_preserves_previous_meta(isolated_home, tmp_path, monkeypatch) -> None:
    """部分源失败时，失败源的旧 fingerprint 必须保留在提交结果中（下次可继续增量）。"""
    import json as json_mod

    from src.sources.ds10_api import _source_key, check_update

    src_a = tmp_path / "a.json"
    src_a.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    src_b = tmp_path / "b.json"
    src_b.write_text(json.dumps({"dynamic_ids": [VALID_ID2]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_a.as_posix()}", f"file://{src_b.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")
    monkeypatch.setattr("src.sources.ds10_api.OUTPUT_PATH", tmp_path / "ds10_latest.json")

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)
    prev_map = json_mod.loads(r1.cv_id)
    key_b = _source_key(f"file://{src_b.as_posix()}")
    assert key_b in prev_map
    b_old_fp = prev_map[key_b]["fp"]

    # b 源损坏（部分失败），a 内容变化 → updated=True 且提交结果保留 b 的旧 meta
    src_b.unlink()
    src_a.write_text(json.dumps({"dynamic_ids": [VALID_ID, VALID_ID3]}), encoding="utf-8")
    r2 = check_update()
    assert r2.updated is True
    new_map = json_mod.loads(r2.cv_id)
    assert new_map[key_b]["fp"] == b_old_fp  # 失败源旧指纹未丢失


def test_ds10_single_source_transport_error_does_not_abort(
    isolated_home, tmp_path, monkeypatch
) -> None:
    """#20：单个 HTTP 源抛 httpx.ConnectError 时包装为 RuntimeError 降级，
    不中断其它源；整体绝不静默伪装成"无更新"。"""
    import httpx as _httpx

    from src.sources.ds10_api import check_update

    src_b = tmp_path / "b.json"
    src_b.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, "https://bad.example/feed.json", f"file://{src_b.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")

    def fake_get(url, timeout, follow_redirects, proxy, headers=None):
        raise _httpx.ConnectError("connection refused")

    monkeypatch.setattr(_httpx, "get", fake_get)

    result = check_update()
    assert result.updated is True
    assert VALID_ID in " ".join(result.activity_links)


def test_ds10_all_sources_transport_error_raises(isolated_home, tmp_path, monkeypatch) -> None:
    """#20：所有源都因 transport 错误失败时，必须抛 RuntimeError（计入整体失败）。"""
    import httpx as _httpx

    from src.sources.ds10_api import check_update

    _write_ds10_conf(tmp_path, "https://bad.example/feed.json")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")

    def fake_get(url, timeout, follow_redirects, proxy, headers=None):
        raise _httpx.ConnectError("connection refused")

    monkeypatch.setattr(_httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="全部外部源失败"):
        check_update()


def test_ds10_file_source_oserror_wrapped(isolated_home, tmp_path, monkeypatch) -> None:
    """#20：file:// 源读取抛 OSError（如 read_text 对目录）时包装为 RuntimeError。"""
    from src.sources.ds10_api import _fetch_payload_with_meta

    src_dir = tmp_path / "feed_dir"
    src_dir.mkdir()
    with pytest.raises(RuntimeError, match="外部源读取失败"):
        _fetch_payload_with_meta(f"file://{src_dir.as_posix()}", None)


def test_ds10_fingerprint_key_is_hashed_not_plaintext(isolated_home, tmp_path, monkeypatch) -> None:
    """#21：fingerprint map 的 key 是 URL 的 sha256；cv_id 落库内容不含明文 URL（token 不落库）。"""
    from src.sources.ds10_api import _source_key, check_update

    src_a = tmp_path / "a.json"
    src_a.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_a.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)
    stored = load_source_fingerprint("DS-10")
    assert stored is not None
    parsed = json.loads(stored)
    url = f"file://{src_a.as_posix()}"
    assert _source_key(url) in parsed
    assert url not in stored


def test_ds10_removed_source_key_purged(isolated_home, tmp_path, monkeypatch) -> None:
    """#22：配置里移除的源其旧 fingerprint key 必须被清理，不得残留在新映射中。"""
    from src.sources.ds10_api import _source_key, check_update

    src_a = tmp_path / "a.json"
    src_a.write_text(json.dumps({"dynamic_ids": [VALID_ID]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_a.as_posix()}")
    monkeypatch.setattr("src.sources.ds10_api.CONFIG_FILE", tmp_path / "api_sources.txt")

    r1 = check_update()
    assert r1.updated is True
    commit_source_checkpoint(r1)

    # 移除 a，换成 b → b 是首次（updated=True），且 a 的 key 必须被清理
    src_b = tmp_path / "b.json"
    src_b.write_text(json.dumps({"dynamic_ids": [VALID_ID2]}), encoding="utf-8")
    _write_ds10_conf(tmp_path, f"file://{src_b.as_posix()}")
    r2 = check_update()
    assert r2.updated is True
    new_map = json.loads(r2.cv_id)
    assert _source_key(f"file://{src_b.as_posix()}") in new_map
    assert _source_key(f"file://{src_a.as_posix()}") not in new_map
