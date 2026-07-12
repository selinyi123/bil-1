from __future__ import annotations

import time
import urllib.parse
from http.cookies import SimpleCookie
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
COOKIE_PATH = ROOT / "config" / "cookies.txt"
QR_IMAGE_PATH = ROOT / "data" / "login_qrcode.png"

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


def _poll_status(body: dict) -> int:
    """扫码状态在 data.code，不是顶层 code。"""
    data = body.get("data") or {}
    if isinstance(data.get("code"), int):
        return int(data["code"])
    return int(body.get("code", -1))


def _parse_set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    jar: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        sc = SimpleCookie()
        sc.load(header)
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
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(cookie_str.strip(), encoding="utf-8")
    return COOKIE_PATH


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
    cross_url = data.get("url") or ""

    cookies = _merge_cookies(
        _parse_set_cookie_headers(poll),
        _parse_cross_domain_url(cross_url),
        _cookies_from_jar(client),
    )

    if cross_url:
        try:
            client.get(cross_url)
            cookies = _merge_cookies(cookies, _cookies_from_jar(client))
        except httpx.HTTPError:
            pass

    try:
        client.get("https://www.bilibili.com")
        client.get("https://api.bilibili.com/x/web-interface/nav")
        cookies = _merge_cookies(cookies, _cookies_from_jar(client))
    except httpx.HTTPError:
        pass

    return cookies


def login_with_qrcode(*, timeout: float = 180.0) -> str:
    client = httpx.Client(headers=PASSPORT_HEADERS, follow_redirects=True, timeout=20.0)
    try:
        client.get("https://www.bilibili.com")

        gen = client.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            params={"source": "main-fe-header"},
        )
        gen.raise_for_status()
        gen_data = gen.json()
        if gen_data.get("code") != 0:
            raise BilibiliLoginError(f"获取二维码失败: {gen_data.get('message')}")

        qrcode_url = gen_data["data"]["url"]
        qrcode_key = gen_data["data"]["qrcode_key"]

        print("请使用哔哩哔哩手机 App 扫描下方二维码登录：")
        print(qrcode_url)

        if _generate_qrcode_image(qrcode_url, QR_IMAGE_PATH):
            print(f"\n二维码图片已保存: {QR_IMAGE_PATH}")
            try:
                import os
                os.startfile(QR_IMAGE_PATH)
            except OSError:
                pass
        else:
            print("\n（未安装 qrcode 库，请安装: pip install qrcode[pil]）")

        print("\n等待扫码确认", end="", flush=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            poll = client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key, "source": "main-fe-header"},
            )
            poll.raise_for_status()
            body = poll.json()
            status = _poll_status(body)

            if status == POLL_SUCCESS:
                print("\n登录成功！")
                cookies = _collect_login_cookies(client, poll, body)
                if "SESSDATA" not in cookies:
                    raise BilibiliLoginError(
                        "未能提取 SESSDATA。"
                        "请重新运行 python scripts/bili_login.py 再扫一次。"
                    )
                essential = {k: v for k, v in cookies.items() if k in ESSENTIAL_KEYS}
                cookie_str = cookies_to_header(essential or cookies)
                save_cookies(cookie_str)
                return cookie_str

            if status == POLL_EXPIRED:
                raise BilibiliLoginError("二维码已过期，请重新运行登录脚本")

            if status == POLL_SCANNED:
                print(".", end="", flush=True)
                time.sleep(1)
                continue

            if status == POLL_WAITING:
                print(".", end="", flush=True)
                time.sleep(2)
                continue

            raise BilibiliLoginError(
                f"未知扫码状态 data.code={status} message={body.get('message')}"
            )

        raise BilibiliLoginError(f"登录超时（{int(timeout)} 秒），请重试")
    finally:
        client.close()
