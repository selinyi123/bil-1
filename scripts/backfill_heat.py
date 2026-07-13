"""补全已有活动的转发数（热度）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fetch_activity_info import backfill_repost_counts


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    def on_progress(done: int, total: int, message: str) -> None:
        if total > 0:
            print(f"\r{message}", end="", flush=True, file=sys.stderr)
        else:
            print(message, file=sys.stderr)

    try:
        result = backfill_repost_counts(on_progress=on_progress)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(file=sys.stderr)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
