from __future__ import annotations

from src.pipeline.classify_fetch_context import ClassifyFetchContext


def test_is_deleted_link_reuses_detail_probe(monkeypatch) -> None:
    calls = {"n": 0}

    class _Client:
        pass

    def fake_probe(client, dynamic_id, *, retries=2):
        calls["n"] += 1
        return None, 0, "0"

    monkeypatch.setattr(
        "src.pipeline.classify_fetch_context.probe_dynamic_detail_api",
        fake_probe,
    )

    ctx = ClassifyFetchContext(_Client(), "123")
    assert ctx.is_deleted_link() is True
    assert ctx.get_additional() is None
    assert calls["n"] == 1
