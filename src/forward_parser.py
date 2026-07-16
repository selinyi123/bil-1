from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from src.bilibili_client import BilibiliClient
from src.forward_classify_cache import get_cached_classify, put_cached_classify
from src.forward_parse_cache import get_cached_parse, put_cached_parse
from src.llm_client import chat_json
from src.sources.common import opus_link

PARSER_VERSION = 6
CLASSIFY_PARSER_VERSION = 3
# 仅用于从 HTML 抓取正文，不参与奖品/时间/条件/人数四类字段解析
INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", re.S)
MIN_CONTENT_LEN = 12
CLASSIFY_MIN_CONTENT_LEN = 1
DYNAMIC_TYPE_FORWARD = "DYNAMIC_TYPE_FORWARD"
CN_TZ = timezone(timedelta(hours=8))
HTML_FETCH_ATTEMPTS = 2
HTML_FETCH_BACKOFF_SEC = (1.5, 3.0)
CLASSIFY_CONTENT_ATTEMPTS = 4
CLASSIFY_CONTENT_BACKOFF_SEC = (1.0, 2.5, 5.0, 8.0)


class DynamicContentFetchError(RuntimeError):
    """动态正文抓取失败（网络/限流等可重试）。"""

    def __init__(self, message: str, *, dynamic_id: str = "", retryable: bool = True) -> None:
        super().__init__(message)
        self.dynamic_id = dynamic_id
        self.retryable = retryable

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
- 摘录或概括正文中写明的**抽奖赠品/回馈物品**；多个奖品用简短中文连接（如「、」「+」）。
- 以下情形视为正文已写明奖品（须忠实于正文措辞概括，禁止臆造品牌、型号或数量）：
  - **显性标注**：`奖品` `福利` `好礼` `壕礼` `赠送` `回馈` `奖品内容` 等词后的具体物品。
  - **动宾结构**：`送/抽/揪/赢/获得/赠送/roll` 等动词直接搭配的物品（如「抽 3 人送月卡」→「月卡」）。
  - **数量绑定**：`XX×N`、`N 份 XX`、`每位/每人得 XX` 中的 `XX`。
  - **宣发+抽奖一体**：正文同时出现 (1) 可辨认的具体产品/周边/卡券/实物名称，与 (2) 抽奖或赠送动作（`抽/揪/送/roll/福利` 等），且未另行指定其他赠品时，将该物品视为回馈物（如宣发「新品轴体」且「随机揪一位」→「新品轴体」）。
- 以下情形**不算**已写明奖品，必须输出 `""`：
  - 仅空泛表述：`福利` `详情见图` `奖品丰厚` `神秘大礼` 等，但正文未出现任何可辨认物品名。
  - 仅有抽奖动作（如「随机揪一位」「抽粉丝」）而正文完全未出现可辨认的物品/产品/卡券/周边名称。
  - 参与条件、话题标签、`@` 用户名、口号 slogan，均不得当作奖品。
- 正文未写明奖品 → 空字符串 `""`。

### lottery_time_text / lottery_time_unix
- lottery_time_text：保留正文中的开奖时间原文片段；无法确定 → ""。
- lottery_time_unix：根据正文与参考时间推算 Unix 秒（北京时间 UTC+8）。
  - 正文写出明确日期/时间时，**必须**输出对应的 `lottery_time_unix`，仅日期无具体时刻时按当日 00:00（北京时间）推算。
  - **开奖时间可以早于参考时间**（已开奖/已过期）：仍按正文真实日期填写 unix，**禁止**因已过去而填 null 或改写成未来时间。
  - 正文完全未提及开奖时间、或仅有「见图」等无法推算的表述 → `lottery_time_unix=null`。
- 本阶段不判断是否已结束、是否仍可参与；只忠实提取正文时间。

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

### is_lottery（准入门槛，须同时满足才可为 true）
1. **参与行动**：正文须出现下列四类 UP 要求的粉丝行动中的**至少一类**（含常见同义表述，emoji/符号不能替代缺失的语义）：
   - **点赞**：点赞、点个赞、赞一下、赞、三连（明确含点赞/赞语义时）
   - **转发**：转发、转发动态、分享、分享这条动态
   - **关注**：关注、关注@、成为粉丝
   - **收藏**：收藏、收进收藏夹、三连（明确含收藏语义时）
   - 以上四类**一个都未出现** → `is_lottery=false`（仅有评论/留言/私信/@/话题标签不算）。
2. **奖品依据**：按 `prize_description` 规则，正文能归纳出**非空**的可辨认回馈物名称。
   - 仅有空泛词（福利、好礼、新品、吃新品、幸运鹅等）而无具体物品/卡券/周边/产品名 → `is_lottery=false`。
   - 若按规则 `prize_description` 只能为 `""` → 必须 `is_lottery=false`。
3. **排除**：纯广告、日常、招聘、直播预告、带货、万粉庆祝口号、无抽奖规则的粉丝寒暄 → `is_lottery=false`。

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

### 示例 D
正文：「新品轴体，即将上市。关注@某品牌，评论+转发，plq随机揪一位粉丝」
输出：
{"is_lottery":true,"prize_description":"新品轴体","winner_count":1,"lottery_time_text":"","lottery_time_unix":null,"need_follow":true,"need_repost":true,"need_comment":true,"confidence":"medium"}

### 示例 E
正文：「关注并转发，随机揪一位幸运儿，福利见图」
输出：
{"is_lottery":false,"prize_description":"","winner_count":0,"lottery_time_text":"","lottery_time_unix":null,"need_follow":true,"need_repost":true,"need_comment":false,"confidence":"low"}

### 示例 F
正文：「正是七月，本条🤏7位幸运鹅吃新品哦~ #万粉万粉万万粉#」
输出：
{"is_lottery":false,"prize_description":"","winner_count":0,"lottery_time_text":"","lottery_time_unix":null,"need_follow":false,"need_repost":false,"need_comment":false,"confidence":"low"}

### 示例 G（已过期开奖日仍须填 unix）
正文：「关注并转发并评论即可参与；开奖日期：2026年7月8日」
参考时间：2026-07-16 12:00:00 +0800
输出：
{"is_lottery":true,"prize_description":"鼠标","winner_count":0,"lottery_time_text":"2026年7月8日","lottery_time_unix":1783440000,"need_follow":true,"need_repost":true,"need_comment":true,"confidence":"medium"}
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


def _text_from_rich_text_nodes(nodes: list[dict]) -> str:
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        parts.append(str(node.get("orig_text") or node.get("text") or ""))
    return "".join(parts)


def _extract_desc_text(module_dynamic: dict) -> str:
    desc = module_dynamic.get("desc") or {}
    if not isinstance(desc, dict):
        return ""
    text = str(desc.get("text") or "").strip()
    if text:
        return text
    rich_nodes = desc.get("rich_text_nodes") or []
    if rich_nodes:
        return _text_from_rich_text_nodes(rich_nodes).strip()
    return ""


def _extract_major_lottery_text(module_dynamic: dict) -> str:
    major = module_dynamic.get("major") or {}
    if not isinstance(major, dict):
        return ""
    lottery = major.get("lottery") or {}
    if isinstance(lottery, dict):
        for key in ("desc", "text", "title"):
            value = str(lottery.get(key) or "").strip()
            if value:
                return value
    return ""


def _extract_module_dynamic_text(module_dynamic: dict) -> str:
    chunks: list[str] = []
    desc_text = _extract_desc_text(module_dynamic)
    if desc_text:
        chunks.append(desc_text)
    for key in ("module_content", "major"):
        content = module_dynamic.get(key) or {}
        if isinstance(content, dict):
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                chunks.append(text)
    lottery_text = _extract_major_lottery_text(module_dynamic)
    if lottery_text:
        chunks.append(lottery_text)
    return "\n".join(chunks)


def _extract_from_detail_item(item: dict, *, _seen: set[int] | None = None) -> str:
    seen = _seen or set()
    item_key = id(item)
    if item_key in seen:
        return ""
    seen.add(item_key)

    chunks: list[str] = []
    modules = item.get("modules") or {}
    if isinstance(modules, dict):
        module_dynamic = modules.get("module_dynamic") or {}
        if isinstance(module_dynamic, dict):
            text = _extract_module_dynamic_text(module_dynamic)
            if text:
                chunks.append(text)
        content = modules.get("module_content") or {}
        if isinstance(content, dict):
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                chunks.append(text)

    if isinstance(modules, list):
        for mod in modules:
            if not isinstance(mod, dict):
                continue
            module_dynamic = mod.get("module_dynamic") or {}
            if isinstance(module_dynamic, dict):
                text = _extract_module_dynamic_text(module_dynamic)
                if text:
                    chunks.append(text)
            content = mod.get("module_content") or {}
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                chunks.append(text)

    orig = item.get("orig")
    if isinstance(orig, dict):
        orig_text = _extract_from_detail_item(orig, _seen=seen)
        if orig_text:
            chunks.append(orig_text)

    unique: list[str] = []
    for chunk in chunks:
        normalized = chunk.strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return "\n".join(unique)


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

    modules = detail.get("modules")
    if isinstance(modules, list):
        for mod in modules:
            if isinstance(mod, dict):
                module_dynamic = mod.get("module_dynamic") or {}
                if isinstance(module_dynamic, dict):
                    text = _extract_module_dynamic_text(module_dynamic)
                    if text:
                        return text
                content = mod.get("module_content") or {}
                text = _collect_paragraph_text(content.get("paragraphs") or [])
                if text:
                    return text

    for mod in detail.get("modules") or []:
        if isinstance(mod, dict):
            content = mod.get("module_content") or {}
            text = _collect_paragraph_text(content.get("paragraphs") or [])
            if text:
                return text
    return ""


def _merge_unique_text_parts(*chunks: str) -> str:
    parts: list[str] = []
    for chunk in chunks:
        normalized = str(chunk or "").strip()
        if normalized and normalized not in parts:
            parts.append(normalized)
    return "\n".join(parts)


def _is_sufficient_content(text: str) -> bool:
    return len(str(text or "").strip()) >= MIN_CONTENT_LEN


def _is_forward_dynamic_item(item: dict | None) -> bool:
    return (item or {}).get("type") == DYNAMIC_TYPE_FORWARD


def _fetch_html_dynamic_text(client: BilibiliClient, dynamic_id: str) -> str:
    """从 opus 页 HTML 提取正文（不读图片）。无 __INITIAL_STATE__ 时立即放弃，不访问 t.bilibili.com。"""
    url = opus_link(dynamic_id)
    last_error: Exception | None = None
    for attempt in range(HTML_FETCH_ATTEMPTS):
        try:
            html = client.get_text(url, referer="https://www.bilibili.com", retries=1)
            if not INITIAL_STATE_RE.search(html):
                return ""
            text = _extract_from_initial_state(html)
            if _is_sufficient_content(text):
                return text.strip()
        except RuntimeError as exc:
            last_error = exc
        if attempt < HTML_FETCH_ATTEMPTS - 1:
            time.sleep(HTML_FETCH_BACKOFF_SEC[attempt])
    if last_error:
        raise DynamicContentFetchError(
            f"HTML 正文抓取失败: {last_error}",
            dynamic_id=dynamic_id,
            retryable=True,
        )
    return ""


def fetch_dynamic_content(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    detail_item: dict | None = None,
    try_html: bool = True,
) -> str:
    """拉取动态纯文本正文：dynamic/detail → opus/detail → opus HTML（不含图片 OCR）。"""
    from src.lottery_api import _fetch_dynamic_api_item, _fetch_opus_detail_item

    collected: list[str] = []
    forward_api_only = False
    detail_resolved = detail_item is not None

    if detail_item is not None:
        forward_api_only = _is_forward_dynamic_item(detail_item)
        text = _extract_from_detail_item(detail_item)
        if _is_sufficient_content(text):
            return text
        # 转发帖：detail 有字即正常，不再走 HTML
        if forward_api_only and text.strip():
            return text.strip()
        if text.strip():
            collected.append(text.strip())
    else:
        dynamic_item = _fetch_dynamic_api_item(client, dynamic_id)
        if dynamic_item:
            detail_resolved = True
            forward_api_only = _is_forward_dynamic_item(dynamic_item)
            text = _extract_from_detail_item(dynamic_item)
            if _is_sufficient_content(text):
                return text
            if forward_api_only and text.strip():
                return text.strip()
            if text.strip():
                collected.append(text.strip())

        if not forward_api_only:
            opus_item = _fetch_opus_detail_item(client, dynamic_id)
            if opus_item:
                detail_resolved = True
                text = _extract_from_detail_item(opus_item)
                if _is_sufficient_content(text):
                    return text
                if text.strip():
                    collected.append(text.strip())

    merged_api = _merge_unique_text_parts(*collected)
    if _is_sufficient_content(merged_api):
        return merged_api

    html_text = ""
    if try_html:
        html_text = _fetch_html_dynamic_text(client, dynamic_id)
    merged = _merge_unique_text_parts(merged_api, html_text)
    if _is_sufficient_content(merged):
        return merged

    if merged.strip():
        return merged.strip()

    if detail_resolved:
        return ""

    raise DynamicContentFetchError(
        "各抓取路径均未获得足够长度的正文",
        dynamic_id=dynamic_id,
        retryable=True,
    )


def fetch_dynamic_content_with_retry(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    initial_detail_item: dict | None = None,
) -> str:
    """分类阶段用：网络/限流导致正文拉取失败时自动重试，不 skip。"""
    last_error: Exception | None = None
    forward_cached = _is_forward_dynamic_item(initial_detail_item)
    preview_len = 0
    if initial_detail_item is not None:
        preview_len = len(_extract_from_detail_item(initial_detail_item).strip())
    attempts = CLASSIFY_CONTENT_ATTEMPTS
    forward_empty_detail = forward_cached and initial_detail_item is not None and preview_len <= 0
    if forward_empty_detail:
        # detail 完全无字：只试 1 轮，并允许 HTML 兜底
        attempts = 1
    for attempt in range(attempts):
        try:
            return fetch_dynamic_content(
                client,
                dynamic_id,
                detail_item=initial_detail_item,
                try_html=(attempt == 0) and (not forward_cached or forward_empty_detail),
            )
        except DynamicContentFetchError as exc:
            last_error = exc
            if not exc.retryable:
                break
        except RuntimeError as exc:
            last_error = DynamicContentFetchError(
                str(exc),
                dynamic_id=dynamic_id,
                retryable=True,
            )
        if attempt < attempts - 1:
            time.sleep(CLASSIFY_CONTENT_BACKOFF_SEC[attempt])
    message = f"无法获取动态正文: {dynamic_id}"
    if last_error:
        raise RuntimeError(message) from last_error
    raise RuntimeError(message)


CLASSIFY_SYSTEM_PROMPT = """## 角色
你是 B 站动态「是否转发抽奖活动」分类器。你只判断正文是否描述 UP 自发组织、粉丝可按规则参与的抽奖/赠送活动，不提取奖品、时间、人数等详情。

## 背景
- 互动抽奖、预约抽奖、充电抽奖由上游 API 处理；你只处理 API 未识别的正文。
- 详情字段（奖品、开奖时间等）由下游另一模块解析；你不得输出这些字段。

## 任务
阅读用户消息中的「正文」，判断是否为转发抽奖活动（is_lottery）。

## 无正文
- 若正文字段为空、为「(无正文)」或无任何可判断字符，直接输出 `{"is_lottery":false,"confidence":"high"}`，无需其他推理。

## 输入格式（由用户消息提供）
- 动态 ID：仅作上下文，不得用于编造信息
- 正文：待判断的纯文本

## 输出格式
- 只输出一个 JSON 对象，无 markdown 代码块、无注释、无推理过程、无额外字段。
- 字段必须齐全，类型必须严格匹配下方 Schema。

## JSON Schema
{
  "is_lottery": boolean,
  "confidence": "high" | "medium" | "low"
}

## 字段规则
### is_lottery（准入门槛，须同时满足才可为 true）
1. **参与行动**：正文须出现下列四类粉丝行动要求中的**至少一类**（含常见同义表述；emoji/符号不能替代缺失的语义）：
   - **点赞**：点赞、点个赞、赞一下、赞、三连（明确含点赞/赞语义时）
   - **转发**：转发、转发动态、分享、分享这条动态
   - **关注**：关注、关注@、成为粉丝
   - **收藏**：收藏、收进收藏夹、三连（明确含收藏语义时）
   - 以上四类**一个都未出现** → `is_lottery=false`（仅有评论/留言/私信/@/话题标签不算）。
2. **奖品依据**：正文能归纳出**可辨认的回馈物/赠品名称**（如月卡、键盘、周边、某型号产品、某品牌卡券等）。
   - 仅有空泛词（福利、好礼、新品、吃新品、幸运鹅、详情见图、奖品丰厚等）而无具体物品名 → `is_lottery=false`。
3. **肯定情形**：
   - 同时满足 1+2，且有抽/揪/roll/送/赠/福利抽奖等组织语义 → `is_lottery=true`。
   - 含 `#互动抽奖#` 等标签且语境为粉丝福利抽奖（非单纯话题）→ 通常 `is_lottery=true`（仍须满足 1+2）。
4. **排除情形**（`is_lottery=false`）：
   - 纯广告、日常、招聘、直播预告、带货、万粉庆祝口号、无抽奖规则的粉丝寒暄。
   - 仅有抽奖动作（如「抽 7 人」）但无参与行动词、或无具体奖品名。

### confidence
- high：参与行动与奖品在正文中均清晰
- medium：有一项表述略模糊但仍有正文依据
- low：勉强判断或刚满足最低门槛

## 禁止事项
- 禁止输出 prize_description、lottery_time、winner_count、need_follow 等详情字段
- 禁止编造正文不存在的信息
- 禁止因「抽 N 人/幸运儿」等人数表述 alone 判 true

## 示例

### 示例 A
正文：「转发+关注，抽 3 人送月卡，7月20日晚8点开奖」
输出：
{"is_lottery":true,"confidence":"high"}

### 示例 B
正文：「新品轴体即将上市，评论+转发，plq随机揪一位粉丝」
输出：
{"is_lottery":true,"confidence":"medium"}

### 示例 C
正文：「本周粉丝福利，详情见图」
输出：
{"is_lottery":false,"confidence":"low"}

### 示例 D
正文：「正是七月，本条🤏7位幸运鹅吃新品哦~ #万粉万粉万万粉#」
输出：
{"is_lottery":false,"confidence":"low"}

### 示例 E
正文：「恭喜万粉！以后继续宠粉～」
输出：
{"is_lottery":false,"confidence":"low"}
"""


def _build_classify_user_prompt(*, dynamic_id: str, content_text: str) -> str:
    body = content_text.strip() or "(无正文)"
    return f"## 动态 ID\n{dynamic_id}\n\n## 正文\n{body}"


def _normalize_classify_parsed(raw: dict[str, Any]) -> dict[str, Any]:
    confidence = str(raw.get("confidence") or "medium").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    return {
        "classify_parser_version": CLASSIFY_PARSER_VERSION,
        "is_lottery": bool(raw.get("is_lottery", False)),
        "confidence": confidence,
    }


def _empty_classify_parse(*, error: str | None = None) -> dict[str, Any]:
    return {
        "classify_parser_version": CLASSIFY_PARSER_VERSION,
        "is_lottery": False,
        "confidence": "low",
        "from_cache": False,
        "error": error,
    }


def classify_forward_lottery(dynamic_id: str, content_text: str) -> dict[str, Any]:
    """分类阶段：轻量 LLM，仅判断 is_lottery。"""
    cached = get_cached_classify(dynamic_id, content_text)
    if cached and cached.get("classify_parser_version") == CLASSIFY_PARSER_VERSION:
        parsed = _normalize_classify_parsed(cached)
        parsed["from_cache"] = True
        return parsed

    raw = chat_json(
        system=CLASSIFY_SYSTEM_PROMPT,
        user=_build_classify_user_prompt(dynamic_id=dynamic_id, content_text=content_text),
    )
    parsed = _normalize_classify_parsed(raw)
    parsed["from_cache"] = False
    put_cached_classify(dynamic_id, content_text, parsed)
    return parsed


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
