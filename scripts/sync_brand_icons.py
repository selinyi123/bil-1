"""将 assets/brand/icon.svg 同步到全站 favicon / logo 副本。

改图标流程：
1. 只编辑 assets/brand/icon.svg
2. python scripts/sync_brand_icons.py
3. python scripts/render_brand_png.py  （更新 packaging/assets/app-icon.png）
4. python packaging/windows/generate_icon.py && python packaging/macos/generate_icns.py
5. cd web/frontend && npm run build
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "icon.svg"

TARGETS = [
    ROOT / "web" / "frontend" / "public" / "favicon.svg",
    ROOT / "web" / "static" / "favicon.svg",
    ROOT / "docs" / "images" / "logo.svg",
    ROOT / "docs" / "images" / "favicon.svg",
]


def main() -> int:
    if not SOURCE.is_file():
        print(f"缺少 SSOT: {SOURCE}", file=sys.stderr)
        return 1
    for path in TARGETS:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE, path)
        print(f"同步 -> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
