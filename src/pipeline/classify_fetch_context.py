from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.bilibili_client import BilibiliClient
from src.dead_links import is_dynamic_detail_permanently_gone
from src.forward_parser import (
    CLASSIFY_MIN_CONTENT_LEN,
    _extract_from_detail_item,
    fetch_dynamic_content_with_retry,
)
from src.lottery_api import (
    _fetch_opus_detail_item,
    _normalize_dynamic_item,
    fetch_lottery_notice,
    is_detail_api_enabled,
    probe_dynamic_detail_api,
    resolve_reserve_business,
)
from src.lottery_classifier import (
    _has_reserve_from_page,
    _is_live_stream_reserve_only,
)
from src.sources.common import opus_link

_UNSET = object()


@dataclass
class ClassifyFetchContext:
    """单条分类内复用 dynamic/detail 与预约 notice 查询，不改变判定顺序与结果。"""

    client: BilibiliClient
    dynamic_id: str
    _additional: Any = field(default=_UNSET, repr=False)
    _detail_api_item: Any = field(default=_UNSET, repr=False)
    _detail_api_code: Any = field(default=_UNSET, repr=False)
    _detail_api_message: Any = field(default=_UNSET, repr=False)
    _detail_api_extra_attempted: bool = field(default=False, repr=False)
    _detail_item: Any = field(default=_UNSET, repr=False)
    _reserve_lottery_notice: Any = field(default=_UNSET, repr=False)
    _reserve_notice_resolved: Any = field(default=_UNSET, repr=False)
    _resolved_content: str = field(default="", repr=False)

    def _fetch_detail_api_item(self, *, retries: int) -> dict | None:
        if not is_detail_api_enabled():
            self._detail_api_code = None
            self._detail_api_message = ""
            return None
        item, code, message = probe_dynamic_detail_api(
            self.client,
            self.dynamic_id,
            retries=retries,
        )
        self._detail_api_code = code
        self._detail_api_message = message
        return item or None

    def _ensure_detail_api_item(self) -> dict | None:
        if self._detail_api_item is not _UNSET:
            return self._detail_api_item
        self._detail_api_item = self._fetch_detail_api_item(retries=2)
        return self._detail_api_item

    def is_deleted_link(self) -> bool:
        self._ensure_detail_api_item()
        if self._detail_api_item is not _UNSET and self._detail_api_item is not None:
            return False
        code = None if self._detail_api_code is _UNSET else self._detail_api_code
        message = "" if self._detail_api_message is _UNSET else str(self._detail_api_message or "")
        return is_dynamic_detail_permanently_gone(
            item=None if self._detail_api_item is _UNSET else self._detail_api_item,
            code=code,
            message=message,
        )

    def get_additional(self) -> dict | None:
        if self._additional is not _UNSET:
            return self._additional
        if not is_detail_api_enabled():
            self._additional = None
            return None
        item = self._ensure_detail_api_item()
        if item is None:
            self._additional = None
            return None
        module_dynamic = (item.get("modules") or {}).get("module_dynamic") or {}
        self._additional = module_dynamic.get("additional") or {}
        return self._additional

    def get_detail_item(self) -> dict | None:
        if self._detail_item is not _UNSET:
            return self._detail_item
        item = self._ensure_detail_api_item()
        if not item and not self._detail_api_extra_attempted:
            self._detail_api_extra_attempted = True
            item = self._fetch_detail_api_item(retries=1)
            if item:
                self._detail_api_item = item
        if not item:
            item = _fetch_opus_detail_item(self.client, self.dynamic_id)
        if not item:
            self._detail_item = None
            return None
        self._detail_item = _normalize_dynamic_item(item)
        return self._detail_item

    def resolve_reserve_lottery_notice(self) -> tuple[dict, str, int] | None:
        if self._reserve_notice_resolved is not _UNSET:
            cached = self._reserve_notice_resolved
            return cached if cached else None
        resolved_business = resolve_reserve_business(
            self.client,
            self.dynamic_id,
            detail_item=self.get_detail_item(),
        )
        if not resolved_business:
            self._reserve_notice_resolved = None
            self._reserve_lottery_notice = False
            return None
        business_id, business_type = resolved_business
        notice = fetch_lottery_notice(
            self.client,
            business_id=business_id,
            business_type=business_type,
            referer=opus_link(self.dynamic_id),
            retries=2,
        )
        if notice and notice.get("lottery_id"):
            bundle = (notice, business_id, business_type)
            self._reserve_notice_resolved = bundle
            self._reserve_lottery_notice = True
            return bundle
        self._reserve_notice_resolved = None
        self._reserve_lottery_notice = False
        return None

    def has_reserve_lottery_notice(self) -> bool:
        if self._reserve_lottery_notice is not _UNSET:
            return self._reserve_lottery_notice
        return self.resolve_reserve_lottery_notice() is not None

    def classify_detail_snapshot(self) -> dict | None:
        return self.get_detail_item() or self._cached_detail_for_content()

    def _cached_detail_for_content(self) -> dict | None:
        if self._detail_item is not _UNSET:
            return self._detail_item
        if self._detail_api_item is not _UNSET and self._detail_api_item is not None:
            code = None if self._detail_api_code is _UNSET else self._detail_api_code
            if code == 0:
                return self._detail_api_item
        return None

    def classify_reserve_candidate(
        self,
        additional: dict | None,
    ) -> Literal["预约抽奖", "skip", "not_reserve"]:
        reserve = (additional or {}).get("reserve") if additional else None
        has_reserve_block = bool(reserve)
        if not has_reserve_block:
            if additional is not None:
                return "not_reserve"
            if not _has_reserve_from_page(self.client, self.dynamic_id):
                return "not_reserve"

        reserve = reserve or {}
        if reserve and _is_live_stream_reserve_only(reserve) and not self.has_reserve_lottery_notice():
            return "skip"
        if self.has_reserve_lottery_notice():
            return "预约抽奖"
        return "not_reserve"

    def _extract_cached_classify_content(self) -> str:
        detail_item = self._cached_detail_for_content()
        if not detail_item:
            return ""
        text = _extract_from_detail_item(detail_item).strip()
        if len(text) >= CLASSIFY_MIN_CONTENT_LEN:
            return text
        return ""

    def resolve_classify_content(self) -> str:
        """优先复用已拉取的 dynamic/detail 正文，避免分类阶段二次抓取。"""
        if self._resolved_content:
            return self._resolved_content
        cached = self._extract_cached_classify_content()
        if cached:
            self._resolved_content = cached
            return cached
        self._resolved_content = self.fetch_content_with_retry()
        return self._resolved_content

    def fetch_content_with_retry(self) -> str:
        return fetch_dynamic_content_with_retry(
            self.client,
            self.dynamic_id,
            initial_detail_item=self._cached_detail_for_content(),
        )
