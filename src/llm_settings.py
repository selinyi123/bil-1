from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.llm_config import LLM_ENV_PATH, LlmConfig, _parse_env_file
from src.user_data import get_active_uid, user_dir

DEFAULT_LLM_BASE_URL = "https://www.autodl.art/api/v1"
DEFAULT_LLM_MODEL_NAME = "DeepSeek-V4-Flash"


def _llm_env_path() -> Path:
    uid = get_active_uid()
    if uid:
        return user_dir(uid) / "llm.env"
    return LLM_ENV_PATH


def _read_values() -> dict[str, str]:
    values = _parse_env_file(_llm_env_path())
    if values:
        return values
    if _llm_env_path() != LLM_ENV_PATH:
        return _parse_env_file(LLM_ENV_PATH)
    return {}


def mask_api_key(api_key: str) -> str:
    cleaned = (api_key or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "****"
    return f"****{cleaned[-4:]}"


def load_llm_values() -> dict[str, str]:
    return _read_values()


def is_llm_configured() -> bool:
    values = _read_values()
    return bool(
        values.get("LLM_API_KEY", "").strip()
        and values.get("LLM_BASE_URL", "").strip()
        and values.get("LLM_MODEL_NAME", "").strip()
    )


def get_llm_config() -> LlmConfig | None:
    values = _read_values()
    api_key = values.get("LLM_API_KEY", "").strip()
    base_url = values.get("LLM_BASE_URL", "").strip().rstrip("/")
    model_name = values.get("LLM_MODEL_NAME", "").strip()
    if not api_key or not base_url or not model_name:
        return None
    return LlmConfig(api_key=api_key, base_url=base_url, model_name=model_name)


def get_llm_settings_public() -> dict[str, str | bool]:
    values = _read_values()
    api_key = values.get("LLM_API_KEY", "").strip()
    base_url = values.get("LLM_BASE_URL", "").strip() or DEFAULT_LLM_BASE_URL
    model_name = values.get("LLM_MODEL_NAME", "").strip() or DEFAULT_LLM_MODEL_NAME
    configured = bool(api_key and base_url and model_name)
    return {
        "configured": configured,
        "base_url": base_url,
        "model_name": model_name,
        "api_key_hint": mask_api_key(api_key) if configured else "",
    }


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
    next_base = (base_url or "").strip() or DEFAULT_LLM_BASE_URL
    next_model = (model_name or "").strip() or DEFAULT_LLM_MODEL_NAME
    if not next_key:
        raise ValueError("请填写 LLM API Key")

    path = _llm_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"LLM_API_KEY={next_key}",
        f"LLM_BASE_URL={next_base.rstrip('/')}",
        f"LLM_MODEL_NAME={next_model}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return get_llm_settings_public()
