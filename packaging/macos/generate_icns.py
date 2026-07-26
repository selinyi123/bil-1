"""从 packaging/assets/app-icon.png 生成 macOS .icns（尽力；失败不阻断构建）。"""

from __future__ import annotations

import importlib.util
import struct
import sys
from io import BytesIO
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "binggo.icns"
_ICON_RASTER = Path(__file__).resolve().parents[1] / "icon_raster.py"

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


def _load_raster_icon():
    spec = importlib.util.spec_from_file_location("binggo_icon_raster", _ICON_RASTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {_ICON_RASTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.raster_icon


def _png_chunk(raster_icon, fourcc: str, size: int) -> bytes:
    img = raster_icon(size)
    buf = BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    return fourcc.encode("ascii") + struct.pack(">I", len(data) + 8) + data


def write_icns(path: Path) -> None:
    raster_icon = _load_raster_icon()
    chunks: list[bytes] = []
    for fourcc, size in _ICNS_SIZES:
        chunks.append(_png_chunk(raster_icon, fourcc, size))
    body = b"".join(chunks)
    file_size = 8 + len(body)
    path.write_bytes(b"icns" + struct.pack(">I", file_size) + body)


def main() -> int:
    try:
        write_icns(OUT_PATH)
        print(f"已生成: {OUT_PATH}")
        return 0
    except Exception as exc:
        print(f"generate_icns failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
