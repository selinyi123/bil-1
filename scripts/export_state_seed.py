#!/usr/bin/env python3
"""从本地 state 导出可选 state_seed.json（默认不随发行版分发；仅维护者本地调试用）。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state_seed import sanitize_seed_state
from src.state_store import STATE_PATH

DEFAULT_SOURCE = STATE_PATH
DEFAULT_OUTPUT = ROOT / "config" / "state_seed.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="导出可选 state_seed.json（不随发行版分发）")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="本地 state.json 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出种子文件路径")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"源文件不存在: {args.source}", file=sys.stderr)
        return 1

    raw = json.loads(args.source.read_text(encoding="utf-8"))
    cleaned = sanitize_seed_state(raw)
    if not cleaned.get("sources"):
        print("导出失败：未找到有效的 DS-1～DS-6 检查点", file=sys.stderr)
        return 1

    seed = {
        "seed_version": 1,
        "exported_at": int(time.time()),
        "source": "bundled",
        **cleaned,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"已导出 {len(cleaned['sources'])} 个数据源检查点 → {args.output} "
        f"({args.output.stat().st_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
