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


def capture_current_account_context(*, expected_uid: int | str) -> AccountContext:
    """Capture current cookie/proxy once and fail closed on UID mismatch.

    The current cookie source remains compatible with the legacy materialized
    ``config/cookies.txt`` contract.  A future account-switching slice can add
    a direct ``capture_account_context_for_uid`` path without changing this
    value object or its consumers.
    """
    try:
        bound_uid = int(expected_uid)
    except (TypeError, ValueError) as exc:
        raise AccountContextUnavailable("invalid bound account uid") from exc
    if bound_uid <= 0:
        raise AccountContextUnavailable("invalid bound account uid")

    from src.bilibili_client import _load_cookie_string

    cookie = (_load_cookie_string() or "").strip()
    cookie_source = "env" if os.environ.get("BILI_COOKIE", "").strip() else "cookies.txt"
    current_uid = parse_cookie_uid(cookie)
    csrf = parse_cookie_csrf(cookie)
    if current_uid is None or not csrf:
        raise AccountContextUnavailable("current login cookie is incomplete")
    if current_uid != bound_uid:
        raise AccountContextUnavailable(
            f"bound account uid mismatch: expected={bound_uid}, cookie={current_uid}"
        )

    proxy_url = get_proxy_url(uid=bound_uid)
    fingerprint = hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16]
    return AccountContext(
        uid=bound_uid,
        cookie=cookie,
        csrf=csrf,
        proxy_url=proxy_url,
        cookie_source=cookie_source,
        proxy_source=_proxy_source(bound_uid, proxy_url),
        cookie_fingerprint=fingerprint,
        captured_at=int(time.time()),
    )
