from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from src.bilibili_client import BilibiliClient
from src.lottery_api import extract_activity_heat, fetch_dynamic_detail

_UNSET = object()


@dataclass
class EnrichFetchContext:
    """单条详情 enrich 内复用 dynamic/detail，避免热度与正文重复请求。"""

    client: BilibiliClient
    dynamic_id: str
    preloaded_detail: dict | None = None
    _detail_item: Any = field(default=_UNSET, repr=False)

    def get_detail_item(self) -> dict | None:
        if self._detail_item is not _UNSET:
            return self._detail_item
        if self.preloaded_detail is not None:
            self._detail_item = self.preloaded_detail
            return self.preloaded_detail
        self._detail_item = fetch_dynamic_detail(self.client, self.dynamic_id)
        return self._detail_item

    def attach_repost_count(self, activity: Any) -> Any:
        item = self.get_detail_item()
        if not item:
            self._detail_item = _UNSET
            item = self.get_detail_item()
        if not item:
            raise RuntimeError(f"无法获取活动热度: {activity.dynamic_id}")
        heat, from_reserve = extract_activity_heat(item, lottery_type=activity.lottery_type)
        return replace(
            activity,
            repost_count=heat,
            repost_fetched=True,
            repost_zero_confirmed=heat == 0,
            heat_from_reserve=from_reserve,
        )
