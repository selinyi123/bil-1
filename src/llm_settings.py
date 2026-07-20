from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.llm_config import LlmConfig, _parse_env_file

from urllib.parse import urlparse

DEFAULT_LLM_BASE_URL = "https://www.autodl.art/api/v1"
DEFAULT_LLM_MODEL_NAME = "DeepSeek-V4-Flash"

_MODEL_NAME_MAX_LEN = 200


def _llm_env_path() -> Path:
    from src import app_paths

    return app_paths.llm_env_file()


def _read_values() -> dict[str, str]:
    return _parse_env_file(_llm_env_path())


def _config_fingerprint(api_key: str, base_url: str, model_name: str) -> str:
    payload = f"{api_key}|{base_url}|{model_name}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _write_values(values: dict[str, str]) -> None:
    path = _llm_env_path()
    lines = [
        f"LLM_API_KEY={values.get('LLM_API_KEY', '')}",
        f"LLM_BASE_URL={values.get('LLM_BASE_URL', '')}",
        f"LLM_MODEL_NAME={values.get('LLM_MODEL_NAME', '')}",
        f"LLM_TEST_PASSED={values.get('LLM_TEST_PASSED', 'false')}",
        f"LLM_TEST_FINGERPRINT={values.get('LLM_TEST_FINGERPRINT', '')}",
        "",
    ]
    from src.secure_files import write_text_secret

    write_text_secret(path, "\n".join(lines))


def mask_api_key(api_key: str) -> str:
    cleaned = (api_key or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:4]}****{cleaned[-4:]}"


def load_llm_values() -> dict[str, str]:
    return _read_values()


def is_llm_configured() -> bool:
    values = _read_values()
    return bool(
        values.get("LLM_API_KEY", "").strip()
        and values.get("LLM_MODEL_NAME", "").strip()
    )


def is_llm_tested() -> bool:
    values = _read_values()
    if values.get("LLM_TEST_PASSED", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    fingerprint = _config_fingerprint(
        values.get("LLM_API_KEY", "").strip(),
        values.get("LLM_BASE_URL", "").strip(),
        values.get("LLM_MODEL_NAME", "").strip(),
    )
    return values.get("LLM_TEST_FINGERPRINT", "").strip() == fingerprint


def is_llm_ready() -> bool:
    return is_llm_configured() and is_llm_tested()


def _resolve_base_url(raw: str) -> str:
    cleaned = (raw or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_LLM_BASE_URL
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("LLM 接口地址仅支持 http 或 https")
    if not parsed.netloc:
        raise ValueError("LLM 接口地址格式无效")
    return cleaned


def get_llm_config() -> LlmConfig | None:
    values = _read_values()
    api_key = values.get("LLM_API_KEY", "").strip()
    model_name = values.get("LLM_MODEL_NAME", "").strip()
    if not api_key or not model_name:
        return None
    try:
        base_url = _resolve_base_url(values.get("LLM_BASE_URL", ""))
    except ValueError:
        return None
    return LlmConfig(api_key=api_key, base_url=base_url, model_name=model_name)


def get_llm_settings_public() -> dict[str, str | bool]:
    values = _read_values()
    api_key = values.get("LLM_API_KEY", "").strip()
    base_url = values.get("LLM_BASE_URL", "").strip()
    model_name = values.get("LLM_MODEL_NAME", "").strip()
    configured = bool(api_key and model_name)
    return {
        "configured": configured,
        "test_passed": is_llm_tested(),
        "ready": configured and is_llm_tested(),
        "base_url": base_url,
        "model_name": model_name,
        "api_key_hint": mask_api_key(api_key) if api_key else "",
    }


def build_llm_config_from_inputs(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
) -> LlmConfig:
    current = _read_values()
    next_key = (api_key or "").strip() or current.get("LLM_API_KEY", "").strip()
    if base_url is not None:
        next_base_raw = (base_url or "").strip().rstrip("/")
        if next_base_raw:
            next_base = _resolve_base_url(next_base_raw)
        else:
            next_base = current.get("LLM_BASE_URL", "").strip().rstrip("/")
    else:
        next_base = current.get("LLM_BASE_URL", "").strip().rstrip("/")
    next_model = (model_name or "").strip() or current.get("LLM_MODEL_NAME", "").strip()
    if not next_key:
        raise ValueError("请填写 API Key")
    if not next_model:
        raise ValueError("请填写模型名称")
    return LlmConfig(
        api_key=next_key,
        base_url=_resolve_base_url(next_base),
        model_name=next_model,
    )


@dataclass(frozen=True)
class LlmSettingsUpdate:
    api_key: str | None
    base_url: str
    model_name: str


def save_llm_settings(
    *,
    api_key: str | None,
    base_url: str,
    model_name: str,
) -> dict[str, str | bool]:
    current = _read_values()
    next_key = (api_key or "").strip()
    if not next_key:
        next_key = current.get("LLM_API_KEY", "").strip()
    next_base_raw = (base_url or "").strip().rstrip("/")
    if next_base_raw:
        next_base = _resolve_base_url(next_base_raw)
    else:
        next_base = current.get("LLM_BASE_URL", "").strip().rstrip("/")
    next_model = (model_name or "").strip()
    if not next_key:
        raise ValueError("请填写 LLM API Key")
    if not next_model:
        raise ValueError("请填写模型名称")
    if len(next_model) > _MODEL_NAME_MAX_LEN:
        raise ValueError(f"模型名称过长（最多 {_MODEL_NAME_MAX_LEN} 字符）")

    _write_values(
        {
            "LLM_API_KEY": next_key,
            "LLM_BASE_URL": next_base,
            "LLM_MODEL_NAME": next_model,
            "LLM_TEST_PASSED": "false",
            "LLM_TEST_FINGERPRINT": "",
        }
    )
    return get_llm_settings_public()


def mark_llm_test_passed(*, api_key: str, base_url: str, model_name: str) -> dict[str, str | bool]:
    values = _read_values()
    next_key = (api_key or "").strip()
    next_base_raw = (base_url or "").strip().rstrip("/")
    if next_base_raw:
        next_base = _resolve_base_url(next_base_raw)
    else:
        next_base = values.get("LLM_BASE_URL", "").strip().rstrip("/")
    next_model = (model_name or "").strip()
    if not next_key or not next_model:
        raise ValueError("请先保存完整的 LLM 配置")
    saved_key = values.get("LLM_API_KEY", "").strip()
    saved_base = values.get("LLM_BASE_URL", "").strip()
    saved_model = values.get("LLM_MODEL_NAME", "").strip()
    if next_key != saved_key or next_base != saved_base or next_model != saved_model:
        raise ValueError("请先保存配置，再执行连接测试")

    fingerprint = _config_fingerprint(next_key, next_base, next_model)
    values.update(
        {
            "LLM_API_KEY": next_key,
            "LLM_BASE_URL": next_base,
            "LLM_MODEL_NAME": next_model,
            "LLM_TEST_PASSED": "true",
            "LLM_TEST_FINGERPRINT": fingerprint,
        }
    )
    _write_values(values)
    return get_llm_settings_public()
