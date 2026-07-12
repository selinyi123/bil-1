"""检查 DS-5 互动抽奖娘：对比最新 Opus 帖是否变化，变化则提取正文中的活动链接。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.check_cli import run_check
from src.sources.ds5_hudong import OUTPUT_PATH, check_update, save_result

if __name__ == "__main__":
    raise SystemExit(
        run_check(
            description="DS-5 互动抽奖娘 — 每日更新检查",
            force_help="忽略已记录的 Opus 帖链接，强制重新解析最新正文",
            no_update_label="最新 Opus 帖未变化",
            check_update=check_update,
            save_result=save_result,
            output_path=OUTPUT_PATH,
        )
    )
