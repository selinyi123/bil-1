from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLM_ENV_PATH = ROOT / "config" / "llm.env"


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model_name: str


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_llm_config() -> LlmConfig | None:
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    model_name = os.environ.get("LLM_MODEL_NAME", "").strip()
    if api_key and base_url and model_name:
        return LlmConfig(api_key=api_key, base_url=base_url.rstrip("/"), model_name=model_name)

    from src.llm_settings import get_llm_config

    return get_llm_config()
