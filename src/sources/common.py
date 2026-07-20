from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

EXCLUDE_CONTEXT_RE = re.compile(r"上期传送门|本期完|\(本期完\)")
OPUS_ID_RE = re.compile(r"/opus/(\d{18,19})")
T_BILI_RE = re.compile(r"t\.bilibili\.com/(\d{19})")
T_BILI_URL_RE = re.compile(r"https://t\.bilibili\.com/\d{19}")
VALID_OPUS_ID_RE = re.compile(r"^\d{18,19}$")
ZHIDING_SECTION_RE = re.compile(r"【置顶抽奖")
SECTION_HEADING_RE = re.compile(
    r"^(?:#+\s*)?(?:【)?(充电抽奖|预约抽奖|互动抽奖|官方抽奖|非方?官方抽奖|转发抽奖)(?:】)?"
)

LotteryHint = Literal["转发抽奖", "预约抽奖", "互动抽奖", "充电抽奖"]
SECTION_TO_HINT: dict[str, LotteryHint] = {
    "转发抽奖": "转发抽奖",
    "预约抽奖": "预约抽奖",
    "互动抽奖": "互动抽奖",
    "官方抽奖": "互动抽奖",
    "非官方抽奖": "转发抽奖",
    "非方官方抽奖": "转发抽奖",
    "充电抽奖": "充电抽奖",
}


@dataclass
class CheckResult:
    source_id: str
    updated: bool
    container_url: str
    container_id: str
    title: str
    published_at: int
    previous_container_url: str | None
    activity_links: list[str]
    checked_at: int
    link_hints: dict[str, LotteryHint] = field(default_factory=dict)
    cv_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def commit_source_checkpoint(result: CheckResult) -> None:
    """流水线/检查成功后再写入专栏检查点；检查阶段不得提前调用。"""
    if not result.updated:
        return
    from src.state_store import set_last_container

    set_last_container(
        result.source_id,
        result.container_url,
        container_id=result.container_id or None,
        title=result.title or None,
        cv_id=result.cv_id,
    )


def opus_link(opus_id: str) -> str:
    return f"https://www.bilibili.com/opus/{opus_id}"


def normalize_activity_id(url: str) -> str | None:
    """从活动链接提取动态 ID，用于跨数据源去重。"""
    for pattern in (OPUS_ID_RE, T_BILI_RE):
        match = pattern.search(url)
        if match and VALID_OPUS_ID_RE.fullmatch(match.group(1)):
            return match.group(1)
    return None


def normalize_activity_url(url: str) -> str | None:
    activity_id = normalize_activity_id(url)
    if activity_id:
        return opus_link(activity_id)
    return None


def is_valid_dynamic_id(dynamic_id: str) -> bool:
    """校验 B 站动态 ID 格式（18–19 位数字）。"""
    return bool(VALID_OPUS_ID_RE.fullmatch(str(dynamic_id or "").strip()))


def load_previous_output(path: Path) -> dict | None:
    """优先从 DB 快照读取；文件仅作导入/兼容回退。"""
    from src.db.snapshots import FILENAME_TO_SOURCE, load_ds_check_dict, load_watch_sync_dict

    name = Path(path).name
    if name in {"activities_latest.json", "enriched_latest.json"}:
        from src.activity_store import load_payload

        payload = load_payload()
        if not payload.get("activities") and not int(payload.get("updated_at") or 0):
            return None
        return payload

    source_id = FILENAME_TO_SOURCE.get(name)
    if source_id == "WATCH":
        return load_watch_sync_dict()
    if source_id:
        return load_ds_check_dict(source_id)

    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_result(path: Path, result: CheckResult) -> Path | None:
    if not result.updated:
        return None

    from src.db.snapshots import save_ds_check_dict

    save_ds_check_dict(result.to_dict())
    return path


def parse_opus_id(link_obj: dict) -> str | None:
    biz_id = str(link_obj.get("biz_id") or "")
    if biz_id and VALID_OPUS_ID_RE.fullmatch(biz_id):
        return biz_id

    url = link_obj.get("link") or ""
    for pattern in (OPUS_ID_RE, T_BILI_RE):
        match = pattern.search(url)
        if match and VALID_OPUS_ID_RE.fullmatch(match.group(1)):
            return match.group(1)
    return None


def extract_t_bilibili_links_with_hints(desc: str) -> tuple[list[str], dict[str, LotteryHint]]:
    """从视频简介等纯文本提取 t.bilibili.com 链接及分区提示。"""
    text = desc or ""
    seen: set[str] = set()
    links: list[str] = []
    hints: dict[str, LotteryHint] = {}
    current_section: LotteryHint | None = None

    for line in text.splitlines():
        current_section = _section_hint_from_text(line, current_section)
        for url in T_BILI_URL_RE.findall(line):
            activity_id = normalize_activity_id(url)
            if not activity_id or activity_id in seen:
                continue
            seen.add(activity_id)
            links.append(url)
            if current_section:
                hints[activity_id] = current_section

    for url in T_BILI_URL_RE.findall(text):
        activity_id = normalize_activity_id(url)
        if not activity_id or activity_id in seen:
            continue
        seen.add(activity_id)
        links.append(url)

    return links, hints


def _section_hint_from_text(text: str, current: LotteryHint | None) -> LotteryHint | None:
    if ZHIDING_SECTION_RE.search(text):
        return "转发抽奖"
    match = SECTION_HEADING_RE.match(text.strip())
    if match:
        return SECTION_TO_HINT.get(match.group(1), current)
    return current


def extract_opus_links_with_hints(
    article: dict,
    *,
    container_opus_id: str | None = None,
    exclude_link_text: re.Pattern | None = None,
    default_hint: LotteryHint | None = None,
) -> tuple[list[str], dict[str, LotteryHint]]:
    """从专栏/Opus 帖结构化正文提取活动链接及分区提示。"""
    opus = article.get("opus") or {}
    content = opus.get("content")
    if not content:
        raise RuntimeError("内容缺少 opus 结构化正文，无法提取活动链接")

    paragraphs = content.get("paragraphs") or []
    seen: set[str] = set()
    links: list[str] = []
    hints: dict[str, LotteryHint] = {}
    current_section: LotteryHint | None = default_hint

    for para in paragraphs:
        text_nodes = (para.get("text") or {}).get("nodes") or []
        para_text = "".join(
            (node.get("word") or {}).get("words", "")
            for node in text_nodes
            if node.get("node_type") == 1
        )
        current_section = _section_hint_from_text(para_text, current_section)
        skip_links = bool(EXCLUDE_CONTEXT_RE.search(para_text))

        for node in text_nodes:
            if node.get("node_type") != 4:
                continue

            link_obj = node.get("link") or {}
            show_text = link_obj.get("show_text") or ""
            if exclude_link_text and (
                exclude_link_text.search(show_text) or exclude_link_text.search(para_text)
            ):
                continue

            opus_id = parse_opus_id(link_obj)
            if not opus_id:
                continue
            if container_opus_id and opus_id == container_opus_id:
                continue
            if opus_id in seen or skip_links:
                continue

            seen.add(opus_id)
            links.append(opus_link(opus_id))
            if current_section:
                hints[opus_id] = current_section

    return links, hints


def extract_opus_links_from_article(
    article: dict,
    *,
    container_opus_id: str | None = None,
    exclude_link_text: re.Pattern | None = None,
    default_hint: LotteryHint | None = None,
) -> list[str]:
    """从专栏/Opus 帖结构化正文提取去重后的活动链接。"""
    links, _ = extract_opus_links_with_hints(
        article,
        container_opus_id=container_opus_id,
        exclude_link_text=exclude_link_text,
        default_hint=default_hint,
    )
    return links
