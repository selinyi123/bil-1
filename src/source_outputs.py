from __future__ import annotations

from pathlib import Path

from src.state_store import DATA_DIR

OUTPUT_DIR = DATA_DIR / "output"

SOURCE_OUTPUTS: tuple[tuple[str, Path], ...] = (
    ("DS-1", OUTPUT_DIR / "ds1_latest.json"),
    ("DS-2", OUTPUT_DIR / "ds2_latest.json"),
    ("DS-3", OUTPUT_DIR / "ds3_latest.json"),
    ("DS-4", OUTPUT_DIR / "ds4_latest.json"),
    ("DS-5", OUTPUT_DIR / "ds5_latest.json"),
    ("DS-6", OUTPUT_DIR / "ds6_latest.json"),
    ("DS-7", OUTPUT_DIR / "ds7_latest.json"),
    ("WATCH", OUTPUT_DIR / "watch_latest.json"),
)
