"""参与活动：互动/转发执行五项操作，预约执行预约点击。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_client import BilibiliClient
from src.classify_links import CLASSIFIED_OUTPUT_PATH
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.user_settings import get_participate_text
from src.participation import participate_activity
from src.sources.common import load_previous_output

SUPPORTED_TYPES = {"互动抽奖", "转发抽奖", "预约抽奖"}


def _lookup_lottery_type(dynamic_id: str) -> str:
    for path in (ENRICHED_OUTPUT_PATH, CLASSIFIED_OUTPUT_PATH):
        payload = load_previous_output(path)
        if not payload:
            continue
        for item in payload.get("activities") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("dynamic_id") or "") != dynamic_id:
                continue
            lottery_type = str(item.get("lottery_type") or "")
            if lottery_type in SUPPORTED_TYPES:
                return lottery_type
    raise RuntimeError(
        f"未找到活动 {dynamic_id} 的类型信息，请先运行 classify_links.py 与 fetch_activity_info.py"
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="参与抽奖活动")
    parser.add_argument("dynamic_id", help="动态 ID")
    args = parser.parse_args()

    try:
        lottery_type = _lookup_lottery_type(args.dynamic_id)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    with BilibiliClient() as client:
        result = participate_activity(
            client,
            dynamic_id=args.dynamic_id,
            lottery_type=lottery_type,
            action_text=get_participate_text(),
            dry_run=False,
            persist=True,
        )

    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.status == "joined" else 1


if __name__ == "__main__":
    raise SystemExit(main())
