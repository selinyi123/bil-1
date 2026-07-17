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
    "refresh_source": "更新数据源",
    "refresh_status": "刷新任务状态",
    "participate": "参与活动",
    "participate_triple": "三连参与",
    "refresh_watch": "更新监控用户动态",
}

_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_UNIX_PATH_PATTERN = re.compile(r"(?<!\w)/(?:[\w.-]+/)+[\w.-]+\.(?:py|json|txt|png)")


def friendly_network_error(message: str) -> str:
    lowered = message.lower()
    markers = (
        "handshake",
        "timed out",
        "timeout",
        "connecttimeout",
        "connecterror",
        "ssl",
        "network",
        "网络请求失败",
        "connection",
    )
    if any(marker in lowered for marker in markers):
        return "无法连接 B 站服务器，请检查网络、代理或 DNS 后点击「刷新账号」"
    return message.strip() or "网络异常，请稍后重试"


def _friendly_plain_message(msg: str) -> str:
    text = msg.strip()
    if not text:
        return ""
    lowered = text.lower()

    if "cookie" in lowered and any(token in text for token in ("过期", "失效", "重新", "无效")):
        return "Cookie 已过期，请重新扫码登录"
    if "请先扫码登录" in text or "未检测到有效登录" in text:
        return "请先扫码登录后再试"
    if any(token in text for token in ("频繁", "限流", "风控")) or any(token in lowered for token in ("412", "-509")):
        return "请求过于频繁，请稍后重试；日常建议在「数据源」页逐个更新"
    if "未配置 llm" in lowered or ("llm" in lowered and "未配置" in text):
        return "未配置 LLM，请在概览页填写 API Key 与模型名称并保存"
    if "连接测试" in text or "请先测试" in text:
        return "请先完成 LLM 连接测试后再使用项目功能"
    if "无法连接 llm" in lowered:
        return "无法连接 LLM 接口，请检查 API Key、接口地址与网络"
    if "llm 服务" in lowered or "llm 返回" in lowered:
        return text if len(text) <= 120 else "LLM 服务暂时不可用，请稍后重试"
    if any(token in text for token in ("已有任务", "正在运行", "仍在运行")):
        return "当前已有任务在运行，请等待结束后再试"
    if "任务已取消" in text or text == "已取消":
        return "任务已取消"
    if "无可参与" in text or "没有可参与" in text:
        return text

    return friendly_network_error(text) if "网络请求失败" in text else text


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, LoginCancelledError):
        return "已取消扫码登录"

    if isinstance(exc, BilibiliLoginError):
        msg = str(exc).strip()
        if "取消" in msg:
            return "已取消扫码登录"
        if "过期" in msg:
            return "二维码已过期，请重新发起登录"
        if "确认超时" in msg:
            return "扫码后确认超时，请重新发起登录"
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
        if "任务已取消" in msg:
            return "任务已取消"

    if _looks_like_internal_error(msg):
        if any(token in msg.lower() for token in ("handshake", "timeout", "ssl", "connect", "网络")):
            return friendly_network_error(msg)
        return "操作失败，请稍后重试"

    mapped = _friendly_plain_message(msg)
    if mapped:
        return mapped
    return "操作失败，请稍后重试"


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
        line = re.sub(r"→\s*\S+", "", line).strip()
        if not line:
            continue
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
