"""从 packaging/assets/app-icon.png 生成 Windows .ico 文件。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "binggo.ico"
_ICON_RASTER = Path(__file__).resolve().parents[1] / "icon_raster.py"


def _load_raster_icon():
    spec = importlib.util.spec_from_file_location("binggo_icon_raster", _ICON_RASTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {_ICON_RASTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.raster_icon


def main() -> None:
    raster_icon = _load_raster_icon()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [raster_icon(size) for size in sizes]
    images[0].save(
        OUT_PATH,
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=images[1:],
    )
    print(f"已生成: {OUT_PATH}")


if __name__ == "__main__":
    main()
