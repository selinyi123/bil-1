"""从网站 favicon 风格生成 Windows .ico 文件。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "binggo.ico"
BG = "#C46F52"
FG = "#FFF8F2"


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(4, size * 16 // 64)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG)

    font_size = max(10, size * 30 // 64)
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
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


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_draw_icon(size) for size in sizes]
    images[0].save(
        OUT_PATH,
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=images[1:],
    )
    print(f"已生成: {OUT_PATH}")


if __name__ == "__main__":
    main()
