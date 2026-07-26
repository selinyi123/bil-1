"""从 packaging/assets/app-icon.png 生成各尺寸栅格图标。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SOURCE_PATH = Path(__file__).resolve().parent / "assets" / "app-icon.png"


def raster_icon(size: int) -> Image.Image:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f"缺少图标源文件: {SOURCE_PATH}")
    img = Image.open(SOURCE_PATH).convert("RGBA")
    return img.resize((size, size), Image.Resampling.LANCZOS)
