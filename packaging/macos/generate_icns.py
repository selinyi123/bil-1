"""从现有 Windows 图标逻辑生成 macOS .icns（尽力；失败不阻断构建）。"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_PATH = Path(__file__).resolve().parent / "binggo.icns"
BG = "#C46F52"
FG = "#FFF8F2"

# icns 类型 → 像素边长
_ICNS_SIZES: list[tuple[str, int]] = [
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
    ("ic11", 32),
    ("ic12", 64),
    ("ic13", 256),
    ("ic14", 512),
]


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(4, size * 16 // 64)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG)

    font_size = max(10, size * 30 // 64)
    try:
        font = ImageFont.truetype("Arial Bold.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    text = "B"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - size * 2 // 64
    draw.text((x, y), text, fill=FG, font=font)

    dot_r = max(2, size * 5 // 64)
    cx = size * 46 // 64
    cy = size * 24 // 64
    draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=FG)
    return img


def _png_bytes(size: int) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    _draw_icon(size).save(buf, format="PNG")
    return buf.getvalue()


def write_icns(path: Path) -> None:
    """最小 PNG-based icns 写入（无需 iconutil）。"""
    entries: list[tuple[bytes, bytes]] = []
    for type_code, size in _ICNS_SIZES:
        data = _png_bytes(size)
        entries.append((type_code.encode("ascii"), data))

    file_size = 8 + sum(8 + len(data) for _, data in entries)
    chunks = [b"icns", struct.pack(">I", file_size)]
    for type_code, data in entries:
        chunks.append(type_code)
        chunks.append(struct.pack(">I", 8 + len(data)))
        chunks.append(data)
    path.write_bytes(b"".join(chunks))


def main() -> int:
    try:
        write_icns(OUT_PATH)
        print(f"wrote {OUT_PATH}")
        return 0
    except Exception as exc:
        print(f"generate_icns failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
