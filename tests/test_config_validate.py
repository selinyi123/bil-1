from __future__ import annotations

import pytest

from src.config_validate import validate_cookie_string, validate_llm_env_dict
from src.llm_settings import save_llm_settings


def test_validate_cookie_requires_fields() -> None:
    with pytest.raises(ValueError, match="空"):
        validate_cookie_string("  ")
    with pytest.raises(ValueError, match="SESSDATA"):
        validate_cookie_string("bili_jct=abc")
    with pytest.raises(ValueError, match="bili_jct"):
        validate_cookie_string("SESSDATA=abc")
    assert validate_cookie_string("SESSDATA=a; bili_jct=b") == "SESSDATA=a; bili_jct=b"


def test_validate_llm_env_dict_ignores_extra() -> None:
    model = validate_llm_env_dict({"LLM_API_KEY": "k", "EXTRA": "x"})
    assert model.LLM_API_KEY == "k"


def test_save_llm_rejects_bad_url(isolated_home, monkeypatch) -> None:
    env_path = isolated_home / "config" / "llm.env"
    monkeypatch.setattr("src.app_paths.llm_env_file", lambda: env_path)
    with pytest.raises(ValueError, match="http"):
        save_llm_settings(api_key="sk-test-key-123456", base_url="ftp://bad", model_name="m")
    assert not env_path.exists()
