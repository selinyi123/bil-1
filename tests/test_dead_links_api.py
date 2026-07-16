from __future__ import annotations

from src.dead_links import is_dynamic_deleted, is_dynamic_detail_permanently_gone


def test_permanently_gone_when_code_zero_without_item() -> None:
    assert is_dynamic_detail_permanently_gone(item=None, code=0, message="0") is True


def test_not_gone_when_item_present() -> None:
    assert is_dynamic_detail_permanently_gone(item={"id": "1"}, code=0, message="0") is False


def test_not_gone_on_transient_failure() -> None:
    assert is_dynamic_detail_permanently_gone(item=None, code=None, message="network") is False
    assert is_dynamic_detail_permanently_gone(item=None, code=-352, message="风控") is False


def test_permanently_gone_on_not_found_message() -> None:
    assert is_dynamic_detail_permanently_gone(item=None, code=-1, message="稿件不存在") is True


def test_is_dynamic_deleted_uses_detail_api(monkeypatch) -> None:
    class _Client:
        pass

    calls = {"n": 0}

    def fake_probe(client, dynamic_id, *, retries=0):
        calls["n"] += 1
        return None, 0, "0"

    monkeypatch.setattr("src.lottery_api.probe_dynamic_detail_api", fake_probe)
    assert is_dynamic_deleted(_Client(), "123") is True
    assert calls["n"] == 1


def test_is_dynamic_deleted_false_when_item_exists(monkeypatch) -> None:
    class _Client:
        pass

    monkeypatch.setattr(
        "src.lottery_api.probe_dynamic_detail_api",
        lambda *args, **kwargs: ({"modules": {}}, 0, "0"),
    )
    assert is_dynamic_deleted(_Client(), "123") is False
