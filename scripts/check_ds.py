"""检查某个 UP 合集（DS-1…DS-7）：对比最新容器是否变化，变化则提取活动链接。

用法：
  python scripts/check_ds.py 1
  python scripts/check_ds.py 5 --force
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sources.common import commit_source_checkpoint  # noqa: E402

# 容器类型只有三种，「未变化」提示按类型走
NO_UPDATE_LABEL = {
    "video": "最新视频未变化",
    "cv": "最新专栏未变化",
    "opus": "最新 Opus 帖未变化",
}

SOURCES = {
    1: ("ds1_xiaozhuli", "哔哩抽奖小助理", "video"),
    2: ("ds2_fanqiao", "番茄薯条喵", "cv"),
    3: ("ds3_gongjuren", "你的抽奖工具人", "cv"),
    4: ("ds4_junming", "J君名", "cv"),
    5: ("ds5_hudong", "互动抽奖娘", "opus"),
    6: ("ds6_nuomi", "糯米是个背包", "cv"),
    7: ("ds7_dajinli", "大锦鲤", "cv"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="UP 合集每日更新检查（DS-1…DS-7）")
    parser.add_argument(
        "source",
        type=int,
        choices=sorted(SOURCES),
        help="数据源编号：" + "、".join(f"{n}={name}" for n, (_, name, _) in SOURCES.items()),
    )
    parser.add_argument("--force", action="store_true", help="忽略已记录的容器链接，强制重新解析最新正文")
    args = parser.parse_args()

    module_name, _display_name, kind = SOURCES[args.source]
    no_update_label = NO_UPDATE_LABEL[kind]
    module = importlib.import_module(f"src.sources.{module_name}")

    try:
        result = module.check_update(force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    out_path = module.save_result(result)
    if out_path:
        commit_source_checkpoint(result)
        print(f"\n结果已写入: {out_path}", file=sys.stderr)
        print(f"检测到更新，共提取 {len(result.activity_links)} 条活动链接。", file=sys.stderr)
    else:
        print(
            f"\n{no_update_label}，跳过链接提取，保留已有结果: {module.OUTPUT_PATH}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
