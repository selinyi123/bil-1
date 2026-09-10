"""Immutable execution identity captured for one account-bound job.

The context is intentionally a small runtime value object.  It is not a
configuration container and it must never be serialized into job rows, SSE
events, logs, or result payloads.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field

from src import app_paths
from src.proxy_config import get_proxy_url


_UID_RE = re.compile(r"(?:^|[;\s])DedeUserID=(\d+)(?:;|\s|$)")
_CSRF_RE = re.compile(r"(?:^|[;\s])bili_jct=([^;\s]+)")


class AccountContextUnavailable(RuntimeError):
    """The current login material cannot be safely bound to the requested UID."""


@dataclass(frozen=True, slots=True)
class AccountContext:
    """A secret-bearing, immutable snapshot used only during one execution."""

    uid: int
    cookie: str = field(repr=False, compare=False)
    csrf: str = field(repr=False, compare=False)
    proxy_url: str | None = field(default=None, repr=False, compare=False)
    cookie_source: str = "unknown"
    proxy_source: str = "none"
    cookie_fingerprint: str = ""
    captured_at: int = 0

    @property
    def login_uid(self) -> int:
        return self.uid

    @property
    def csrf_token(self) -> str:
        return self.csrf


def parse_cookie_uid(cookie: str) -> int | None:
    match = _UID_RE.search(cookie or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_cookie_csrf(cookie: str) -> str | None:
    match = _CSRF_RE.search(cookie or "")
    value = match.group(1).strip() if match else ""
    return value or None


def _proxy_source(uid: int, proxy_url: str | None) -> str:
    if not proxy_url:
        return "none"
    from src.account_pool import get_account_proxy
    from src.proxy_config import get_env_proxy_url, get_global_proxy_url

    if get_env_proxy_url() == proxy_url:
        return "env"
    if get_account_proxy(uid) == proxy_url:
        return "account"
    if get_global_proxy_url() == proxy_url:
        return "global"
    return "resolved"


def _require_bound_uid(expected_uid: int | str) -> int:
    try:
        bound_uid = int(expected_uid)
    except (TypeError, ValueError) as exc:
        raise AccountContextUnavailable("invalid bound account uid") from exc
    if bound_uid <= 0:
        raise AccountContextUnavailable("invalid bound account uid")
    return bound_uid


def _build_context(*, bound_uid: int, cookie: str, cookie_source: str) -> AccountContext:
    """校验 cookie 属于 bound_uid 且材料完整，然后冻成快照。

    两条捕获路径共用这一段：UID 不符或缺 CSRF 一律 fail-closed，绝不带着
    错误身份去发请求（SPEC §8 不变量 #4）。
    """
    cookie_uid = parse_cookie_uid(cookie)
    csrf = parse_cookie_csrf(cookie)
    if cookie_uid is None or not csrf:
        raise AccountContextUnavailable("login cookie is incomplete")
    if cookie_uid != bound_uid:
        raise AccountContextUnavailable(
            f"bound account uid mismatch: expected={bound_uid}, cookie={cookie_uid}"
        )

    proxy_url = get_proxy_url(uid=bound_uid)
    return AccountContext(
        uid=bound_uid,
        cookie=cookie,
        csrf=csrf,
        proxy_url=proxy_url,
        cookie_source=cookie_source,
        proxy_source=_proxy_source(bound_uid, proxy_url),
        cookie_fingerprint=hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16],
        captured_at=int(time.time()),
    )


def capture_current_account_context(*, expected_uid: int | str) -> AccountContext:
    """Capture current cookie/proxy once and fail closed on UID mismatch.

    Reads the materialized ``config/cookies.txt`` (or the ``BILI_COOKIE``
    override), i.e. the *active* account.  Rotation must not use this path:
    see :func:`capture_account_context_for_uid`.
    """
    bound_uid = _require_bound_uid(expected_uid)

    from src.bilibili_client import _load_cookie_string

    cookie = (_load_cookie_string() or "").strip()
    cookie_source = "env" if os.environ.get("BILI_COOKIE", "").strip() else "cookies.txt"
    return _build_context(bound_uid=bound_uid, cookie=cookie, cookie_source=cookie_source)


def capture_account_context_for_uid(expected_uid: int | str) -> AccountContext:
    """按 uid 直接从账号池取凭据，不经过 cookies.txt，也不改变活跃账号。

    串行轮转用这条路径：后台轮到账号 B 时不该把 UI 顶部的身份也切成 B，
    更不该反复重写 cookies.txt。`BILI_COOKIE` 环境变量在此**不参与**——
    env 覆盖表达的是"所有请求都用这个身份"，与逐账号轮转互相排斥，
    调用方（调度器）负责在 env 生效时不启用轮转。
    """
    bound_uid = _require_bound_uid(expected_uid)

    path = app_paths.accounts_dir() / f"{bound_uid}.txt"
    if not path.exists():
        raise AccountContextUnavailable(f"account {bound_uid} is not in the pool")
    try:
        cookie = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise AccountContextUnavailable(f"cannot read account {bound_uid}") from exc

    return _build_context(bound_uid=bound_uid, cookie=cookie, cookie_source="account_pool")
