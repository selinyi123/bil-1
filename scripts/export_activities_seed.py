#!/usr/bin/env python3
"""从本地活动库导出可选种子 JSON（默认不随发行版分发；仅维护者本地调试用）。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.activity_seed import extract_seed_activities, sanitize_seed_activity
from src.sources.common import load_previous_output
from src.state_store import DATA_DIR

DEFAULT_SOURCE = DATA_DIR / "output" / "activities_latest.json"
DEFAULT_OUTPUT = ROOT / "config" / "activities_seed.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="导出可选 activities_seed.json（不随发行版分发）")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="本地活动库路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出种子文件路径")
    parser.add_argument("--include-ended", action="store_true", help="包含已结束活动（默认仅导出未结束）")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"源文件不存在: {args.source}", file=sys.stderr)
        return 1

    payload = load_previous_output(args.source) or {}
    now = int(time.time())
    if args.include_ended:
        activities = [
            sanitize_seed_activity(item)
            for item in (payload.get("activities") or [])
            if isinstance(item, dict) and item.get("dynamic_id")
        ]
    else:
        activities = extract_seed_activities(payload, now=now)

    activities.sort(key=lambda row: str(row.get("dynamic_id")))
    seed = {
        "seed_version": 1,
        "exported_at": now,
        "source": "bundled",
        "activity_count": len(activities),
        "activities": activities,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导出 {len(activities)} 条活动 → {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
