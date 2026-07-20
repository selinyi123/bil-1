from __future__ import annotations

from src.config_health import reset_config_health_log_flag_for_tests, run_config_health_checks


def test_health_env_cookie_warning(monkeypatch, isolated_home) -> None:
    reset_config_health_log_flag_for_tests()
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=x; bili_jct=y")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: isolated_home / "config" / "cookies.txt")
    monkeypatch.setattr("src.app_paths.llm_env_file", lambda: isolated_home / "config" / "llm.env")
    report = run_config_health_checks()
    codes = {item.code for item in report.findings}
    assert "env_cookie_override" in codes
    assert "env_llm_override" not in codes
    assert report.bind_host == "127.0.0.1"
    assert report.data_dir
    assert report.runtime


def test_health_cookie_missing_fields(monkeypatch, isolated_home) -> None:
    reset_config_health_log_flag_for_tests()
    monkeypatch.delenv("BILI_COOKIE", raising=False)
    cookie = isolated_home / "config" / "cookies.txt"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_text("foo=bar", encoding="utf-8")
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: cookie)
    monkeypatch.setattr("src.app_paths.llm_env_file", lambda: isolated_home / "config" / "llm.env")
    report = run_config_health_checks()
    assert any(item.code == "cookie_missing_fields" for item in report.findings)


def test_health_llm_env_override_only_when_complete(monkeypatch, isolated_home) -> None:
    reset_config_health_log_flag_for_tests()
    monkeypatch.delenv("BILI_COOKIE", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    monkeypatch.setattr("src.app_paths.cookie_file", lambda: isolated_home / "config" / "cookies.txt")
    monkeypatch.setattr("src.app_paths.llm_env_file", lambda: isolated_home / "config" / "llm.env")
    report = run_config_health_checks()
    assert "env_llm_override" not in {item.code for item in report.findings}

    monkeypatch.setenv("LLM_BASE_URL", "https://example.com")
    monkeypatch.setenv("LLM_MODEL_NAME", "m")
    report2 = run_config_health_checks()
    assert "env_llm_override" in {item.code for item in report2.findings}
