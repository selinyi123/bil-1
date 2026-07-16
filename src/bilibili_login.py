from __future__ import annotations

import threading
import time
import urllib.parse
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Callable

import httpx

try:
    from src.app_logging import get_logger
except ImportError:  # pragma: no cover
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("login")

from src.app_paths import COOKIE_PATH, QR_IMAGE_PATH, ensure_user_dirs

PASSPORT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}

POLL_WAITING = 86101
POLL_SCANNED = 86090
POLL_EXPIRED = 86038
POLL_SUCCESS = 0

ESSENTIAL_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "buvid3", "b_nut")


class BilibiliLoginError(Exception):
    pass


class LoginCancelledError(BilibiliLoginError):
    pass


def _poll_status(body: dict) -> int:
    """扫码状态在 data.code，不是顶层 code。"""
    data = body.get("data") or {}
    for candidate in (data.get("code"), body.get("code")):
        if candidate is None:
            continue
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return -1


def _parse_set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    jar: dict[str, str] = {}
    try:
        headers = response.headers.get_list("set-cookie")
    except AttributeError:
        raw = response.headers.get("set-cookie")
        headers = [raw] if raw else []
    for header in headers:
        if not header:
            continue
        sc = SimpleCookie()
        try:
            sc.load(header)
        except (ValueError, KeyError):
            continue
        for key, morsel in sc.items():
            jar[key] = morsel.value
    return jar


def _parse_cross_domain_url(url: str) -> dict[str, str]:
    if not url:
        return {}
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    jar: dict[str, str] = {}
    for key in ESSENTIAL_KEYS:
        if key in query and query[key]:
            jar[key] = query[key][0]
    return jar


def _merge_cookies(*sources: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for src in sources:
        merged.update(src)
    return merged


def _cookies_from_jar(client: httpx.Client) -> dict[str, str]:
    """从 cookie jar 安全提取，同名多 domain 时优先 .bilibili.com。"""
    grouped: dict[str, list] = {}
    for cookie in client.cookies.jar:
        grouped.setdefault(cookie.name, []).append(cookie)

    result: dict[str, str] = {}
    for name, items in grouped.items():
        chosen = items[-1]
        for item in items:
            domain = item.domain or ""
            if domain.endswith("bilibili.com"):
                chosen = item
        result[name] = chosen.value
    return result


def cookies_to_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def save_cookies(cookie_str: str) -> Path:
    content = cookie_str.strip()
    if not content:
        raise BilibiliLoginError("Cookie 内容为空，无法保存")
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = COOKIE_PATH.with_suffix(".txt.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(COOKIE_PATH)
    return COOKIE_PATH


def _request_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    retries: int = 3,
) -> dict:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("响应不是 JSON 对象")
            return body
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            last_exc = exc
            if attempt + 1 < retries:
                logger.warning("请求失败，重试 %s/%s: %s", attempt + 1, retries, exc)
                time.sleep(0.4 * (attempt + 1))
    raise BilibiliLoginError("网络请求失败，请检查网络后重试") from last_exc


def _poll_request(
    client: httpx.Client,
    qrcode_key: str,
) -> tuple[dict, httpx.Response]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            poll = client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key, "source": "main-fe-header"},
            )
            poll.raise_for_status()
            body = poll.json()
            if not isinstance(body, dict):
                raise ValueError("轮询响应不是 JSON 对象")
            return body, poll
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            last_exc = exc
            if attempt + 1 < 3:
                logger.warning("扫码轮询失败，重试 %s/3: %s", attempt + 1, exc)
                time.sleep(0.4 * (attempt + 1))
    raise BilibiliLoginError("扫码轮询失败，请检查网络后重试") from last_exc


def _generate_qrcode_image(url: str, out_path: Path) -> bool:
    try:
        import qrcode
    except ImportError:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(url)
    img.save(out_path)
    return True


def _collect_login_cookies(client: httpx.Client, poll: httpx.Response, body: dict) -> dict[str, str]:
    data = body.get("data") or {}
    cross_url = str(data.get("url") or "").strip()

    cookies = _merge_cookies(
        _parse_set_cookie_headers(poll),
        _parse_cross_domain_url(cross_url),
    )

    if cross_url:
        try:
            client.get(cross_url, timeout=12.0)
            cookies = _merge_cookies(cookies, _cookies_from_jar(client))
        except httpx.HTTPError as exc:
            logger.warning("登录 SSO 跳转失败: %s", exc)

    if "SESSDATA" not in cookies or "bili_jct" not in cookies:
        try:
            client.get("https://www.bilibili.com", timeout=12.0)
            cookies = _merge_cookies(cookies, _cookies_from_jar(client))
        except httpx.HTTPError as exc:
            logger.warning("登录后访问首页失败: %s", exc)

    if "SESSDATA" not in cookies:
        try:
            client.get("https://api.bilibili.com/x/web-interface/nav", timeout=12.0)
            cookies = _merge_cookies(cookies, _cookies_from_jar(client))
        except httpx.HTTPError as exc:
            logger.warning("登录后校验 nav 失败: %s", exc)

    return cookies


def login_with_qrcode(
    *,
    timeout: float = 180.0,
    open_image: bool = True,
    auto_refresh_on_expire: bool = False,
    cancel_event: threading.Event | None = None,
    on_qrcode_ready: Callable[[], None] | None = None,
    on_status_change: Callable[[str, str], None] | None = None,
) -> str:
    client = httpx.Client(headers=PASSPORT_HEADERS, follow_redirects=True, timeout=20.0)

    def _check_cancelled() -> None:
        if cancel_event and cancel_event.is_set():
            raise LoginCancelledError("登录已取消")

    def _emit(phase: str, message: str) -> None:
        if on_status_change:
            on_status_change(phase, message)

    def _issue_qrcode() -> tuple[str, str]:
        gen_data = _request_json(
            client,
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            params={"source": "main-fe-header"},
        )
        if gen_data.get("code") != 0:
            raise BilibiliLoginError(f"获取二维码失败: {gen_data.get('message')}")
        data = gen_data.get("data") or {}
        qrcode_url = str(data.get("url") or "").strip()
        qrcode_key = str(data.get("qrcode_key") or "").strip()
        if not qrcode_url or not qrcode_key:
            raise BilibiliLoginError("获取二维码失败：响应缺少 url 或 qrcode_key")
        if open_image:
            print("请使用哔哩哔哩手机 App 扫描下方二维码登录：")
            print(qrcode_url)
        image_ok = _generate_qrcode_image(qrcode_url, QR_IMAGE_PATH)
        if on_qrcode_ready and not image_ok:
            raise BilibiliLoginError("无法生成二维码图片，请安装: pip install qrcode[pil]")
        if image_ok and open_image:
            print(f"\n二维码图片已保存: {QR_IMAGE_PATH}")
            try:
                import os

                os.startfile(QR_IMAGE_PATH)
            except OSError:
                pass
        elif open_image and not image_ok:
            print("\n（未安装 qrcode 库，请安装: pip install qrcode[pil]）")
        if on_qrcode_ready:
            on_qrcode_ready()
        _emit("waiting", "请使用哔哩哔哩 App 扫描二维码")
        return qrcode_url, qrcode_key

    try:
        if QR_IMAGE_PATH.exists():
            try:
                QR_IMAGE_PATH.unlink()
            except OSError:
                pass
        client.get("https://www.bilibili.com")
        _, qrcode_key = _issue_qrcode()

        if open_image:
            print("\n等待扫码确认", end="", flush=True)
        deadline = time.time() + timeout
        scanned_seen = False
        scanned_notified = False
        while time.time() < deadline:
            _check_cancelled()
            body, poll = _poll_request(client, qrcode_key)
            status = _poll_status(body)
            if status != POLL_WAITING:
                logger.info("扫码轮询 status=%s qrcode_key=%s…", status, qrcode_key[:12])
            else:
                logger.debug("扫码轮询 status=%s", status)

            if status == POLL_SUCCESS:
                _emit("confirming", "已确认，正在完成登录…")
                if open_image:
                    print("\n登录成功！")
                cookies = _collect_login_cookies(client, poll, body)
                if "SESSDATA" not in cookies or "bili_jct" not in cookies:
                    raise BilibiliLoginError("登录未完成，请重新扫码")
                essential = {k: v for k, v in cookies.items() if k in ESSENTIAL_KEYS}
                cookie_str = cookies_to_header(essential or cookies)
                save_cookies(cookie_str)
                _emit("success", "登录成功")
                return cookie_str

            if status == POLL_EXPIRED:
                if scanned_seen:
                    raise BilibiliLoginError("扫码后确认超时，请重新发起登录")
                if auto_refresh_on_expire:
                    _emit("refreshing", "二维码已过期，正在自动刷新…")
                    _, qrcode_key = _issue_qrcode()
                    scanned_seen = False
                    scanned_notified = False
                    time.sleep(1)
                    continue
                raise BilibiliLoginError("二维码已过期，请重新发起登录")

            if status == POLL_SCANNED:
                scanned_seen = True
                if not scanned_notified:
                    scanned_notified = True
                    _emit("scanned", "扫码成功，请在手机上点击「确认登录」")
                if open_image:
                    print(".", end="", flush=True)
                time.sleep(0.3)
                continue

            if status == POLL_WAITING:
                if open_image:
                    print(".", end="", flush=True)
                time.sleep(0.5 if scanned_seen else 1)
                continue

            raise BilibiliLoginError(f"扫码状态异常（{status}），请重试")

        raise BilibiliLoginError(f"登录超时（{int(timeout)} 秒），请重试")
    finally:
        client.close()
