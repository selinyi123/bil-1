"""多渠道推送通知（源自 LAS lib/helper/notify.js，15 渠道）。

配置：`config/notify.json`（全部凭据可选，缺失的渠道静默跳过）：

```json
{
  "enabled": true,
  "channels": {
    "serverchan": {"sckey": ""},
    "sct": {"sendkey": ""},
    "coolpush": {"key": "", "mode": "send"},
    "bark": {"push": "", "sound": ""},
    "pushdeer": {"url": "", "pushkey": ""},
    "telegram": {"bot_token": "", "chat_id": ""},
    "dingtalk": {"token": "", "secret": ""},
    "qywx_app": {"corpid": "", "secret": "", "agentid": "", "touser": ""},
    "qywx_bot": {"key": ""},
    "igot": {"key": ""},
    "pushplus": {"token": "", "topic": ""},
    "qmsg": {"key": "", "qq": "", "socket": ""},
    "email": {"host": "", "port": 465, "user": "", "pass": "", "to": ""},
    "gotify": {"url": "", "appkey": ""},
    "feishu": {"webhook": "", "secret": ""}
  }
}
```

用法：`send_notify(title, desp)` —— 并发发送所有已配置渠道，返回发送结果。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import smtplib
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx

from src.app_paths import config_dir

_lock = threading.RLock()
_cache: dict | None = None
_CACHE_MTIME: float | None = None

_TIMEOUT = 10.0


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _http_ok(response: Any, *, ok_codes: tuple[int, ...] = (0,)) -> bool:
    """渠道响应确认：HTTP >= 400 或业务 JSON 明确报错视为失败（不产生假发送成功）。

    - 成功码按渠道约定（多数为 0；bark/pushplus 为 200）；
    - 2xx 但无法解析 JSON 的响应视为到达（部分渠道返回纯文本，不再额外惩罚）；
    - 解析出的业务码不在 ok_codes 中 → 失败（如 telegram 401、钉钉 errcode!=0）。
    """
    if int(getattr(response, "status_code", 200) or 200) >= 400:
        return False
    try:
        body = response.json()
    except (ValueError, AttributeError):
        return True
    if not isinstance(body, dict):
        return True
    if "errcode" in body:
        code = _as_int(body.get("errcode"))
        # fail-closed：provider 明确给了业务码但无法解析 → 视为失败（中奖通知链路宁严勿宽）
        return code is not None and code in ok_codes
    if "code" in body:
        code = _as_int(body.get("code"))
        return code is not None and code in ok_codes
    if "success" in body:
        return body["success"] is True
    if "ok" in body:
        return body["ok"] is True
    return True


def _config_path() -> Path:
    return config_dir() / "notify.json"


def load_notify_config() -> dict:
    global _cache, _CACHE_MTIME
    path = _config_path()
    with _lock:
        mtime = path.stat().st_mtime if path.exists() else None
        if _cache is not None and mtime == _CACHE_MTIME:
            return _cache
        raw: dict = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        _cache = raw
        _CACHE_MTIME = mtime
        return _cache


def reset_notify_config_cache() -> None:
    global _cache, _CACHE_MTIME
    with _lock:
        _cache = None
        _CACHE_MTIME = None


def _channels() -> dict:
    cfg = load_notify_config()
    channels = cfg.get("channels") or {}
    return channels if isinstance(channels, dict) else {}


def _enabled() -> bool:
    return bool(load_notify_config().get("enabled", True))


# ---------------------------------------------------------------------------
# 渠道实现（每个函数：凭据缺失返回 None 表示跳过；返回 str 表示渠道名已发送）
# ---------------------------------------------------------------------------

def _serverchan(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("sckey") or "").strip()
    if not key:
        return None
    try:
        response = httpx.get(f"https://sc.ftqq.com/{key}.send", params={"text": title, "desp": desp}, timeout=_TIMEOUT)
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "serverchan"
    except httpx.HTTPError:
        return None


def _sct(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("sendkey") or "").strip()
    if not key:
        return None
    try:
        response = httpx.get(f"https://sctapi.ftqq.com/{key}.send", params={"title": title, "desp": desp}, timeout=_TIMEOUT)
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "sct"
    except httpx.HTTPError:
        return None


def _coolpush(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("key") or "").strip()
    if not key:
        return None
    mode = str(cfg.get("mode") or "send").strip() or "send"
    try:
        response = httpx.post(
            f"https://push.xuthus.cc/{mode}/{key}",
            data={"c": title, "title": title, "d": desp},
            timeout=_TIMEOUT,
        )
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "coolpush"
    except httpx.HTTPError:
        return None


def _bark(cfg: dict, title: str, desp: str) -> str | None:
    push = str(cfg.get("push") or "").strip().rstrip("/")
    if not push:
        return None
    sound = str(cfg.get("sound") or "").strip()
    try:
        url = f"{push}/{urllib.parse.quote(title)}/{urllib.parse.quote(desp)}"
        params = {}
        if sound:
            params["sound"] = sound
        response = httpx.get(url, params=params, timeout=_TIMEOUT)
        # bark 成功响应 code=200，失败（如 key 无效）code!=200
        if not _http_ok(response, ok_codes=(200,)):
            return None
        return "bark"
    except httpx.HTTPError:
        return None


def _pushdeer(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("pushkey") or "").strip()
    if not key:
        return None
    base = str(cfg.get("url") or "https://api2.pushdeer.com/message/push").strip().rstrip("/")
    try:
        response = httpx.post(
            base,
            data={"pushkey": key, "text": title, "desp": desp},
            timeout=_TIMEOUT,
        )
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "pushdeer"
    except httpx.HTTPError:
        return None


def _telegram(cfg: dict, title: str, desp: str) -> str | None:
    token = str(cfg.get("bot_token") or "").strip()
    chat_id = str(cfg.get("chat_id") or "").strip()
    if not token or not chat_id:
        return None
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"{title}\n{desp}"},
            timeout=_TIMEOUT,
        )
        # telegram 明确返回 {"ok": false}（401/403 时 HTTP 层也会 >=400）
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "telegram"
    except httpx.HTTPError:
        return None


def _dingtalk(cfg: dict, title: str, desp: str) -> str | None:
    token = str(cfg.get("token") or "").strip()
    if not token:
        return None
    secret = str(cfg.get("secret") or "").strip()
    params: dict[str, Any] = {"access_token": token}
    headers = {}
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        signature = urllib.parse.quote_plus(
            base64.b64encode(hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest())
        )
        params["timestamp"] = timestamp
        params["sign"] = signature
        headers["Content-Type"] = "application/json"
    try:
        response = httpx.post(
            "https://oapi.dingtalk.com/robot/send",
            params=params,
            headers=headers,
            json={"msgtype": "text", "text": {"content": f"{title}\n{desp}"}},
            timeout=_TIMEOUT,
        )
        # 钉钉业务错误（errcode!=0，如 invalid token）不抛 HTTPError，必须显式检查
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "dingtalk"
    except httpx.HTTPError:
        return None


def _qywx_app(cfg: dict, title: str, desp: str) -> str | None:
    corpid = str(cfg.get("corpid") or "").strip()
    secret = str(cfg.get("secret") or "").strip()
    agentid = str(cfg.get("agentid") or "").strip()
    if not corpid or not secret or not agentid:
        return None
    try:
        token_payload = httpx.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corpid, "corpsecret": secret},
            timeout=_TIMEOUT,
        ).json()
        access_token = token_payload.get("access_token")
        if not access_token:
            return None
        response = httpx.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": access_token},
            json={
                "touser": str(cfg.get("touser") or "@all"),
                "msgtype": "text",
                "agentid": agentid,
                "text": {"content": f"{title}\n{desp}"},
            },
            timeout=_TIMEOUT,
        )
        # 发送结果 errcode=0 才算成功
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "qywx_app"
    except httpx.HTTPError:
        return None


def _qywx_bot(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("key") or "").strip()
    if not key:
        return None
    try:
        response = httpx.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}",
            json={"msgtype": "text", "text": {"content": f"{title}\n{desp}"}},
            timeout=_TIMEOUT,
        )
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "qywx_bot"
    except httpx.HTTPError:
        return None


def _igot(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("key") or "").strip()
    if not key:
        return None
    try:
        response = httpx.post(f"https://push.hellyw.com/{key}", json={"title": title, "content": desp}, timeout=_TIMEOUT)
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "igot"
    except httpx.HTTPError:
        return None


def _pushplus(cfg: dict, title: str, desp: str) -> str | None:
    token = str(cfg.get("token") or "").strip()
    if not token:
        return None
    payload: dict[str, Any] = {"token": token, "title": title, "content": desp}
    topic = str(cfg.get("topic") or "").strip()
    if topic:
        payload["topic"] = topic
    try:
        response = httpx.post("https://www.pushplus.plus/send", data=payload, timeout=_TIMEOUT)
        # pushplus 成功响应 code=200
        if not _http_ok(response, ok_codes=(200,)):
            return None
        return "pushplus"
    except httpx.HTTPError:
        return None


def _qmsg(cfg: dict, title: str, desp: str) -> str | None:
    key = str(cfg.get("key") or "").strip()
    if not key:
        return None
    socket = str(cfg.get("socket") or "qmsg.zendee.cn").strip().rstrip("/")
    qq = str(cfg.get("qq") or "").strip()
    try:
        response = httpx.get(
            f"https://{socket}/send/{key}",
            params={"msg": f"{title}\n{desp}"} | ({"qq": qq} if qq else {}),
            timeout=_TIMEOUT,
        )
        # qmsg 返回 {"success": true} 或 {"success": false, ...}
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "qmsg"
    except httpx.HTTPError:
        return None


def _email(cfg: dict, title: str, desp: str) -> str | None:
    host = str(cfg.get("host") or "").strip()
    user = str(cfg.get("user") or "").strip()
    password = str(cfg.get("pass") or "").strip()
    to_user = str(cfg.get("to") or "").strip()
    if not host or not user or not password or not to_user:
        return None
    port = int(cfg.get("port") or 465)
    message = MIMEText(desp, "plain", "utf-8")
    message["Subject"] = Header(title, "utf-8")
    message["From"] = user
    message["To"] = to_user
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT)
        else:
            server = smtplib.SMTP(host, port, timeout=_TIMEOUT)
            server.starttls()
        try:
            server.login(user, password)
            server.sendmail(user, [to_user], message.as_string())
        finally:
            server.quit()
        return "email"
    except (smtplib.SMTPException, OSError):
        return None


def _gotify(cfg: dict, title: str, desp: str) -> str | None:
    url = str(cfg.get("url") or "").strip().rstrip("/")
    appkey = str(cfg.get("appkey") or "").strip()
    if not url or not appkey:
        return None
    try:
        response = httpx.post(
            f"{url}/message",
            params={"token": appkey},
            json={"title": title, "message": desp},
            timeout=_TIMEOUT,
        )
        # gotify 认证失败返回 4xx；2xx 即确认入队
        if not _http_ok(response, ok_codes=(0,)):
            return None
        return "gotify"
    except httpx.HTTPError:
        return None


def _feishu(cfg: dict, title: str, desp: str) -> str | None:
    webhook = str(cfg.get("webhook") or "").strip()
    if not webhook:
        return None
    secret = str(cfg.get("secret") or "").strip()
    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": f"{title}\n{desp}"}}
    try:
        if secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{secret}"
            # 飞书官方签名：HMAC-SHA256(key=f"{timestamp}\n{secret}", msg=空串) 再 Base64。
            # 注意：key 是 string_to_sign，消息体为空（此前把二者写反导致 19021 sign match fail）。
            sign = base64.b64encode(
                hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
            ).decode()
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        response = httpx.post(webhook, json=payload, timeout=_TIMEOUT)
        # 飞书业务错误不抛 HTTPError（code != 0），须检查返回体，避免静默假成功
        try:
            code = (response.json() or {}).get("code")
        except ValueError:
            code = None
        if response.status_code >= 400 or (code is not None and code != 0):
            return None
        return "feishu"
    except httpx.HTTPError:
        return None


_CHANNEL_HANDLERS = {
    "serverchan": _serverchan,
    "sct": _sct,
    "coolpush": _coolpush,
    "bark": _bark,
    "pushdeer": _pushdeer,
    "telegram": _telegram,
    "dingtalk": _dingtalk,
    "qywx_app": _qywx_app,
    "qywx_bot": _qywx_bot,
    "igot": _igot,
    "pushplus": _pushplus,
    "qmsg": _qmsg,
    "email": _email,
    "gotify": _gotify,
    "feishu": _feishu,
}

ALL_CHANNEL_NAMES = tuple(_CHANNEL_HANDLERS.keys())


def send_notify(title: str, desp: str = "") -> dict[str, Any]:
    """并发发送到全部已配置渠道。

    返回 {"sent": [渠道名...], "skipped": [渠道名...]}。
    """
    if not _enabled():
        return {"sent": [], "skipped": []}
    channels = _channels()
    sent: list[str] = []
    skipped: list[str] = []

    def _run(name: str) -> str | None:
        handler = _CHANNEL_HANDLERS[name]
        cfg = channels.get(name)
        if not isinstance(cfg, dict):
            return None
        try:
            return handler(cfg, title, desp)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(8, len(_CHANNEL_HANDLERS))) as executor:
        futures = {executor.submit(_run, name): name for name in _CHANNEL_HANDLERS}
        for future in as_completed(futures):
            name = futures[future]
            result = future.result()
            if result:
                sent.append(result)
            else:
                skipped.append(name)
    return {"sent": sorted(sent), "skipped": sorted(skipped)}
