"""E2E 最小种子：活动 + llm.env。"""

from __future__ import annotations

import time
from pathlib import Path


def assert_safe_e2e_home(home: Path, root: Path) -> None:
    """拒绝指向仓库根或 data/（及其子目录）的 HOME，防止污染开发库。"""
    home_r = home.resolve()
    root_r = root.resolve()
    data_r = (root_r / "data").resolve()
    if home_r == root_r:
        raise ValueError("BINGGO_HOME 不能指向仓库根目录")
    if home_r == data_r:
        raise ValueError("BINGGO_HOME 不能指向仓库 data/ 目录")
    try:
        home_r.relative_to(data_r)
    except ValueError:
        return
    raise ValueError("BINGGO_HOME 不能位于仓库 data/ 之下")


def seed_activities() -> int:
    from src.activity_store import replace_all_activities

    now = int(time.time())
    items = [
        {
            "dynamic_id": "1111111111111111111",
            "source_url": "https://t.bilibili.com/1111111111111111111",
            "activity_title": "E2E 互动抽奖奖品",
            "prize": "E2E 互动奖品",
            "lottery_type": "互动抽奖",
            "draw_status": "active",
            "activity_status": "未参加",
            "lottery_time": now + 86_400,
            "can_participate": True,
            "repost_count": 10,
            "status_classified": True,
        },
        {
            "dynamic_id": "2222222222222222222",
            "source_url": "https://t.bilibili.com/2222222222222222222",
            "activity_title": "E2E 转发抽奖奖品",
            "prize": "E2E 转发奖品",
            "lottery_type": "转发抽奖",
            "draw_status": "active",
            "activity_status": "已参加",
            "lottery_time": now + 7_200,
            "platform_participated": True,
            "can_participate": False,
            "repost_count": 20,
            "status_classified": True,
        },
        {
            "dynamic_id": "3333333333333333333",
            "source_url": "https://t.bilibili.com/3333333333333333333",
            "activity_title": "E2E 预约抽奖奖品",
            "prize": "E2E 预约奖品",
            "lottery_type": "预约抽奖",
            "draw_status": "ended",
            "activity_status": "已结束",
            "lottery_time": now - 3_600,
            "can_participate": False,
            "repost_count": 5,
            "status_classified": True,
        },
    ]
    replace_all_activities(items)
    return len(items)


def write_llm_env(config_dir: Path, *, ready: bool = True) -> None:
    """写入与 src.llm_settings 指纹算法一致的 llm.env。"""
    from src.llm_settings import _config_fingerprint

    config_dir.mkdir(parents=True, exist_ok=True)
    api_key = "e2e-test-key-not-real"
    base_url = "https://example.invalid/api/v1"
    model_name = "DeepSeek-V4-Flash"
    if ready:
        fp = _config_fingerprint(api_key, base_url, model_name)
        passed = "true"
    else:
        fp = ""
        passed = "false"
    (config_dir / "llm.env").write_text(
        "\n".join(
            [
                f"LLM_API_KEY={api_key}",
                f"LLM_BASE_URL={base_url}",
                f"LLM_MODEL_NAME={model_name}",
                f"LLM_TEST_PASSED={passed}",
                f"LLM_TEST_FINGERPRINT={fp}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def seed_e2e_home(home: Path) -> None:
    """在已设置 BINGGO_HOME 且可 import 项目模块后调用。"""
    from src.app_paths import CONFIG_DIR, USER_HOME, ensure_user_dirs
    from src.db.engine import db_path, reset_engine_for_tests
    from src.db.schema import init_db
    from web.e2e_hooks import set_e2e_state

    home = home.resolve()
    ensure_user_dirs()
    # 首轮 import 的 USER_HOME/CONFIG_DIR 必须与本次 HOME 一致
    if USER_HOME.resolve() != home:
        raise RuntimeError(
            f"BINGGO_HOME 与 app_paths.USER_HOME 不一致：env={home} bound={USER_HOME.resolve()}。"
            "请确保在首次 import src.app_paths 之前设置 BINGGO_HOME。"
        )
    if CONFIG_DIR.resolve() != (home / "config").resolve():
        raise RuntimeError(f"CONFIG_DIR 未落在 HOME 下：{CONFIG_DIR}")

    reset_engine_for_tests()
    init_db()
    resolved = db_path().resolve()
    assert resolved.is_relative_to(home), resolved
    count = seed_activities()
    write_llm_env(CONFIG_DIR, ready=True)
    set_e2e_state(account="logged_out", llm="not_ready")
    print(f"E2E seed: activities={count} db={resolved}", flush=True)
