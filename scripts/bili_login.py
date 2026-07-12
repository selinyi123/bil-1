"""哔哩哔哩扫码登录 — 自动保存 Cookie 到 config/cookies.txt"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bilibili_login import BilibiliLoginError, COOKIE_PATH, login_with_qrcode


def main() -> int:
    try:
        cookie = login_with_qrcode()
    except BilibiliLoginError as exc:
        print(f"登录失败: {exc}", file=sys.stderr)
        return 1

    print(f"Cookie 已保存到: {COOKIE_PATH}")
    print(f"长度: {len(cookie)} 字符")
    print("现在可以运行: python scripts/check_ds1.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
