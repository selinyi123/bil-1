"""定时点击调度器配置（仅允许 4 个按钮 action）。"""

from __future__ import annotations

REFRESH_HOURS = frozenset({0, 3, 6, 9, 12, 15, 18, 21})
TRIPLE_MINUTES = frozenset(range(5, 60, 5))

ALLOWED_CLICK_ACTIONS = frozenset(
    {
        "refresh_all",
        "refresh_watch",
        "refresh_status",
        "participate_triple",
    }
)

ACTION_LABELS = {
    "refresh_all": "一键更新活动链接",
    "refresh_watch": "更新监控用户动态",
    "refresh_status": "刷新任务状态",
    "participate_triple": "三连参与",
}

JOB_POLL_INTERVAL_SEC = 2.0
JOB_POLL_TIMEOUT_SEC = 6 * 60 * 60
