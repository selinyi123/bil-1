from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.llm_config import LlmConfig, load_llm_config
from src.retry_utils import is_transient_http_error, retry_call

import threading

_llm_lock = threading.Semaphore(3)
_LLM_TIMEOUT = 90.0
_LLM_RETRY_ATTEMPTS = 3


def _format_llm_http_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    message = ""
    try:
        body = exc.response.json()
        if isinstance(body.get("error"), dict):
            message = str(body["error"].get("message") or "").strip()
        else:
            message = str(body.get("message") or body.get("detail") or "").strip()
    except Exception:
        message = (exc.response.text or "").strip()[:200]
    if status == 401:
        return f"API Key 无效或已过期{('：' + message) if message else ''}"
    if status == 404:
        return f"接口地址或模型不存在{('：' + message) if message else ''}"
    if status in {408, 429, 500, 502, 503, 504}:
        return f"LLM 服务暂时不可用（HTTP {status}）{('：' + message) if message else ''}"
    return f"连接失败（HTTP {status}）{('：' + message) if message else ''}"


def _llm_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (json.JSONDecodeError, RuntimeError)):
        message = str(exc)
        if "无法解析为 JSON" in message or "不是对象" in message:
            return True
    return is_transient_http_error(exc)


def _post_chat_completion(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    def _call() -> dict[str, Any]:
        with httpx.Client(timeout=_LLM_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    return retry_call(_call, attempts=_LLM_RETRY_ATTEMPTS, retry_on=_llm_retryable)


def test_llm_connection(config: LlmConfig) -> str:
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{config.base_url}/chat/completions"
    try:
        _post_chat_completion(url=url, headers=headers, payload=payload)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(_format_llm_http_error(exc)) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"无法连接接口地址：{exc}") from exc
    return f"{config.model_name} @ {config.base_url}"


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
        try:
            data = _post_chat_completion(url=url, headers=headers, payload=payload)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(_format_llm_http_error(exc)) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"无法连接 LLM 接口：{exc}") from exc

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()

    def _parse() -> dict[str, Any]:
        return _extract_json_object(content)

    return retry_call(_parse, attempts=2, base_delay=0.5, multiplier=1.5)


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
