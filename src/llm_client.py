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
# 连接测试只需极短回复，但 DeepSeek V4 等模型在部分网关下 max_tokens=1 会触发 400。
_LLM_TEST_MAX_TOKENS = 64


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
    # 注：chat_json 对 JSON 解析不再重试（_extract_json_object 单次执行），此分支
    # 仍服务于 _post_chat_completion 中 resp.json() 的解析失败，保留无副作用。
    if isinstance(exc, (json.JSONDecodeError, RuntimeError)):
        message = str(exc)
        if "无法解析为 JSON" in message or "不是对象" in message:
            return True
    return is_transient_http_error(exc)


def _supports_thinking_toggle(config: LlmConfig) -> bool:
    base = (config.base_url or "").lower()
    model = (config.model_name or "").lower()
    return "deepseek" in base or "deepseek" in model


def _build_chat_payload(
    config: LlmConfig,
    *,
    messages: list[dict[str, str]],
    temperature: float = 0,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    # DeepSeek V4 系列默认开启 thinking，结构化抽取不需要链式推理。
    if _supports_thinking_toggle(config):
        payload["thinking"] = {"type": "disabled"}
    return payload


def _post_chat_completion(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    def _call() -> dict[str, Any]:
        with httpx.Client(timeout=_LLM_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    return retry_call(_call, attempts=_LLM_RETRY_ATTEMPTS, retry_on=_llm_retryable)


def test_llm_connection(config: LlmConfig) -> str:
    payload = _build_chat_payload(
        config,
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        temperature=0,
        max_tokens=_LLM_TEST_MAX_TOKENS,
    )
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{config.base_url}/chat/completions"
    try:
        data = _post_chat_completion(url=url, headers=headers, payload=payload)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(_format_llm_http_error(exc)) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"无法连接接口地址：{exc}") from exc
    _extract_llm_content(data)
    return f"{config.model_name} @ {config.base_url}"


def chat_json(*, system: str, user: str, config: LlmConfig | None = None) -> dict[str, Any]:
    cfg = config or load_llm_config()
    if not cfg:
        raise RuntimeError("未配置 LLM，请检查 config/llm.env")

    payload = _build_chat_payload(
        cfg,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
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

    content = _extract_llm_content(data)
    return _extract_json_object(content)


def _extract_llm_content(data: dict[str, Any]) -> str:
    """校验 OpenAI-compatible 响应结构并提取 choices[0].message.content。

    结构不合法（缺 choices/message/content，或 content 非字符串/为空）时抛
    RuntimeError，避免把空内容或非字符串内容送去 JSON 解析。
    """
    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM 响应格式不兼容：缺少 choices[0].message.content")
    return content.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # 逐个扫描「{」并尝试解析完整 JSON 对象，取第一个。相比 re.search(r"\{.*\}", text, re.S)
    # 的贪婪匹配，响应含多个 JSON 对象时只取第一个完整对象，不会吞掉整段导致解析失败。
    decoder = json.JSONDecoder()
    search_from = 0
    while True:
        start = text.find("{", search_from)
        if start == -1:
            break
        try:
            parsed, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            search_from = start + 1
            continue
        if isinstance(parsed, dict):
            return parsed
        search_from = start + 1
    raise RuntimeError(f"LLM 返回无法解析为 JSON: {text[:200]}")
