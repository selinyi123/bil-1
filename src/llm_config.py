from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.app_logging import get_logger
from src.app_paths import LLM_ENV_PATH
from src.config_validate import validate_llm_env_dict

logger = get_logger("llm_config")


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model_name: str


def _parse_env_file_raw(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("读取 llm.env 失败：%s", exc)
        return {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_env_file(path: Path) -> dict[str, str]:
    raw = _parse_env_file_raw(path)
    if not raw:
        return {}
    try:
        model = validate_llm_env_dict(raw)
    except Exception as exc:
        logger.warning("llm.env 校验失败，忽略文件内容：%s", exc)
        return {}
    return {
        "LLM_API_KEY": model.LLM_API_KEY,
        "LLM_BASE_URL": model.LLM_BASE_URL,
        "LLM_MODEL_NAME": model.LLM_MODEL_NAME,
        "LLM_TEST_PASSED": model.LLM_TEST_PASSED,
        "LLM_TEST_FINGERPRINT": model.LLM_TEST_FINGERPRINT,
    }


def load_llm_config() -> LlmConfig | None:
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    model_name = os.environ.get("LLM_MODEL_NAME", "").strip()
    if api_key and base_url and model_name:
        return LlmConfig(api_key=api_key, base_url=base_url.rstrip("/"), model_name=model_name)

    from src.llm_settings import get_llm_config

    return get_llm_config()
