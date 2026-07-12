"""检查 DS-1 哔哩抽奖小助理：对比最新视频链接是否变化，变化则提取简介中的活动链接。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.check_cli import run_check
from src.sources.ds1_xiaozhuli import OUTPUT_PATH, check_update, save_result

if __name__ == "__main__":
    raise SystemExit(
        run_check(
            description="DS-1 哔哩抽奖小助理 — 每日更新检查",
            force_help="忽略已记录的视频链接，强制重新解析最新视频简介",
            no_update_label="最新视频未变化",
            check_update=check_update,
            save_result=save_result,
            output_path=OUTPUT_PATH,
        )
    )
