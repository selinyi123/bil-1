from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# 活动列表开奖时间统一格式：YYYY-MM-DD HH:mm（北京时间）
LOTTERY_TIME_DISPLAY_FMT = "%Y-%m-%d %H:%M"
LOTTERY_TIME_DISPLAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
BEIJING_TZ = timezone(timedelta(hours=8))

_WEEKDAY_SUFFIX_RE = re.compile(r"[（(][^）)]*[）)]")
_NOISE_SUFFIX_RE = re.compile(r"(?:前|后|左右|左右开奖|直播.*|录屏.*|开奖.*)$")
_CHINESE_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_RELATIVE_WEEKDAY_RE = re.compile(r"下(?:周|星期|礼拜)([一二三四五六日天])")
_RELATIVE_TIME_RE = re.compile(
    r"^(?:下|本|上)?(?:周|星期|礼拜)[一二三四五六日天]?|"
    r"^(?:明天|后天|大后天|今天|今晚|明晚)(?:[晚早]?\d{1,2}[:：点]\d{0,2})?$"
)


def is_standard_lottery_time_display(text: str) -> bool:
    return bool(LOTTERY_TIME_DISPLAY_RE.fullmatch(text.strip()))


def format_timestamp(ts: int | None) -> str:
    """将 Unix 时间戳格式化为北京时间 YYYY-MM-DD HH:mm。"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=BEIJING_TZ).strftime(LOTTERY_TIME_DISPLAY_FMT)
    except (OSError, OverflowError, ValueError):
        return ""


def _default_year() -> int:
    return datetime.now(BEIJING_TZ).year


def _compose(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _clean_text(text: str) -> str:
    raw = text.strip()
    raw = _WEEKDAY_SUFFIX_RE.sub("", raw)
    raw = _NOISE_SUFFIX_RE.sub("", raw).strip()
    return raw


def _preprocess_lottery_text(text: str) -> str:
    raw = text.strip()
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("当天", "").replace("当日", "")
    return raw


def _resolve_relative_weekday(text: str, ref: datetime) -> str:
    match = _RELATIVE_WEEKDAY_RE.search(text.strip())
    if not match:
        return ""
    target = _CHINESE_WEEKDAY.get(match.group(1))
    if target is None:
        return ""
    days_until_next_monday = (7 - ref.weekday()) % 7 or 7
    next_monday = ref + timedelta(days=days_until_next_monday)
    result_day = next_monday + timedelta(days=target)
    clock = _parse_clock(text)
    hour, minute = clock if clock else (0, 0)
    return _compose(result_day.year, result_day.month, result_day.day, hour, minute)


def is_relative_lottery_time_text(text: str) -> bool:
    raw = _preprocess_lottery_text(text)
    if not raw:
        return False
    if _RELATIVE_WEEKDAY_RE.search(raw):
        return False
    return bool(_RELATIVE_TIME_RE.search(raw))


def _parse_clock(raw: str) -> tuple[int, int] | None:
    """从中文片段解析时分，例如「晚8点」「18:30」「20点30分」。"""
    evening = re.search(r"晚(?P<hour>\d{1,2})(?:[:：点](?P<minute>\d{2})|点(?P<minute2>\d{1,2})?|点)?", raw)
    if evening:
        hour = int(evening.group("hour"))
        if hour < 12:
            hour += 12
        minute = int(evening.group("minute") or evening.group("minute2") or 0)
        return hour, minute

    colon = re.search(r"(?P<hour>\d{1,2})[:：](?P<minute>\d{2})", raw)
    if colon:
        return int(colon.group("hour")), int(colon.group("minute"))

    point = re.search(r"(?P<hour>\d{1,2})点(?P<minute>\d{1,2})?分?", raw)
    if point:
        return int(point.group("hour")), int(point.group("minute") or 0)

    return None


def normalize_lottery_time_text(text: str, *, ref: datetime | None = None) -> str:
    raw = _clean_text(_preprocess_lottery_text(text))
    if not raw:
        return ""
    if ref is not None:
        relative = _resolve_relative_weekday(raw, ref)
        if is_standard_lottery_time_display(relative):
            return relative
    if is_relative_lottery_time_text(text):
        return ""

    if is_standard_lottery_time_display(raw):
        return raw

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return f"{raw} 00:00"
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", raw):
        parts = raw.split("/")
        return _compose(int(parts[0]), int(parts[1]), int(parts[2]))
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", raw):
        parts = raw.split(".")
        return _compose(int(parts[0]), int(parts[1]), int(parts[2]))

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
        if kind in {"ymd", "md", "dot_md", "md_hao"}:
            clock = _parse_clock(raw)
            if clock:
                hour, minute = clock
            else:
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
        clock = _parse_clock(raw)
        if clock:
            hour, minute = clock
            return _compose(year, month, day, hour, minute)
        return _compose(year, month, day)

    dot_loose = re.search(r"(\d{1,2})\.(\d{1,2})", raw)
    if dot_loose:
        year = _default_year()
        month = int(dot_loose.group(1))
        day = int(dot_loose.group(2))
        clock = _parse_clock(raw)
        if clock:
            return _compose(year, month, day, clock[0], clock[1])
        return _compose(year, month, day)

    return ""


def lottery_time_unix(item: dict, *, ref_ts: int | None = None) -> int | None:
    """解析活动开奖时间的 Unix 时间戳（北京时间语义）。"""
    lottery_time = item.get("lottery_time")
    if lottery_time:
        try:
            return int(lottery_time)
        except (TypeError, ValueError):
            pass

    ref = datetime.fromtimestamp(int(ref_ts or item.get("enriched_at") or time.time()), tz=BEIJING_TZ)
    conditions = item.get("conditions") or {}
    normalized = normalize_lottery_time_text(
        str(conditions.get("lottery_time_text") or ""),
        ref=ref,
    )
    if not is_standard_lottery_time_display(normalized):
        return None
    try:
        return int(datetime.strptime(normalized, LOTTERY_TIME_DISPLAY_FMT).replace(tzinfo=BEIJING_TZ).timestamp())
    except ValueError:
        return None


def migrate_lottery_time_fields(item: dict) -> bool:
    """修正单条已保存活动的时间字段，返回是否有改动。"""
    import time

    changed = False
    conditions = item.get("conditions")
    if not isinstance(conditions, dict):
        conditions = {}
        item["conditions"] = conditions
        changed = True

    ref_ts = int(item.get("enriched_at") or time.time())
    raw_text = str(conditions.get("lottery_time_text") or "")

    unix: int | None
    try:
        unix = int(item["lottery_time"]) if item.get("lottery_time") else None
    except (TypeError, ValueError):
        item.pop("lottery_time", None)
        unix = None
        changed = True

    if not unix:
        parsed = lottery_time_unix(item, ref_ts=ref_ts)
        if parsed:
            item["lottery_time"] = parsed
            unix = parsed
            changed = True

    display = lottery_time_text(item)
    if display:
        if raw_text != display:
            conditions["lottery_time_text"] = display
            changed = True
    elif raw_text:
        conditions["lottery_time_text"] = ""
        changed = True

    return changed


def migrate_stored_lottery_times(activities: list[dict]) -> int:
    """批量修正已保存活动的开奖时间字段。"""
    migrated = 0
    for item in activities:
        if isinstance(item, dict) and migrate_lottery_time_fields(item):
            migrated += 1
    return migrated


def lottery_time_text(item: dict) -> str:
    """返回统一格式的开奖时间，无法解析时返回空字符串。"""
    lottery_time = item.get("lottery_time")
    if lottery_time:
        formatted = format_timestamp(int(lottery_time))
        if is_standard_lottery_time_display(formatted):
            return formatted

    conditions = item.get("conditions") or {}
    ref = datetime.fromtimestamp(int(item.get("enriched_at") or time.time()), tz=BEIJING_TZ)
    normalized = normalize_lottery_time_text(
        str(conditions.get("lottery_time_text") or ""),
        ref=ref,
    )
    if is_standard_lottery_time_display(normalized):
        return normalized
    return ""
