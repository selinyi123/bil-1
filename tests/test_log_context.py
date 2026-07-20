from __future__ import annotations

from src.log_context import bind_job, get_context_fields, job_log_context, reset_job


def test_bind_and_reset() -> None:
    assert get_context_fields() == {}
    tokens = bind_job(job_id=42, action="refresh_status", job_source="ui")
    try:
        assert get_context_fields() == {
            "job_id": 42,
            "action": "refresh_status",
            "job_source": "ui",
        }
    finally:
        reset_job(tokens)
    assert get_context_fields() == {}


def test_job_log_context_manager() -> None:
    with job_log_context(job_id=7, action="refresh_all", job_source="auto"):
        fields = get_context_fields()
        assert fields["job_id"] == 7
        assert fields["job_source"] == "auto"
    assert get_context_fields() == {}
