from __future__ import annotations

import re
from datetime import datetime, timezone

LOTTERY_TIME_DISPLAY_FMT = "%Y-%m-%d %H:%M"
_WEEKDAY_SUFFIX_RE = re.compile(r"[（(][^）)]*[）)]")
_NOISE_SUFFIX_RE = re.compile(r"(?:前|后|左右|左右开奖|直播.*|录屏.*|开奖.*)$")
_RELATIVE_TIME_RE = re.compile(
    r"^(?:下|本|上)?(?:周|星期|礼拜)[一二三四五六日天]?|"
    r"^(?:明天|后天|大后天|今天|今晚|明晚)(?:[晚早]?\d{1,2}[:：点]\d{0,2})?$"
)


def format_timestamp(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        return (
            datetime.fromtimestamp(int(ts), tz=timezone.utc)
            .astimezone()
            .strftime(LOTTERY_TIME_DISPLAY_FMT)
        )
    except (OSError, OverflowError, ValueError):
        return str(ts)


def _default_year() -> int:
    return datetime.now().year


def _compose(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _clean_text(text: str) -> str:
    raw = text.strip()
    raw = _WEEKDAY_SUFFIX_RE.sub("", raw)
    raw = _NOISE_SUFFIX_RE.sub("", raw).strip()
    return raw


def is_relative_lottery_time_text(text: str) -> bool:
    raw = text.strip()
    if not raw:
        return False
    return bool(_RELATIVE_TIME_RE.search(raw))


def normalize_lottery_time_text(text: str) -> str:
    raw = _clean_text(text)
    if not raw:
        return ""
    if is_relative_lottery_time_text(raw):
        return ""

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return f"{raw} 00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", raw):
        return raw

    patterns: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"^(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s*"
                r"(?P<hour>\d{1,2})[:：点](?P<minute>\d{2})?$"
            ),
            "ymd_hm",
        ),
        (
            re.compile(r"^(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日$"),
            "ymd",
        ),
        (
            re.compile(
                r"^(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s*"
                r"(?P<hour>\d{1,2})[:：点](?P<minute>\d{2})?$"
            ),
            "md_hm",
        ),
        (re.compile(r"^(?P<month>\d{1,2})月(?P<day>\d{1,2})日$"), "md"),
        (re.compile(r"^(?P<month>\d{1,2})月(?P<day>\d{1,2})号$"), "md_hao"),
        (
            re.compile(r"^(?P<month>\d{1,2})\.(?P<day>\d{1,2})号?$"),
            "dot_md",
        ),
        (
            re.compile(
                r"^(?P<month>\d{1,2})\.(?P<day>\d{1,2})\s*"
                r"(?P<hour>\d{1,2})[:：](?P<minute>\d{2})?$"
            ),
            "dot_md_hm",
        ),
    ]

    for pattern, kind in patterns:
        match = pattern.match(raw)
        if not match:
            continue
        groups = match.groupdict()
        year = int(groups.get("year") or _default_year())
        month = int(groups["month"])
        day = int(groups["day"])
        hour = int(groups.get("hour") or 0)
        minute = int(groups.get("minute") or 0)
        if kind in {"ymd", "md", "dot_md"}:
            hour = 0
            minute = 0
        return _compose(year, month, day, hour, minute)

    loose = re.search(
        r"(?P<year>\d{4})?年?(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号]",
        raw,
    )
    if loose:
        year = int(loose.group("year") or _default_year())
        month = int(loose.group("month"))
        day = int(loose.group("day"))
        time_match = re.search(r"(\d{1,2})[:：点](\d{2})", raw)
        if time_match:
            return _compose(year, month, day, int(time_match.group(1)), int(time_match.group(2)))
        return _compose(year, month, day)

    dot_loose = re.search(r"(\d{1,2})\.(\d{1,2})", raw)
    if dot_loose:
        return _compose(_default_year(), int(dot_loose.group(1)), int(dot_loose.group(2)))

    if is_relative_lottery_time_text(raw):
        return ""

    return ""


def lottery_time_text(item: dict) -> str:
    lottery_time = item.get("lottery_time")
    if lottery_time:
        return format_timestamp(int(lottery_time))
    conditions = item.get("conditions") or {}
    normalized = normalize_lottery_time_text(str(conditions.get("lottery_time_text") or ""))
    if normalized and re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", normalized):
        return normalized
    return ""
