"""应用版本解析与比较（SSOT 辅助；权威字符串在 app_paths.__version__）。"""

from __future__ import annotations

import re

from src.app_paths import __version__

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def get_version() -> str:
    return str(__version__)


def strip_v_prefix(text: str) -> str:
    """去掉单一前导 v/V（勿用 str.lstrip('vV')，以免误伤）。"""
    raw = (text or "").strip()
    if len(raw) >= 2 and raw[0] in "vV" and raw[1].isdigit():
        return raw[1:].strip()
    return raw


def parse_version(text: str) -> tuple[int, int, int] | None:
    raw = strip_v_prefix(text)
    match = _SEMVER_RE.match(raw)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def compare_versions(current: str, latest: str) -> int | None:
    """current < latest → -1；相等 → 0；current > latest → 1；不可比 → None。"""
    left = parse_version(current)
    right = parse_version(latest)
    if left is None or right is None:
        cur_n = strip_v_prefix(current)
        lat_n = strip_v_prefix(latest)
        if cur_n and cur_n == lat_n:
            return 0
        return None
    if left < right:
        return -1
    if left > right:
        return 1
    return 0
