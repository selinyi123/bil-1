"""扫描本地全部活动链接，清除已 404 的失效动态。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_client import BilibiliClient
from src.dead_links import collect_all_local_dynamic_ids, partition_alive_dynamic_ids, purge_dynamic_ids
from src.status_refresh import refresh_local_activity_statuses


def main() -> int:
    dynamic_ids = collect_all_local_dynamic_ids()
    if not dynamic_ids:
        print(json.dumps({"ok": True, "message": "本地无活动链接", "total": 0}, ensure_ascii=False))
        return 0

    print(f"扫描 {len(dynamic_ids)} 条本地活动链接…", file=sys.stderr, flush=True)
    with BilibiliClient() as client:
        alive, dead = partition_alive_dynamic_ids(client, dynamic_ids)

    removed = purge_dynamic_ids(dead) if dead else []
    status = refresh_local_activity_statuses() if removed else {"skipped": True}

    summary = {
        "ok": True,
        "scanned": len(dynamic_ids),
        "alive": len(alive),
        "dead": len(dead),
        "removed": len(removed),
        "removed_ids": removed[:100],
        "status_refresh": status,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
