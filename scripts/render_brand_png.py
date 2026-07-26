"""从 assets/brand/icon.svg 导出 packaging/assets/app-icon.png（1024×1024）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "icon.svg"
OUT = ROOT / "packaging" / "assets" / "app-icon.png"
SIZE = 1024


def main() -> int:
    if not SOURCE.is_file():
        print(f"缺少 {SOURCE}", file=sys.stderr)
        return 1
    try:
        import cairosvg
    except ImportError:
        print(
            "需要 cairosvg：pip install cairosvg\n"
            "或手动将 1024×1024 PNG 保存到 packaging/assets/app-icon.png",
            file=sys.stderr,
        )
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        url=str(SOURCE),
        write_to=str(OUT),
        output_width=SIZE,
        output_height=SIZE,
    )
    print(f"已生成 {OUT.relative_to(ROOT)} ({SIZE}×{SIZE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
