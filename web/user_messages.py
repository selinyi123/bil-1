from __future__ import annotations

import re
from typing import Any

from src.bilibili_login import BilibiliLoginError, LoginCancelledError

PARTICIPATE_ACTION_LABELS: dict[str, str] = {
    "like": "点赞",
    "follow": "关注",
    "favorite": "收藏",
    "repost": "转发",
    "comment": "评论",
    "reserve": "预约",
}

JOB_ACTION_LABELS: dict[str, str] = {
    "login": "扫码登录",
    "refresh_all": "一键更新活动链接",
    "refresh_status": "刷新任务状态",
    "participate": "参与活动",
}

_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_UNIX_PATH_PATTERN = re.compile(r"(?<!\w)/(?:[\w.-]+/)+[\w.-]+\.(?:py|json|txt|png)")


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, LoginCancelledError):
        return "已取消扫码登录"

    if isinstance(exc, BilibiliLoginError):
        msg = str(exc).strip()
        if "取消" in msg:
            return "已取消扫码登录"
        if "过期" in msg:
            return "二维码已过期，请重新发起登录"
        if "超时" in msg:
            return "扫码登录超时，请重试"
        if "SESSDATA" in msg:
            return "登录未完成，请重新扫码"
        return msg or "登录失败，请重试"

    msg = str(exc).strip()
    if isinstance(exc, ValueError):
        if "缺少 dynamic_id" in msg or "活动 ID 无效" in msg:
            return "未找到活动信息，请刷新页面后重试"
        if msg.startswith("未知操作"):
            return "暂不支持该操作"

    if _looks_like_internal_error(msg):
        return "操作失败，请稍后重试"

    return msg or "操作失败，请稍后重试"


def _looks_like_internal_error(message: str) -> bool:
    lowered = message.lower()
    markers = (
        "traceback",
        "nameerror",
        "attributeerror",
        "typeerror",
        "keyerror",
        "modulenotfounderror",
        "oserror",
        "systemexit",
        "winerror",
        "errno",
        "uvicorn",
        "asyncio",
        "line ",
        ".py",
        "exception",
        "raise systemexit",
    )
    return any(marker in lowered for marker in markers)


def _is_stack_frame_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("File ") or stripped.startswith("During handling"):
        return True
    if re.search(r'\sFile "[^"]+", line \d+', line):
        return True
    if re.match(r"^[A-Za-z_][\w.]*Error:", stripped):
        return True
    if "uvicorn.run" in stripped or "asyncio_run" in stripped or "server.run" in stripped:
        return True
    return False


def sanitize_log(log: str) -> str:
    text = (log or "").strip()
    if not text:
        return ""

    in_traceback = False
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if "Traceback (most recent call last)" in stripped:
            in_traceback = True
            continue
        if in_traceback:
            if (
                stripped.startswith("File ")
                or stripped.startswith("During handling")
                or _looks_like_internal_error(stripped)
                or _is_stack_frame_line(raw)
                or (raw[:1].isspace() and not stripped.startswith("==="))
            ):
                continue
            in_traceback = False
        if stripped.startswith("File ") or "Traceback" in stripped or _is_stack_frame_line(raw):
            continue
        if _looks_like_internal_error(stripped):
            continue
        line = _PATH_PATTERN.sub("[本地文件]", stripped)
        line = _UNIX_PATH_PATTERN.sub("[本地文件]", line)
        line = re.sub(r"→\s*\S+", "→ 已保存", line)
        lines.append(line)
    return "\n".join(lines).strip()


def format_participation_log(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for item in payload.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "")
        label = PARTICIPATE_ACTION_LABELS.get(action, action)
        mark = "✓" if item.get("ok") else "✗"
        detail = str(item.get("detail") or "").strip()
        if detail and _looks_like_internal_error(detail):
            detail = "未完成"
        lines.append(f"{mark} {label}{f' · {detail}' if detail else ''}")
    message = str(payload.get("message") or "").strip()
    if message:
        lines.append(message)
    return "\n".join(lines).strip()
