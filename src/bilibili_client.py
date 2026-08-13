from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import httpx

from src.bilibili_rate_limit import acquire_bilibili_request_slot

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_RATE_LIMIT_CODES = frozenset({-352, -509})


class _ApiError(RuntimeError):
    """B 站 API 业务错误（code 非 0 且非限流）：不参与 retry，直接抛出。

    get_json 中用于把「业务码错误」与「WBI 前置步骤的 RuntimeError（可重试）」
    区分开（#28）。
    """

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]

WBI_FILTER_RE = re.compile(r"[!'()*]")


def api_code(payload: dict) -> int:
    """解析 B 站 API 响应 code；code=0 表示成功（勿用 ``code or -1``，0 会被误判）。"""
    code = payload.get("code")
    if code is None:
        return -1
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def _load_cookie_string() -> str | None:
    from src import app_paths

    env = os.environ.get("BILI_COOKIE", "").strip()
    if env:
        return env
    path = app_paths.cookie_file()
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _load_csrf_token() -> str | None:
    """从当前 Cookie 提取 bili_jct（写操作 CSRF）。"""
    from src.bilibili_auth import get_csrf_token

    return get_csrf_token()


def _load_login_uid() -> int:
    """从当前 Cookie 提取登录 uid；无登录返回 0。"""
    from src.bilibili_auth import get_login_uid

    return get_login_uid() or 0


def _mixin_key(img_key: str, sub_key: str) -> str:
    material = img_key + sub_key
    return "".join(material[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    signed = {k: WBI_FILTER_RE.sub("", str(v)) for k, v in params.items()}
    signed["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((query + _mixin_key(img_key, sub_key)).encode()).hexdigest()
    return signed


class BilibiliClient:
    def __init__(
        self,
        timeout: float = 25.0,
        *,
        warmup: bool = True,
        proxy: str | None = None,
        account_context: object | None = None,
    ) -> None:
        headers = dict(DEFAULT_HEADERS)
        self.account_context = account_context
        if account_context is not None:
            cookie = str(getattr(account_context, "cookie", "") or "").strip() or None
            self._login_uid = int(getattr(account_context, "uid", 0) or 0)
            self._csrf_token = str(getattr(account_context, "csrf", "") or "").strip() or None
            # The captured proxy is part of the execution identity.  Do not
            # re-resolve it after a job has started.
            proxy = getattr(account_context, "proxy_url", None)
        else:
            cookie = _load_cookie_string()
            self._login_uid = None
            self._csrf_token = None
        if cookie:
            headers["Cookie"] = cookie
        if proxy is None:
            from src.bilibili_auth import resolve_effective_uid
            from src.proxy_config import get_proxy_url

            proxy = get_proxy_url(uid=resolve_effective_uid())
        self._client = httpx.Client(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            proxy=proxy,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._img_key: str | None = None
        self._sub_key: str | None = None
        self._http_lock = threading.Lock()
        if warmup:
            self._warmup()

    def require_login(self) -> tuple[str, int]:
        """Return the identity used by this client, without consulting globals."""
        csrf = self.csrf_token
        uid = int(self.login_uid or 0)
        if not csrf or not uid:
            raise RuntimeError("当前未登录，无法执行需要登录的操作")
        return csrf, uid

    @property
    def login_uid(self) -> int:
        if self.account_context is not None:
            return int(self._login_uid or 0)
        return _load_login_uid()

    @property
    def csrf_token(self) -> str | None:
        if self.account_context is not None:
            return self._csrf_token
        return _load_csrf_token()

    def _warmup(self) -> None:
        try:
            self._http_get("https://www.bilibili.com")
            if "buvid3" not in self._client.cookies:
                self._client.cookies.set(
                    "buvid3",
                    f"{uuid.uuid4().hex}infoc",
                    domain=".bilibili.com",
                )
        except httpx.HTTPError:
            pass

    def _http_get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        acquire_bilibili_request_slot()
        with self._http_lock:
            return self._client.get(url, params=params or {}, headers=headers)

    def _http_post(
        self,
        url: str,
        *,
        data: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        acquire_bilibili_request_slot()
        with self._http_lock:
            return self._client.post(
                url,
                params=params or {},
                data=data,
                json=json,
                headers=headers,
            )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BilibiliClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _reset_wbi_keys(self) -> None:
        self._img_key = None
        self._sub_key = None

    def _ensure_wbi_keys(self) -> None:
        if self._img_key and self._sub_key:
            return
        resp = self._http_get("https://api.bilibili.com/x/web-interface/nav")
        resp.raise_for_status()
        data = resp.json()
        wbi = (data.get("data") or {}).get("wbi_img") or {}
        img = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
        sub = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
        if not img or not sub:
            raise RuntimeError("无法获取 WBI 签名密钥")
        self._img_key, self._sub_key = img, sub

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        *,
        wbi: bool = False,
        referer: str | None = None,
        retries: int = 3,
    ) -> dict:
        """请求 JSON 并校验 B 站业务 code。

        尝试循环统一 retry 语义（#28）：WBI 前置步骤（nav 请求/签名密钥）、
        HTTP GET、JSON 解析、业务码检查整体包进同一个 try，nav 失败
        （httpx 异常或 RuntimeError）与 HTTP GET 失败一样参与 retry。
        """
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            req_params = dict(params or {})
            headers = {"Referer": referer} if referer else None
            try:
                if wbi:
                    if attempt > 0:
                        self._reset_wbi_keys()
                    self._ensure_wbi_keys()
                    req_params = wbi_sign(req_params, self._img_key, self._sub_key)
                resp = self._http_get(url, params=req_params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                code = data.get("code")
                if code in (0, None):
                    return data
                if code in (-352, -509, -799) and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {data.get('message')}")
                    continue
                raise _ApiError(f"API error {code}: {data.get('message')}")
            except _ApiError:
                # 业务码错误（非限流）：不参与 retry，保持原语义直接抛出
                raise
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
            except RuntimeError as exc:
                # WBI 前置步骤失败（nav 请求失败/密钥缺失，含测试替身）：
                # 与 HTTP GET 同一 retry 语义（#28）
                last_error = exc
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def request_json(self, url: str, params: dict | None = None, *, referer: str | None = None, retries: int = 3) -> dict:
        """请求 JSON 但不因业务 code 非 0 抛错（供 lottery_notice 等接口使用）。"""
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_get(url, params=params or {}, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < retries and (
                    isinstance(exc, httpx.RequestError)
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise RuntimeError("响应不是有效 JSON") from exc
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def post_form(
        self,
        url: str,
        data: dict,
        *,
        referer: str | None = None,
        retries: int = 3,
        raise_on_code: bool = True,
    ) -> dict:
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_post(url, data=data, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                code = payload.get("code")
                if code in (0, None):
                    return payload
                if not raise_on_code and code not in _RATE_LIMIT_CODES:
                    return payload
                if code in _RATE_LIMIT_CODES and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {payload.get('message')}")
                    continue
                if raise_on_code:
                    message = payload.get("message") or payload.get("msg") or ""
                    raise RuntimeError(f"API error {code}: {message}")
                return payload
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                if isinstance(exc, json.JSONDecodeError):
                    raise RuntimeError("响应不是有效 JSON") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def post_json(
        self,
        url: str,
        payload: dict,
        *,
        params: dict | None = None,
        referer: str | None = None,
        retries: int = 3,
        raise_on_code: bool = True,
    ) -> dict:
        headers = {"Referer": referer, "Content-Type": "application/json"} if referer else {
            "Content-Type": "application/json"
        }
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_post(url, params=params or {}, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                code = data.get("code")
                if code in (0, None):
                    return data
                if not raise_on_code and code not in _RATE_LIMIT_CODES:
                    return data
                if code in _RATE_LIMIT_CODES and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {data.get('message')}")
                    continue
                if raise_on_code:
                    message = data.get("message") or data.get("msg") or ""
                    raise RuntimeError(f"API error {code}: {message}")
                return data
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                if isinstance(exc, json.JSONDecodeError):
                    raise RuntimeError("响应不是有效 JSON") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def get_text(self, url: str, *, referer: str | None = None, retries: int = 3) -> str:
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_get(url, headers=headers)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def get_latest_video(self, mid: int) -> dict:
        referer = f"https://space.bilibili.com/{mid}/video"
        params = {
            "mid": mid,
            "pn": 1,
            "ps": 1,
            "tid": 0,
            "order": "pubdate",
            "platform": "web",
        }
        errors: list[str] = []
        try:
            data = self.get_json(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=params,
                wbi=True,
                referer=referer,
            )
            vlist = (data.get("data") or {}).get("list", {}).get("vlist") or []
            if vlist:
                return vlist[0]
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            errors.append(str(exc))

        try:
            return self._get_latest_video_fallback(mid, referer=referer)
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            errors.append(str(exc))
            raise RuntimeError(
                "获取最新视频失败（B 站风控 -352/-412）。\n"
                "请将浏览器 Cookie 保存到 config/cookies.txt 后重试。\n"
                "参考 config/cookies.txt.example\n"
                + "\n".join(errors)
            ) from exc

    def _get_latest_video_fallback(self, mid: int, *, referer: str) -> dict:
        """WBI 风控时，尝试旧接口（有 Cookie 时通常可用）。"""
        data = self.get_json(
            "https://api.bilibili.com/x/space/arc/search",
            params={"mid": mid, "pn": 1, "ps": 1, "order": "pubdate"},
            referer=referer,
        )
        vlist = (data.get("data") or {}).get("list", {}).get("vlist") or []
        if not vlist:
            raise RuntimeError("未找到该 UP 的投稿视频")
        return vlist[0]

    def get_video_detail(self, bvid: str) -> dict:
        referer = f"https://www.bilibili.com/video/{bvid}"
        try:
            data = self.get_json(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                referer=referer,
            )
            detail = data.get("data")
            if detail:
                return detail
        except RuntimeError:
            pass
        return self._get_video_detail_from_page(bvid, referer=referer)

    def _get_video_detail_from_page(self, bvid: str, *, referer: str) -> dict:
        html = self.get_text(f"https://www.bilibili.com/video/{bvid}", referer=referer)
        state_match = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
            html,
            re.S,
        )
        if not state_match:
            raise RuntimeError(f"无法从视频页解析详情: {bvid}")
        state = json.loads(state_match.group(1))
        video_data = state.get("videoData") or {}
        if not video_data:
            raise RuntimeError(f"无法从视频页解析详情: {bvid}")
        return video_data

    def get_latest_article(self, mid: int) -> dict:
        return self.get_recent_articles(mid, limit=1)[0]

    def get_recent_articles(self, mid: int, *, limit: int = 2) -> list[dict]:
        referer = f"https://space.bilibili.com/{mid}/upload/opus"
        data = self.get_json(
            "https://api.bilibili.com/x/space/article",
            params={"mid": mid, "pn": 1, "ps": max(1, limit), "sort": "publish_time"},
            referer=referer,
        )
        articles = (data.get("data") or {}).get("articles") or []
        if not articles:
            raise RuntimeError("未找到该 UP 的专栏文章")
        return articles[:limit]

    def get_article_detail(self, cv_id: int) -> dict:
        referer = f"https://www.bilibili.com/read/cv{cv_id}"
        data = self.get_json(
            "https://api.bilibili.com/x/article/view",
            params={"id": cv_id},
            referer=referer,
        )
        detail = data.get("data")
        if not detail:
            raise RuntimeError(f"无法获取专栏详情: cv{cv_id}")
        return detail

    def get_tag_id(self, tag_name: str) -> int | None:
        """按话题名查询 tag_id（P1-3 话题源）；失败返回 None。"""
        try:
            data = self.request_json(
                "https://api.bilibili.com/x/tag/info",
                params={"tag_name": tag_name},
                referer="https://t.bilibili.com/",
            )
        except RuntimeError:
            return None
        if api_code(data) != 0:
            return None
        tag_id = (data.get("data") or {}).get("tag_id")
        try:
            return int(tag_id) if tag_id else None
        except (TypeError, ValueError):
            return None

    def get_topic_new(self, topic_name: str) -> dict | None:
        """拉取话题热门动态页（topic/new，含一条最新），失败返回 None。"""
        try:
            data = self.request_json(
                "https://api.vc.bilibili.com/topic_svr/v1/topic_svr/topic_new",
                params={"topic_name": topic_name},
                referer="https://t.bilibili.com/",
            )
        except RuntimeError:
            return None
        if api_code(data) != 0:
            return None
        return data.get("data") or {}

    def get_topic_history(
        self,
        topic_name: str,
        *,
        offset_dynamic_id: str = "",
        page_size: int = 20,
    ) -> dict | None:
        """拉取话题历史动态页（topic/history），失败返回 None。"""
        params: dict[str, object] = {"topic_name": topic_name, "page_size": page_size}
        if offset_dynamic_id:
            params["offset_dynamic_id"] = offset_dynamic_id
        try:
            data = self.request_json(
                "https://api.vc.bilibili.com/topic_svr/v1/topic_svr/topic_history",
                params=params,
                referer="https://t.bilibili.com/",
            )
        except RuntimeError:
            return None
        if api_code(data) != 0:
            return None
        return data.get("data") or {}

    # ------------------------------------------------------------------
    # Line 多线路容灾（源自 LAS）
    # ------------------------------------------------------------------

    def get_user_followers(self, uid: int) -> int | None:
        """查询用户粉丝数：card → relation/stat 两线自动切换（Line 容灾）。

        返回粉丝数，全部失败返回 None。
        """
        from src.line import Line

        def _via_card() -> int | None:
            data = self.request_json(
                "https://api.bilibili.com/x/web-interface/card",
                params={"mid": uid},
                referer="https://space.bilibili.com/",
            )
            card = (data.get("data") or {}).get("card") or {}
            try:
                fans = int(card.get("fans"))
                return fans or None
            except (TypeError, ValueError):
                return None

        def _via_stat() -> int | None:
            data = self.request_json(
                "https://api.bilibili.com/x/relation/stat",
                params={"vmid": uid},
                referer="https://space.bilibili.com/",
            )
            stat = data.get("data") or {}
            try:
                fans = int(stat.get("follower"))
                return fans or None
            except (TypeError, ValueError):
                return None

        return Line("get_user_followers", [_via_card, _via_stat], fallback=None).run()

    # ------------------------------------------------------------------
    # 关注分区管理（源自 LAS partition 机制）
    # ------------------------------------------------------------------

    def get_relation_tags(self) -> list[dict]:
        """获取全部关注分区列表（[{tagid, name, count}]）。"""
        try:
            data = self.request_json(
                "https://api.bilibili.com/x/relation/tags",
                referer="https://space.bilibili.com/",
            )
        except RuntimeError:
            return []
        tags = data.get("data")
        return tags if isinstance(tags, list) else []

    def create_relation_tag(self, name: str) -> int | None:
        """创建关注分区，返回 tagid；失败返回 None。"""
        csrf = self.csrf_token
        if not csrf:
            return None
        try:
            payload = self.post_form(
                "https://api.bilibili.com/x/relation/tag/create",
                {"tag": name, "csrf": csrf},
                referer="https://space.bilibili.com/",
                raise_on_code=False,
            )
        except RuntimeError:
            return None
        data = payload.get("data") or {}
        try:
            return int(data.get("tagid"))
        except (TypeError, ValueError):
            return None

    def move_to_relation_tag(self, uid: int, tagid: int) -> bool:
        """把用户移入关注分区。返回是否成功（已在该分区也视为成功）。"""
        csrf = self.csrf_token
        if not csrf:
            return False
        try:
            payload = self.post_form(
                "https://api.bilibili.com/x/relation/tags/addUsers",
                {"tag_id": tagid, "uids": uid, "csrf": csrf},
                referer="https://space.bilibili.com/",
                raise_on_code=False,
            )
        except RuntimeError:
            return False
        return api_code(payload) == 0

    def get_partition_uids(self, tagid: int, *, pn: int = 1, ps: int = 50) -> list[int]:
        """分页读取分区内用户 uid 列表。"""
        try:
            data = self.request_json(
                "https://api.bilibili.com/x/relation/tag",
                params={"tagid": tagid, "pn": pn, "ps": ps},
                referer="https://space.bilibili.com/",
            )
        except RuntimeError:
            return []
        data = data.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else []
        uids: list[int] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                uids.append(int(item.get("mid")))
            except (TypeError, ValueError):
                continue
        return uids

    # ------------------------------------------------------------------
    # 清理（源自 LAS clear）
    # ------------------------------------------------------------------

    def get_my_space_feed(self, offset: str = "") -> dict | None:
        """分页读取自己的空间动态（feed/space），失败返回 None。"""
        params: dict[str, object] = {"host_mid": self.login_uid, "timezone_offset": -480}
        if offset:
            params["offset"] = offset
        try:
            data = self.get_json(
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
                params=params,
                wbi=True,
                referer="https://space.bilibili.com/",
                retries=2,
            )
        except RuntimeError:
            return None
        return data.get("data") if isinstance(data, dict) else None

    def delete_dynamic(self, dynamic_id: str) -> bool:
        """删除自己的动态。返回是否成功。"""
        csrf = self.csrf_token
        if not csrf:
            return False
        try:
            payload = self.post_form(
                "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/rm_dynamic",
                {"dynamic_id": dynamic_id, "csrf": csrf},
                referer="https://space.bilibili.com/",
                raise_on_code=False,
            )
        except RuntimeError:
            return False
        return api_code(payload) == 0

    def cancel_attention(self, uid: int) -> bool:
        """取关用户（relation/modify act=2）。返回是否成功。"""
        csrf = self.csrf_token
        if not csrf:
            return False
        try:
            payload = self.post_form(
                "https://api.bilibili.com/x/relation/modify",
                {"fid": uid, "act": 2, "csrf": csrf},
                referer="https://space.bilibili.com/",
                raise_on_code=False,
            )
        except RuntimeError:
            return False
        return api_code(payload) == 0
