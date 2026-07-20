"""配置校验纯函数（B2）：LLM 文件模型 + Cookie 关键字段。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

_SESSDATA_RE = re.compile(r"(?:^|;\s*)SESSDATA=([^;]+)", re.IGNORECASE)
_BILI_JCT_RE = re.compile(r"(?:^|;\s*)bili_jct=([^;]+)", re.IGNORECASE)
_DEDE_UID_RE = re.compile(r"(?:^|;\s*)DedeUserID=([^;]+)", re.IGNORECASE)


class LlmEnvFileModel(BaseModel):
    """llm.env 解析后的宽松模型；未知键忽略。"""

    model_config = ConfigDict(extra="ignore")

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL_NAME: str = ""
    LLM_TEST_PASSED: str = "false"
    LLM_TEST_FINGERPRINT: str = ""


def cookie_field_value(cookie_str: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(cookie_str or "")
    if not match:
        return None
    value = (match.group(1) or "").strip()
    return value or None


def validate_cookie_string(cookie_str: str) -> str:
    """返回 strip 后内容；缺关键字段抛 ValueError。"""
    content = (cookie_str or "").strip()
    if not content:
        raise ValueError("Cookie 内容为空，无法保存")
    if not cookie_field_value(content, _SESSDATA_RE):
        raise ValueError("Cookie 缺少有效 SESSDATA，请重新扫码登录")
    if not cookie_field_value(content, _BILI_JCT_RE):
        raise ValueError("Cookie 缺少有效 bili_jct，请重新扫码登录")
    return content


def cookie_missing_hard_fields(cookie_str: str) -> list[str]:
    """自检用：返回缺失的硬性字段名。"""
    content = (cookie_str or "").strip()
    missing: list[str] = []
    if not content:
        return ["SESSDATA", "bili_jct"]
    if not cookie_field_value(content, _SESSDATA_RE):
        missing.append("SESSDATA")
    if not cookie_field_value(content, _BILI_JCT_RE):
        missing.append("bili_jct")
    return missing


def cookie_has_dede_user_id(cookie_str: str) -> bool:
    return cookie_field_value(cookie_str or "", _DEDE_UID_RE) is not None


def validate_llm_env_dict(raw: dict[str, Any]) -> LlmEnvFileModel:
    return LlmEnvFileModel.model_validate(raw or {})
