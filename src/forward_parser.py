from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from src.bilibili_client import BilibiliClient
from src.forward_parse_cache import get_cached_parse, put_cached_parse
from src.llm_client import chat_json
from src.lottery_api import fetch_dynamic_detail
from src.sources.common import opus_link

PARSER_VERSION = 3
# 仅用于从 HTML 抓取正文，不参与奖品/时间/条件/人数四类字段解析
INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", re.S)
MIN_CONTENT_LEN = 12
CN_TZ = timezone(timedelta(hours=8))

PARSE_SYSTEM_PROMPT = """## 角色
你是 B 站「转发抽奖」动态结构化信息提取器。你只从 UP 自发组织的转发类抽奖正文中抽取字段，不做评论、不做建议。

## 背景
- 转发抽奖没有官方结构化接口，正文是唯一依据。
- 中奖名单、是否已参加由下游其他模块处理；你不得推断或输出这两类信息。

## 任务
阅读用户消息中的「正文」，完成：
1. 判断是否为转发抽奖活动（is_lottery）
2. 若 is_lottery=true，仅提取以下四类信息：
   - 奖品内容 → prize_description
   - 开奖时间 → lottery_time_text + lottery_time_unix
   - 参与条件 → need_follow / need_repost / need_comment
   - 抽取人数（中奖名额总数）→ winner_count

## 输入格式（由用户消息提供）
- 参考时间：Unix 秒级时间戳 + 北京时间，用于推算相对日期（如「今晚」「本周五」）
- 动态 ID：仅作上下文，不得用于编造信息
- 正文：待解析的纯文本

## 输出格式
- 只输出一个 JSON 对象，无 markdown 代码块、无注释、无推理过程、无额外字段。
- 字段必须齐全，类型必须严格匹配下方 Schema。

## JSON Schema
{
  "is_lottery": boolean,
  "prize_description": string,
  "winner_count": integer,
  "lottery_time_text": string,
  "lottery_time_unix": integer | null,
  "need_follow": boolean,
  "need_repost": boolean,
  "need_comment": boolean,
  "confidence": "high" | "medium" | "low"
}

## 字段规则
### prize_description
- 摘录或概括正文中写明的奖品；多个奖品用简短中文连接。
- 正文未写明奖品 → 空字符串 ""。

### lottery_time_text / lottery_time_unix
- lottery_time_text：保留正文中的开奖时间原文片段；无法确定 → ""。
- lottery_time_unix：根据正文与参考时间推算 Unix 秒（北京时间 UTC+8）；无法确定 → null。
- 禁止输出过去已开奖活动的「假未来时间」；若正文暗示已开奖/已结束，is_lottery 可仍为 true，但 lottery_time_unix 按正文语义填写。

### need_follow / need_repost / need_comment
- 正文明确要求某条件 → true；未提及 → false。
- 「转发/转发动态/分享」→ need_repost=true；「关注」→ need_follow=true；「评论/留言」→ need_comment=true。

### winner_count
- 正文中奖人数/名额的整数总和（如「抽 3 人」「键盘×2」→ 2 或 3，按正文语义）。
- 未说明 → 0；禁止猜测默认值。

### confidence
- high：四类信息均可从正文明确读出
- medium：部分字段模糊但仍有正文依据
- low：仅能弱判断为抽奖，或多数字段缺失

### is_lottery=false 时
- prize_description=""，winner_count=0，lottery_time_text=""，lottery_time_unix=null
- need_follow/need_repost/need_comment 均为 false，confidence="low"

## 禁止事项
- 禁止编造正文不存在的奖品、时间、规则或人数
- 禁止输出 winners、participated、activity_status、中奖名单、中奖用户、是否已参加等字段
- 禁止输出 Schema 之外的键

## 示例

### 示例 A
正文：「转发+关注@某UP 奖品：机械键盘×2 7月20日晚8点开奖」
参考时间：2026-07-12 12:00:00 +0800
输出：
{"is_lottery":true,"prize_description":"机械键盘×2","winner_count":2,"lottery_time_text":"7月20日晚8点","lottery_time_unix":1784548800,"need_follow":true,"need_repost":true,"need_comment":false,"confidence":"high"}

### 示例 B
正文：「关注并转发，抽 5 位送月卡，开奖时间见图」
输出：
{"is_lottery":true,"prize_description":"月卡","winner_count":5,"lottery_time_text":"","lottery_time_unix":null,"need_follow":true,"need_repost":true,"need_comment":false,"confidence":"medium"}

### 示例 C
正文：「本周粉丝福利，详情见图」
输出：
{"is_lottery":false,"prize_description":"","winner_count":0,"lottery_time_text":"","lottery_time_unix":null,"need_follow":false,"need_repost":false,"need_comment":false,"confidence":"low"}
"""


def _build_user_prompt(*, dynamic_id: str, content_text: str, reference_ts: int) -> str:
    ref_dt = datetime.fromtimestamp(reference_ts, tz=CN_TZ)
    return (
        f"## 参考时间\n"
        f"- Unix 时间戳（秒）: {reference_ts}\n"
        f"- 北京时间: {ref_dt.strftime('%Y-%m-%d %H:%M:%S %z')}\n\n"
        f"## 动态 ID\n{dynamic_id}\n\n"
        f"## 正文\n{content_text}"
    )


def _text_from_nodes(nodes: list[dict]) -> str:
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type") or node.get("node_type")
        if node_type in ("TEXT_NODE_TYPE_WORD", 1):
            word = node.get("word") or {}
            if isinstance(word, dict):
                parts.append(str(word.get("words") or ""))
            continue
        rich = node.get("rich") or {}
        if rich:
            parts.append(str(rich.get("orig_text") or rich.get("text") or ""))
    return "".join(parts)


def _collect_paragraph_text(paragraphs: list[dict]) -> str:
    chunks: list[str] = []
    for para in paragraphs:
        text_obj = para.get("text") or {}
        nodes = text_obj.get("nodes") or []
        line = _text_from_nodes(nodes).strip()
        if line:
            chunks.append(line)
    return "\n".join(chunks)


def _extract_from_detail_item(item: dict) -> str:
    modules = item.get("modules") or {}
    if isinstance(modules, dict):
        module_dynamic = modules.get("module_dynamic") or {}
        for key in ("module_content", "major"):
            content = module_dynamic.get(key) or {}
            if isinstance(content, dict):
                text = _collect_paragraph_text(content.get("paragraphs") or [])
                if text:
                    return text

    if isinstance(modules, list):
        for mod in modules:
            if not isinstance(mod, dict):
                continue
            content = mod.get("module_content") or {}
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                return text
    return ""


def _extract_from_initial_state(html: str) -> str:
    match = INITIAL_STATE_RE.search(html)
    if not match:
        return ""
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""

    detail = state.get("detail") or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}

    text = _extract_from_detail_item(detail)
    if text:
        return text

    for mod in detail.get("modules") or []:
        if isinstance(mod, dict):
            content = mod.get("module_content") or {}
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                return text
    return ""


def fetch_dynamic_content(client: BilibiliClient, dynamic_id: str) -> str:
    item = fetch_dynamic_detail(client, dynamic_id)
    if item:
        text = _extract_from_detail_item(item)
        if text:
            return text

    try:
        html = client.get_text(opus_link(dynamic_id), referer="https://www.bilibili.com", retries=1)
    except RuntimeError:
        return ""
    return _extract_from_initial_state(html)


def _coerce_lottery_time_unix(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return ts


def _normalize_parsed(raw: dict[str, Any]) -> dict[str, Any]:
    confidence = str(raw.get("confidence") or "medium").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    winner_count = raw.get("winner_count")
    try:
        winner_count = max(0, int(winner_count))
    except (TypeError, ValueError):
        winner_count = 0

    return {
        "parser_version": PARSER_VERSION,
        "is_lottery": bool(raw.get("is_lottery", False)),
        "prize_description": str(raw.get("prize_description") or "").strip(),
        "winner_count": winner_count,
        "lottery_time_text": str(raw.get("lottery_time_text") or "").strip(),
        "lottery_time_unix": _coerce_lottery_time_unix(raw.get("lottery_time_unix")),
        "need_follow": bool(raw.get("need_follow")),
        "need_repost": bool(raw.get("need_repost")),
        "need_comment": bool(raw.get("need_comment")),
        "confidence": confidence,
    }


def _empty_parse(*, error: str | None = None) -> dict[str, Any]:
    return {
        "parser_version": PARSER_VERSION,
        "is_lottery": False,
        "prize_description": "",
        "winner_count": 0,
        "lottery_time_text": "",
        "lottery_time_unix": None,
        "need_follow": False,
        "need_repost": False,
        "need_comment": False,
        "confidence": "low",
        "from_cache": False,
        "error": error,
    }


def parse_forward_content(dynamic_id: str, content_text: str) -> dict[str, Any]:
    cached = get_cached_parse(dynamic_id, content_text)
    if cached and cached.get("parser_version") == PARSER_VERSION:
        base = {
            key: value
            for key, value in cached.items()
            if key not in ("from_cache", "error")
        }
        parsed = _normalize_parsed(base)
        parsed["from_cache"] = True
        return parsed

    if len(content_text.strip()) < MIN_CONTENT_LEN:
        return _empty_parse(error="正文过短")

    reference_ts = int(time.time())
    raw = chat_json(
        system=PARSE_SYSTEM_PROMPT,
        user=_build_user_prompt(
            dynamic_id=dynamic_id,
            content_text=content_text,
            reference_ts=reference_ts,
        ),
    )
    parsed = _normalize_parsed(raw)
    parsed["from_cache"] = False
    put_cached_parse(dynamic_id, content_text, parsed)
    return parsed
