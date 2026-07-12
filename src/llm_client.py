from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx

from src.llm_config import LlmConfig, load_llm_config

import threading

_llm_lock = threading.Semaphore(3)


def chat_json(*, system: str, user: str, config: LlmConfig | None = None) -> dict[str, Any]:
    cfg = config or load_llm_config()
    if not cfg:
        raise RuntimeError("未配置 LLM，请检查 config/llm.env")

    payload = {
        "model": cfg.model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{cfg.base_url}/chat/completions"

    with _llm_lock:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    return _extract_json_object(content)


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RuntimeError(f"LLM 返回无法解析为 JSON: {text[:200]}")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM 返回的 JSON 不是对象")
    return parsed
